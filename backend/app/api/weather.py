"""
backend/app/api/weather.py
Module 5 — Weather & Time Analysis endpoint.

POST /api/weather/current
  - Accepts a latitude/longitude coordinate
  - Returns normalized weather data, time features, and ML feature vector
  - Always returns a response; never raises 500 due to weather unavailability
"""

import logging
from fastapi import APIRouter, HTTPException

from app.schemas.weather import WeatherRequest, WeatherResponse
from app.services.weather_service import get_current_weather

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/weather",
    tags=["weather"],
)


@router.post("/current", response_model=WeatherResponse)
async def current_weather(request: WeatherRequest):
    """
    Fetch current weather and time features for a geographic coordinate.

    Returns available=False with an error message when OpenWeather is unreachable
    or the API key is missing/invalid, so that upstream callers (route display,
    etc.) can degrade gracefully without showing an error page.
    """
    if not (-90 <= request.latitude <= 90) or not (-180 <= request.longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid coordinates.")

    logger.info(f"Weather request: ({request.latitude}, {request.longitude})")
    return await get_current_weather(request.latitude, request.longitude)
