"""
backend/app/services/live_snapshot_service.py
Module 7.5 — Bengaluru-wide Live Data Snapshot Collection Service.

Responsibilities:
  1. Evaluate freshness for each source independently (incidents, traffic, weather).
  2. Refresh only stale/missing sources — never re-fetch a fresh source.
  3. Persist new snapshots to Supabase PostgreSQL + PostGIS.
  4. Return a SnapshotBundle to the Module 7 feature pipeline.
  5. Protect against concurrent duplicate refreshes via asyncio.Lock.
  6. Fall back to local JSON files when Supabase is not configured (dev only).

CRITICAL DATA QUALITY RULE:
  A failed API call is NEVER stored as an empty dataset.
  SnapshotStatus.FAILED means the API was unreachable — no rows are inserted.
  SnapshotStatus.OK with record_count=0 means the API responded: zero results found.

CONCURRENCY:
  asyncio.Lock() prevents duplicate refresh calls when multiple users
  hit /api/features/analyze at the same moment and all find stale data.
  Only the first coroutine fetches; others wait and reuse the result.
  NOTE: Single-process uvicorn only. For multi-worker deploys, replace
  with a Postgres advisory lock via supabase.rpc().

TRAFFIC GRID:
  TomTom Traffic Flow API works per-point (not bbox). We query a fixed
  15-point grid covering Bengaluru's major corridors. This gives city-wide
  coverage without querying every road segment.

BENGALURU INCIDENT BBOX:
  (77.30, 12.70, 77.90, 13.30) — matches settings.blr_lon_min/max etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict

import httpx

from app.config.settings import get_settings
from app.db.supabase_client import get_supabase
from app.schemas.snapshot import (
    LiveDataSnapshotRow,
    IncidentObservationRow,
    TrafficObservationRow,
    WeatherObservationRow,
    SnapshotBundle,
    SnapshotSource,
    SnapshotStatus,
    SourceStatus,
    SnapshotStatusResponse,
    SnapshotLatestResponse,
)
from app.schemas.incident import Incident
from app.schemas.traffic import TrafficSegment
from app.schemas.weather import WeatherResponse
from app.services.tomtom_service import get_incidents, fetch_traffic_for_point
from app.services.weather_service import get_current_weather

logger = logging.getLogger(__name__)

# ── Bengaluru-wide traffic reference grid ──────────────────────────────────────
# 15 representative points covering major Bengaluru corridors.
# TomTom Flow API is queried at each point concurrently.
BENGALURU_TRAFFIC_GRID: List[tuple[float, float]] = [
    (12.9716, 77.5946),   # City Centre (MG Road)
    (12.9784, 77.6408),   # Indiranagar
    (12.9279, 77.6271),   # Koramangala
    (12.9165, 77.6101),   # BTM Layout
    (12.9116, 77.6389),   # HSR Layout
    (12.9591, 77.6971),   # Marathahalli
    (12.9698, 77.7499),   # Whitefield
    (13.0043, 77.6991),   # KR Puram
    (13.0358, 77.5970),   # Hebbal
    (13.1005, 77.5963),   # Yelahanka
    (13.0241, 77.5437),   # Yeshwanthpur
    (12.9250, 77.5938),   # Jayanagar
    (12.8383, 77.6768),   # Electronic City
    (12.8681, 77.5970),   # Bannerghatta Road
    (12.8560, 77.7878),   # Sarjapur
]

# ── Bengaluru-wide incident bounding box ──────────────────────────────────────
BENGALURU_BBOX = (77.30, 12.70, 77.90, 13.30)  # (min_lon, min_lat, max_lon, max_lat)


class LiveSnapshotService:
    """
    Manages Bengaluru-wide live data snapshots.

    Usage (in FastAPI route):
        bundle = await live_snapshot_service.get_or_refresh()
        # Pass bundle to Module 7 pipeline instead of re-fetching APIs.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # In-memory cache of the latest bundle (avoids DB round-trip
        # for requests that arrive within the same second)
        self._cached_bundle: Optional[SnapshotBundle] = None
        self._cached_at: Optional[datetime] = None

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def get_or_refresh(self) -> SnapshotBundle:
        """
        Return a SnapshotBundle, refreshing only stale sources.

        This is the primary entry point called by the Module 7 feature pipeline.
        Protected by asyncio.Lock() to prevent concurrent duplicate refreshes.

        Structured logging output per request:
            LIVE SNAPSHOT
            Traffic:   FRESH (2.1 min)
            Incidents: FRESH (3.4 min)
            Weather:   STALE (18.2 min)
            Action: Refresh weather only
            Snapshot ID: <uuid>
        """
        async with self._lock:
            settings = get_settings()
            now = datetime.now(tz=timezone.utc)

            # Check freshness for each source independently
            incident_status = await self._get_source_status(SnapshotSource.INCIDENTS)
            traffic_status  = await self._get_source_status(SnapshotSource.TRAFFIC)
            weather_status  = await self._get_source_status(SnapshotSource.WEATHER)

            incident_fresh = self._is_fresh(incident_status, settings.snapshot_incident_freshness_minutes)
            traffic_fresh  = self._is_fresh(traffic_status,  settings.snapshot_traffic_freshness_minutes)
            weather_fresh  = self._is_fresh(weather_status,  settings.snapshot_weather_freshness_minutes)

            # Log freshness report
            self._log_freshness_report(
                incident_status, traffic_status, weather_status,
                incident_fresh, traffic_fresh, weather_fresh,
            )

            # Determine action
            stale_sources = []
            if not incident_fresh: stale_sources.append("incidents")
            if not traffic_fresh:  stale_sources.append("traffic")
            if not weather_fresh:  stale_sources.append("weather")

            if not stale_sources:
                logger.info("LIVE SNAPSHOT — All sources FRESH. Reusing existing snapshots.")
                return await self._build_bundle_from_db(incident_status, traffic_status, weather_status)

            logger.info("LIVE SNAPSHOT — Refreshing: %s", ", ".join(stale_sources))

            # Refresh stale sources concurrently
            refresh_tasks = {}
            if not incident_fresh: refresh_tasks["incidents"] = self._refresh_incidents()
            if not traffic_fresh:  refresh_tasks["traffic"]   = self._refresh_traffic()
            if not weather_fresh:  refresh_tasks["weather"]   = self._refresh_weather()

            results = await asyncio.gather(*refresh_tasks.values(), return_exceptions=True)
            refreshed: Dict[str, SnapshotBundle] = {}
            for key, result in zip(refresh_tasks.keys(), results):
                if isinstance(result, Exception):
                    logger.error("Refresh failed for %s: %s", key, result)
                else:
                    refreshed[key] = result

            # Build and return bundle using fresh + newly-fetched data
            return await self._merge_into_bundle(
                incident_status=incident_status if incident_fresh else refreshed.get("incidents"),
                traffic_status=traffic_status   if traffic_fresh  else refreshed.get("traffic"),
                weather_status=weather_status   if weather_fresh  else refreshed.get("weather"),
            )

    async def get_status(self) -> SnapshotStatusResponse:
        """Return current freshness status of all sources (no refresh)."""
        settings = get_settings()
        now = datetime.now(tz=timezone.utc)

        incident_status = await self._get_source_status(SnapshotSource.INCIDENTS)
        traffic_status  = await self._get_source_status(SnapshotSource.TRAFFIC)
        weather_status  = await self._get_source_status(SnapshotSource.WEATHER)

        incident_fresh = self._is_fresh(incident_status, settings.snapshot_incident_freshness_minutes)
        traffic_fresh  = self._is_fresh(traffic_status,  settings.snapshot_traffic_freshness_minutes)
        weather_fresh  = self._is_fresh(weather_status,  settings.snapshot_weather_freshness_minutes)

        supabase = await get_supabase()

        return SnapshotStatusResponse(
            checked_at=now,
            sources={
                "incidents": incident_status,
                "traffic":   traffic_status,
                "weather":   weather_status,
            },
            all_fresh=all([incident_fresh, traffic_fresh, weather_fresh]),
            supabase_connected=(supabase is not None),
        )

    async def get_latest(self) -> SnapshotLatestResponse:
        """Return latest snapshot metadata per source (no data, no refresh)."""
        return SnapshotLatestResponse(
            incident_snapshot=await self._get_source_status(SnapshotSource.INCIDENTS),
            traffic_snapshot= await self._get_source_status(SnapshotSource.TRAFFIC),
            weather_snapshot= await self._get_source_status(SnapshotSource.WEATHER),
        )

    async def force_refresh_all(self) -> SnapshotBundle:
        """Force-refresh all sources regardless of freshness (admin endpoint)."""
        async with self._lock:
            logger.info("LIVE SNAPSHOT — Force refresh all sources requested.")
            results = await asyncio.gather(
                self._refresh_incidents(),
                self._refresh_traffic(),
                self._refresh_weather(),
                return_exceptions=True,
            )
            inc, trx, wth = results
            return await self._merge_into_bundle(
                incident_status=inc if not isinstance(inc, Exception) else None,
                traffic_status= trx if not isinstance(trx, Exception) else None,
                weather_status= wth if not isinstance(wth, Exception) else None,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Freshness logic
    # ──────────────────────────────────────────────────────────────────────────

    def _is_fresh(self, status: Optional[SourceStatus], window_minutes: int) -> bool:
        """True if the snapshot is not None and within the freshness window."""
        if status is None or status.collected_at is None:
            return False
        if status.status == SnapshotStatus.FAILED:
            return False  # Failed snapshots are never considered fresh
        now = datetime.now(tz=timezone.utc)
        age = (now - status.collected_at).total_seconds() / 60
        return age <= window_minutes

    # ──────────────────────────────────────────────────────────────────────────
    # Database: read latest snapshot per source
    # ──────────────────────────────────────────────────────────────────────────

    async def _get_source_status(self, source: SnapshotSource) -> Optional[SourceStatus]:
        """
        Query Supabase for the latest non-failed snapshot for the given source.
        Falls back to local file lookup if Supabase is not configured.
        """
        supabase = await get_supabase()

        if supabase:
            return await self._db_get_source_status(supabase, source)
        else:
            return await self._file_get_source_status(source)

    async def _db_get_source_status(self, supabase, source: SnapshotSource) -> Optional[SourceStatus]:
        try:
            result = await (
                supabase.table("live_data_snapshots")
                .select("snapshot_id, collected_at, status, record_count, error_message")
                .eq("source", source.value)
                .neq("status", "failed")
                .order("collected_at", desc=True)
                .limit(1)
                .execute()
            )
            if not result.data:
                return SourceStatus(source=source)

            row = result.data[0]
            collected_at = datetime.fromisoformat(row["collected_at"])
            # Ensure timezone-aware
            if collected_at.tzinfo is None:
                collected_at = collected_at.replace(tzinfo=timezone.utc)

            age = (datetime.now(tz=timezone.utc) - collected_at).total_seconds() / 60

            return SourceStatus(
                source=source,
                snapshot_id=row["snapshot_id"],
                collected_at=collected_at,
                age_minutes=round(age, 1),
                is_fresh=False,  # caller decides based on window
                record_count=row["record_count"],
                status=SnapshotStatus(row["status"]),
            )
        except Exception as exc:
            logger.error("DB read failed for source %s: %s", source.value, exc)
            return SourceStatus(source=source, error=str(exc))

    # ──────────────────────────────────────────────────────────────────────────
    # Refresh: fetch live data from APIs
    # ──────────────────────────────────────────────────────────────────────────

    async def _refresh_incidents(self) -> Optional[SnapshotBundle]:
        """Fetch Bengaluru-wide incidents from TomTom and persist to Supabase."""
        now = datetime.now(tz=timezone.utc)
        snapshot_id = str(uuid.uuid4())

        try:
            incidents: List[Incident] = await get_incidents(BENGALURU_BBOX)
            logger.info(
                "LIVE SNAPSHOT — Incidents: fetched %d from Bengaluru-wide bbox.",
                len(incidents),
            )
        except Exception as exc:
            logger.error("LIVE SNAPSHOT — Incidents API failed: %s", exc)
            await self._persist_snapshot_row(
                snapshot_id=snapshot_id,
                source=SnapshotSource.INCIDENTS,
                collected_at=now,
                status=SnapshotStatus.FAILED,
                record_count=0,
                error=str(exc),
            )
            return SnapshotBundle(
                incident_snapshot_id=snapshot_id,
                incidents=[],
                incidents_available=False,
            )

        # Persist snapshot row first
        await self._persist_snapshot_row(
            snapshot_id=snapshot_id,
            source=SnapshotSource.INCIDENTS,
            collected_at=now,
            status=SnapshotStatus.OK,
            record_count=len(incidents),
        )

        # Persist individual observations
        if incidents:
            rows = [
                IncidentObservationRow(
                    snapshot_id=snapshot_id,
                    external_id=inc.id,
                    incident_type=inc.type,
                    icon_category=inc.icon_category,
                    magnitude_of_delay=inc.magnitude_of_delay,
                    latitude=inc.latitude,
                    longitude=inc.longitude,
                    description=inc.description or None,
                    road_name=inc.road_name,
                    from_location=inc.from_location,
                    to_location=inc.to_location,
                    length_meters=inc.length_meters,
                    delay_seconds=inc.delay_seconds,
                    start_time=inc.start_time,
                    end_time=inc.end_time,
                    time_validity=inc.time_validity,
                    number_of_reports=inc.number_of_reports,
                    last_report_time=inc.last_report_time,
                )
                for inc in incidents
            ]
            await self._batch_insert("incident_observations", [r.to_db_dict() for r in rows])

        return SnapshotBundle(
            incident_snapshot_id=snapshot_id,
            incidents=incidents,
            incidents_available=True,
        )

    async def _refresh_traffic(self) -> Optional[SnapshotBundle]:
        """Fetch traffic flow for the Bengaluru grid and persist to Supabase."""
        now = datetime.now(tz=timezone.utc)
        snapshot_id = str(uuid.uuid4())
        settings = get_settings()

        if not settings.tomtom_api_key:
            logger.warning("LIVE SNAPSHOT — Traffic: TOMTOM_API_KEY not set.")
            await self._persist_snapshot_row(
                snapshot_id=snapshot_id, source=SnapshotSource.TRAFFIC,
                collected_at=now, status=SnapshotStatus.FAILED,
                record_count=0, error="TOMTOM_API_KEY not configured",
            )
            return SnapshotBundle(traffic_snapshot_id=snapshot_id, traffic_points=[], traffic_available=False)

        traffic_segments: List[TrafficSegment] = []
        try:
            async with httpx.AsyncClient() as client:
                tasks = [
                    fetch_traffic_for_point(client, lat, lon, settings.tomtom_api_key)
                    for lat, lon in BENGALURU_TRAFFIC_GRID
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning("Traffic point %d failed: %s", i, result)
                else:
                    traffic_segments.append(result)

            logger.info(
                "LIVE SNAPSHOT — Traffic: fetched %d/%d grid points.",
                len(traffic_segments), len(BENGALURU_TRAFFIC_GRID),
            )
        except Exception as exc:
            logger.error("LIVE SNAPSHOT — Traffic fetch error: %s", exc)
            await self._persist_snapshot_row(
                snapshot_id=snapshot_id, source=SnapshotSource.TRAFFIC,
                collected_at=now, status=SnapshotStatus.FAILED,
                record_count=0, error=str(exc),
            )
            return SnapshotBundle(traffic_snapshot_id=snapshot_id, traffic_points=[], traffic_available=False)

        status = SnapshotStatus.OK if len(traffic_segments) == len(BENGALURU_TRAFFIC_GRID) else SnapshotStatus.PARTIAL

        await self._persist_snapshot_row(
            snapshot_id=snapshot_id, source=SnapshotSource.TRAFFIC,
            collected_at=now, status=status, record_count=len(traffic_segments),
        )

        if traffic_segments:
            rows = [
                TrafficObservationRow(
                    snapshot_id=snapshot_id,
                    latitude=seg.latitude,
                    longitude=seg.longitude,
                    current_speed=seg.current_speed,
                    free_flow_speed=seg.free_flow_speed,
                    current_travel_time=seg.current_travel_time,
                    free_flow_travel_time=seg.free_flow_travel_time,
                    confidence=seg.confidence,
                    congestion_ratio=seg.congestion_ratio,
                    delay_seconds=seg.delay_seconds,
                    road_closure=seg.road_closure or False,
                )
                for seg in traffic_segments
                if seg.latitude and seg.longitude
            ]
            await self._batch_insert("traffic_observations", [r.to_db_dict() for r in rows])

        return SnapshotBundle(
            traffic_snapshot_id=snapshot_id,
            traffic_points=traffic_segments,
            traffic_available=True,
        )

    async def _refresh_weather(self) -> Optional[SnapshotBundle]:
        """Fetch weather at Bengaluru city center and persist to Supabase."""
        now = datetime.now(tz=timezone.utc)
        snapshot_id = str(uuid.uuid4())
        settings = get_settings()

        lat, lon = settings.bengaluru_center_lat, settings.bengaluru_center_lon

        weather_resp: WeatherResponse = await get_current_weather(lat, lon)

        if not weather_resp.available or weather_resp.weather is None:
            err = weather_resp.error or "Unknown weather error"
            logger.error("LIVE SNAPSHOT — Weather API failed: %s", err)
            await self._persist_snapshot_row(
                snapshot_id=snapshot_id, source=SnapshotSource.WEATHER,
                collected_at=now, status=SnapshotStatus.FAILED,
                record_count=0, error=err,
            )
            return SnapshotBundle(weather_snapshot_id=snapshot_id, weather=None, weather_available=False)

        w = weather_resp.weather

        await self._persist_snapshot_row(
            snapshot_id=snapshot_id, source=SnapshotSource.WEATHER,
            collected_at=now, status=SnapshotStatus.OK, record_count=1,
        )

        row = WeatherObservationRow(
            snapshot_id=snapshot_id,
            latitude=lat,
            longitude=lon,
            temperature_c=w.temperature_c,
            feels_like_c=w.feels_like_c,
            humidity_percent=w.humidity_percent,
            pressure_hpa=w.pressure_hpa,
            visibility_m=w.visibility_m,
            wind_speed_ms=w.wind_speed_ms,
            wind_gust_ms=w.wind_gust_ms,
            wind_direction_deg=w.wind_direction_deg,
            cloudiness_percent=w.cloudiness_percent,
            weather_id=w.weather.id if w.weather else None,
            weather_main=w.weather.main if w.weather else None,
            weather_description=w.weather.description if w.weather else None,
            rain_1h_mm=w.rain_1h_mm,
            snow_1h_mm=w.snow_1h_mm,
            collected_at=now,
        )
        await self._batch_insert("weather_observations", [row.to_db_dict()])

        logger.info(
            "LIVE SNAPSHOT — Weather: %s, %.1f°C, rain=%.2fmm",
            w.weather.description if w.weather else "N/A",
            w.temperature_c or 0,
            w.rain_1h_mm,
        )

        return SnapshotBundle(
            weather_snapshot_id=snapshot_id,
            weather=weather_resp,
            weather_available=True,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Database: persist snapshot row
    # ──────────────────────────────────────────────────────────────────────────

    async def _persist_snapshot_row(
        self,
        snapshot_id: str,
        source: SnapshotSource,
        collected_at: datetime,
        status: SnapshotStatus,
        record_count: int,
        error: Optional[str] = None,
    ) -> None:
        row = LiveDataSnapshotRow(
            snapshot_id=snapshot_id,
            collected_at=collected_at,
            source=source,
            status=status,
            record_count=record_count,
            error_message=error,
        )
        supabase = await get_supabase()
        if supabase:
            try:
                await supabase.table("live_data_snapshots").insert(row.to_db_dict()).execute()
                logger.debug("Persisted snapshot row: %s / %s", source.value, snapshot_id)
            except Exception as exc:
                logger.error("Failed to persist snapshot row: %s", exc)
        else:
            await self._file_persist_snapshot(row)

    async def _batch_insert(self, table: str, rows: List[dict]) -> None:
        """Insert a batch of rows into a Supabase table."""
        if not rows:
            return
        supabase = await get_supabase()
        if supabase:
            try:
                # Insert in chunks to avoid request size limits
                chunk_size = 100
                for i in range(0, len(rows), chunk_size):
                    chunk = rows[i:i + chunk_size]
                    await supabase.table(table).insert(chunk).execute()
                logger.debug("Inserted %d rows into %s.", len(rows), table)
            except Exception as exc:
                logger.error("Batch insert failed for %s: %s", table, exc)
        else:
            await self._file_persist_observations(table, rows)

    async def _build_bundle_from_db(
        self,
        incident_status: Optional[SourceStatus],
        traffic_status:  Optional[SourceStatus],
        weather_status:  Optional[SourceStatus],
    ) -> SnapshotBundle:
        """
        Build a SnapshotBundle from existing DB snapshots (all-fresh case).
        Fetches only the observation data needed by Module 7.
        """
        bundle = SnapshotBundle(
            incident_snapshot_id=incident_status.snapshot_id if incident_status else None,
            traffic_snapshot_id= traffic_status.snapshot_id  if traffic_status  else None,
            weather_snapshot_id= weather_status.snapshot_id  if weather_status  else None,
            source_status={
                "incidents": incident_status or SourceStatus(source=SnapshotSource.INCIDENTS),
                "traffic":   traffic_status  or SourceStatus(source=SnapshotSource.TRAFFIC),
                "weather":   weather_status  or SourceStatus(source=SnapshotSource.WEATHER),
            },
        )

        supabase = await get_supabase()
        if not supabase:
            # For local dev without DB, just return empty bundle — data was never persisted
            return bundle

        # Load incidents from DB
        if incident_status and incident_status.snapshot_id:
            try:
                result = await (
                    supabase.table("incident_observations")
                    .select("*")
                    .eq("snapshot_id", incident_status.snapshot_id)
                    .execute()
                )
                bundle.incidents = [_row_to_incident(row) for row in result.data]
                bundle.incidents_available = True
                logger.info(
                    "LIVE SNAPSHOT — Incidents REUSED from snapshot %s (%d records).",
                    incident_status.snapshot_id[:8], len(bundle.incidents),
                )
            except Exception as exc:
                logger.warning("Failed to load incidents from DB: %s", exc)

        # Load weather from DB
        if weather_status and weather_status.snapshot_id:
            try:
                result = await (
                    supabase.table("weather_observations")
                    .select("*")
                    .eq("snapshot_id", weather_status.snapshot_id)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    bundle.weather = _row_to_weather_response(result.data[0])
                    bundle.weather_available = True
                    logger.info(
                        "LIVE SNAPSHOT — Weather REUSED from snapshot %s.",
                        weather_status.snapshot_id[:8],
                    )
            except Exception as exc:
                logger.warning("Failed to load weather from DB: %s", exc)

        return bundle

    async def _merge_into_bundle(
        self,
        incident_status,
        traffic_status,
        weather_status,
    ) -> SnapshotBundle:
        """Merge freshly-fetched and reused data into a single SnapshotBundle."""
        # Determine what each arg is (could be SnapshotBundle from refresh or SourceStatus from reuse)
        bundle = SnapshotBundle()

        # Incidents
        if isinstance(incident_status, SnapshotBundle):
            bundle.incident_snapshot_id = incident_status.incident_snapshot_id
            bundle.incidents = incident_status.incidents
            bundle.incidents_available = incident_status.incidents_available
        elif isinstance(incident_status, SourceStatus) and incident_status:
            sub = await self._build_bundle_from_db(incident_status, None, None)
            bundle.incident_snapshot_id = sub.incident_snapshot_id
            bundle.incidents = sub.incidents
            bundle.incidents_available = sub.incidents_available

        # Traffic
        if isinstance(traffic_status, SnapshotBundle):
            bundle.traffic_snapshot_id = traffic_status.traffic_snapshot_id
            bundle.traffic_points = traffic_status.traffic_points
            bundle.traffic_available = traffic_status.traffic_available
        elif isinstance(traffic_status, SourceStatus) and traffic_status:
            bundle.traffic_snapshot_id = traffic_status.snapshot_id
            bundle.traffic_available = True  # Data was in DB but not loaded (traffic not used by M7 directly)

        # Weather
        if isinstance(weather_status, SnapshotBundle):
            bundle.weather_snapshot_id = weather_status.weather_snapshot_id
            bundle.weather = weather_status.weather
            bundle.weather_available = weather_status.weather_available
        elif isinstance(weather_status, SourceStatus) and weather_status:
            sub = await self._build_bundle_from_db(None, None, weather_status)
            bundle.weather_snapshot_id = sub.weather_snapshot_id
            bundle.weather = sub.weather
            bundle.weather_available = sub.weather_available

        return bundle

    # ──────────────────────────────────────────────────────────────────────────
    # Route request recording
    # ──────────────────────────────────────────────────────────────────────────

    async def record_route_request(
        self,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        bundle: SnapshotBundle,
    ) -> Optional[str]:
        """
        Record an S→D route request with the snapshot IDs used.
        Returns the request_id UUID.
        """
        from app.schemas.snapshot import RouteRequestRow
        now = datetime.now(tz=timezone.utc)
        request_id = str(uuid.uuid4())

        row = RouteRequestRow(
            request_id=request_id,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
            requested_at=now,
            incident_snapshot_id=bundle.incident_snapshot_id,
            traffic_snapshot_id=bundle.traffic_snapshot_id,
            weather_snapshot_id=bundle.weather_snapshot_id,
        )

        supabase = await get_supabase()
        if supabase:
            try:
                await supabase.table("route_requests").insert(row.to_db_dict()).execute()
                logger.debug("Route request recorded: %s", request_id)
            except Exception as exc:
                logger.warning("Failed to record route request: %s", exc)

        return request_id

    # ──────────────────────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────────────────────

    def _log_freshness_report(
        self,
        inc: Optional[SourceStatus], trx: Optional[SourceStatus], wth: Optional[SourceStatus],
        inc_fresh: bool, trx_fresh: bool, wth_fresh: bool,
    ) -> None:
        def _fmt(status, fresh):
            if status is None or status.collected_at is None:
                return "MISSING"
            age = status.age_minutes or 0
            return f"{'FRESH' if fresh else 'STALE'} ({age:.1f} min)"

        logger.info(
            "LIVE SNAPSHOT\n"
            "  Traffic:   %s\n"
            "  Incidents: %s\n"
            "  Weather:   %s",
            _fmt(trx, trx_fresh),
            _fmt(inc, inc_fresh),
            _fmt(wth, wth_fresh),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Local file fallback (dev only — no Supabase configured)
    # ──────────────────────────────────────────────────────────────────────────

    async def _file_get_source_status(self, source: SnapshotSource) -> Optional[SourceStatus]:
        settings = get_settings()
        meta_dir = Path(settings.snapshot_dir) / "meta"
        meta_file = meta_dir / f"{source.value}_meta.json"

        if not meta_file.exists():
            return SourceStatus(source=source)

        try:
            data = json.loads(meta_file.read_text())
            collected_at = datetime.fromisoformat(data["collected_at"])
            if collected_at.tzinfo is None:
                collected_at = collected_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(tz=timezone.utc) - collected_at).total_seconds() / 60
            return SourceStatus(
                source=source,
                snapshot_id=data.get("snapshot_id"),
                collected_at=collected_at,
                age_minutes=round(age, 1),
                record_count=data.get("record_count", 0),
                status=SnapshotStatus(data.get("status", "ok")),
            )
        except Exception as exc:
            logger.warning("File meta read failed for %s: %s", source.value, exc)
            return SourceStatus(source=source, error=str(exc))

    async def _file_persist_snapshot(self, row: LiveDataSnapshotRow) -> None:
        settings = get_settings()
        meta_dir = Path(settings.snapshot_dir) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / f"{row.source.value}_meta.json"
        meta_file.write_text(json.dumps({
            "snapshot_id": row.snapshot_id,
            "collected_at": row.collected_at.isoformat(),
            "status": row.status.value,
            "record_count": row.record_count,
            "error_message": row.error_message,
        }, indent=2))

    async def _file_persist_observations(self, table: str, rows: List[dict]) -> None:
        settings = get_settings()
        obs_dir = Path(settings.snapshot_dir) / table
        obs_dir.mkdir(parents=True, exist_ok=True)
        fname = obs_dir / f"{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        fname.write_text(json.dumps(rows, indent=2, default=str))


# ── Helper converters: DB row → domain object ──────────────────────────────────

def _row_to_incident(row: dict) -> Incident:
    """Convert a Supabase incident_observations row back to an Incident schema."""
    return Incident(
        id=row.get("external_id") or row.get("id", "unknown"),
        type=row.get("incident_type", "Unknown"),
        description=row.get("description", ""),
        latitude=row["latitude"],
        longitude=row["longitude"],
        icon_category=row.get("icon_category"),
        magnitude_of_delay=row.get("magnitude_of_delay"),
        delay_seconds=row.get("delay_seconds"),
        road_name=row.get("road_name"),
        from_location=row.get("from_location"),
        to_location=row.get("to_location"),
        length_meters=row.get("length_meters"),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        time_validity=row.get("time_validity"),
        number_of_reports=row.get("number_of_reports"),
        last_report_time=row.get("last_report_time"),
    )


def _row_to_weather_response(row: dict) -> WeatherResponse:
    """Convert a Supabase weather_observations row back to a WeatherResponse."""
    from app.schemas.weather import WeatherData, WeatherCondition, WeatherLocation, WeatherResponse

    condition = None
    if row.get("weather_id"):
        condition = WeatherCondition(
            id=row["weather_id"],
            main=row.get("weather_main", ""),
            description=row.get("weather_description", ""),
        )

    weather_data = WeatherData(
        temperature_c=row.get("temperature_c"),
        feels_like_c=row.get("feels_like_c"),
        humidity_percent=row.get("humidity_percent"),
        pressure_hpa=row.get("pressure_hpa"),
        visibility_m=row.get("visibility_m"),
        wind_speed_ms=row.get("wind_speed_ms"),
        wind_gust_ms=row.get("wind_gust_ms"),
        wind_direction_deg=row.get("wind_direction_deg"),
        cloudiness_percent=row.get("cloudiness_percent"),
        weather=condition,
        rain_1h_mm=row.get("rain_1h_mm", 0.0),
        snow_1h_mm=row.get("snow_1h_mm", 0.0),
    )

    return WeatherResponse(
        available=True,
        location=WeatherLocation(latitude=row["latitude"], longitude=row["longitude"]),
        weather=weather_data,
    )


# ── Module-level singleton ─────────────────────────────────────────────────────
live_snapshot_service = LiveSnapshotService()
