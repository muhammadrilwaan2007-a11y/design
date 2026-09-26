"""
backend/app/schemas/incident.py
Pydantic schemas for Module 4 — Live Incident Detection.

Normalized incident objects are intentionally decoupled from the raw TomTom
response so that switching to another incident provider in the future only
requires a change in the service layer, not these schemas.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel

from app.schemas.route import RouteGeometry


# ── Request schemas ────────────────────────────────────────────────────────────

class RouteIncidentRequest(BaseModel):
    """A single candidate route for incident analysis."""
    route_id: str
    geometry: RouteGeometry


class IncidentAnalysisRequest(BaseModel):
    """Request body: one or more candidate routes to analyze."""
    routes: list[RouteIncidentRequest]


# ── Normalized incident ────────────────────────────────────────────────────────

class Incident(BaseModel):
    """
    A single normalized traffic incident.

    'type' comes from events[].description (human-readable) when available,
    falling back to a generic label derived from iconCategory.

    All fields are Optional to safely handle incomplete TomTom responses.
    """
    id: str
    type: str = "Unknown"
    description: str = ""
    latitude: float
    longitude: float
    icon_category: Optional[int] = None
    magnitude_of_delay: Optional[int] = None   # TomTom: 0–4 scale
    delay_seconds: Optional[int] = None
    road_name: Optional[str] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    length_meters: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    time_validity: Optional[str] = None
    number_of_reports: Optional[int] = None
    last_report_time: Optional[str] = None

    # Added by spatial matching — not from TomTom
    is_route_relevant: bool = False
    distance_to_route_m: Optional[float] = None


# ── Feature vector for ML pipeline ────────────────────────────────────────────

class IncidentFeatures(BaseModel):
    """
    Numerical features per route, ready for consumption by the future
    Safety Risk Engine (Module 5+).

    No scoring or weighting is applied here — raw counts/measurements only.
    """
    incident_count: int = 0
    accident_count: int = 0
    roadwork_count: int = 0
    road_closure_count: int = 0
    lane_closure_count: int = 0
    traffic_jam_incident_count: int = 0
    dangerous_condition_count: int = 0
    total_incident_delay_seconds: int = 0
    nearest_incident_distance_m: Optional[float] = None
    severe_incident_count: int = 0         # magnitude_of_delay >= 3


# ── Response schemas ───────────────────────────────────────────────────────────

class RouteIncidentAnalysis(BaseModel):
    """Incident analysis result for a single candidate route."""
    route_id: str
    incidents: list[Incident] = []           # all route-relevant incidents
    features: IncidentFeatures = IncidentFeatures()


class IncidentAnalysisResponse(BaseModel):
    """Top-level response wrapping analysis for all candidate routes."""
    routes: list[RouteIncidentAnalysis]
    total_incidents_fetched: int = 0         # for logging / debug
