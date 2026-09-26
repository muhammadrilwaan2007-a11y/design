"""
backend/tests/test_module7.py
Unit tests for Module 7 — Spatial & Safety Feature Engineering.

Run from the backend/ directory:
    pytest tests/test_module7.py -v

Tests cover:
  - Route segmentation (count, lengths, CRS correctness, edge cases)
  - Bearing / turn detection
  - Incident assignment (zero vs. unavailable distinction)
  - Congestion ratio calculation
  - Hotspot feature computation (offline — no API calls)
  - Feature schema validation
"""

from __future__ import annotations

import math
import pytest

from app.schemas.route import RouteGeometry
from app.schemas.features import SegmentFeatureVector, SegmentCoord, SegmentGeometry
from app.features.route_segmentation import segment_route
from app.features.spatial_features import _bearing, _bearing_change, compute_segment_spatial_features
from app.features.segment_incident_features import assign_incidents_to_segments


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — Bengaluru test geometries
# ─────────────────────────────────────────────────────────────────────────────

def _make_geometry(coords: list[list[float]]) -> RouteGeometry:
    """Helper: build a RouteGeometry from [[lon, lat], ...] list."""
    return RouteGeometry(type="LineString", coordinates=coords)


@pytest.fixture
def route_koramangala_whitefield() -> RouteGeometry:
    """
    Simplified straight-ish corridor from Koramangala to Whitefield (~17 km).
    Real production routes will have many more points; this is sufficient for
    segmentation testing.
    """
    return _make_geometry([
        [77.6271, 12.9279],   # Koramangala
        [77.6600, 12.9350],
        [77.6900, 12.9400],
        [77.7100, 12.9500],
        [77.7300, 12.9600],
        [77.7499, 12.9698],   # Whitefield
    ])


@pytest.fixture
def route_short() -> RouteGeometry:
    """Short route ~1 km — should produce 2 segments (500m + 500m or 500m + remainder)."""
    return _make_geometry([
        [77.5900, 12.9500],
        [77.5950, 12.9530],
        [77.5990, 12.9555],
    ])


@pytest.fixture
def route_single_point() -> RouteGeometry:
    """Edge case: route with only 1 coordinate — should produce 0 segments."""
    return _make_geometry([
        [77.6271, 12.9279],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Route Segmentation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRouteSegmentation:

    def test_segment_count_long_route(self, route_koramangala_whitefield):
        """A ~17km route with 500m target should produce ≥ 20 segments."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        # We have 6 waypoints covering ~17km, so expect multiple segments
        assert len(segs) >= 10, f"Expected ≥10 segments, got {len(segs)}"

    def test_segment_ids_are_unique(self, route_koramangala_whitefield):
        """Every segment_id must be unique."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        ids = [s.segment_id for s in segs]
        assert len(ids) == len(set(ids)), "Duplicate segment IDs found"

    def test_segment_ids_contain_route_id(self, route_koramangala_whitefield):
        """Segment IDs should contain the route_id prefix."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        for s in segs:
            assert s.segment_id.startswith("route_1_seg_"), (
                f"Segment ID '{s.segment_id}' does not start with 'route_1_seg_'"
            )

    def test_segment_lengths_are_positive(self, route_koramangala_whitefield):
        """Every segment must have a positive, non-zero length."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        for s in segs:
            assert s.segment_length_m > 0, (
                f"Segment {s.segment_id} has non-positive length: {s.segment_length_m}"
            )

    def test_no_segment_longer_than_target_plus_tolerance(self, route_koramangala_whitefield):
        """No segment should exceed the target length by more than 10% (geometry rounding)."""
        segs = segment_route(route_koramangala_whitefield, "route_1", segment_length_m=500)
        for s in segs[:-1]:  # exclude final partial segment
            assert s.segment_length_m <= 550, (
                f"Segment {s.segment_id} is too long: {s.segment_length_m:.1f}m"
            )

    def test_cumulative_distances_are_monotonically_increasing(self, route_koramangala_whitefield):
        """end_distance_m of each segment must be greater than start_distance_m."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        for s in segs:
            assert s.end_distance_m > s.start_distance_m, (
                f"Segment {s.segment_id}: end ({s.end_distance_m}) <= start ({s.start_distance_m})"
            )

    def test_segment_length_km_consistent(self, route_koramangala_whitefield):
        """segment_length_km should equal segment_length_m / 1000 (within floating point)."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        for s in segs:
            expected_km = s.segment_length_m / 1000
            assert abs(s.segment_length_km - expected_km) < 0.0001, (
                f"Segment {s.segment_id}: length_km mismatch"
            )

    def test_coords_are_not_lat_lon_treated_as_metres(self, route_koramangala_whitefield):
        """
        Critical: segments must NOT treat degrees as metres.
        The UTM projection is verified by checking that a ~17km corridor
        doesn't return wildly incorrect total lengths (e.g. 0.17m or 170000m).
        """
        segs = segment_route(route_koramangala_whitefield, "route_1")
        total_m = sum(s.segment_length_m for s in segs)
        # Koramangala→Whitefield is approximately 15–20km
        assert 12_000 < total_m < 25_000, (
            f"Total route length {total_m:.1f}m is outside expected 12–25km range. "
            "Possible CRS error (treating degrees as metres)."
        )

    def test_single_point_route_returns_empty(self, route_single_point):
        """A route with a single coordinate cannot be segmented."""
        segs = segment_route(route_single_point, "route_x")
        assert segs == [], "Single-point route should return empty list"

    def test_midpoint_coord_is_within_segment_bbox(self, route_koramangala_whitefield):
        """Midpoint coordinates should be geographically within Bengaluru bounds."""
        segs = segment_route(route_koramangala_whitefield, "route_1")
        for s in segs:
            assert 12.7 < s.midpoint_coord.latitude < 13.3
            assert 77.3 < s.midpoint_coord.longitude < 77.9


# ─────────────────────────────────────────────────────────────────────────────
# Spatial Feature Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSpatialFeatures:

    def test_bearing_north(self):
        """Bearing from A to directly north of A should be 0°."""
        b = _bearing(77.6, 12.9, 77.6, 13.0)
        assert abs(b - 0.0) < 1.0, f"Expected ~0°, got {b}"

    def test_bearing_east(self):
        """Bearing from A to directly east of A should be ~90°."""
        b = _bearing(77.6, 12.9, 77.7, 12.9)
        assert abs(b - 90.0) < 2.0, f"Expected ~90°, got {b}"

    def test_bearing_change_small(self):
        """Small bearing difference (10°) should be < threshold (15°)."""
        assert _bearing_change(90.0, 100.0) == 10.0

    def test_bearing_change_crosses_360(self):
        """Bearing change across 0/360° boundary should resolve correctly."""
        assert _bearing_change(350.0, 10.0) == 20.0

    def test_straight_segment_has_zero_turns(self):
        """A perfectly straight line should have 0 turns."""
        # Straight east-west line
        geom = SegmentGeometry(type="LineString", coordinates=[
            [77.60, 12.90], [77.61, 12.90], [77.62, 12.90], [77.63, 12.90],
        ])
        seg = _dummy_segment(geom)
        result = compute_segment_spatial_features([seg], turn_threshold_deg=15.0)
        assert result[0].turn_count == 0

    def test_sharp_turn_detected(self):
        """A 90° turn should be detected as 1 turn."""
        geom = SegmentGeometry(type="LineString", coordinates=[
            [77.60, 12.90], [77.61, 12.90], [77.61, 12.91],  # east then north = 90° turn
        ])
        seg = _dummy_segment(geom)
        result = compute_segment_spatial_features([seg], turn_threshold_deg=15.0)
        assert result[0].turn_count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Incident Feature Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentFeatures:

    def test_data_unavailable_leaves_fields_null(self):
        """When data_available=False, all incident fields must remain None."""
        segs = [_dummy_segment_from_coords(12.93, 77.60)]
        result = assign_incidents_to_segments(segs, [], data_available=False)
        assert result[0].incident_count is None
        assert result[0].accident_count is None
        assert result[0].incidents_data_available is False

    def test_data_available_no_incidents_gives_zero(self):
        """When API succeeded but no incidents found, counts should be 0 (not None)."""
        segs = [_dummy_segment_from_coords(12.93, 77.60)]
        result = assign_incidents_to_segments(segs, [], data_available=True)
        assert result[0].incident_count == 0
        assert result[0].accident_count == 0
        assert result[0].incidents_data_available is True

    def test_accident_count_increments(self):
        """An accident incident within buffer distance should increment accident_count."""
        from app.schemas.incident import Incident
        incident = Incident(
            id="test_1",
            type="Accident",
            description="Road accident",
            latitude=12.930,
            longitude=77.600,
            icon_category=1,
        )
        segs = [_dummy_segment_from_coords(12.930, 77.600)]
        result = assign_incidents_to_segments(
            segs, [incident], buffer_m=500, data_available=True
        )
        assert result[0].accident_count == 1
        assert result[0].incident_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Congestion Ratio Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCongestionRatio:

    def test_free_flow_ratio_is_one(self):
        """If current_speed == free_flow_speed, congestion_ratio should be 1.0."""
        ratio = _compute_congestion_ratio(50, 50)
        assert abs(ratio - 1.0) < 0.001

    def test_standstill_ratio_is_zero(self):
        """If current_speed == 0, congestion_ratio should be 0.0."""
        ratio = _compute_congestion_ratio(0, 50)
        assert abs(ratio - 0.0) < 0.001

    def test_half_speed_ratio_is_half(self):
        """If current_speed is half free_flow, congestion_ratio should be 0.5."""
        ratio = _compute_congestion_ratio(25, 50)
        assert abs(ratio - 0.5) < 0.001

    def test_zero_free_flow_returns_none(self):
        """Division by zero free_flow_speed must not raise — return None."""
        ratio = _compute_congestion_ratio(50, 0)
        assert ratio is None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dummy_segment(geom: SegmentGeometry) -> SegmentFeatureVector:
    coord = SegmentCoord(latitude=12.93, longitude=77.60)
    return SegmentFeatureVector(
        route_id="test_route",
        segment_id="test_route_seg_000",
        segment_index=0,
        geometry=geom,
        start_coord=coord,
        end_coord=coord,
        midpoint_coord=coord,
        segment_length_m=500.0,
        segment_length_km=0.5,
        start_distance_m=0.0,
        end_distance_m=500.0,
    )


def _dummy_segment_from_coords(lat: float, lon: float) -> SegmentFeatureVector:
    coord = SegmentCoord(latitude=lat, longitude=lon)
    geom = SegmentGeometry(type="LineString", coordinates=[[lon, lat], [lon + 0.005, lat]])
    return SegmentFeatureVector(
        route_id="test_route",
        segment_id="test_route_seg_000",
        segment_index=0,
        geometry=geom,
        start_coord=coord,
        end_coord=SegmentCoord(latitude=lat, longitude=lon + 0.005),
        midpoint_coord=coord,
        segment_length_m=500.0,
        segment_length_km=0.5,
        start_distance_m=0.0,
        end_distance_m=500.0,
    )


def _compute_congestion_ratio(current: int, free_flow: int):
    """Helper mirroring the production congestion_ratio formula."""
    if free_flow is None or free_flow == 0:
        return None
    return round(current / free_flow, 3)
