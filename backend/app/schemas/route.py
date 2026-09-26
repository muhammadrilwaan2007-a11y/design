"""
backend/app/schemas/route.py
Pydantic schemas for the routing API.

Designed to be extensible — later modules will add optional fields for:
  traffic, incidents, weather, accident risk, infrastructure, safety score.
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Input schemas ─────────────────────────────────────────────────────────────

class RoutePoint(BaseModel):
    """A geographic coordinate pair."""
    latitude: float = Field(..., ge=-90,  le=90,  description="WGS-84 latitude")
    longitude: float = Field(..., ge=-180, le=180, description="WGS-84 longitude")


class RouteRequest(BaseModel):
    """Request body for POST /api/routes."""
    source: RoutePoint
    destination: RoutePoint


# ── Output schemas ────────────────────────────────────────────────────────────

class RouteGeometry(BaseModel):
    """GeoJSON LineString geometry as returned by OSRM (geometries=geojson)."""
    type: str = Field(default="LineString")
    # List of [longitude, latitude] pairs — GeoJSON coordinate order.
    coordinates: list[list[float]]


class RouteStep(BaseModel):
    """
    A single turn-by-turn step.
    Stores enough data for future ML segment feature extraction.
    """
    name: str = Field(default="", description="Road / street name")
    distance: float = Field(description="Step distance in metres")
    duration: float = Field(description="Step duration in seconds")
    geometry: Optional[RouteGeometry] = Field(
        default=None,
        description="GeoJSON geometry of this step segment",
    )
    maneuver: Optional[dict[str, Any]] = Field(
        default=None,
        description="OSRM maneuver object (type, bearing, location, …)",
    )

    # ── Extensibility placeholders (filled by later modules) ───────────────
    # traffic_speed_kmh: Optional[float] = None
    # accident_risk_score: Optional[float] = None


class RouteResponse(BaseModel):
    """
    A single candidate route.

    Preserves full geometry so later modules can:
      - Extract road segments
      - Match historical accidents
      - Query infrastructure
      - Generate ML features
      - Score route safety
    """
    id: str = Field(description="Stable identifier: route_1, route_2, …")
    distance_meters: float = Field(description="Total route distance in metres")
    duration_seconds: float = Field(description="Total route duration in seconds")
    geometry: RouteGeometry = Field(description="Full GeoJSON LineString geometry")
    steps: list[RouteStep] = Field(default_factory=list)

    # ── Future module hooks (all Optional so schema stays backward-compatible)
    # safety_score: Optional[float] = None
    # traffic_score: Optional[float] = None
    # incident_count: Optional[int] = None
    # weather_risk: Optional[float] = None


class RoutesResponse(BaseModel):
    """Top-level response wrapping all candidate routes."""
    routes: list[RouteResponse]
    source: RoutePoint
    destination: RoutePoint
