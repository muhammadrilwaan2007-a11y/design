"""
backend/app/schemas/weather.py
Pydantic schemas for Module 5 — Weather & Time Analysis.

All fields are intentionally Optional where OpenWeather may omit them
(e.g. rain, snow, wind_gust) so that a missing field never causes
a validation error or broken response.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Request ────────────────────────────────────────────────────────────────────

class WeatherRequest(BaseModel):
    """Request body: geographic coordinate for weather lookup."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


# ── Sub-objects ────────────────────────────────────────────────────────────────

class WeatherLocation(BaseModel):
    latitude: float
    longitude: float


class WeatherCondition(BaseModel):
    """OpenWeather weather condition code, main group, and text description."""
    id: int
    main: str
    description: str


class WeatherData(BaseModel):
    """
    Normalized weather observation.
    All values use metric units (Celsius, m/s, mm, hPa, metres).
    """
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    humidity_percent: Optional[int] = None
    pressure_hpa: Optional[int] = None
    visibility_m: Optional[int] = None

    wind_speed_ms: Optional[float] = None
    wind_gust_ms: Optional[float] = None          # May be absent from API
    wind_direction_deg: Optional[int] = None

    cloudiness_percent: Optional[int] = None

    weather: Optional[WeatherCondition] = None    # Primary weather condition

    rain_1h_mm: float = 0.0                        # Defaults to 0 when not raining
    snow_1h_mm: float = 0.0                        # Defaults to 0 when no snow

    sunrise: Optional[int] = None                  # Unix UTC timestamp
    sunset: Optional[int] = None                   # Unix UTC timestamp


# ── Time features ──────────────────────────────────────────────────────────────

class TimeFeatures(BaseModel):
    """
    Temporal features derived from current Bengaluru time.
    is_night uses actual sunrise/sunset from OpenWeather, not a fixed hour.
    """
    hour: int
    minute: int
    day_of_week: int                # 0=Monday … 6=Sunday
    is_weekend: bool
    is_night: bool
    is_rush_hour: bool
    time_period: str                # early_morning | morning | afternoon | evening | night
    local_time_str: str             # Human-readable e.g. "17:42 IST"


# ── Weather feature vector ─────────────────────────────────────────────────────

class WeatherFeatures(BaseModel):
    """
    Boolean indicators and derived numerical features ready for ML pipeline.

    No scores or weights are applied here — raw measurements only.
    The ML model in Module 8 learns how these features relate to accident risk.
    """
    # Rain
    is_raining: bool = False
    is_heavy_rain: bool = False
    rain_classification: str = "No rain"   # No rain | Light rain | Moderate rain | Heavy rain

    # Visibility
    is_low_visibility: bool = False

    # Wind
    is_strong_wind: bool = False

    # Numerical passthrough for ML
    temperature_c: Optional[float] = None
    humidity_percent: Optional[int] = None
    visibility_m: Optional[int] = None
    wind_speed_ms: Optional[float] = None
    wind_gust_ms: Optional[float] = None
    cloudiness_percent: Optional[int] = None
    rain_1h_mm: float = 0.0
    snow_1h_mm: float = 0.0
    weather_id: Optional[int] = None

    # Time (duplicated here for convenience of ML pipeline)
    hour: Optional[int] = None
    day_of_week: Optional[int] = None
    is_weekend: bool = False
    is_night: bool = False
    is_rush_hour: bool = False
    time_period: Optional[str] = None


# ── Top-level response ─────────────────────────────────────────────────────────

class WeatherResponse(BaseModel):
    """
    Full weather + time response returned by POST /api/weather/current.
    If available=False, only error is populated; all other fields are None.
    """
    available: bool = True
    error: Optional[str] = None

    location: Optional[WeatherLocation] = None
    weather: Optional[WeatherData] = None
    time: Optional[TimeFeatures] = None
    features: Optional[WeatherFeatures] = None
