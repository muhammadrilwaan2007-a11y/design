"""
backend/app/api/features.py
FastAPI router for POST /api/features/analyze — Module 7 + Module 8.

Updated to use LiveSnapshotService: obtains a SnapshotBundle (fresh or reused)
and passes it to the Module 7 pipeline, eliminating duplicate API calls
when multiple routes are analyzed for the same user request.

Module 8 (RiskEngine) runs after Module 7 and adds:
  - historical_risk_prob  per segment  (XGBoost probability)
  - live_condition_deduction per segment (weather/incident adjustment)
  - safety_score          per segment  (0-100)
  - route_safety_score    per route    (length-weighted aggregate)
  - route_risk_category   per route    ("low" | "medium" | "high")

Follows the same patterns as the existing routing, traffic, incidents, and
weather routers: prefix, tags, Pydantic request/response, error handling, logging.
"""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.features import MultiRouteFeatureRequest, MultiRouteFeatureResponse, HeatmapResponse
from app.features.feature_pipeline import run_pipeline_for_routes
from app.features.osm_matcher import get_osm_matcher
from app.services.live_snapshot_service import live_snapshot_service
from app.risk_engine import get_risk_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["features"])


def _risk_category(score: int) -> str:
    """Map a 0-100 Safety Score to a human-readable risk category."""
    if score >= 70:
        return "low"
    if score >= 40:
        return "medium"
    return "high"


def _compute_route_score(route_response) -> tuple[int | None, str | None, float | None, float | None]:
    """
    Compute a length-weighted mean Safety Score across all scored segments.
    Also computes length-weighted raw and calibrated probabilities.

    Weighting by segment_length_m ensures longer road sections contribute
    proportionally more to the overall route score than short connector roads.

    Returns (score, category, raw_prob, cal_prob) or (None, None, None, None) if no segments were scored.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    raw_sum = 0.0
    cal_sum = 0.0

    for seg in route_response.segments:
        if seg.safety_score is not None and seg.segment_length_m > 0:
            weighted_sum += seg.safety_score * seg.segment_length_m
            total_weight += seg.segment_length_m
            if seg.raw_risk_prob is not None:
                raw_sum += seg.raw_risk_prob * seg.segment_length_m
            if seg.calibrated_risk_prob is not None:
                cal_sum += seg.calibrated_risk_prob * seg.segment_length_m

    if total_weight == 0:
        return None, None, None, None

    score = round(weighted_sum / total_weight)
    score = max(0, min(100, score))
    raw_p = round(raw_sum / total_weight, 4)
    cal_p = round(cal_sum / total_weight, 4)
    return score, _risk_category(score), raw_p, cal_p


@router.post(
    "/features/analyze",
    response_model=MultiRouteFeatureResponse,
    summary="Generate safety feature vectors for candidate routes (Module 7 + 8)",
    description=(
        "Accepts one or more candidate routes with their GeoJSON geometries. "
        "Obtains a fresh Bengaluru-wide live snapshot (reusing it if still fresh). "
        "Segments each route into ~500m chunks and computes per-segment feature "
        "vectors including historical accident hotspots, live incidents, traffic "
        "flow, weather measurements, and road geometry features (Module 7). "
        "Then applies the XGBoost Risk Engine (Module 8) to produce a 0-100 "
        "Safety Score per segment and per route. "
        "Live snapshots are persisted to Supabase for future ML training."
    ),
)
async def analyze_route_features(
    request: MultiRouteFeatureRequest,
) -> MultiRouteFeatureResponse:
    """
    POST /api/features/analyze

    Request body:
      {
        "routes": [
          { "route_id": "route_1", "geometry": { "type": "LineString", "coordinates": [...] } }
        ]
      }

    Flow:
      1. LiveSnapshotService checks freshness of incidents/weather sources
      2. Stale/missing sources are refreshed and stored in Supabase
      3. Fresh bundle is passed to Module 7 (no duplicate API calls)
      4. Module 8 RiskEngine scores every segment with XGBoost + live adjustment
      5. Route-level aggregate scores are computed
      6. Full response (all existing fields + new risk fields) returned
    """
    if not request.routes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "NO_ROUTES", "message": "At least one route is required."},
        )

    logger.info(
        "Feature analysis request: %d route(s) submitted.",
        len(request.routes),
    )

    # ── Obtain Bengaluru-wide live snapshot (fresh or reused) ─────────────────
    try:
        snapshot = await live_snapshot_service.get_or_refresh()
        logger.info(
            "Snapshot bundle ready: incidents=%s (%d), weather=%s",
            "OK" if snapshot.incidents_available else "UNAVAILABLE",
            len(snapshot.incidents),
            "OK" if snapshot.weather_available else "UNAVAILABLE",
        )

        # ── Record the route request context ───────────────────────────────────
        if request.routes and request.routes[0].geometry.coordinates:
            origin = request.routes[0].geometry.coordinates[0]
            dest = request.routes[0].geometry.coordinates[-1]
            await live_snapshot_service.record_route_request(
                origin_lat=origin[1],
                origin_lon=origin[0],
                destination_lat=dest[1],
                destination_lon=dest[0],
                bundle=snapshot
            )

    except Exception as exc:
        logger.warning("Snapshot service failed (%s) — falling back to direct API calls.", exc)
        snapshot = None  # Feature pipeline falls back to per-route API calls

    # ── Run Module 7 pipeline with shared snapshot ────────────────────────────
    try:
        route_tuples = [(r.route_id, r.geometry) for r in request.routes]
        result = await run_pipeline_for_routes(route_tuples, snapshot=snapshot)
    except Exception as exc:
        logger.error("Feature pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "FEATURE_PIPELINE_ERROR",
                "message": "Feature engineering pipeline encountered an unexpected error.",
            },
        ) from exc

    # ── Run Module 8: Risk Engine ─────────────────────────────────────────────
    try:
        engine = get_risk_engine()

        for route_response in result.routes:
            # Score all segments in this route and retrieve underlying OSM heatmap edges
            route_response.segments, route_response.heatmap_edges = engine.score_segments_with_heatmap(
                route_response.segments
            )

            # Compute length-weighted route-level aggregate
            r_score, r_category, r_raw_p, r_cal_p = _compute_route_score(route_response)
            route_response.route_safety_score = r_score
            route_response.route_risk_category = r_category
            route_response.route_raw_risk_prob = r_raw_p
            route_response.route_calibrated_risk_prob = r_cal_p

            if r_score is not None:
                logger.info(
                    "Route %s → route_safety_score=%d (%s)  segments=%d  heatmap_edges=%d",
                    route_response.route_id,
                    r_score,
                    r_category,
                    route_response.segment_count,
                    len(route_response.heatmap_edges),
                )

    except Exception as exc:
        # Risk Engine failure must NOT break the existing API response.
        # All existing Module 7 fields are preserved; safety_score fields will be None.
        logger.error(
            "Module 8 Risk Engine failed: %s — returning Module 7 data without scores.",
            exc,
            exc_info=True,
        )

    return result


@router.get(
    "/features/heatmap",
    response_model=HeatmapResponse,
    summary="Retrieve OSM road edges with calibrated historical risk for heatmap visualization",
    description=(
        "Returns underlying OSM road edges with their original geometries, calibrated "
        "historical risk probabilities, and Safety Scores. Supports bounding box filtering "
        "or falls back to key Bengaluru arterial corridors. Cached predictions are reused."
    ),
)
async def get_historical_risk_heatmap(
    min_lat: Optional[float] = Query(None, description="Minimum latitude for bounding box"),
    min_lon: Optional[float] = Query(None, description="Minimum longitude for bounding box"),
    max_lat: Optional[float] = Query(None, description="Maximum latitude for bounding box"),
    max_lon: Optional[float] = Query(None, description="Maximum longitude for bounding box"),
    limit: int = Query(500, ge=1, le=2000, description="Maximum number of road edges to return"),
) -> HeatmapResponse:
    """
    GET /api/features/heatmap
    """
    matcher = get_osm_matcher()
    if not matcher.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MATCHER_NOT_READY", "message": "OSM road network is not initialized."},
        )

    try:
        if min_lat is not None and min_lon is not None and max_lat is not None and max_lon is not None:
            edge_dicts = matcher.get_edges_in_bbox(
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
                limit=limit,
            )
        else:
            edge_dicts = matcher.get_key_corridor_edges(limit=limit)

        engine = get_risk_engine()
        heatmap_edges = engine.score_osm_edges(edge_dicts)

        return HeatmapResponse(
            total_edges=len(heatmap_edges),
            edges=heatmap_edges,
        )
    except Exception as exc:
        logger.error("Failed to generate historical risk heatmap: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "HEATMAP_ERROR", "message": "Failed to generate historical risk heatmap."},
        ) from exc


@router.get(
    "/features/roads/{edge_id}/explanation",
    summary="Local SHAP explanation for a specific OSM road edge",
    description=(
        "Returns a Local SHAP (TreeSHAP) explanation for the given OSM road edge. "
        "Explains WHY the XGBoost model produced its historical risk prediction "
        "in terms of the six structural road features. "
        "IMPORTANT: The SHAP explanation is an interpretation layer ONLY. "
        "It does NOT modify the Safety Score, raw_risk_prob, or calibrated_risk_prob. "
        "SHAP values are in model log-odds / margin space, NOT probability-percentage points. "
        "The edge must have been previously scored (e.g., via the heatmap endpoint)."
    ),
)
async def get_road_explanation(edge_id: int) -> dict:
    """
    GET /api/features/roads/{edge_id}/explanation

    Parameters
    ----------
    edge_id : int
        The unique_edge_id of an OSM road edge (as returned by /api/features/heatmap).

    Response
    --------
    {
      "osm_edge_id": 123456,
      "raw_risk_prob": 0.7853,
      "calibrated_risk_prob": 0.0514,
      "safety_score": 77,
      "shap_base_value": -4.123,
      "shap_model_output": -3.456,
      "output_space": "log_odds_margin",
      "output_space_description": "...",
      "explanation": [
        {
          "feature": "highway_enc",
          "label": "Road type",
          "value": 9,
          "display_value": "Primary",
          "shap_value": 0.52,
          "direction": "higher_risk"
        },
        ...
      ],
      "top_factors": [ ... top 3 by |shap_value| ... ]
    }
    """
    engine = get_risk_engine()

    # Ensure the edge is scored first (call score_osm_edges if not in cache)
    if edge_id not in engine._edge_cache:
        # Try to score it on-demand via the matcher
        try:
            matcher = get_osm_matcher()
            if not matcher.is_ready:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "code": "MATCHER_NOT_READY",
                        "message": "OSM road network is not initialized.",
                    },
                )
            # Get the edge dict from the matcher's GDF
            gdf = matcher._gdf
            if gdf is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "EDGE_NOT_FOUND", "message": f"Edge {edge_id} not found."},
                )

            import pandas as pd
            matches = gdf[gdf["unique_edge_id"] == edge_id]
            if matches.empty:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "EDGE_NOT_FOUND",
                        "message": f"OSM edge {edge_id} does not exist in the road network.",
                    },
                )

            from app.features.osm_matcher import clean_highway, encode_highway
            row = matches.iloc[0]
            hw_clean = clean_highway(row.get("highway"))
            hw_enc = encode_highway(hw_clean)
            orig_len_km = float(row.get("length_km", 0.0))
            oneway = 1 if row.get("oneway") in (True, "True", 1, "1") else 0
            junction = 1 if pd.notna(row.get("junction")) else 0
            bridge = 1 if pd.notna(row.get("bridge")) else 0
            tunnel = 1 if pd.notna(row.get("tunnel")) else 0

            geom_wgs = row.get("geometry_wgs84")
            coords: list = []
            if geom_wgs is not None and hasattr(geom_wgs, "geom_type"):
                if geom_wgs.geom_type == "LineString":
                    coords = [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in geom_wgs.coords]

            edge_dict = {
                "unique_edge_id": edge_id,
                "highway":        hw_clean,
                "highway_enc":    hw_enc,
                "length_km":      orig_len_km,
                "oneway":         oneway,
                "junction":       junction,
                "bridge":         bridge,
                "tunnel":         tunnel,
                "geometry_coords": coords,
            }
            engine.score_osm_edges([edge_dict])

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to score edge %d on-demand: %s", edge_id, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "EDGE_SCORE_ERROR", "message": f"Could not score edge {edge_id}."},
            ) from exc

    result = engine.explain_edge(edge_id)
    if result is None:
        from app.shap_explainer import get_shap_service
        shap_svc = get_shap_service()
        if not shap_svc.is_ready:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "SHAP_NOT_READY",
                    "message": (
                        "Local SHAP explainer is not initialized. "
                        "Ensure the XGBoost model loaded successfully at startup."
                    ),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EXPLANATION_UNAVAILABLE",
                "message": (
                    f"Could not generate explanation for edge {edge_id}. "
                    "The edge may not exist in the road network."
                ),
            },
        )

    return result
