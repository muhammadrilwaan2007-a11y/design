"""
backend/app/schemas/features.py
Pydantic schemas for Module 7 — Spatial & Safety Feature Engineering.

Units (all distances in metres, speeds in km/h, rain in mm/h):
  - segment_length_m          → metres
  - hotspot distances          → metres
  - incident distances         → metres
  - current_speed_kmh          → km/h
  - free_flow_speed_kmh        → km/h
  - congestion_ratio           → dimensionless (0.0–1.0+)
  - travel_time_s              → seconds
  - rain_1h_mm                 → mm/h
  - visibility_m               → metres
  - wind_speed_ms              → m/s
  - turn_density               → turns per km
  - hotspot_density            → hotspots per km
  - accidents_per_km           → accidents per km

data_available flags:
  True  → API responded successfully (even if count is 0)
  False → API call failed / data unavailable (null feature fields)
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.schemas.route import RouteGeometry


# ── Request schemas ────────────────────────────────────────────────────────────

class RouteForFeatures(BaseModel):
    """A single candidate route submitted for feature engineering."""
    route_id: str
    geometry: RouteGeometry


class MultiRouteFeatureRequest(BaseModel):
    """Request body: one or more candidate routes to analyze."""
    routes: list[RouteForFeatures]


# ── Segment geometry ───────────────────────────────────────────────────────────

class SegmentCoord(BaseModel):
    """A single WGS-84 coordinate."""
    latitude: float
    longitude: float


class SegmentGeometry(BaseModel):
    """GeoJSON LineString geometry for a single route segment."""
    type: str = Field(default="LineString")
    coordinates: list[list[float]]   # [[lon, lat], ...]


# ── Per-segment feature vector ─────────────────────────────────────────────────

class SegmentFeatureVector(BaseModel):
    """
    Full feature vector for a single route segment.

    Module 8 (XGBoost) consumes a list of these to produce segment risk scores.

    null values indicate data was UNAVAILABLE (API failure), not that the value
    is zero. Module 8 must handle nulls explicitly (e.g., via XGBoost's native
    missing-value handling).

    See schema docstring for unit definitions.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    route_id: str
    segment_id: str                     # e.g. "route_1_seg_003"
    segment_index: int                  # 0-based position along route

    # ── Geometry ──────────────────────────────────────────────────────────────
    geometry: Optional[SegmentGeometry] = None    # GeoJSON for frontend visualization
    start_coord: SegmentCoord
    end_coord: SegmentCoord
    midpoint_coord: SegmentCoord

    # ── Spatial dimensions ────────────────────────────────────────────────────
    segment_length_m: float             # Actual geometry-derived length (UTM calc)
    segment_length_km: float            # Convenience: segment_length_m / 1000
    start_distance_m: float             # Cumulative offset from route start
    end_distance_m: float               # Cumulative offset to segment end

    # ── Historical accident features (from Module 6 hotspots) ─────────────────
    hotspot_count: int = 0              # Number of hotspots within buffer
    fatal_hotspot_count: int = 0        # Hotspots with fatal_accident_count > 0
    hotspot_density: float = 0.0        # hotspots per km of segment
    nearest_hotspot_distance_m: Optional[float] = None   # null if no hotspots
    accidents_per_km: float = 0.0       # Total accidents in buffer / segment km

    # ── Live incident features (from TomTom Incidents API) ────────────────────
    incident_count: Optional[int] = None
    accident_count: Optional[int] = None
    roadwork_count: Optional[int] = None
    road_closure_count: Optional[int] = None
    lane_closure_count: Optional[int] = None
    traffic_jam_incident_count: Optional[int] = None
    dangerous_condition_count: Optional[int] = None
    nearest_incident_distance_m: Optional[float] = None
    incidents_data_available: bool = False   # True = API responded (even if 0)

    # ── Traffic flow features (from TomTom Traffic Flow API) ──────────────────
    current_speed_kmh: Optional[float] = None
    free_flow_speed_kmh: Optional[float] = None
    congestion_ratio: Optional[float] = None   # current_speed / free_flow_speed
    travel_time_s: Optional[float] = None
    traffic_data_available: bool = False

    # ── Weather features (from OpenWeather — uniform across route) ─────────────
    rain_1h_mm: Optional[float] = None      # mm/h
    visibility_m: Optional[int] = None      # metres
    wind_speed_ms: Optional[float] = None   # m/s
    weather_risk: Optional[int] = None      # 0=none, 1=light, 2=heavy, 3=heavy+low_vis
    weather_data_available: bool = False

    # ── Road/spatial features (derived from geometry) ─────────────────────────
    turn_count: int = 0
    turn_density: float = 0.0              # turns per km

    # road_class is populated from matched OSM road edges
    road_class: Optional[str] = None       # Primary OSM highway type from matched edges
    speed_limit_kmh: Optional[float] = None # Future: TomTom/HERE speed limit API
    matched_edges_count: Optional[int] = None # Number of underlying OSM edges matched
    osm_edge_ids: Optional[list[int]] = None # List of unique_edge_ids matched

    # ── Module 8: Risk Engine output ───────────────────────────────────────────
    # raw_risk_prob: raw uncalibrated XGBoost probability from model.predict_proba()
    # calibrated_risk_prob: Calibrated Historical Risk (Bayes unbiasing with scale_pos_weight=67.53)
    # historical_risk_prob: Historical Risk Probability (calibrated model risk probability, backward compatibility)
    # live_condition_deduction: score points removed by live-condition adjustment (diagnostic only)
    # safety_score: final 0-100 Safety Score (100 = safest, 0 = most dangerous) derived from calibrated_risk_prob
    raw_risk_prob: Optional[float] = None             # Raw uncalibrated XGBoost output
    calibrated_risk_prob: Optional[float] = None      # Calibrated Historical Risk
    historical_risk_prob: Optional[float] = None      # Historical Risk Probability (backward compat)
    live_condition_deduction: Optional[int] = None    # Points deducted for live events (diagnostic only)
    safety_score: Optional[int] = None                # Final 0-100 Safety Score

    # ── Future extension point (not activated in V1) ───────────────────────────
    # temporal_features: Optional[TemporalFeatureVector] = None



# ── Heatmap Edge Schema (OSM Road Edge) ────────────────────────────────────────

class OSMHeatmapEdge(BaseModel):
    """
    Representation of an underlying OpenStreetMap road edge with its
    calibrated historical risk prediction and safety score.
    Used for Leaflet map heatmap visualization.
    """
    edge_id: int = Field(..., description="Unique OSM edge identifier")
    name: Optional[str] = Field(default="", description="Road name if available")
    road_class: str = Field(..., description="OSM functional road class (e.g. primary, residential)")
    length_km: float = Field(..., description="Original training-edge length in km")
    length_m: float = Field(..., description="Original training-edge length in metres")
    calibrated_risk_prob: float = Field(..., description="Calibrated Historical Risk probability [0, 1]")
    raw_risk_prob: Optional[float] = Field(default=None, description="Raw uncalibrated model probability for diagnostics")
    safety_score: int = Field(..., description="Historical Safety Score [0, 100], computed as 100 - 100*sqrt(calibrated_risk_prob)")
    geometry: SegmentGeometry = Field(..., description="GeoJSON LineString geometry in WGS84 [[lon, lat], ...]")


class HeatmapResponse(BaseModel):
    """Standalone response containing OSM road edges for historical risk heatmap visualization."""
    total_edges: int = Field(..., description="Number of road edges returned")
    edges: list[OSMHeatmapEdge] = Field(default_factory=list, description="List of road edges with calibrated risk and geometry")


# ── Response schemas ───────────────────────────────────────────────────────────

class RouteFeatureResponse(BaseModel):
    """Feature engineering result for a single candidate route."""
    route_id: str
    segment_count: int
    total_route_length_m: float
    segments: list[SegmentFeatureVector]

    # ── Module 8 route-level aggregates ───────────────────────────────────────
    # Set by RiskEngine after scoring all segments.
    # route_safety_score: length-weighted mean of segment safety_score values.
    # Null if Risk Engine was unavailable for this route.
    route_safety_score: Optional[int] = None        # 0-100 overall route score
    route_risk_category: Optional[str] = None       # "low" | "medium" | "high"
    route_raw_risk_prob: Optional[float] = None     # Length-weighted raw probability
    route_calibrated_risk_prob: Optional[float] = None # Length-weighted calibrated probability

    # ── Historical Risk Heatmap OSM edges ─────────────────────────────────────
    # Underlying matched OSM road edges with geometry and calibrated risk.
    # Deduplicated by edge_id for efficient Leaflet rendering.
    heatmap_edges: list[OSMHeatmapEdge] = Field(
        default_factory=list,
        description="Deduplicated OSM road edges with calibrated risk and geometry for historical heatmap visualization",
    )


class MultiRouteFeatureResponse(BaseModel):
    """Top-level response wrapping feature analysis for all candidate routes."""
    routes: list[RouteFeatureResponse]
    total_segments: int


# ── Temporal extension stub (not activated in V1) ──────────────────────────────

class TemporalFeatureVector(BaseModel):
    """
    Future temporal feature vector. Not activated in V1.

    Will be populated when the harvested live incident dataset provides
    per-incident timestamps, enabling the XGBoost model to learn time-of-day
    and day-of-week accident patterns.

    Activation: add `temporal_features: Optional[TemporalFeatureVector]`
    to SegmentFeatureVector and wire TemporalFeatureExtractor into feature_pipeline.py.
    """
    hour: Optional[int] = None            # 0–23 IST
    day_of_week: Optional[int] = None     # 0=Mon … 6=Sun
    is_weekend: Optional[bool] = None
    is_night: Optional[bool] = None
    is_rush_hour: Optional[bool] = None
    time_period: Optional[str] = None     # early_morning | morning | afternoon | evening | night
