"""
backend/app/api/incidents.py
Module 4 — Live Incident Detection endpoint.

POST /api/incidents/analyze
  - Accepts one or more candidate routes (with geometry)
  - Computes a combined bounding box for all routes
  - Fetches incidents from TomTom once (single API call)
  - Spatially matches each incident to each route
  - Returns normalized incidents + ML feature vector per route
"""

import logging
from fastapi import APIRouter, HTTPException

from app.config.settings import get_settings
from app.schemas.incident import (
    IncidentAnalysisRequest,
    IncidentAnalysisResponse,
    RouteIncidentAnalysis,
    IncidentFeatures,
)
from app.services.tomtom_service import (
    compute_combined_bbox,
    get_incidents,
    match_incidents_to_route,
    compute_incident_features,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
)


@router.post("/analyze", response_model=IncidentAnalysisResponse)
async def analyze_incidents(request: IncidentAnalysisRequest):
    """
    Detect live incidents near candidate routes.

    Fetches incidents for the combined bounding box of all routes (one API call),
    then spatially matches each incident to every individual route using the
    configured distance threshold.
    """
    settings = get_settings()
    threshold_m = settings.incident_route_distance_threshold_meters
    closure_threshold_m = settings.incident_road_closure_distance_threshold_meters

    if not request.routes:
        raise HTTPException(status_code=400, detail="No routes provided.")

    # ── Step 1: compute combined bbox ─────────────────────────────────────────
    try:
        geometries = [r.geometry for r in request.routes]
        bbox = compute_combined_bbox(geometries, buffer_deg=0.015)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid route geometry: {e}")

    # ── Step 2: fetch incidents once ──────────────────────────────────────────
    all_incidents = await get_incidents(bbox)
    logger.info(
        f"Incident analysis: {len(all_incidents)} incidents fetched for "
        f"{len(request.routes)} route(s). General threshold: {threshold_m} m, Closure threshold: {closure_threshold_m} m."
    )

    # ── Step 3: per-route spatial matching + feature extraction ───────────────
    route_analyses = []
    for route_req in request.routes:
        # Compute distance of every incident to this route's geometry with 2-tier thresholds
        matched = match_incidents_to_route(
            all_incidents,
            route_req.geometry,
            threshold_m=threshold_m,
            road_closure_threshold_m=closure_threshold_m,
        )
        relevant = [inc for inc in matched if inc.is_route_relevant]
        features = compute_incident_features(relevant)

        # Log summary for this route
        type_counts = {}
        for inc in relevant:
            type_counts[inc.type] = type_counts.get(inc.type, 0) + 1
        logger.info(
            f"  Route {route_req.route_id}: {len(relevant)} relevant incidents — "
            f"{type_counts if type_counts else 'none'}"
        )

        route_analyses.append(
            RouteIncidentAnalysis(
                route_id=route_req.route_id,
                incidents=relevant,
                features=features,
            )
        )

    return IncidentAnalysisResponse(
        routes=route_analyses,
        total_incidents_fetched=len(all_incidents),
    )
