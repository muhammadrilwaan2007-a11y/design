"""
backend/app/schemas/snapshot.py
Pydantic schemas for Module 7.5 — Live Snapshot Collection System.

These schemas represent:
  - Data persisted to Supabase PostgreSQL + PostGIS
  - The SnapshotBundle passed to Module 7 feature pipeline
  - API response shapes for /api/live/snapshot/* endpoints

All timestamps are timezone-aware UTC.
Field names match the Supabase table column names exactly for
direct dict serialisation without transformation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Any, Dict

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class SnapshotSource(str, Enum):
    INCIDENTS = "incidents"
    TRAFFIC   = "traffic"
    WEATHER   = "weather"


class SnapshotStatus(str, Enum):
    OK      = "ok"       # All records fetched successfully
    PARTIAL = "partial"  # Fetch succeeded but some records failed to parse
    FAILED  = "failed"   # API call itself failed — no data stored


# ── Per-source freshness metadata ──────────────────────────────────────────────

class SourceStatus(BaseModel):
    """Freshness status for a single data source."""
    source: SnapshotSource
    snapshot_id: Optional[str] = None       # UUID of the snapshot row
    collected_at: Optional[datetime] = None # When this snapshot was collected (UTC)
    age_minutes: Optional[float] = None     # How old the snapshot is
    is_fresh: bool = False                  # True = within freshness window
    record_count: int = 0
    status: SnapshotStatus = SnapshotStatus.FAILED
    error: Optional[str] = None


# ── Database row models (maps to Supabase tables) ─────────────────────────────

class LiveDataSnapshotRow(BaseModel):
    """
    Maps to: live_data_snapshots table.
    One row per source per refresh event.
    """
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collected_at: datetime
    source: SnapshotSource
    status: SnapshotStatus = SnapshotStatus.OK
    record_count: int = 0
    coverage_area: str = "bengaluru_wide"
    error_message: Optional[str] = None

    def to_db_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "collected_at": self.collected_at.isoformat(),
            "source": self.source.value,
            "status": self.status.value,
            "record_count": self.record_count,
            "coverage_area": self.coverage_area,
            "error_message": self.error_message,
        }


class IncidentObservationRow(BaseModel):
    """
    Maps to: incident_observations table.
    One row per individual incident in a snapshot.
    """
    snapshot_id: str
    external_id: Optional[str] = None
    incident_type: str = "Unknown"
    icon_category: Optional[int] = None
    magnitude_of_delay: Optional[int] = None
    latitude: float
    longitude: float
    description: Optional[str] = None
    road_name: Optional[str] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    length_meters: Optional[float] = None
    delay_seconds: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    time_validity: Optional[str] = None
    number_of_reports: Optional[int] = None
    last_report_time: Optional[str] = None

    def to_db_dict(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class TrafficObservationRow(BaseModel):
    """
    Maps to: traffic_observations table.
    One row per traffic grid point in a snapshot.
    """
    snapshot_id: str
    latitude: float
    longitude: float
    current_speed: Optional[float] = None
    free_flow_speed: Optional[float] = None
    current_travel_time: Optional[float] = None
    free_flow_travel_time: Optional[float] = None
    confidence: Optional[float] = None
    congestion_ratio: Optional[float] = None
    delay_seconds: Optional[float] = None
    road_closure: bool = False

    def to_db_dict(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class WeatherObservationRow(BaseModel):
    """
    Maps to: weather_observations table.
    One row per weather observation in a snapshot (city-center point).
    """
    snapshot_id: str
    latitude: float
    longitude: float
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    humidity_percent: Optional[int] = None
    pressure_hpa: Optional[int] = None
    visibility_m: Optional[int] = None
    wind_speed_ms: Optional[float] = None
    wind_gust_ms: Optional[float] = None
    wind_direction_deg: Optional[int] = None
    cloudiness_percent: Optional[int] = None
    weather_id: Optional[int] = None
    weather_main: Optional[str] = None
    weather_description: Optional[str] = None
    rain_1h_mm: float = 0.0
    snow_1h_mm: float = 0.0
    collected_at: datetime

    def to_db_dict(self) -> dict:
        d = self.model_dump()
        d["collected_at"] = self.collected_at.isoformat()
        return {k: v for k, v in d.items() if v is not None}


class RouteRequestRow(BaseModel):
    """
    Maps to: route_requests table.
    One row per S→D request, recording which snapshots were used.
    """
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    origin_lat: float
    origin_lon: float
    destination_lat: float
    destination_lon: float
    requested_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    incident_snapshot_id: Optional[str] = None
    traffic_snapshot_id: Optional[str] = None
    weather_snapshot_id: Optional[str] = None
    status: str = "completed"

    def to_db_dict(self) -> dict:
        d = self.model_dump()
        d["requested_at"] = self.requested_at.isoformat()
        return {k: v for k, v in d.items() if v is not None}


# ── The live bundle passed to Module 7 ────────────────────────────────────────

class SnapshotBundle(BaseModel):
    """
    Container of live Bengaluru-wide data passed into the Module 7 pipeline.

    Produced by LiveSnapshotService.get_or_refresh().
    Consumed by feature_pipeline.run_pipeline_for_route().

    Source statuses indicate what data is actually available:
      - incidents_available=True → incidents list is valid (may be empty)
      - incidents_available=False → API failed, incidents is empty (not zero)
      - Same pattern for weather and traffic.
    """
    # Source snapshot IDs (for recording in route_requests)
    incident_snapshot_id: Optional[str] = None
    traffic_snapshot_id: Optional[str] = None
    weather_snapshot_id: Optional[str] = None

    # Pre-fetched live data
    incidents: List[Any] = []           # List[Incident] from tomtom_service
    traffic_points: List[Any] = []      # List[TrafficSegment] from tomtom_service
    weather: Optional[Any] = None       # WeatherResponse from weather_service

    # Availability flags (True = API succeeded, even if list is empty)
    incidents_available: bool = False
    traffic_available: bool = False
    weather_available: bool = False

    # Per-source freshness at time of bundle creation
    source_status: Dict[str, SourceStatus] = {}


# ── API response schemas ───────────────────────────────────────────────────────

class SnapshotStatusResponse(BaseModel):
    """Response for GET /api/live/snapshot/status"""
    checked_at: datetime
    sources: Dict[str, SourceStatus]
    all_fresh: bool
    supabase_connected: bool


class SnapshotLatestResponse(BaseModel):
    """Response for GET /api/live/snapshot/latest"""
    incident_snapshot: Optional[SourceStatus] = None
    traffic_snapshot: Optional[SourceStatus] = None
    weather_snapshot: Optional[SourceStatus] = None


class SnapshotRefreshResponse(BaseModel):
    """Response for POST /api/live/snapshot/refresh"""
    refreshed_at: datetime
    sources_refreshed: List[str]
    sources_skipped: List[str]
    total_records: int
    bundle: Optional[SnapshotBundle] = None
