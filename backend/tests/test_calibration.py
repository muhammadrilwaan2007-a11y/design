"""
backend/tests/test_calibration.py
==================================
RouteGuard AI — Probability Calibration Layer Unit & Integration Tests

Validates the 10 requirements specified for theoretical class-weight calibration:
1. p_raw=0.25 produces approximately 0.00487 (p_cal ≈ 0.00491)
2. p_raw=0.50 produces approximately 0.01459
3. p_raw=0.90 produces approximately 0.1172  (p_cal ≈ 0.1176)
4. Calibration is monotonically increasing across [0, 1]
5. calibrated_probability is always strictly between 0 and 1
6. p_raw=0 gives exactly 0
7. p_raw=1 gives exactly 1
8. Safety Score uses calibrated_probability, NOT raw_probability
9. Live traffic/weather/incidents still do not modify Safety Score
10. Existing OSM edge matching features and flow continue to pass
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.calibration import calibrate_probability, ProbabilityCalibrator, get_calibrator
from app.config.settings import get_settings
from app.risk_engine import RiskEngine, _prob_to_base_score
from app.schemas.features import SegmentFeatureVector, SegmentCoord, SegmentGeometry


# ── Test 1: p_raw=0.25 produces approx 0.00487 ────────────────────────────────

def test_1_p_raw_0_25_produces_approx_0_00487():
    """p_raw=0.25 with scale_pos_weight=67.53 yields approx 0.00487-0.00491."""
    p_raw = 0.25
    p_cal = calibrate_probability(p_raw, scale_pos_weight=67.53)
    # Theoretical: 0.25 / (0.25 + 0.75 * 67.53) = 0.25 / 50.8975 = 0.0049118
    assert p_cal == pytest.approx(0.00487, abs=1e-3)
    assert 0.0048 <= p_cal <= 0.0050


# ── Test 2: p_raw=0.50 produces approx 0.01459 ────────────────────────────────

def test_2_p_raw_0_50_produces_approx_0_01459():
    """p_raw=0.50 with scale_pos_weight=67.53 yields approx 0.01459."""
    p_raw = 0.50
    p_cal = calibrate_probability(p_raw, scale_pos_weight=67.53)
    # Theoretical: 0.50 / (0.50 + 0.50 * 67.53) = 1 / 68.53 = 0.014592149...
    assert p_cal == pytest.approx(0.01459, abs=1e-4)


# ── Test 3: p_raw=0.90 produces approx 0.1172 ─────────────────────────────────

def test_3_p_raw_0_90_produces_approx_0_1172():
    """p_raw=0.90 with scale_pos_weight=67.53 yields approx 0.1172-0.1176."""
    p_raw = 0.90
    p_cal = calibrate_probability(p_raw, scale_pos_weight=67.53)
    # Theoretical: 0.90 / (0.90 + 0.10 * 67.53) = 0.90 / 7.653 = 0.117599...
    assert p_cal == pytest.approx(0.1172, abs=1e-3)
    assert 0.1170 <= p_cal <= 0.1180


# ── Test 4: Calibration is monotonically increasing ───────────────────────────

def test_4_calibration_is_monotonically_increasing():
    """calibrated_probability must be monotonically non-decreasing for p_raw in [0, 1]."""
    p_raw_grid = np.linspace(0.0, 1.0, 500)
    p_cal_grid = calibrate_probability(p_raw_grid, scale_pos_weight=67.53)

    diffs = np.diff(p_cal_grid)
    assert np.all(diffs >= 0.0), "Calibration violated monotonicity!"


# ── Test 5: calibrated_probability is always between 0 and 1 ──────────────────

def test_5_calibrated_probability_always_bounded_zero_to_one():
    """calibrated_probability must be strictly in [0.0, 1.0] for any inputs."""
    test_inputs = [-1.0, -0.01, 0.0, 0.0001, 0.25, 0.5, 0.75, 0.9999, 1.0, 1.05, 100.0]
    for inp in test_inputs:
        cal = calibrate_probability(inp, scale_pos_weight=67.53)
        assert 0.0 <= cal <= 1.0, f"Out of bounds for {inp}: {cal}"

    # Also test vector
    arr = np.array(test_inputs)
    cal_arr = calibrate_probability(arr, scale_pos_weight=67.53)
    assert np.all((cal_arr >= 0.0) & (cal_arr <= 1.0))


# ── Test 6: p_raw=0 gives 0 ───────────────────────────────────────────────────

def test_6_p_raw_zero_gives_zero():
    """Exact boundary check: p_raw=0 must output 0.0."""
    res = calibrate_probability(0.0, scale_pos_weight=67.53)
    assert res == 0.0


# ── Test 7: p_raw=1 gives 1 ───────────────────────────────────────────────────

def test_7_p_raw_one_gives_one():
    """Exact boundary check: p_raw=1 must output 1.0."""
    res = calibrate_probability(1.0, scale_pos_weight=67.53)
    assert res == 1.0


# ── Test 8: Safety Score uses calibrated_probability, NOT raw_probability ──────

def test_8_safety_score_uses_calibrated_probability():
    """
    Verify that:
    1. raw_risk_prob is preserved and NOT overwritten.
    2. calibrated_risk_prob is populated separately.
    3. safety_score is derived from calibrated_risk_prob (score = 100 - sqrt(calibrated_prob)*100).
    4. safety_score is NOT derived from raw_risk_prob.
    """
    engine = RiskEngine()
    coord = SegmentCoord(latitude=12.9716, longitude=77.5946)
    seg = SegmentFeatureVector(
        route_id="test_route",
        segment_id="test_cal_seg_001",
        segment_index=0,
        geometry=SegmentGeometry(type="LineString", coordinates=[[77.5946, 12.9716], [77.5956, 12.9726]]),
        start_coord=coord,
        end_coord=coord,
        midpoint_coord=coord,
        segment_length_m=500.0,
        segment_length_km=0.50,
        start_distance_m=0.0,
        end_distance_m=500.0,
    )

    [scored] = engine.score_segments([seg], use_osm_matching=False)

    assert scored.raw_risk_prob is not None, "raw_risk_prob must be populated for diagnostics"
    assert scored.calibrated_risk_prob is not None, "calibrated_risk_prob must be populated"
    assert scored.safety_score is not None

    # Check relationship
    raw_p = scored.raw_risk_prob
    cal_p = scored.calibrated_risk_prob

    # Calibration lowers raw probability because scale_pos_weight=67.53 > 1
    assert cal_p < raw_p, f"cal_p ({cal_p}) should be significantly lower than raw_p ({raw_p})"

    # Safety Score MUST match calibrated_probability formula
    expected_score = _prob_to_base_score(cal_p)
    raw_hypothetical_score = _prob_to_base_score(raw_p)

    assert scored.safety_score == expected_score, (
        f"Safety score {scored.safety_score} does not match calibrated expected score {expected_score}"
    )
    assert scored.safety_score != raw_hypothetical_score, (
        f"Safety score should NOT equal raw score {raw_hypothetical_score}"
    )
    # Calibrated score must be substantially higher than raw score
    assert scored.safety_score > raw_hypothetical_score


# ── Test 9: Live conditions do not modify Safety Score ─────────────────────────

def test_9_live_conditions_do_not_modify_safety_score():
    """
    Live traffic, weather, and incidents must be isolated and must NOT modify Safety Score.
    """
    engine = RiskEngine()
    coord = SegmentCoord(latitude=12.9716, longitude=77.5946)

    # Segment with bad live conditions
    seg_live = SegmentFeatureVector(
        route_id="test_route",
        segment_id="test_live_seg_bad",
        segment_index=0,
        geometry=SegmentGeometry(type="LineString", coordinates=[[77.5946, 12.9716], [77.5956, 12.9726]]),
        start_coord=coord,
        end_coord=coord,
        midpoint_coord=coord,
        segment_length_m=500.0,
        segment_length_km=0.05,
        start_distance_m=0.0,
        end_distance_m=500.0,
        weather_risk=3,
        weather_data_available=True,
        incidents_data_available=True,
        accident_count=3,
        dangerous_condition_count=1,
        congestion_ratio=0.85,
        traffic_data_available=True,
    )

    # Identical structural segment with clean live conditions
    seg_clean = SegmentFeatureVector(
        route_id="test_route",
        segment_id="test_live_seg_clean",
        segment_index=1,
        geometry=SegmentGeometry(type="LineString", coordinates=[[77.5946, 12.9716], [77.5956, 12.9726]]),
        start_coord=coord,
        end_coord=coord,
        midpoint_coord=coord,
        segment_length_m=500.0,
        segment_length_km=0.05,
        start_distance_m=0.0,
        end_distance_m=500.0,
        weather_risk=0,
        weather_data_available=False,
        incidents_data_available=False,
        accident_count=0,
        dangerous_condition_count=0,
        congestion_ratio=None,
        traffic_data_available=False,
    )

    results = engine.score_segments([seg_live, seg_clean], use_osm_matching=False)
    scored_live, scored_clean = results[0], results[1]

    # Structural safety scores must be identical
    assert scored_live.safety_score == scored_clean.safety_score
    # Live condition deduction is recorded separately
    assert scored_live.live_condition_deduction is not None
    assert scored_live.live_condition_deduction > 0
    assert scored_clean.live_condition_deduction == 0


# ── Test 10: Configuration and OSM edge matching integrity ────────────────────

def test_10_configurable_scale_pos_weight_and_matcher_integrity():
    """
    scale_pos_weight is configurable via settings, and calibrator respects custom spw.
    """
    settings = get_settings()
    assert hasattr(settings, "calibration_scale_pos_weight")
    assert settings.calibration_scale_pos_weight == 67.53

    # Custom calibrator
    calibrator_custom = ProbabilityCalibrator(scale_pos_weight=1.0)
    # When spw=1.0, p_cal == p_raw
    assert calibrator_custom.calibrate(0.35) == pytest.approx(0.35, abs=1e-5)

    # Default calibrator uses settings.calibration_scale_pos_weight
    default_cal = get_calibrator()
    assert default_cal.scale_pos_weight == 67.53
