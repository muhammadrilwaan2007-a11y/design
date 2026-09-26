"""
backend/app/api/live_snapshot.py
FastAPI router for live snapshot status and management endpoints.

Endpoints:
  GET  /api/live/snapshot/status   — current freshness of all sources
  GET  /api/live/snapshot/latest   — latest snapshot metadata per source
  POST /api/live/snapshot/refresh  — force-refresh all sources (admin)
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from app.schemas.snapshot import (
    SnapshotStatusResponse,
    SnapshotLatestResponse,
    SnapshotRefreshResponse,
)
from app.services.live_snapshot_service import live_snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live-snapshot"])


@router.get(
    "/snapshot/status",
    response_model=SnapshotStatusResponse,
    summary="Get freshness status of all Bengaluru live data sources",
    description=(
        "Returns current freshness metadata for incident, traffic, and weather sources. "
        "Does NOT trigger any API calls or refreshes. "
        "Use this to monitor how stale your data is before requesting routes."
    ),
)
async def get_snapshot_status() -> SnapshotStatusResponse:
    """GET /api/live/snapshot/status"""
    try:
        return await live_snapshot_service.get_status()
    except Exception as exc:
        logger.error("Failed to get snapshot status: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SNAPSHOT_STATUS_ERROR", "message": str(exc)},
        )


@router.get(
    "/snapshot/latest",
    response_model=SnapshotLatestResponse,
    summary="Get latest snapshot metadata per source",
    description=(
        "Returns snapshot IDs, collection timestamps, and record counts "
        "for the most recent non-failed snapshot of each data source. "
        "Does NOT return the actual observation data."
    ),
)
async def get_snapshot_latest() -> SnapshotLatestResponse:
    """GET /api/live/snapshot/latest"""
    try:
        return await live_snapshot_service.get_latest()
    except Exception as exc:
        logger.error("Failed to get latest snapshot: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SNAPSHOT_LATEST_ERROR", "message": str(exc)},
        )


@router.post(
    "/snapshot/refresh",
    response_model=SnapshotRefreshResponse,
    summary="Force-refresh all Bengaluru live data sources",
    description=(
        "Immediately fetches fresh Bengaluru-wide data from all sources "
        "(TomTom Incidents, TomTom Traffic, OpenWeather) regardless of current freshness. "
        "Persists new snapshots to Supabase. "
        "Returns the new snapshot metadata and record counts."
    ),
)
async def force_refresh_snapshot() -> SnapshotRefreshResponse:
    """POST /api/live/snapshot/refresh"""
    from datetime import datetime, timezone

    try:
        bundle = await live_snapshot_service.force_refresh_all()

        sources_refreshed = []
        total_records = 0

        if bundle.incidents_available:
            sources_refreshed.append("incidents")
            total_records += len(bundle.incidents)
        if bundle.traffic_available:
            sources_refreshed.append("traffic")
            total_records += len(bundle.traffic_points)
        if bundle.weather_available:
            sources_refreshed.append("weather")
            total_records += 1

        sources_failed = [
            s for s in ["incidents", "traffic", "weather"]
            if s not in sources_refreshed
        ]

        logger.info(
            "Force refresh complete: %s refreshed, %d total records.",
            ", ".join(sources_refreshed), total_records,
        )

        return SnapshotRefreshResponse(
            refreshed_at=datetime.now(tz=timezone.utc),
            sources_refreshed=sources_refreshed,
            sources_skipped=sources_failed,
            total_records=total_records,
        )
    except Exception as exc:
        logger.error("Force refresh failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SNAPSHOT_REFRESH_ERROR", "message": str(exc)},
        )
