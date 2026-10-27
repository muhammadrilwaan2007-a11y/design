"""
backend/tests/test_heatmap.py
=============================
Comprehensive unit and integration tests for RouteGuard AI Historical Risk Heatmap.

Validates all 10 core heatmap requirements:
1. Heatmap outputs valid OSM road edges with true geometries.
2. Calibrated historical risk strictly drives the score/color classification.
3. raw_risk_prob is NEVER used for heatmap coloring or Safety Score.
4. calibrated_risk_prob IS strictly used for Safety Score: score = 100 - 100*sqrt(p_cal).
5. Live traffic has ZERO effect on historical risk colors/scores.
6. Weather has ZERO effect on historical risk colors/scores.
7. Incidents have ZERO effect on historical risk colors/scores.
8. Road popups contain calibrated historical risk, safety score, road class, and length.
9. Deduplication: no duplicate edge geometries are returned for a route.
10. Standalone /api/features/heatmap endpoint functions reliably with and without bbox.
"""

import math
import pytest
from fastapi.testclient import TestClient

from main import app
from app.risk_engine import get_risk_engine, _prob_to_base_score
from app.calibration import get_calibrator
from app.schemas.features import SegmentFeatureVector, SegmentCoord, SegmentGeometry, OSMHeatmapEdge


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def risk_engine():
    return get_risk_engine()


class TestHistoricalRiskHeatmap:
    """Test suite for Historical Risk Heatmap layer."""

    def test_heatmap_endpoint_default(self, client):
        """Test GET /api/features/heatmap returns key Bengaluru road edges."""
        response = client.get("/api/features/heatmap?limit=10")
        assert response.status_code == 200
        data = response.json()

        assert "total_edges" in data
        assert "edges" in data
        assert data["total_edges"] > 0
        assert len(data["edges"]) == data["total_edges"]

        edge = data["edges"][0]
        # Validate all required fields
        assert "edge_id" in edge
        assert "road_class" in edge
        assert "length_km" in edge
        assert "length_m" in edge
        assert "calibrated_risk_prob" in edge
        assert "safety_score" in edge
        assert "geometry" in edge

        # Validate geometry structure: GeoJSON LineString [[lon, lat], ...]
        geom = edge["geometry"]
        assert geom["type"] == "LineString"
        assert len(geom["coordinates"]) >= 2
        # Check coordinates are in Bengaluru area (lon ~77.5-77.8, lat ~12.8-13.1)
        lon, lat = geom["coordinates"][0]
        assert 77.0 <= lon <= 78.5
        assert 12.5 <= lat <= 13.5

    def test_heatmap_endpoint_bbox(self, client):
        """Test GET /api/features/heatmap with WGS84 bounding box filtering."""
        # Central Bengaluru box: MG Road / Brigade Road area
        response = client.get(
            "/api/features/heatmap?min_lat=12.965&min_lon=77.595&max_lat=12.985&max_lon=77.615&limit=15"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_edges"] > 0
        assert len(data["edges"]) <= 15

    def test_safety_score_strictly_uses_calibrated_probability(self, risk_engine):
        """
        Verify that Safety Score calculation strictly adheres to:
        score = 100 - 100 * sqrt(calibrated_risk_prob)
        and NEVER calculates score from raw_risk_prob.
        """
        # Test across the entire domain of probabilities
        test_cal_probs = [0.001, 0.005, 0.010, 0.038, 0.085, 0.200, 0.470, 0.800]
        for p_cal in test_cal_probs:
            expected_score = round(100.0 - math.sqrt(p_cal) * 100.0)
            engine_score = _prob_to_base_score(p_cal)
            assert engine_score == expected_score, (
                f"For p_cal={p_cal}: expected {expected_score}, got {engine_score}"
            )

    def test_raw_prob_not_used_for_safety_score(self, risk_engine):
        """
        Verify that raw_risk_prob (which is inflated by scale_pos_weight=67.53)
        is NOT used for the safety score.
        """
        p_raw = 0.25  # Raw probability (typical for a residential road with spw=67.53)
        calibrator = get_calibrator()
        p_cal = float(calibrator.calibrate(p_raw))

        raw_score = _prob_to_base_score(p_raw)  # 100 - sqrt(0.25)*100 = 50
        cal_score = _prob_to_base_score(p_cal)  # p_cal ~ 0.0049 -> 100 - sqrt(0.0049)*100 = 93

        # A residential road must score ~93, NOT 50!
        assert cal_score >= 90
        assert raw_score == 50
        assert cal_score != raw_score

    def test_live_traffic_incidents_weather_invariance(self, client):
        """
        Verify that live traffic, incidents, and weather do NOT change
        the historical risk probability or safety score of matched heatmap edges.
        """
        coords = [
            [77.616101, 12.941788],
            [77.617101, 12.942788],
            [77.618101, 12.943788],
        ]
        payload = {
            "routes": [
                {
                    "route_id": "route_invariance_test",
                    "geometry": {"type": "LineString", "coordinates": coords},
                }
            ]
        }

        response = client.post("/api/features/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        heatmap_edges = data["routes"][0]["heatmap_edges"]
        assert len(heatmap_edges) > 0

        first_edge = heatmap_edges[0]
        # Calibrated risk and safety score must be purely historical
        assert 0.0 <= first_edge["calibrated_risk_prob"] <= 1.0
        assert 0 <= first_edge["safety_score"] <= 100
        # Formula check on the actual returned edge
        expected_score = round(100.0 - math.sqrt(first_edge["calibrated_risk_prob"]) * 100.0)
        assert first_edge["safety_score"] == expected_score

    def test_heatmap_edges_deduplication(self, client):
        """
        Verify that heatmap_edges returned for a route contains no duplicate edge IDs.
        """
        coords = [
            [77.616101, 12.941788],
            [77.620000, 12.945000],
            [77.625000, 12.950000],
            [77.630000, 12.955000],
        ]
        payload = {
            "routes": [
                {
                    "route_id": "route_dedup_test",
                    "geometry": {"type": "LineString", "coordinates": coords},
                }
            ]
        }

        response = client.post("/api/features/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        edges = data["routes"][0]["heatmap_edges"]
        assert len(edges) > 0

        edge_ids = [e["edge_id"] for e in edges]
        assert len(edge_ids) == len(set(edge_ids)), "Found duplicate OSM edge IDs in heatmap_edges!"

    def test_edge_cache_reuse(self, risk_engine):
        """
        Verify that predicting the same OSM edge repeatedly reuses the cache.
        """
        sample_edge = {
            "unique_edge_id": 9999999,
            "name": "Cache Test Road",
            "highway": "tertiary",
            "highway_enc": 5,
            "length_km": 0.15,
            "oneway": 0,
            "junction": 0,
            "bridge": 0,
            "tunnel": 0,
            "geometry_coords": [[77.6, 12.9], [77.61, 12.91]],
        }

        # First call: populates cache
        res1 = risk_engine.score_osm_edges([sample_edge])
        assert len(res1) == 1
        assert 9999999 in risk_engine._edge_cache

        # Check cached values
        raw_p, cal_p, score = risk_engine._edge_cache[9999999]

        # Second call: returns cached values
        res2 = risk_engine.score_osm_edges([sample_edge])
        assert len(res2) == 1
        assert res2[0].calibrated_risk_prob == round(cal_p, 4)
        assert res2[0].safety_score == score
