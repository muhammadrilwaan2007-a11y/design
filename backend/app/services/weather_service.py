"""
backend/app/services/weather_service.py
Module 5 — Weather & Time Analysis.

Responsibilities:
  1. Call OpenWeather current weather API.
  2. Normalize the raw response into WeatherData.
  3. Compute time features using Bengaluru (IST) local time.
  4. Compute weather feature indicators for the ML pipeline.
  5. Handle all API errors gracefully — never break route generation.

Architecture: FastAPI endpoint → weather_service → OpenWeather HTTP API.
The OpenWeather API key never leaves the backend.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

import httpx

from app.config.settings import get_settings
from app.schemas.weather import (
    WeatherCondition,
    WeatherData,
    WeatherFeatures,
    WeatherLocation,
    WeatherResponse,
    TimeFeatures,
)

logger = logging.getLogger(__name__)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _classify_time_period(hour: int) -> str:
    """Map hour (0–23) to a named time period."""
    if 5 <= hour < 8:
        return "early_morning"
    if 8 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _is_night_from_sun(now_utc: datetime, sunrise_unix: Optional[int], sunset_unix: Optional[int]) -> bool:
    """
    Determine night using actual sunrise/sunset timestamps from OpenWeather.
    Falls back to a simple hour-based check (21:00–05:00 IST) when data is missing.
    """
    if sunrise_unix is not None and sunset_unix is not None:
        sunrise_dt = datetime.fromtimestamp(sunrise_unix, tz=timezone.utc)
        sunset_dt  = datetime.fromtimestamp(sunset_unix,  tz=timezone.utc)
        return not (sunrise_dt <= now_utc <= sunset_dt)

    # Fallback: use IST hour
    settings = get_settings()
    ist = ZoneInfo(settings.bengaluru_timezone)
    local_hour = now_utc.astimezone(ist).hour
    return local_hour >= 21 or local_hour < 5


def _is_rush_hour(hour: int, minute: int) -> bool:
    """
    Check whether the current local IST time falls in a Bengaluru rush-hour window.
    Morning: 07:00–10:30  |  Evening: 16:30–20:30
    Boundaries are loaded from settings so they can be changed without code edits.
    """
    settings = get_settings()
    # Convert to fractional hours for easy comparison
    t = hour + minute / 60.0
    morning_window = (
        settings.rush_morning_start_hour <= t < settings.rush_morning_end_hour + 0.5
    )
    evening_window = (
        settings.rush_evening_start_hour + 0.5 <= t < settings.rush_evening_end_hour + 0.5
    )
    return morning_window or evening_window


def compute_time_features(
    now_utc: Optional[datetime] = None,
    sunrise_unix: Optional[int] = None,
    sunset_unix: Optional[int] = None,
) -> TimeFeatures:
    """
    Build a TimeFeatures object from the current moment in Bengaluru IST.
    `now_utc` is injectable for unit-testing; defaults to the real current time.
    """
    settings = get_settings()
    ist = ZoneInfo(settings.bengaluru_timezone)

    if now_utc is None:
        now_utc = datetime.now(tz=timezone.utc)

    local_dt = now_utc.astimezone(ist)
    hour      = local_dt.hour
    minute    = local_dt.minute
    dow       = local_dt.weekday()   # 0=Monday … 6=Sunday

    return TimeFeatures(
        hour=hour,
        minute=minute,
        day_of_week=dow,
        is_weekend=(dow >= 5),
        is_night=_is_night_from_sun(now_utc, sunrise_unix, sunset_unix),
        is_rush_hour=_is_rush_hour(hour, minute),
        time_period=_classify_time_period(hour),
        local_time_str=local_dt.strftime("%H:%M IST"),
    )


def _classify_rain(rain_mm: float) -> tuple[bool, bool, str]:
    """Return (is_raining, is_heavy_rain, rain_classification)."""
    s = get_settings()
    if rain_mm <= 0:
        return False, False, "No rain"
    if rain_mm <= s.rain_light_threshold_mm:
        return True, False, "Light rain"
    if rain_mm <= s.rain_heavy_threshold_mm:
        return True, False, "Moderate rain"
    return True, True, "Heavy rain"


def compute_weather_features(
    data: WeatherData,
    time: TimeFeatures,
) -> WeatherFeatures:
    """Build the ML feature vector from normalized weather + time data."""
    s = get_settings()

    is_raining, is_heavy_rain, rain_class = _classify_rain(data.rain_1h_mm)

    # Also treat OpenWeather weather_id 2xx (thunderstorm) and 5xx (rain) as raining
    # even if rain_1h is absent (some stations don't report precip volume).
    wid = data.weather.id if data.weather else None
    if wid is not None and (200 <= wid < 600) and not is_raining:
        is_raining = True
        if wid in range(502, 532):   # heavy / extreme rain codes
            is_heavy_rain = True
        if rain_class == "No rain":
            rain_class = "Light rain"

    vis = data.visibility_m or 10_000
    wind = data.wind_speed_ms or 0.0

    return WeatherFeatures(
        is_raining=is_raining,
        is_heavy_rain=is_heavy_rain,
        rain_classification=rain_class,
        is_low_visibility=(vis < s.low_visibility_threshold_m),
        is_strong_wind=(wind >= s.strong_wind_threshold_ms),
        temperature_c=data.temperature_c,
        humidity_percent=data.humidity_percent,
        visibility_m=data.visibility_m,
        wind_speed_ms=data.wind_speed_ms,
        wind_gust_ms=data.wind_gust_ms,
        cloudiness_percent=data.cloudiness_percent,
        rain_1h_mm=data.rain_1h_mm,
        snow_1h_mm=data.snow_1h_mm,
        weather_id=wid,
        hour=time.hour,
        day_of_week=time.day_of_week,
        is_weekend=time.is_weekend,
        is_night=time.is_night,
        is_rush_hour=time.is_rush_hour,
        time_period=time.time_period,
    )


def _parse_openweather_response(raw: dict, lat: float, lon: float) -> WeatherData:
    """Parse and normalize the raw OpenWeather /data/2.5/weather JSON response."""
    main    = raw.get("main", {})
    wind    = raw.get("wind", {})
    clouds  = raw.get("clouds", {})
    sys     = raw.get("sys", {})
    conds   = raw.get("weather", [])

    # Primary weather condition
    condition: Optional[WeatherCondition] = None
    if conds:
        c = conds[0]
        condition = WeatherCondition(
            id=c.get("id", 0),
            main=c.get("main", ""),
            description=c.get("description", ""),
        )

    # Precipitation — both keys may be absent when there is no precipitation
    rain_1h = raw.get("rain", {}).get("1h", 0.0)
    snow_1h = raw.get("snow", {}).get("1h", 0.0)

    # Visibility is in metres; may be absent in some stations
    visibility = raw.get("visibility")

    return WeatherData(
        temperature_c=main.get("temp"),
        feels_like_c=main.get("feels_like"),
        humidity_percent=main.get("humidity"),
        pressure_hpa=main.get("pressure"),
        visibility_m=visibility,
        wind_speed_ms=wind.get("speed"),
        wind_gust_ms=wind.get("gust"),
        wind_direction_deg=wind.get("deg"),
        cloudiness_percent=clouds.get("all"),
        weather=condition,
        rain_1h_mm=float(rain_1h) if rain_1h else 0.0,
        snow_1h_mm=float(snow_1h) if snow_1h else 0.0,
        sunrise=sys.get("sunrise"),
        sunset=sys.get("sunset"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_weather(lat: float, lon: float) -> WeatherResponse:
    """
    Fetch current weather from OpenWeather and return a fully normalized
    WeatherResponse containing raw data, time features, and ML feature vector.

    On any failure, returns WeatherResponse(available=False, error=...) so that
    routes/traffic/incidents continue to function without weather data.
    """
    settings = get_settings()
    api_key  = settings.openweather_api_key

    if not api_key:
        logger.warning("OPENWEATHER_API_KEY is not set — skipping weather fetch.")
        return WeatherResponse(available=False, error="Weather API key not configured.")

    params = {
        "lat":   lat,
        "lon":   lon,
        "appid": api_key,
        "units": "metric",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                OPENWEATHER_URL, params=params, timeout=settings.openweather_timeout
            )

        if response.status_code == 401:
            logger.error("OpenWeather: invalid API key (401).")
            return WeatherResponse(available=False, error="Invalid weather API key.")
        if response.status_code == 429:
            logger.warning("OpenWeather: rate limit hit (429).")
            return WeatherResponse(available=False, error="Weather API rate limit exceeded.")

        response.raise_for_status()
        raw = response.json()

    except httpx.TimeoutException:
        logger.error("OpenWeather request timed out.")
        return WeatherResponse(available=False, error="Weather request timed out.")
    except httpx.RequestError as e:
        logger.error(f"OpenWeather request error: {e}")
        return WeatherResponse(available=False, error="Weather service unreachable.")
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenWeather HTTP error: {e}")
        return WeatherResponse(available=False, error=f"Weather API error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Unexpected error fetching weather: {e}", exc_info=True)
        return WeatherResponse(available=False, error="Unexpected weather service error.")

    try:
        weather_data = _parse_openweather_response(raw, lat, lon)
        time_features = compute_time_features(
            sunrise_unix=weather_data.sunrise,
            sunset_unix=weather_data.sunset,
        )
        weather_features = compute_weather_features(weather_data, time_features)

        logger.info(
            f"Weather fetched for ({lat},{lon}): "
            f"{weather_data.weather.description if weather_data.weather else 'N/A'}, "
            f"{weather_data.temperature_c}°C, "
            f"rain={weather_data.rain_1h_mm}mm, "
            f"is_night={time_features.is_night}, "
            f"is_rush_hour={time_features.is_rush_hour}"
        )

        return WeatherResponse(
            available=True,
            location=WeatherLocation(latitude=lat, longitude=lon),
            weather=weather_data,
            time=time_features,
            features=weather_features,
        )

    except Exception as e:
        logger.error(f"Error parsing OpenWeather response: {e}", exc_info=True)
        return WeatherResponse(available=False, error="Failed to parse weather data.")
