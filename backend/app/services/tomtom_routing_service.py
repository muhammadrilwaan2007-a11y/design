"""
backend/app/services/tomtom_routing_service.py
TomTom Routing Service — replaces OSRM.

Responsibilities:
  1. Build TomTom calculateRoute request
  2. Send HTTP request with traffic-aware routing
  3. Validate response and handle HTTP/API errors gracefully
  4. Parse raw TomTom routes into our existing RouteResponse schema
"""

import logging
import httpx

from app.config.settings import get_settings
from app.schemas.route import (
    RouteGeometry,
    RouteResponse,
    RouteStep,
    RoutePoint,
)

logger = logging.getLogger(__name__)

class TomTomRoutingError(Exception):
    """Raised when TomTom API returns an error."""

class NoRouteFound(TomTomRoutingError):
    """Raised when no route can be found between points."""


def _normalise_instruction(instruction: dict) -> RouteStep:
    """Convert a TomTom instruction into our RouteStep schema."""
    maneuver = {
        "type": instruction.get("maneuver", "straight"),
        "modifier": instruction.get("direction", "")
    }
    
    return RouteStep(
        name=instruction.get("street", instruction.get("message", "Unnamed road")),
        distance=float(instruction.get("routeOffsetInMeters", 0)),
        duration=float(instruction.get("travelTimeInSeconds", 0)),
        geometry=None, # Step-level geometry omitted for simplicity
        maneuver=maneuver,
    )


def _normalise_route(raw_route: dict, index: int) -> RouteResponse:
    """Convert a raw TomTom route dict into our RouteResponse schema."""
    route_id = f"route_{index + 1}"

    summary = raw_route.get("summary", {})
    legs = raw_route.get("legs", [])
    
    if not legs:
        raise TomTomRoutingError(f"Route {route_id} missing legs")
        
    leg = legs[0]
    points = leg.get("points", [])
    
    if not points:
        raise TomTomRoutingError(f"Route {route_id}: missing geometry points")

    # Map [{latitude: x, longitude: y}] -> [[lon, lat]] for GeoJSON LineString
    coordinates = [[p["longitude"], p["latitude"]] for p in points]
    
    geometry = RouteGeometry(
        type="LineString",
        coordinates=coordinates,
    )

    # Use traffic-aware travel time
    duration_seconds = float(summary.get("travelTimeInSeconds", 0))
    distance_meters = float(summary.get("lengthInMeters", 0))

    # Parse instructions if available
    guidance = raw_route.get("guidance", {})
    raw_instructions = guidance.get("instructions", [])
    steps = [_normalise_instruction(inst) for inst in raw_instructions]

    return RouteResponse(
        id=route_id,
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
        geometry=geometry,
        steps=steps,
    )


async def fetch_tomtom_routes(
    source: RoutePoint,
    destination: RoutePoint,
) -> list[RouteResponse]:
    """
    Call TomTom Routing API and return a list of normalised RouteResponse objects.
    """
    settings = get_settings()
    api_key = settings.tomtom_api_key
    
    if not api_key:
        raise TomTomRoutingError("TomTom API key is not configured on the server.")

    # TomTom expects lat,lon format
    locations = f"{source.latitude},{source.longitude}:{destination.latitude},{destination.longitude}"
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{locations}/json"
    
    params = {
        "key": api_key,
        "maxAlternatives": 2,          # Up to 3 routes total
        "traffic": "true",             # Critical: Live traffic-aware routing
        "computeTravelTimeFor": "all", # Provides traffic delay info if needed later
        "instructionsType": "text",    # Required for turn-by-turn steps
        "routeRepresentation": "polyline",
    }

    logger.info("Calling TomTom Routing API (traffic-aware)...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            
        if response.status_code == 403 or response.status_code == 401:
            raise TomTomRoutingError("TomTom routing authentication failed (API Key).")
        if response.status_code == 429:
            raise TomTomRoutingError("Routing service rate limit exceeded.")
        
        response.raise_for_status()
        data = response.json()
        
    except httpx.TimeoutException as exc:
        raise TomTomRoutingError("Routing service timed out. Please try again.") from exc
    except httpx.HTTPStatusError as exc:
        logger.error(f"TomTom HTTP error: {exc.response.text}")
        if exc.response.status_code == 400:
            err_code = exc.response.json().get("error", {}).get("description", "")
            if "NO_ROUTE_FOUND" in err_code or "NO_ROUTE" in err_code:
                raise NoRouteFound("No route found between the selected locations.")
        raise TomTomRoutingError(f"TomTom routing failed with status {exc.response.status_code}.") from exc
    except Exception as exc:
        logger.exception("Unexpected error during routing")
        raise TomTomRoutingError("Unexpected error communicating with routing service.") from exc

    raw_routes = data.get("routes", [])
    if not raw_routes:
        raise NoRouteFound("No route could be found between these locations.")

    routes: list[RouteResponse] = []
    for i, raw in enumerate(raw_routes):
        try:
            routes.append(_normalise_route(raw, i))
        except TomTomRoutingError as exc:
            logger.warning("Skipping route %d due to error: %s", i + 1, exc)

    if not routes:
        raise TomTomRoutingError("Routes were returned but could not be processed.")

    logger.info(f"Returning {len(routes)} candidate route(s). Distance: {routes[0].distance_meters}m, Traffic ETA: {routes[0].duration_seconds}s")
    return routes
