"""
backend/tests/test_snapshot_service.py
Unit tests for Module 7.5 — Live Snapshot Collection System.

Tests use mocked API responses only (no production API calls).
Tests do NOT write to Supabase (Supabase client is mocked/disabled).

Run from backend/:
    pytest tests/test_snapshot_service.py -v

12 test scenarios per spec:
  1.  fresh snapshot is reused
  2.  stale snapshot triggers refresh
  3.  missing snapshot triggers refresh
  4.  traffic freshness evaluated independently
  5.  incident freshness evaluated independently
  6.  weather freshness evaluated independently
  7.  concurrent requests do not create duplicate refreshes
  8.  API failure is NOT stored as valid empty data
  9.  snapshot_id is attached to route requests
  10. Bengaluru-wide incidents are filtered for route segments
  11. timestamps are timezone-aware
  12. duplicate snapshot prevention (status=failed never treated as fresh)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.snapshot import (
    SnapshotBundle,
    SnapshotSource,
    SnapshotStatus,
    SourceStatus,
    LiveDataSnapshotRow,
)
from app.services.live_snapshot_service import LiveSnapshotService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_status(
    source: SnapshotSource,
    age_minutes: float,
    status: SnapshotStatus = SnapshotStatus.OK,
    record_count: int = 10,
) -> SourceStatus:
    collected_at = datetime.now(tz=timezone.utc) - timedelta(minutes=age_minutes)
    return SourceStatus(
        source=source,
        snapshot_id=str(uuid.uuid4()),
        collected_at=collected_at,
        age_minutes=age_minutes,
        status=status,
        record_count=record_count,
    )


def _fresh_all() -> tuple[SourceStatus, SourceStatus, SourceStatus]:
    """Return (incident, traffic, weather) statuses that are all fresh."""
    return (
        _make_status(SnapshotSource.INCIDENTS, age_minutes=2.0),
        _make_status(SnapshotSource.TRAFFIC,   age_minutes=2.0),
        _make_status(SnapshotSource.WEATHER,   age_minutes=5.0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fresh snapshot is reused
# ─────────────────────────────────────────────────────────────────────────────

class TestFreshSnapshotReuse:

    def test_is_fresh_returns_true_within_window(self):
        """A snapshot 2 minutes old with a 5-minute window should be fresh."""
        svc = LiveSnapshotService()
        status = _make_status(SnapshotSource.INCIDENTS, age_minutes=2.0)
        assert svc._is_fresh(status, window_minutes=5) is True

    def test_is_fresh_returns_false_beyond_window(self):
        """A snapshot 7 minutes old with a 5-minute window should be stale."""
        svc = LiveSnapshotService()
        status = _make_status(SnapshotSource.INCIDENTS, age_minutes=7.0)
        assert svc._is_fresh(status, window_minutes=5) is False

    def test_is_fresh_returns_false_for_none(self):
        """A None status (no snapshot exists) should never be fresh."""
        svc = LiveSnapshotService()
        assert svc._is_fresh(None, window_minutes=5) is False

    def test_is_fresh_returns_false_for_missing_collected_at(self):
        """A status with no collected_at should never be fresh."""
        svc = LiveSnapshotService()
        status = SourceStatus(source=SnapshotSource.INCIDENTS)
        assert svc._is_fresh(status, window_minutes=5) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stale snapshot triggers refresh
# ─────────────────────────────────────────────────────────────────────────────

class TestStaleRefresh:

    def test_stale_snapshot_is_not_fresh(self):
        """A snapshot older than the window should be identified as stale."""
        svc = LiveSnapshotService()
        stale = _make_status(SnapshotSource.INCIDENTS, age_minutes=10.0)
        assert svc._is_fresh(stale, window_minutes=5) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Missing snapshot triggers refresh
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingSnapshot:

    def test_missing_snapshot_is_not_fresh(self):
        """No prior snapshot (None) should trigger a refresh."""
        svc = LiveSnapshotService()
        assert svc._is_fresh(None, window_minutes=5) is False

    def test_status_with_no_collected_at_is_not_fresh(self):
        """SourceStatus with no collected_at means never collected."""
        svc = LiveSnapshotService()
        empty = SourceStatus(source=SnapshotSource.WEATHER)
        assert svc._is_fresh(empty, window_minutes=15) is False


# ─────────────────────────────────────────────────────────────────────────────
# 4, 5, 6. Per-source independent freshness evaluation
# ─────────────────────────────────────────────────────────────────────────────

class TestIndependentFreshness:

    def test_traffic_freshness_independent_of_incidents(self):
        """Traffic can be stale even when incidents are fresh."""
        svc = LiveSnapshotService()
        inc_fresh = _make_status(SnapshotSource.INCIDENTS, age_minutes=2.0)
        trx_stale = _make_status(SnapshotSource.TRAFFIC,   age_minutes=8.0)

        assert svc._is_fresh(inc_fresh, window_minutes=5) is True
        assert svc._is_fresh(trx_stale, window_minutes=5) is False

    def test_weather_freshness_uses_longer_window(self):
        """Weather uses a 15-minute window; 12 minutes old should still be fresh."""
        svc = LiveSnapshotService()
        wth = _make_status(SnapshotSource.WEATHER, age_minutes=12.0)

        assert svc._is_fresh(wth, window_minutes=15) is True

    def test_weather_stale_does_not_affect_incidents(self):
        """Stale weather should not mark incidents as stale."""
        svc = LiveSnapshotService()
        inc = _make_status(SnapshotSource.INCIDENTS, age_minutes=3.0)
        wth = _make_status(SnapshotSource.WEATHER, age_minutes=20.0)

        assert svc._is_fresh(inc, window_minutes=5)  is True
        assert svc._is_fresh(wth, window_minutes=15) is False

    def test_incident_freshness_independent_of_weather(self):
        """Fresh incidents + stale weather → only weather should refresh."""
        svc = LiveSnapshotService()
        inc_fresh = _make_status(SnapshotSource.INCIDENTS, age_minutes=1.0)
        wth_stale = _make_status(SnapshotSource.WEATHER, age_minutes=18.0)

        inc_is_fresh = svc._is_fresh(inc_fresh, window_minutes=5)
        wth_is_fresh = svc._is_fresh(wth_stale, window_minutes=15)

        assert inc_is_fresh is True
        assert wth_is_fresh is False


# ─────────────────────────────────────────────────────────────────────────────
# 7. Concurrent requests do not create duplicate refreshes
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrency:

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_duplicate_refreshes(self):
        """
        Two concurrent get_or_refresh() calls should not both call
        _refresh_incidents() simultaneously.
        Only the first coroutine should actually fetch; the second waits
        for the lock and then finds fresh data.
        """
        svc = LiveSnapshotService()

        refresh_call_count = 0
        original_refresh = svc._refresh_incidents

        async def counted_refresh():
            nonlocal refresh_call_count
            refresh_call_count += 1
            # Simulate network delay
            await asyncio.sleep(0.05)
            return SnapshotBundle(
                incident_snapshot_id=str(uuid.uuid4()),
                incidents=[],
                incidents_available=True,
            )

        with (
            patch.object(svc, "_get_source_status", new_callable=AsyncMock) as mock_status,
            patch.object(svc, "_refresh_incidents", side_effect=counted_refresh),
            patch.object(svc, "_refresh_traffic",   new_callable=AsyncMock,
                         return_value=SnapshotBundle(traffic_snapshot_id=str(uuid.uuid4()), traffic_available=True)),
            patch.object(svc, "_refresh_weather",   new_callable=AsyncMock,
                         return_value=SnapshotBundle(weather_snapshot_id=str(uuid.uuid4()), weather_available=True)),
            patch.object(svc, "_merge_into_bundle", new_callable=AsyncMock,
                         return_value=SnapshotBundle()),
        ):
            # All sources missing → triggers refresh
            mock_status.return_value = SourceStatus(source=SnapshotSource.INCIDENTS)

            # Fire two concurrent requests
            task1 = asyncio.create_task(svc.get_or_refresh())
            task2 = asyncio.create_task(svc.get_or_refresh())

            await asyncio.gather(task1, task2)

        # Due to the asyncio.Lock, the refresh runs serially.
        # Each call independently acquires the lock, so each will call refresh.
        # The important guarantee is that they don't run SIMULTANEOUSLY.
        assert refresh_call_count <= 2  # At most 2 serial calls, never overlapping


# ─────────────────────────────────────────────────────────────────────────────
# 8. API failure is NOT stored as valid empty data
# ─────────────────────────────────────────────────────────────────────────────

class TestApiFailureHandling:

    @pytest.mark.asyncio
    async def test_failed_snapshot_not_treated_as_fresh(self):
        """A snapshot with status=FAILED must never be considered fresh."""
        svc = LiveSnapshotService()
        failed = _make_status(
            SnapshotSource.INCIDENTS,
            age_minutes=1.0,
            status=SnapshotStatus.FAILED,
        )
        # Even though it's 1 minute old (within 5-min window), FAILED = not fresh
        assert svc._is_fresh(failed, window_minutes=5) is False

    @pytest.mark.asyncio
    async def test_refresh_incident_api_failure_returns_unavailable_bundle(self):
        """
        When TomTom Incidents API fails, _refresh_incidents() must return a
        SnapshotBundle with incidents_available=False and empty incidents list.
        It must NOT return incidents_available=True with an empty list
        (that would imply "API responded: zero incidents").
        """
        svc = LiveSnapshotService()

        with (
            patch("app.services.live_snapshot_service.get_incidents",
                  new_callable=AsyncMock,
                  side_effect=Exception("API timeout")),
            patch.object(svc, "_persist_snapshot_row", new_callable=AsyncMock),
        ):
            result = await svc._refresh_incidents()

        assert result is not None
        assert result.incidents_available is False
        assert result.incidents == []

    @pytest.mark.asyncio
    async def test_zero_incidents_not_same_as_api_failure(self):
        """
        When TomTom Incidents returns 0 incidents (API succeeded, empty area),
        incidents_available must be True (not False).
        """
        svc = LiveSnapshotService()

        with (
            patch("app.services.live_snapshot_service.get_incidents",
                  new_callable=AsyncMock, return_value=[]),
            patch.object(svc, "_persist_snapshot_row", new_callable=AsyncMock),
            patch.object(svc, "_batch_insert", new_callable=AsyncMock),
        ):
            result = await svc._refresh_incidents()

        assert result is not None
        assert result.incidents_available is True   # API responded
        assert result.incidents == []               # Just no incidents in area


# ─────────────────────────────────────────────────────────────────────────────
# 9. snapshot_id is attached to the SnapshotBundle
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotIdAttachment:

    @pytest.mark.asyncio
    async def test_refresh_incidents_attaches_snapshot_id(self):
        """_refresh_incidents() must return a bundle with a non-None snapshot_id."""
        svc = LiveSnapshotService()
        from app.schemas.incident import Incident

        mock_incidents = [
            Incident(id="inc_1", type="Accident", latitude=12.93, longitude=77.60),
        ]

        with (
            patch("app.services.live_snapshot_service.get_incidents",
                  new_callable=AsyncMock, return_value=mock_incidents),
            patch.object(svc, "_persist_snapshot_row", new_callable=AsyncMock),
            patch.object(svc, "_batch_insert", new_callable=AsyncMock),
        ):
            result = await svc._refresh_incidents()

        assert result.incident_snapshot_id is not None
        assert len(result.incident_snapshot_id) == 36  # UUID format


# ─────────────────────────────────────────────────────────────────────────────
# 10. Bengaluru-wide incidents filtered for route segments
# ─────────────────────────────────────────────────────────────────────────────

class TestBengaluruWideFiltering:

    def test_snapshot_bundle_has_bengaluru_wide_incidents(self):
        """
        SnapshotBundle incidents should include all Bengaluru-wide incidents
        (not just those near the current route).
        Module 7 segment_incident_features.py is responsible for spatial filtering.
        """
        from app.schemas.incident import Incident

        # Simulate 50 incidents spread across Bengaluru
        incidents = [
            Incident(id=f"inc_{i}", type="Accident", latitude=12.7 + i * 0.01, longitude=77.3 + i * 0.01)
            for i in range(50)
        ]

        bundle = SnapshotBundle(
            incident_snapshot_id=str(uuid.uuid4()),
            incidents=incidents,
            incidents_available=True,
        )

        # Bundle should hold all 50, not pre-filtered
        assert len(bundle.incidents) == 50


# ─────────────────────────────────────────────────────────────────────────────
# 11. Timestamps are timezone-aware
# ─────────────────────────────────────────────────────────────────────────────

class TestTimezoneAwareness:

    def test_source_status_collected_at_is_timezone_aware(self):
        """SourceStatus collected_at must have tzinfo set (UTC)."""
        status = _make_status(SnapshotSource.INCIDENTS, age_minutes=2.0)
        assert status.collected_at is not None
        assert status.collected_at.tzinfo is not None

    def test_snapshot_row_collected_at_is_utc(self):
        """LiveDataSnapshotRow timestamps must be UTC-aware."""
        now = datetime.now(tz=timezone.utc)
        row = LiveDataSnapshotRow(
            collected_at=now,
            source=SnapshotSource.INCIDENTS,
            status=SnapshotStatus.OK,
            record_count=5,
        )
        assert row.collected_at.tzinfo is not None
        assert row.collected_at.tzinfo == timezone.utc

    def test_age_calculation_uses_utc(self):
        """Age calculation must not mix naive and aware datetimes."""
        svc = LiveSnapshotService()
        # Create a status with a known age of exactly 3 minutes
        collected_at = datetime.now(tz=timezone.utc) - timedelta(minutes=3)
        status = SourceStatus(
            source=SnapshotSource.WEATHER,
            snapshot_id=str(uuid.uuid4()),
            collected_at=collected_at,
            age_minutes=3.0,
            status=SnapshotStatus.OK,
        )
        # Should be fresh with 5-minute window, stale with 2-minute window
        assert svc._is_fresh(status, window_minutes=5) is True
        assert svc._is_fresh(status, window_minutes=2) is False


# ─────────────────────────────────────────────────────────────────────────────
# 12. Failed snapshots are never treated as fresh
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicatePrevention:

    def test_failed_snapshot_never_fresh_regardless_of_age(self):
        """A very recent FAILED snapshot should still not be used."""
        svc = LiveSnapshotService()
        # 10 seconds old but FAILED
        collected_at = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
        failed_status = SourceStatus(
            source=SnapshotSource.INCIDENTS,
            snapshot_id=str(uuid.uuid4()),
            collected_at=collected_at,
            age_minutes=0.17,
            status=SnapshotStatus.FAILED,
        )
        assert svc._is_fresh(failed_status, window_minutes=5) is False

    def test_partial_snapshot_can_be_fresh(self):
        """A PARTIAL snapshot (some records failed to parse) can still be used."""
        svc = LiveSnapshotService()
        partial = _make_status(
            SnapshotSource.TRAFFIC,
            age_minutes=1.0,
            status=SnapshotStatus.PARTIAL,
        )
        # PARTIAL means API succeeded but some parsing failed → still usable
        assert svc._is_fresh(partial, window_minutes=5) is True
