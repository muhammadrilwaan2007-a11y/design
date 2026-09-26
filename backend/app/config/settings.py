"""
backend/app/config/settings.py
Application configuration via environment variables / .env file.

Allows OSRM_BASE_URL to be changed without touching application code —
useful when switching from the public OSRM demo to a self-hosted instance.
"""

from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── TomTom ───────────────────────────────────────────────────────────────
    tomtom_api_key: str = ""

    # ── Incident matching ─────────────────────────────────────────────────────
    incident_route_distance_threshold_meters: float = 150.0
    incident_road_closure_distance_threshold_meters: float = 25.0

    # ── OpenWeather ───────────────────────────────────────────────────────────
    openweather_api_key: str = ""
    openweather_timeout: float = 10.0

    # ── Weather feature thresholds ────────────────────────────────────────────
    rain_light_threshold_mm: float = 2.5       # > 0 and <= this → Light rain
    rain_heavy_threshold_mm: float = 7.6       # > this → Heavy rain
    low_visibility_threshold_m: float = 5000.0 # below this → is_low_visibility
    strong_wind_threshold_ms: float = 8.0      # >= this → is_strong_wind

    # ── Rush-hour windows (Bengaluru, 24h clock) ──────────────────────────────
    rush_morning_start_hour: int = 7
    rush_morning_end_hour: int = 10            # up to 10:30 (30 min grace in code)
    rush_evening_start_hour: int = 16          # from 16:30 (30 min grace in code)
    rush_evening_end_hour: int = 20

    # ── Timezone ──────────────────────────────────────────────────────────────
    bengaluru_timezone: str = "Asia/Kolkata"


    # ── Module 6: Historical Accident Data ───────────────────────────────────
    # Path to the raw accident CSV. Override in .env to use a different location.
    accident_csv_path: str = r"C:\Users\Madhan\Downloads\Copy of AccidentReports.csv\Copy of AccidentReports.csv"

    # Bengaluru district filter keywords (lowercase, comma-separated in .env)
    bengaluru_filter_keywords: str = "bengaluru"

    # Bounding box for plausible Bengaluru coordinates (WGS84)
    blr_lat_min: float = 12.7
    blr_lat_max: float = 13.3
    blr_lon_min: float = 77.3
    blr_lon_max: float = 77.9

    # DBSCAN hotspot detection parameters
    # eps is the maximum distance (metres) between two points in a cluster
    hotspot_eps_meters: float = 300.0
    # Minimum number of accidents to form a hotspot cluster
    hotspot_min_samples: int = 5

    # Radius (metres) used when computing segment-level accident features
    segment_radius_meters: float = 500.0

    # Processed data output directory (relative to backend/)
    processed_data_dir: str = "data/processed"
    features_data_dir: str = "data/features"

    # ── Module 7: Spatial & Safety Feature Engineering ────────────────────────
    # Target length of each route segment in metres (actual length is geometry-derived)
    segment_length_m: int = 500

    # Spatial buffer (metres) around each segment when intersecting with hotspots
    hotspot_buffer_m: float = 300.0

    # Distance threshold (metres) for assigning live incidents to a segment
    segment_incident_buffer_m: float = 150.0

    # Minimum bearing change (degrees) to count as a "turn" in spatial features
    turn_bearing_threshold_deg: float = 15.0

    # EPSG code for the projected CRS used in metric distance calculations
    # EPSG:32643 = UTM Zone 43N — correct for Bengaluru (77–78°E, 12–14°N)
    utm_epsg: int = 32643

    # ── Supabase / PostgreSQL + PostGIS ──────────────────────────────────────
    supabase_url: str = ""
    supabase_service_key: str = ""

    # ── Module 7.5: Live Snapshot System ─────────────────────────────────────
    # Freshness windows (minutes) — overridable in .env without code changes
    snapshot_traffic_freshness_minutes: int = 5
    snapshot_incident_freshness_minutes: int = 5
    snapshot_weather_freshness_minutes: int = 15

    # Local dev fallback storage (used only when Supabase is not configured)
    snapshot_dir: str = "data/snapshots"

    # Bengaluru city center — used for weather snapshot collection
    bengaluru_center_lat: float = 12.9716
    bengaluru_center_lon: float = 77.5946

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins.  Override in .env if needed.
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173"

    # ── Module 8: Risk Engine ─────────────────────────────────────────────────
    # Path to the trained XGBoost model (relative to backend/ or absolute).
    # Override in .env to point at a different model file without code changes.
    xgboost_model_path: str = "models/xgboost_baseline.json"

    # OSM road-edge map matching tolerances
    osm_match_buffer_m: float = 15.0       # MATCH_BUFFER_M: lateral buffer around route polyline
    osm_max_match_distance_m: float = 25.0 # MAX_MATCH_DISTANCE_M: maximum distance to accept an OSM edge match
    osm_roads_gpkg_path: str = "data/processed/osm_roads_with_accidents.gpkg"

    # Probability calibration factor (derived from training scale_pos_weight: 330,718 neg / 4,897 pos)
    calibration_scale_pos_weight: float = 67.53

    # Live-condition adjustment caps — keep penalty small and bounded.
    # Each value is a safety-score DEDUCTION (0–100 scale), not a probability.
    live_adjustment_rain_light: int = 3       # Light rain deduction
    live_adjustment_rain_heavy: int = 8       # Heavy rain deduction
    live_adjustment_low_vis: int = 5          # Low-visibility deduction
    live_adjustment_strong_wind: int = 2      # Strong wind deduction
    live_adjustment_accident_incident: int = 6  # Live accident on route deduction
    live_adjustment_dangerous_condition: int = 4  # TomTom dangerous condition
    live_adjustment_severe_congestion: int = 3  # Congestion ratio >= 0.7

    # ── LLM Safety Assistant (Groq / GPT-OSS 120B) ───────────────────────────
    # The Groq API key is loaded strictly from environment variable / .env.
    # NEVER expose this key to frontend or logs.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 25.0

    # ── App meta ─────────────────────────────────────────────────────────────
    app_version: str = "0.3.0"

    class Config:
        env_file = ("../.env", ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
