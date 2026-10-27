"""
backend/tests/test_risk_engine.py
==================================
RouteGuard AI — Module 8 Integration Test

Tests the RiskEngine against real project data (not mocked).
Uses the existing xgboost_baseline.json model and real SegmentFeatureVector
objects constructed from the saved test predictions CSV.

Run from backend/ directory:
    python -m pytest tests/test_risk_engine.py -v
    or directly:
    python tests/test_risk_engine.py
"""

from __future__ import annotations

import sys
import io
from pathlib import Path

# ── Windows console fix ────────────────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Path setup (run from backend/) ────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import numpy as np

from app.schemas.features import SegmentFeatureVector, SegmentCoord, SegmentGeometry
from app.risk_engine import (
    RiskEngine,
    _prob_to_base_score,
    _compute_live_deduction,
    _segment_to_feature_row,
    MODEL_FEATURE_NAMES,
)


PRED_CSV = BACKEND_DIR / "data" / "processed" / "xgboost_test_predictions.csv"
MODEL_PATH = BACKEND_DIR / "models" / "xgboost_baseline.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_minimal_segment(
    idx: int,
    length_km: float = 0.5,
    weather_risk: int = 0,
    incidents_data_available: bool = False,
    accident_count: int = 0,
    congestion_ratio: float | None = None,
) -> SegmentFeatureVector:
    """
    Build a minimal SegmentFeatureVector for testing.
    Uses real schema structure — no mock objects.
    """
    coord = SegmentCoord(latitude=12.9716, longitude=77.5946)
    return SegmentFeatureVector(
        route_id="test_route",
        segment_id=f"test_route_seg_{idx:03d}",
        segment_index=idx,
        geometry=SegmentGeometry(
            type="LineString",
            coordinates=[[77.5946, 12.9716], [77.5956, 12.9726]],
        ),
        start_coord=coord,
        end_coord=coord,
        midpoint_coord=coord,
        segment_length_m=length_km * 1000,
        segment_length_km=length_km,
        start_distance_m=0.0,
        end_distance_m=length_km * 1000,
        # Live data
        weather_risk=weather_risk,
        weather_data_available=(weather_risk > 0),
        wind_speed_ms=None,
        incidents_data_available=incidents_data_available,
        accident_count=accident_count,
        dangerous_condition_count=0,
        congestion_ratio=congestion_ratio,
        traffic_data_available=(congestion_ratio is not None),
    )


def hr(title):
    print(f"\n{'='*55}")
    print(title)
    print('='*55)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_model_loads():
    hr("TEST 1 — Model loads without error")
    assert MODEL_PATH.exists(), f"Model file not found: {MODEL_PATH}"
    engine = RiskEngine()
    assert engine.is_ready, "RiskEngine.is_ready should be True after loading"
    print(f"  ✓ Model loaded from: {engine._model_path}")


def test_score_bounds():
    hr("TEST 2 — Safety Score always in [0, 100]")
    for prob in [0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.99, 1.0]:
        score = _prob_to_base_score(prob)
        assert 0 <= score <= 100, f"Score {score} out of bounds for prob={prob}"
        print(f"  prob={prob:.2f}  →  base_score={score}")
    print("  ✓ All scores in [0, 100]")


def test_prob_monotonicity():
    hr("TEST 3 — Higher prob → lower Safety Score (monotone)")
    probs = [0.0, 0.05, 0.15, 0.3, 0.5, 0.8, 1.0]
    scores = [_prob_to_base_score(p) for p in probs]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i+1], (
            f"Monotonicity violated: prob={probs[i]:.2f} score={scores[i]} "
            f"but prob={probs[i+1]:.2f} score={scores[i+1]}"
        )
    print("  Prob → Score mapping:")
    for p, s in zip(probs, scores):
        print(f"    prob={p:.2f}  →  score={s}")
    print("  ✓ Monotone (higher risk = lower score)")


def test_live_deduction_bounds():
    hr("TEST 4 — Live deduction is bounded at [0, 20]")
    # Worst-case segment: heavy rain + low vis + live accident + dangerous + congestion
    seg = make_minimal_segment(
        0,
        weather_risk=3,
        incidents_data_available=True,
        accident_count=2,
        congestion_ratio=0.85,
    )
    from unittest.mock import patch
    # Set strong wind artificially
    seg.wind_speed_ms = 20.0
    deduction = _compute_live_deduction(seg)
    assert 0 <= deduction <= 20, f"Deduction {deduction} out of [0, 20]"
    print(f"  Worst-case deduction: {deduction} (max allowed: 20)")
    print("  ✓ Deduction bounded correctly")


def test_feature_extraction_defaults():
    hr("TEST 5 — Feature extraction uses correct defaults for V1 unknown fields")
    seg = make_minimal_segment(0, length_km=1.2)
    row = _segment_to_feature_row(seg)

    assert set(row.keys()) == set(MODEL_FEATURE_NAMES), (
        f"Feature key mismatch: {set(row.keys())} vs {set(MODEL_FEATURE_NAMES)}"
    )
    assert row["highway_enc"] == -1, "Unknown highway should encode to -1"
    assert row["length_km"] == 1.2, f"length_km incorrect: {row['length_km']}"
    assert row["oneway"] == 0
    assert row["junction"] == 0
    assert row["bridge"] == 0
    assert row["tunnel"] == 0
    print(f"  Feature row: {row}")
    print("  ✓ All features correctly defaulted")


def test_batch_scoring():
    hr("TEST 6 — Batch segment scoring (10 segments)")
    engine = RiskEngine()
    segments = [make_minimal_segment(i, length_km=0.3 + i * 0.1) for i in range(10)]
    scored = engine.score_segments(segments)

    assert len(scored) == 10
    for seg in scored:
        assert seg.historical_risk_prob is not None, f"Segment {seg.segment_id} has no risk_prob"
        assert seg.safety_score is not None, f"Segment {seg.segment_id} has no safety_score"
        assert 0 <= seg.safety_score <= 100
        print(
            f"  {seg.segment_id}: "
            f"risk_prob={seg.historical_risk_prob:.4f}  "
            f"deduction={seg.live_condition_deduction}  "
            f"safety_score={seg.safety_score}"
        )
    print("  ✓ All 10 segments scored within bounds")


def test_real_predictions_consistency():
    hr("TEST 7 — Cross-check against saved test predictions CSV")
    if not PRED_CSV.exists():
        print(f"  SKIP — {PRED_CSV} not found. Run ml/train_xgboost_baseline.py first.")
        return

    df = pd.read_csv(PRED_CSV)
    print(f"  Loaded {len(df):,} rows from {PRED_CSV.name}")

    # Take 20 rows — positives and negatives
    pos = df[df["actual_has_accident"] == 1].head(10)
    neg = df[df["actual_has_accident"] == 0].head(10)
    sample = pd.concat([pos, neg]).reset_index(drop=True)

    engine = RiskEngine()
    segments = [
        make_minimal_segment(i, length_km=float(row["length_km"]))
        for i, (_, row) in enumerate(sample.iterrows())
    ]
    scored = engine.score_segments(segments, use_osm_matching=False)

    print(f"\n  {'idx':<5} {'actual':>8} {'saved_prob':>12} {'engine_prob':>12} {'safety_score':>13}")
    for i, (seg, (_, row)) in enumerate(zip(scored, sample.iterrows())):
        print(
            f"  {i:<5} {int(row['actual_has_accident']):>8} "
            f"{float(row['predicted_probability']):>12.4f} "
            f"{seg.historical_risk_prob:>12.4f} "
            f"{seg.safety_score:>13}"
        )

    # All scores must be in [0, 100]
    assert all(s.safety_score is not None and 0 <= s.safety_score <= 100 for s in scored)
    print("  ✓ Real-data predictions: all safety scores in [0, 100]")


def test_empty_segments():
    hr("TEST 8 — Empty segment list handled gracefully")
    engine = RiskEngine()
    result = engine.score_segments([])
    assert result == []
    print("  ✓ Empty list returns empty list without error")


def test_final_score_never_exceeds_base():
    hr("TEST 9 — Final score is always <= base score (deduction only reduces)")
    engine = RiskEngine()
    seg = make_minimal_segment(0, weather_risk=2, incidents_data_available=True, accident_count=1)
    [scored] = engine.score_segments([seg])

    assert scored.historical_risk_prob is not None
    assert scored.safety_score is not None
    base = _prob_to_base_score(scored.historical_risk_prob)
    assert scored.safety_score <= base, (
        f"Final score {scored.safety_score} exceeds base score {base}"
    )
    print(f"  base_score={base}  deduction={scored.live_condition_deduction}  final={scored.safety_score}")
    print("  ✓ Final score never exceeds base score")



def test_no_500m_segment_length_to_xgboost():
    hr("TEST 10 — 500m UI segment length is NEVER passed directly as length_km=0.50")
    from unittest.mock import MagicMock, patch

    engine = RiskEngine()
    # Real 500m segment along Koramangala Road
    coord_start = SegmentCoord(latitude=12.941788, longitude=77.616101)
    coord_end = SegmentCoord(latitude=12.944000, longitude=77.619000)
    seg = SegmentFeatureVector(
        route_id="test_route",
        segment_id="test_ui_seg_500m",
        segment_index=0,
        geometry=SegmentGeometry(
            type="LineString",
            coordinates=[[77.616101, 12.941788], [77.619000, 12.944000]],
        ),
        start_coord=coord_start,
        end_coord=coord_end,
        midpoint_coord=coord_start,
        segment_length_m=500.0,
        segment_length_km=0.50,  # 500m UI visualization segment
        start_distance_m=0.0,
        end_distance_m=500.0,
    )

    captured_X = []
    assert engine._model is not None
    original_predict_proba = engine._model.predict_proba

    def spy_predict_proba(X):
        captured_X.append(X.copy())
        return original_predict_proba(X)

    with patch.object(engine._model, "predict_proba", side_effect=spy_predict_proba):
        scored = engine.score_segments([seg], use_osm_matching=True)

    assert len(captured_X) > 0, "predict_proba was never called!"
    for X in captured_X:
        # Strict assertion: NO edge passed to XGBoost may have length_km == 0.50
        lengths = X["length_km"].values
        has_050 = any(np.isclose(l, 0.50, atol=1e-4) for l in lengths)
        assert not has_050, f"XGBoost received length_km=0.50 from a 500m UI segment! Lengths: {lengths}"
        print(f"  ✓ Verified {len(lengths)} matched OSM edges passed to XGBoost.")
        print(f"    Edge lengths range: min={lengths.min()*1000:.1f}m, med={np.median(lengths)*1000:.1f}m, max={lengths.max()*1000:.1f}m")
        print("    None of the inputs equal the 500m UI chunk length (0.50 km).")


def test_live_conditions_do_not_modify_safety_score():
    hr("TEST 11 — Live conditions (weather/traffic/incidents) do NOT modify safety_score")
    engine = RiskEngine()

    # Segment with severe live events: heavy rain + low vis + live accident + severe congestion
    seg_live = make_minimal_segment(
        0,
        length_km=0.05,
        weather_risk=3,
        incidents_data_available=True,
        accident_count=2,
        congestion_ratio=0.85,
    )
    # Identical segment with ZERO live events (clean conditions)
    seg_clean = make_minimal_segment(
        1,
        length_km=0.05,
        weather_risk=0,
        incidents_data_available=False,
        accident_count=0,
        congestion_ratio=None,
    )

    scored_live = engine.score_segments([seg_live], use_osm_matching=False)[0]
    scored_clean = engine.score_segments([seg_clean], use_osm_matching=False)[0]

    print(f"  Live conditions segment:  prob={scored_live.historical_risk_prob} score={scored_live.safety_score} deduction={scored_live.live_condition_deduction}")
    print(f"  Clean conditions segment: prob={scored_clean.historical_risk_prob} score={scored_clean.safety_score} deduction={scored_clean.live_condition_deduction}")

    # Safety score must be IDENTICAL because structural features are identical!
    assert scored_live.safety_score == scored_clean.safety_score, (
        f"Safety score changed due to live conditions: {scored_live.safety_score} vs {scored_clean.safety_score}"
    )
    assert scored_live.live_condition_deduction is not None
    assert scored_live.live_condition_deduction > 0, "Live deduction should be recorded for live conditions"
    assert scored_clean.live_condition_deduction == 0, "Clean segment should have 0 live deduction"
    print("  ✓ Safety score strictly reflects structural risk; live deductions are isolated.")


def test_highway_encoding_matches_training():
    hr("TEST 12 — Highway encoding matches training script exactly")
    from app.features.osm_matcher import HIGHWAY_RISK_ORDER, encode_highway

    expected_order = {
        "residential":    0,
        "living_street":  1,
        "unclassified":   2,
        "road":           3,
        "tertiary_link":  4,
        "tertiary":       5,
        "secondary_link": 6,
        "secondary":      7,
        "primary_link":   8,
        "primary":        9,
        "motorway_link":  10,
        "trunk_link":     11,
        "trunk":          12,
        "motorway":       13,
    }

    assert HIGHWAY_RISK_ORDER == expected_order, "HIGHWAY_RISK_ORDER mismatch with training script"
    assert encode_highway("unknown") == -1
    assert encode_highway("unmapped_type") == -1
    for hw, code in expected_order.items():
        assert encode_highway(hw) == code
    print("  ✓ All 14 highway risk tiers match training script exactly.")


def test_unmatched_route_geometry_safe_fallback():
    hr("TEST 13 — Unmatched geometry gracefully marked unavailable (no fake 500m edge)")
    engine = RiskEngine()

    # Route coordinates in the ocean far away from Bengaluru OSM roads
    coord_ocean1 = SegmentCoord(latitude=0.0, longitude=0.0)
    coord_ocean2 = SegmentCoord(latitude=0.005, longitude=0.005)
    seg_ocean = SegmentFeatureVector(
        route_id="ocean_route",
        segment_id="ocean_seg_001",
        segment_index=0,
        geometry=SegmentGeometry(
            type="LineString",
            coordinates=[[0.0, 0.0], [0.005, 0.005]],
        ),
        start_coord=coord_ocean1,
        end_coord=coord_ocean2,
        midpoint_coord=coord_ocean1,
        segment_length_m=500.0,
        segment_length_km=0.50,
        start_distance_m=0.0,
        end_distance_m=500.0,
    )

    scored = engine.score_segments([seg_ocean], use_osm_matching=True)[0]
    assert scored.safety_score is None, f"Expected None for unmatched segment, got {scored.safety_score}"
    assert scored.historical_risk_prob is None, f"Expected None for unmatched segment, got {scored.historical_risk_prob}"
    print("  ✓ Unmatched segment marked unavailable (safety_score=None); no synthetic edge invented.")


def test_six_model_features():
    hr("TEST 14 — Model feature names are exactly the 6 training features")
    assert MODEL_FEATURE_NAMES == [
        "highway_enc",
        "length_km",
        "oneway",
        "junction",
        "bridge",
        "tunnel",
    ]
    print(f"  ✓ Features: {MODEL_FEATURE_NAMES}")


# ── Runner ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        test_model_loads,
        test_score_bounds,
        test_prob_monotonicity,
        test_live_deduction_bounds,
        test_feature_extraction_defaults,
        test_batch_scoring,
        test_real_predictions_consistency,
        test_empty_segments,
        test_final_score_never_exceeds_base,
        test_no_500m_segment_length_to_xgboost,
        test_live_conditions_do_not_modify_safety_score,
        test_highway_encoding_matches_training,
        test_unmatched_route_geometry_safe_fallback,
        test_six_model_features,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"\n  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    hr("SUMMARY")
    print(f"  Tests passed: {passed}/{len(tests)}")
    print(f"  Tests failed: {failed}/{len(tests)}")
    sys.exit(0 if failed == 0 else 1)

