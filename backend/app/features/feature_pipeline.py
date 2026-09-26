"""
backend/app/features/feature_pipeline.py
Module 7 — Master Feature Engineering Pipeline

Orchestrates the full Module 7 pipeline for one or more candidate routes.

Pipeline for each route:
  1. Segment the route geometry into ~500m segments
  2. Compute spatial (turn) features from geometry
  3. Obtain Bengaluru-wide incidents (from SnapshotBundle or direct fetch)
  4. Assign incidents to segments
  5. Fetch traffic data concurrently for all segment midpoints
  6. Obtain weather (from SnapshotBundle or direct fetch)
  7. Compute historical accident features from Module 6 hotspots
  8. Validate and return SegmentFeatureVector list

API call budget per route (with snapshot reuse):
  - 0 × TomTom Incidents  (reused from SnapshotBundle)
  - N × TomTom Traffic Flow (one per segment, concurrent — not yet in bundle)
  - 0 × OpenWeather        (reused from SnapshotBundle)
  - 0 × additional calls for accident features (cached disk data)

Fallback (no SnapshotBundle): original behaviour — fetches all APIs directly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from app.config.settings import get_settings
from app.schemas.features import (
    RouteFeatureResponse,
    MultiRouteFeatureResponse,
    SegmentFeatureVector,
)
from app.schemas.route import RouteGeometry
from app.schemas.snapshot import SnapshotBundle
from app.services.tomtom_service import (
    compute_combined_bbox,
    get_incidents,
)

from app.features.route_segmentation import segment_route
from app.features.segment_accident_features import compute_segment_accident_features
from app.features.segment_incident_features import assign_incidents_to_segments
from app.features.segment_traffic_features import compute_segment_traffic_features
from app.features.segment_weather_features import compute_route_weather_features
from app.features.spatial_features import compute_segment_spatial_features

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Temporal extension stub — NOT activated in V1
# ─────────────────────────────────────────────────────────────────────────────

class TemporalFeatureExtractor:
    """
    Stub for future temporal feature extraction.

    NOT activated in V1. Will be activated when the harvested live incident
    dataset provides per-record timestamps, enabling Module 8 to learn
    time-of-day and day-of-week accident risk patterns.

    Activation steps (when ready):
      1. Uncomment the call in run_pipeline_for_route().
      2. Add temporal_features field to SegmentFeatureVector.
      3. Wire time data source (live timestamp, schedule, etc.).
    """

    @staticmethod
    def extract(segments: List[SegmentFeatureVector]) -> List[SegmentFeatureVector]:
        """
        Future: extract hour, day_of_week, is_rush_hour, is_night etc.
        and add to each segment's temporal_features.
        Currently a no-op.
        """
        logger.debug("TemporalFeatureExtractor: not activated in V1.")
        return segments


# ─────────────────────────────────────────────────────────────────────────────
# Core pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline_for_route(
    route_id: str,
    geometry: RouteGeometry,
    snapshot: Optional[SnapshotBundle] = None,
) -> RouteFeatureResponse:
    """
    Run the full Module 7 feature engineering pipeline for a single route.

    Parameters
    ----------
    route_id : str
        Stable route identifier (e.g. "route_1").
    geometry : RouteGeometry
        Full GeoJSON LineString from the TomTom routing response.
    snapshot : SnapshotBundle, optional
        Pre-fetched Bengaluru-wide live data from LiveSnapshotService.
        When provided:
          - incidents and weather are taken from the bundle (no extra API calls)
          - traffic is still fetched per-segment (segment-level granularity needed)
        When None:
          - original behaviour: all data fetched directly from APIs.

    Returns
    -------
    RouteFeatureResponse
        All segments with their feature vectors populated.
    """
    settings = get_settings()
    logger.info("Module 7 pipeline starting for route %s", route_id)

    # ── Step 1: Segment the route ─────────────────────────────────────────────
    segments = segment_route(geometry, route_id)

    if not segments:
        logger.warning("Route %s produced 0 segments — returning empty response.", route_id)
        return RouteFeatureResponse(
            route_id=route_id,
            segment_count=0,
            total_route_length_m=0.0,
            segments=[],
        )

    # ── Step 2: Spatial features (no API) ────────────────────────────────────
    segments = compute_segment_spatial_features(segments)

    # ── Step 3: Incidents ─────────────────────────────────────────────────────
    if snapshot and snapshot.incidents_available is not None:
        # Use pre-fetched Bengaluru-wide incidents from the snapshot
        incidents = snapshot.incidents
        incidents_ok = snapshot.incidents_available
        logger.info(
            "Route %s: using %d incidents from snapshot %s.",
            route_id, len(incidents),
            (snapshot.incident_snapshot_id or "unknown")[:8],
        )
    else:
        # Fallback: fetch directly for this route's bbox (original behaviour)
        try:
            bbox = compute_combined_bbox([geometry], buffer_deg=0.005)
            incidents = await get_incidents(bbox)
            incidents_ok = True
            logger.info(
                "Route %s: fetched %d live incidents directly.",
                route_id, len(incidents),
            )
        except Exception as exc:
            logger.error("Incident fetch failed for route %s: %s", route_id, exc)
            incidents = []
            incidents_ok = False

    # ── Step 4: Assign incidents to segments ──────────────────────────────────
    segments = assign_incidents_to_segments(
        segments,
        incidents,
        buffer_m=settings.segment_incident_buffer_m,
        data_available=incidents_ok,
    )

    # ── Step 5: Traffic features (concurrent, one call per segment) ───────────
    # Traffic is always fetched per-segment for precise segment-level granularity.
    segments = await compute_segment_traffic_features(segments)

    # ── Step 6: Weather ───────────────────────────────────────────────────────
    if snapshot and snapshot.weather_available and snapshot.weather is not None:
        # Propagate snapshot weather to all segments
        from app.features.segment_weather_features import _compute_weather_risk
        w = snapshot.weather.weather
        risk = _compute_weather_risk(
            w.rain_1h_mm if w else None,
            w.visibility_m if w else None,
            settings,
        )
        for seg in segments:
            seg.weather_data_available = True
            seg.rain_1h_mm = w.rain_1h_mm if w else None
            seg.visibility_m = w.visibility_m if w else None
            seg.wind_speed_ms = w.wind_speed_ms if w else None
            seg.weather_risk = risk
        logger.info(
            "Route %s: weather applied from snapshot %s.",
            route_id, (snapshot.weather_snapshot_id or "unknown")[:8],
        )
    else:
        # Fallback: fetch weather directly at route midpoint
        segments = await compute_route_weather_features(segments, geometry)

    # ── Step 7: Historical accident features (from Module 6 hotspot cache) ────
    segments = compute_segment_accident_features(segments)

    # ── Step 8: Temporal features stub (NOT activated in V1) ──────────────────
    # segments = TemporalFeatureExtractor.extract(segments)

    total_length = (
        segments[-1].end_distance_m if segments else 0.0
    )

    logger.info(
        "Module 7 pipeline complete for route %s: %d segments, %.1f m total.",
        route_id, len(segments), total_length,
    )

    return RouteFeatureResponse(
        route_id=route_id,
        segment_count=len(segments),
        total_route_length_m=round(total_length, 2),
        segments=segments,
    )



async def run_pipeline_for_routes(
    routes: List[tuple[str, RouteGeometry]],
    snapshot: Optional[SnapshotBundle] = None,
) -> MultiRouteFeatureResponse:
    """
    Run the feature pipeline for multiple candidate routes concurrently.

    Parameters
    ----------
    routes : list of (route_id, RouteGeometry) tuples
    snapshot : SnapshotBundle, optional
        Pre-fetched live data. Shared across all routes to avoid duplicate fetches.

    Returns
    -------
    MultiRouteFeatureResponse
    """
    tasks = [
        run_pipeline_for_route(route_id, geometry, snapshot=snapshot)
        for route_id, geometry in routes
    ]
    results: List[RouteFeatureResponse] = await asyncio.gather(*tasks, return_exceptions=False)

    total_segments = sum(r.segment_count for r in results)

    logger.info(
        "Module 7 complete for %d routes, %d total segments.",
        len(results), total_segments,
    )

    return MultiRouteFeatureResponse(
        routes=results,
        total_segments=total_segments,
    )
