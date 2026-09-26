"""
backend/app/api/routing.py
FastAPI router for POST /api/routes.

Frontend calls this endpoint — never OSRM directly.
This layer:
  - Validates the request body (Pydantic)
  - Delegates to osrm_service
  - Maps service exceptions to appropriate HTTP responses
  - Returns a clean RoutesResponse to the frontend
"""

import logging
from fastapi import APIRouter, HTTPException, status

from app.schemas.route import RouteRequest, RoutesResponse
from app.services.tomtom_routing_service import fetch_tomtom_routes, NoRouteFound, TomTomRoutingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["routing"])


@router.post(
    "/routes",
    response_model=RoutesResponse,
    summary="Generate candidate driving routes",
    description=(
        "Accepts source and destination coordinates, calls OSRM, "
        "and returns 1–3 candidate routes with full GeoJSON geometry."
    ),
)
async def get_routes(request: RouteRequest) -> RoutesResponse:
    """
    POST /api/routes

    Returns candidate routes from OSRM.
    Geometry is preserved in full (overview=full, geometries=geojson)
    so that later modules can perform:
      - road segment extraction
      - accident feature matching
      - infrastructure scoring
      - ML feature generation
    """
    logger.info(
        "Route request: src=(%s, %s) dst=(%s, %s)",
        request.source.latitude,
        request.source.longitude,
        request.destination.latitude,
        request.destination.longitude,
    )

    try:
        routes = await fetch_tomtom_routes(request.source, request.destination)
    except NoRouteFound as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "NO_ROUTE", "message": str(exc)},
        ) from exc
    except TomTomRoutingError as exc:
        logger.error("TomTom routing error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ROUTING_ERROR", "message": str(exc)},
        ) from exc

    # ── Asynchronously trigger live snapshot collection ───────────────────────
    # The frontend currently calls /api/routes but not /api/features/analyze.
    # We trigger the snapshot and request recording here in the background so 
    # the S->D search triggers data collection without blocking the UI response.
    from app.services.live_snapshot_service import live_snapshot_service
    import asyncio

    async def collect_snapshot_background(req: RouteRequest, bundle_routes):
        try:
            snapshot = await live_snapshot_service.get_or_refresh()
            await live_snapshot_service.record_route_request(
                origin_lat=req.source.latitude,
                origin_lon=req.source.longitude,
                destination_lat=req.destination.latitude,
                destination_lon=req.destination.longitude,
                bundle=snapshot
            )
        except Exception as e:
            logger.error("Background snapshot collection failed: %s", e)

    # Use asyncio.create_task instead of FastAPI BackgroundTasks since we are 
    # spinning off an async process outside of the request lifecycle.
    asyncio.create_task(collect_snapshot_background(request, routes))

    return RoutesResponse(
        routes=routes,
        source=request.source,
        destination=request.destination,
    )
