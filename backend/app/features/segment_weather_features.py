"""
backend/app/features/segment_weather_features.py
Module 7 — Route-Level Weather Feature Extractor

Maps OpenWeather data to route segments.

Design decisions:
  - Weather is fetched ONCE per route at the route midpoint. Weather is
    spatially uniform across a city-scale Bengaluru route (~5–25 km) and
    fetching per-segment would waste API calls for identical data.
  - Reuses get_current_weather() from weather_service.py. No new API client.
  - weather_risk is computed as an explicit integer (0–3) with documented
    thresholds. No hidden weights. Module 8 learns its relationship to
    accident risk from training data — it is NOT pre-baked here.
  - All weather values propagated are raw measurements (rain_1h_mm,
    visibility_m, wind_speed_ms) so Module 8 can form its own relationships.
  - weather_data_available=False means OpenWeather failed — all weather
    fields remain None (not zero).

weather_risk encoding (explicit, configurable via thresholds in settings):
  0 → No adverse weather
  1 → Light rain OR low visibility (< 5000m)
  2 → Heavy rain (> 7.6 mm/h)
  3 → Heavy rain AND low visibility simultaneously
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.config.settings import get_settings
from app.schemas.features import SegmentFeatureVector
from app.schemas.route import RouteGeometry
from app.services.weather_service import get_current_weather

logger = logging.getLogger(__name__)


def _route_midpoint(geometry: RouteGeometry) -> Tuple[float, float]:
    """Return (lat, lon) of the midpoint coordinate of the full route."""
    coords = geometry.coordinates
    if not coords:
        raise ValueError("Empty route geometry — cannot compute midpoint.")
    mid_idx = len(coords) // 2
    lon, lat = coords[mid_idx]
    return lat, lon


def _compute_weather_risk(
    rain_mm: Optional[float],
    visibility_m: Optional[int],
    settings,
) -> Optional[int]:
    """
    Compute weather_risk as an integer 0–3.

    Thresholds are read from settings (configurable in .env):
      rain_heavy_threshold_mm     → heavy rain cutoff
      low_visibility_threshold_m  → low visibility cutoff

    0 = no adverse weather
    1 = light rain OR low visibility
    2 = heavy rain
    3 = heavy rain AND low visibility
    """
    if rain_mm is None and visibility_m is None:
        return None  # No data available

    is_heavy_rain = (rain_mm or 0) > settings.rain_heavy_threshold_mm
    is_any_rain = (rain_mm or 0) > 0
    is_low_vis = (visibility_m or 10_000) < settings.low_visibility_threshold_m

    if is_heavy_rain and is_low_vis:
        return 3
    if is_heavy_rain:
        return 2
    if is_any_rain or is_low_vis:
        return 1
    return 0


async def compute_route_weather_features(
    segments: List[SegmentFeatureVector],
    route_geometry: RouteGeometry,
) -> List[SegmentFeatureVector]:
    """
    Fetch weather once for the route midpoint and propagate raw measurements
    to all segments.

    Parameters
    ----------
    segments : list[SegmentFeatureVector]
        Segments from route_segmentation.
    route_geometry : RouteGeometry
        Full route geometry (used to find the midpoint for the API call).

    Returns
    -------
    list[SegmentFeatureVector]
        Same list with weather fields populated on every segment.
    """
    if not segments:
        return segments

    settings = get_settings()

    try:
        lat, lon = _route_midpoint(route_geometry)
    except ValueError as exc:
        logger.warning("Cannot compute route midpoint: %s", exc)
        for seg in segments:
            seg.weather_data_available = False
        return segments

    weather_resp = await get_current_weather(lat, lon)

    if not weather_resp.available or weather_resp.weather is None:
        logger.warning(
            "Weather data unavailable for route midpoint (%.4f, %.4f): %s",
            lat, lon, weather_resp.error,
        )
        for seg in segments:
            seg.weather_data_available = False
        return segments

    # Extract raw measurements
    weather = weather_resp.weather
    rain_mm = weather.rain_1h_mm
    visibility = weather.visibility_m
    wind = weather.wind_speed_ms

    risk = _compute_weather_risk(rain_mm, visibility, settings)

    logger.info(
        "Weather for route midpoint (%.4f, %.4f): rain=%.1fmm, vis=%sm, wind=%.1fm/s, risk=%s",
        lat, lon, rain_mm, visibility, wind or 0, risk,
    )

    # Apply to all segments (weather is uniform across the route)
    for seg in segments:
        seg.weather_data_available = True
        seg.rain_1h_mm = rain_mm
        seg.visibility_m = visibility
        seg.wind_speed_ms = wind
        seg.weather_risk = risk

    return segments
