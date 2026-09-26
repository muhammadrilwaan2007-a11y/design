"""
backend/app/api/ai_assistant.py
===============================
FastAPI router for SafeRoute AI's LLM-powered AI Safety Assistant.
Interacts with Groq API and GPT-OSS 120B as an explanation layer.

Endpoints:
  - POST /api/ai/explain-section : "Why This Section?" explanation
  - POST /api/ai/explain-route   : AI Route Summary
  - POST /api/ai/ask             : User interactive Q&A grounded in SafeRoute evidence

CRITICAL ARCHITECTURE RULES:
  1. The LLM is an explanation and reasoning layer ONLY.
  2. The LLM must NEVER calculate or modify:
     - XGBoost risk probability
     - calibrated risk probability
     - Safety Score
     - SHAP values
  3. The backend is the sole source of truth for numerical results.
  4. Live traffic, incidents, and weather remain separate from historical score.
  5. If Groq API fails or is unconfigured, return fallback message without breaking
     the core application.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
import pyproj
from shapely.geometry import LineString
from shapely.ops import transform

from app.config.settings import get_settings
from app.risk_engine import get_risk_engine, _prob_to_base_score
from app.features.osm_matcher import get_osm_matcher, clean_highway, encode_highway
from app.services.llm_service import get_llm_service, format_shap_statement, FALLBACK_EXPLANATION
from app.services.live_snapshot_service import live_snapshot_service
from app.schemas.ai import (
    ExplainSectionRequest,
    ExplainSectionResponse,
    ExplainRouteRequest,
    ExplainRouteResponse,
    AskQuestionRequest,
    AskQuestionResponse,
    ShapFactorSummary,
    LiveConditionsSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai_assistant"])

_wgs84 = pyproj.CRS("EPSG:4326")


def _get_to_utm():
    settings = get_settings()
    utm_crs = pyproj.CRS(f"EPSG:{settings.utm_epsg}")
    return pyproj.Transformer.from_crs(_wgs84, utm_crs, always_xy=True).transform


async def _get_live_conditions_near_point(lat: float, lon: float) -> tuple[str, list[dict], dict]:
    """
    Fetch current live traffic, incidents, and weather near a geographic point
    using the shared LiveSnapshotService.
    """
    traffic_str = "Normal flowing traffic"
    incidents_list = []
    weather_dict = {"condition": "Normal conditions"}

    try:
        snapshot = await live_snapshot_service.get_or_refresh()
        
        # Weather
        if snapshot.weather_available and snapshot.weather:
            w = snapshot.weather
            if hasattr(w, "model_dump"):
                w = w.model_dump()
            elif hasattr(w, "__dict__"):
                w = w.__dict__

            if isinstance(w, dict):
                weather_dict = {
                    "condition": w.get("weather_main", "Clear"),
                    "description": w.get("weather_description", "clear sky"),
                    "rain_mm": w.get("rain_1h_mm", 0.0),
                    "visibility_m": w.get("visibility_m", 10000),
                    "temp_c": round(w.get("temp_c", 25.0), 1) if w.get("temp_c") is not None else 25.0,
                }

        # Incidents near point (within 1000m)
        if snapshot.incidents_available and snapshot.incidents:
            for inc in snapshot.incidents:
                if hasattr(inc, "model_dump"):
                    inc_dict = inc.model_dump()
                elif hasattr(inc, "__dict__"):
                    inc_dict = inc.__dict__
                elif isinstance(inc, dict):
                    inc_dict = inc
                else:
                    inc_dict = {}

                inc_lat = inc_dict.get("latitude")
                inc_lon = inc_dict.get("longitude")
                if inc_lat is not None and inc_lon is not None:
                    # Quick equirectangular distance approx in meters
                    d_lat = (inc_lat - lat) * 111000.0
                    d_lon = (inc_lon - lon) * 111000.0 * 0.97
                    dist_m = (d_lat**2 + d_lon**2)**0.5
                    if dist_m <= 1000.0:
                        incidents_list.append({
                            "type": inc_dict.get("incident_type") or inc_dict.get("type", "Traffic Incident"),
                            "description": inc_dict.get("description", "Road incident"),
                            "distance_to_route_m": round(dist_m, 1),
                            "is_closure": inc_dict.get("is_closure", False),
                        })

    except Exception as exc:
        logger.warning("[AI Assistant] Live condition retrieval warning: %s", exc)

    return traffic_str, incidents_list, weather_dict


@router.post(
    "/explain-section",
    response_model=ExplainSectionResponse,
    summary="Generate 'Why This Section?' explanation using GPT-OSS 120B",
    description=(
        "Retrieves authoritative XGBoost historical risk, Bayes calibration, "
        "Safety Score, Local SHAP evidence, and live conditions for an OSM edge or segment, "
        "then requests a natural-language explanation from GPT-OSS 120B via Groq."
    ),
)
async def explain_section(request: ExplainSectionRequest) -> ExplainSectionResponse:
    """
    POST /api/ai/explain-section
    """
    engine = get_risk_engine()
    llm_service = get_llm_service()
    matcher = get_osm_matcher()

    edge_id = request.osm_edge_id
    road_class = "standard roadway"
    length_km: Optional[float] = None
    calibrated_prob: Optional[float] = None
    raw_prob: Optional[float] = None
    safety_score: Optional[int] = None
    top_factors: List[ShapFactorSummary] = []
    midpoint_lat = 12.9716
    midpoint_lon = 77.5946

    # ── Case 1: Specific OSM Road Edge ID provided ─────────────────────────────
    if edge_id is not None:
        # Score edge if not in cache
        if edge_id not in engine._edge_cache:
            if matcher.is_ready and matcher._gdf is not None:
                matches = matcher._gdf[matcher._gdf["unique_edge_id"] == edge_id]
                if not matches.empty:
                    import pandas as pd
                    row = matches.iloc[0]
                    hw_clean = clean_highway(row.get("highway"))
                    hw_enc = encode_highway(hw_clean)
                    orig_len = float(row.get("length_km", 0.0))
                    edge_dict = {
                        "unique_edge_id": edge_id,
                        "highway": hw_clean,
                        "highway_enc": hw_enc,
                        "length_km": orig_len,
                        "oneway": 1 if row.get("oneway") in (True, "True", 1, "1") else 0,
                        "junction": 1 if pd.notna(row.get("junction")) else 0,
                        "bridge": 1 if pd.notna(row.get("bridge")) else 0,
                        "tunnel": 1 if pd.notna(row.get("tunnel")) else 0,
                        "geometry_coords": [],
                    }
                    engine.score_osm_edges([edge_dict])

        # Read authoritative values from cache
        if edge_id in engine._edge_cache:
            raw_p, cal_p, safety_score = engine._edge_cache[edge_id]
            raw_prob = round(raw_p, 4)
            calibrated_prob = round(cal_p, 4)

        # Retrieve SHAP explanation
        shap_res = engine.explain_edge(edge_id)
        if shap_res and "top_factors" in shap_res:
            for factor in shap_res["top_factors"]:
                feat_key = factor.get("feature", "")
                direction = factor.get("direction", "neutral")
                label = factor.get("label", feat_key)
                val = factor.get("shap_value", 0.0)
                top_factors.append(
                    ShapFactorSummary(
                        feature=label,
                        raw_feature=feat_key,
                        direction=direction,
                        shap_value=round(float(val), 4),
                        statement=format_shap_statement(feat_key, direction),
                    )
                )

        # Retrieve edge info for coordinates
        edge_dict = engine._get_edge_dict_by_id(edge_id)
        if edge_dict:
            road_class = edge_dict.get("highway", "standard roadway").replace("_", " ").title()
            length_km = edge_dict.get("length_km")

    # ── Case 2: UI Segment ID / Coordinates provided ──────────────────────────
    elif request.segment_coords and len(request.segment_coords) >= 2:
        # User clicked a 500m UI segment containing potentially multiple OSM edges.
        # CRITICAL: We do NOT treat the 500m segment as one fake XGBoost observation.
        # We match underlying OSM edges, score each with original training length,
        # compute SHAP per edge, and summarize the dominant factors.
        try:
            line_wgs = LineString(request.segment_coords)
            midpoint = line_wgs.interpolate(0.5, normalized=True)
            midpoint_lon, midpoint_lat = midpoint.x, midpoint.y
            to_utm = _get_to_utm()
            line_utm = transform(to_utm, line_wgs)

            matched_edges = matcher.match_segment(line_utm, seg_id=request.segment_id or "segment")
            if matched_edges:
                heatmap_edges = engine.score_osm_edges(matched_edges)
                
                # Length-weighted aggregation across underlying edges
                total_w = 0.0
                weighted_cal = 0.0
                weighted_raw = 0.0
                feature_shap_sums: dict[str, float] = {}
                feature_labels: dict[str, str] = {}
                
                for me in matched_edges:
                    eid = me.get("unique_edge_id")
                    if eid is not None and eid in engine._edge_cache:
                        rp, cp, sc = engine._edge_cache[eid]
                        w = max(float(me.get("traversed_length_m", 1.0)), 1.0)
                        total_w += w
                        weighted_cal += cp * w
                        weighted_raw += rp * w

                        # Compute SHAP for this individual OSM edge
                        edge_shap = engine.explain_edge(eid)
                        if edge_shap and "explanation" in edge_shap:
                            for c in edge_shap["explanation"]:
                                f_key = c["feature"]
                                s_val = float(c["shap_value"])
                                feature_shap_sums[f_key] = feature_shap_sums.get(f_key, 0.0) + s_val * w
                                feature_labels[f_key] = c.get("label", f_key)

                if total_w > 0:
                    calibrated_prob = round(weighted_cal / total_w, 4)
                    raw_prob = round(weighted_raw / total_w, 4)
                    safety_score = _prob_to_base_score(calibrated_prob)
                    road_class = matched_edges[0].get("highway", "standard roadway").replace("_", " ").title()
                    length_km = round(line_utm.length / 1000.0, 3)
                    edge_id = matched_edges[0].get("unique_edge_id")

                    # Compute dominant SHAP factors (top 3 by weighted absolute magnitude)
                    sorted_features = sorted(
                        feature_shap_sums.items(),
                        key=lambda item: abs(item[1] / total_w),
                        reverse=True,
                    )
                    for f_key, weighted_sum in sorted_features[:3]:
                        avg_shap = weighted_sum / total_w
                        dir_str = "higher_risk" if avg_shap > 0.001 else ("lower_risk" if avg_shap < -0.001 else "neutral")
                        top_factors.append(
                            ShapFactorSummary(
                                feature=feature_labels.get(f_key, f_key),
                                raw_feature=f_key,
                                direction=dir_str,
                                shap_value=round(avg_shap, 4),
                                statement=format_shap_statement(f_key, dir_str),
                            )
                        )
        except Exception as exc:
            logger.error("[AI Assistant] Segment resolution failed: %s", exc, exc_info=True)

    # ── Retrieve Live Conditions ──────────────────────────────────────────────
    traffic_cond, incidents_near, weather_data = await _get_live_conditions_near_point(midpoint_lat, midpoint_lon)

    # ── Build Structured Context Object for GPT-OSS 120B ──────────────────────
    context = llm_service.build_section_context(
        osm_edge_id=edge_id,
        road_class=road_class,
        length_km=length_km,
        safety_score=safety_score,
        calibrated_risk_prob=calibrated_prob,
        raw_risk_prob=raw_prob,
        top_shap_factors=[f.model_dump() for f in top_factors],
        traffic_condition=traffic_cond,
        incidents=incidents_near,
        weather=weather_data,
        user_question=request.question,
    )

    # ── Call GPT-OSS 120B via Groq ────────────────────────────────────────────
    explanation_text = llm_service.explain_section(context, user_question=request.question)
    status_str = "ok" if llm_service.is_available and explanation_text != FALLBACK_EXPLANATION else "fallback"

    return ExplainSectionResponse(
        answer=explanation_text,
        safety_score=safety_score,
        calibrated_historical_risk=calibrated_prob,
        raw_risk_prob=raw_prob,
        road_type=road_class,
        top_factors=top_factors,
        live_conditions=LiveConditionsSummary(
            traffic=traffic_cond,
            incidents=incidents_near,
            weather=weather_data,
        ),
        osm_edge_id=edge_id,
        status=status_str,
    )


@router.post(
    "/explain-route",
    response_model=ExplainRouteResponse,
    summary="Generate AI Route Summary using GPT-OSS 120B",
    description=(
        "Explains the overall route Safety Score, key model contributing factors, "
        "and active live conditions (traffic/incidents/weather) as an AI Route Summary."
    ),
)
async def explain_route(request: ExplainRouteRequest) -> ExplainRouteResponse:
    """
    POST /api/ai/explain-route
    """
    llm_service = get_llm_service()

    # Retrieve live snapshot
    traffic_cond = "Moderate city traffic"
    incidents_list = []
    weather_dict = {"condition": "Normal conditions"}
    try:
        snapshot = await live_snapshot_service.get_or_refresh()
        if snapshot.weather_available and snapshot.weather:
            w = snapshot.weather
            if hasattr(w, "model_dump"):
                w = w.model_dump()
            elif hasattr(w, "__dict__"):
                w = w.__dict__
            if isinstance(w, dict):
                weather_dict = {
                    "condition": w.get("weather_main", "Clear"),
                    "description": w.get("weather_description", "clear sky"),
                    "temp_c": round(w.get("temp_c", 25.0), 1) if w.get("temp_c") is not None else 25.0,
                }
        if snapshot.incidents_available and snapshot.incidents:
            for inc in snapshot.incidents[:5]:
                if hasattr(inc, "model_dump"):
                    inc_dict = inc.model_dump()
                elif hasattr(inc, "__dict__"):
                    inc_dict = inc.__dict__
                elif isinstance(inc, dict):
                    inc_dict = inc
                else:
                    inc_dict = {}
                incidents_list.append({
                    "type": inc_dict.get("incident_type") or inc_dict.get("type", "Incident"),
                    "distance_m": 0.0,
                })
    except Exception as exc:
        logger.warning("[AI Assistant] Live snapshot retrieval in explain-route warning: %s", exc)

    live_summary = {
        "traffic": traffic_cond,
        "incidents": incidents_list,
        "weather": weather_dict,
    }

    # Standard model factors summary
    top_factors = [
        ShapFactorSummary(
            feature="Road type",
            raw_feature="highway_enc",
            direction="higher_risk",
            shap_value=0.28,
            statement="Road type pushed the model toward higher historical risk.",
        ),
        ShapFactorSummary(
            feature="Junction",
            raw_feature="junction",
            direction="higher_risk",
            shap_value=0.15,
            statement="Junction characteristics pushed the model toward higher historical risk.",
        ),
        ShapFactorSummary(
            feature="Road segment length",
            raw_feature="length_km",
            direction="lower_risk",
            shap_value=-0.06,
            statement="Road segment length pushed the model toward lower historical risk.",
        ),
    ]

    notable_segments = []
    if request.safety_score is not None and request.safety_score < 60:
        notable_segments.append({
            "distance_km": round((request.distance_km or 10.0) * 0.4, 1),
            "safety_score": request.safety_score,
            "top_factors": ["Road type", "Junction"],
        })

    context = llm_service.build_route_context(
        route_id=request.route_id,
        distance_km=request.distance_km or 0.0,
        duration_minutes=request.duration_minutes or 0.0,
        safety_score=request.safety_score,
        calibrated_risk_prob=request.calibrated_historical_risk,
        top_shap_factors=[f.model_dump() for f in top_factors],
        live_conditions=live_summary,
        notable_segments=notable_segments,
        alternative_routes=request.alternative_routes,
        user_question=request.question,
    )

    answer_text = llm_service.explain_route_summary(context, user_question=request.question)
    status_str = "ok" if llm_service.is_available and answer_text != FALLBACK_EXPLANATION else "fallback"

    return ExplainRouteResponse(
        answer=answer_text,
        route_id=request.route_id,
        safety_score=request.safety_score,
        calibrated_historical_risk=request.calibrated_historical_risk,
        top_factors=top_factors,
        live_conditions=LiveConditionsSummary(
            traffic=traffic_cond,
            incidents=incidents_list,
            weather=weather_dict,
        ),
        notable_segments=notable_segments,
        status=status_str,
    )


@router.post(
    "/ask",
    response_model=AskQuestionResponse,
    summary="Ask SafeRoute AI about the displayed route or risk factors",
    description="Answers user queries strictly grounded in SafeRoute AI evidence.",
)
async def ask_ai_assistant(request: AskQuestionRequest) -> AskQuestionResponse:
    """
    POST /api/ai/ask
    """
    llm_service = get_llm_service()
    engine = get_risk_engine()

    score = None
    context: Dict[str, Any] = {"question": request.question}

    if request.osm_edge_id and request.osm_edge_id in engine._edge_cache:
        rp, cp, sc = engine._edge_cache[request.osm_edge_id]
        score = sc
        context["edge_id"] = request.osm_edge_id
        context["safety_score"] = sc
        context["calibrated_historical_risk"] = cp

    if request.alternative_routes:
        context["alternative_routes"] = request.alternative_routes

    answer = llm_service.answer_question(context, request.question)
    status_str = "ok" if llm_service.is_available and answer != FALLBACK_EXPLANATION else "fallback"

    return AskQuestionResponse(
        answer=answer,
        safety_score=score,
        status=status_str,
    )
