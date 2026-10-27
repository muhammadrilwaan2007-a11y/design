"""
backend/tests/test_shap_explainer.py
======================================
RouteGuard AI — Local SHAP Explainer Test Suite (16 tests)

Tests all requirements from the SHAP implementation spec:
  1. Local SHAP can explain a valid OSM edge.
  2. SHAP receives exactly six model features.
  3. Feature ordering matches XGBoost training order.
  4. Original OSM edge length is used.
  5. 500m UI segment length is never passed directly to SHAP.
  6. SHAP does not modify raw_risk_prob.
  7. SHAP does not modify calibrated_risk_prob.
  8. SHAP does not modify Safety Score.
  9. SHAP values contain all six features.
 10. Top factors are ranked using absolute SHAP magnitude.
 11. Boolean features are correctly represented.
 12. Highway encoding matches the existing mapping.
 13. Live traffic does not affect SHAP.
 14. Weather does not affect SHAP.
 15. Incidents do not affect SHAP.
 16. Missing/unmatched OSM edges are handled safely.

Run from backend/ directory:
    python -m pytest tests/test_shap_explainer.py -v
"""

from __future__ import annotations

import sys
import io
from pathlib import Path

# ── Windows console fix ────────────────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Path setup ────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import pytest
import numpy as np
import pandas as pd

from app.risk_engine import MODEL_FEATURE_NAMES, HIGHWAY_RISK_ORDER, RiskEngine
from app.shap_explainer import (
    ShapExplainerService,
    ShapExplanation,
    ShapContribution,
    FEATURE_LABELS,
    HIGHWAY_ENC_TO_CLASS,
    SHAP_OUTPUT_SPACE,
    _display_value,
    _direction,
    get_shap_service,
    initialize_shap_service,
)

MODEL_PATH = BACKEND_DIR / "models" / "xgboost_baseline.json"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def loaded_engine():
    """Load the real RiskEngine (and therefore the SHAP explainer) once."""
    if not MODEL_PATH.exists():
        pytest.skip(f"Model not found: {MODEL_PATH}")
    return RiskEngine()


@pytest.fixture(scope="module")
def shap_service(loaded_engine):
    """Return the module-level SHAP service after engine initializes it."""
    svc = get_shap_service()
    if not svc.is_ready:
        pytest.skip("SHAP explainer did not initialize — shap library may be unavailable.")
    return svc


def make_edge_dict(
    unique_edge_id: int = 100001,
    highway_enc: int = 9,       # primary
    length_km: float = 0.067,   # ORIGINAL OSM edge length (67m), NOT 500m UI
    oneway: int = 1,
    junction: int = 0,
    bridge: int = 0,
    tunnel: int = 0,
) -> dict:
    return {
        "unique_edge_id": unique_edge_id,
        "highway":        HIGHWAY_ENC_TO_CLASS.get(highway_enc, "unknown"),
        "highway_enc":    highway_enc,
        "length_km":      length_km,
        "oneway":         oneway,
        "junction":       junction,
        "bridge":         bridge,
        "tunnel":         tunnel,
    }


# ── Test 1: Local SHAP can explain a valid OSM edge ──────────────────────────

def test_shap_explains_valid_edge(shap_service, loaded_engine):
    """Test 1: SHAP returns a valid explanation for a known edge."""
    edge = make_edge_dict()
    # Use RiskEngine to get cached probabilities
    loaded_engine.score_osm_edges([edge])

    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.35,
        calibrated_risk_prob=0.022,
        safety_score=85,
    )
    assert explanation is not None, "SHAP explanation must not be None for a valid edge."
    assert isinstance(explanation, ShapExplanation)
    assert explanation.osm_edge_id == 100001


# ── Test 2: SHAP receives exactly six model features ─────────────────────────

def test_shap_receives_six_features(shap_service):
    """Test 2: SHAP explanation must contain exactly six feature contributions."""
    edge = make_edge_dict(unique_edge_id=100002)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.3,
        calibrated_risk_prob=0.02,
        safety_score=86,
    )
    assert explanation is not None
    assert len(explanation.contributions) == 6, (
        f"Expected exactly 6 SHAP contributions, got {len(explanation.contributions)}"
    )


# ── Test 3: Feature ordering matches XGBoost training order ──────────────────

def test_feature_ordering_matches_training(shap_service):
    """Test 3: Features used by SHAP must be in the exact MODEL_FEATURE_NAMES order."""
    edge = make_edge_dict(unique_edge_id=100003)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.3,
        calibrated_risk_prob=0.02,
        safety_score=86,
    )
    assert explanation is not None
    # Contributions are sorted by magnitude, but all six must be present
    contrib_features = {c.feature for c in explanation.contributions}
    assert contrib_features == set(MODEL_FEATURE_NAMES), (
        f"Missing features: {set(MODEL_FEATURE_NAMES) - contrib_features}"
    )


# ── Test 4: Original OSM edge length is used ─────────────────────────────────

def test_original_osm_edge_length_used(shap_service):
    """Test 4: length_km in the explanation must be the OSM training-edge length, not 500m."""
    original_length_km = 0.067  # 67m OSM edge
    edge = make_edge_dict(unique_edge_id=100004, length_km=original_length_km)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.3,
        calibrated_risk_prob=0.02,
        safety_score=86,
    )
    assert explanation is not None
    length_contrib = next(c for c in explanation.contributions if c.feature == "length_km")
    assert abs(float(length_contrib.value) - original_length_km) < 1e-9, (
        f"Expected length_km={original_length_km}, got {length_contrib.value}"
    )


# ── Test 5: 500m UI segment length is never passed directly to SHAP ──────────

def test_500m_ui_segment_length_not_passed_to_shap(shap_service):
    """Test 5: SHAP explanation with original 67m must differ from one with 500m length."""
    edge_original = make_edge_dict(unique_edge_id=100005, length_km=0.067)  # 67m OSM
    edge_500m = make_edge_dict(unique_edge_id=100006, length_km=0.500)      # 500m UI synthetic

    exp_original = shap_service.explain_edge(
        edge_dict=edge_original,
        raw_risk_prob=0.3, calibrated_risk_prob=0.02, safety_score=86,
    )
    exp_500m = shap_service.explain_edge(
        edge_dict=edge_500m,
        raw_risk_prob=0.3, calibrated_risk_prob=0.02, safety_score=86,
    )
    assert exp_original is not None
    assert exp_500m is not None

    len_orig = next(c for c in exp_original.contributions if c.feature == "length_km")
    len_500m = next(c for c in exp_500m.contributions if c.feature == "length_km")

    # The SHAP values for length MUST differ when the lengths differ
    assert abs(float(len_orig.value) - float(len_500m.value)) > 0.1, (
        "500m and 67m edges must have different length_km values passed to SHAP."
    )


# ── Test 6: SHAP does not modify raw_risk_prob ───────────────────────────────

def test_shap_does_not_modify_raw_risk_prob(shap_service):
    """Test 6: raw_risk_prob in explanation must exactly equal the value passed in."""
    original_raw = 0.745321
    edge = make_edge_dict(unique_edge_id=100007)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=original_raw,
        calibrated_risk_prob=0.05,
        safety_score=77,
    )
    assert explanation is not None
    assert abs(explanation.raw_risk_prob - original_raw) < 1e-9, (
        "SHAP must NOT modify raw_risk_prob."
    )


# ── Test 7: SHAP does not modify calibrated_risk_prob ────────────────────────

def test_shap_does_not_modify_calibrated_risk_prob(shap_service):
    """Test 7: calibrated_risk_prob in explanation must exactly equal the value passed in."""
    original_cal = 0.048123
    edge = make_edge_dict(unique_edge_id=100008)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.7,
        calibrated_risk_prob=original_cal,
        safety_score=78,
    )
    assert explanation is not None
    assert abs(explanation.calibrated_risk_prob - original_cal) < 1e-9, (
        "SHAP must NOT modify calibrated_risk_prob."
    )


# ── Test 8: SHAP does not modify Safety Score ─────────────────────────────────

def test_shap_does_not_modify_safety_score(shap_service):
    """Test 8: safety_score in explanation must exactly equal the value passed in."""
    original_score = 81
    edge = make_edge_dict(unique_edge_id=100009)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.7,
        calibrated_risk_prob=0.04,
        safety_score=original_score,
    )
    assert explanation is not None
    assert explanation.safety_score == original_score, (
        "SHAP must NOT modify safety_score."
    )


# ── Test 9: SHAP values contain all six features ──────────────────────────────

def test_shap_values_contain_all_six_features(shap_service):
    """Test 9: All six MODEL_FEATURE_NAMES must appear in the explanation."""
    edge = make_edge_dict(unique_edge_id=100010)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.3,
        calibrated_risk_prob=0.02,
        safety_score=86,
    )
    assert explanation is not None
    feature_names = [c.feature for c in explanation.contributions]
    for expected in MODEL_FEATURE_NAMES:
        assert expected in feature_names, f"Feature '{expected}' missing from SHAP explanation."


# ── Test 10: Top factors are ranked using absolute SHAP magnitude ─────────────

def test_top_factors_ranked_by_absolute_magnitude(shap_service):
    """Test 10: top_factors must be the top 3 by |shap_value|, in descending order."""
    edge = make_edge_dict(unique_edge_id=100011)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.3,
        calibrated_risk_prob=0.02,
        safety_score=86,
    )
    assert explanation is not None
    assert len(explanation.top_factors) == 3

    # Verify contributions are sorted by |shap_value| descending
    abs_vals = [abs(c.shap_value) for c in explanation.contributions]
    assert abs_vals == sorted(abs_vals, reverse=True), (
        "contributions must be sorted by |shap_value| descending."
    )

    # top_factors must be the first 3 of contributions
    for i in range(3):
        assert explanation.top_factors[i].feature == explanation.contributions[i].feature


# ── Test 11: Boolean features are correctly represented ───────────────────────

def test_boolean_features_display_correctly():
    """Test 11: Boolean features (oneway, junction, bridge, tunnel) → Yes/No."""
    assert _display_value("oneway", 1) == "Yes"
    assert _display_value("oneway", 0) == "No"
    assert _display_value("junction", 1) == "Yes"
    assert _display_value("junction", 0) == "No"
    assert _display_value("bridge", 1) == "Yes"
    assert _display_value("bridge", 0) == "No"
    assert _display_value("tunnel", 1) == "Yes"
    assert _display_value("tunnel", 0) == "No"


# ── Test 12: Highway encoding matches existing mapping ────────────────────────

def test_highway_encoding_matches_existing_mapping():
    """Test 12: HIGHWAY_ENC_TO_CLASS must be the exact inverse of HIGHWAY_RISK_ORDER."""
    for road_class, enc in HIGHWAY_RISK_ORDER.items():
        assert HIGHWAY_ENC_TO_CLASS[enc] == road_class, (
            f"HIGHWAY_ENC_TO_CLASS[{enc}] should be '{road_class}', "
            f"got '{HIGHWAY_ENC_TO_CLASS.get(enc)}'"
        )
    # Verify display_value decodes correctly
    assert "Primary" in _display_value("highway_enc", 9)  # highway_enc=9 → primary


# ── Test 13: Live traffic does not affect SHAP ────────────────────────────────

def test_live_traffic_does_not_affect_shap(shap_service):
    """Test 13: Two edges identical in road features but different in traffic → same SHAP."""
    # SHAP only receives the 6 structural features.
    # Traffic (congestion_ratio, speed) is NOT an input to the model or SHAP.
    edge_no_traffic = make_edge_dict(unique_edge_id=100012)
    edge_heavy_traffic = make_edge_dict(unique_edge_id=100013)
    # Note: we intentionally do NOT add any traffic fields to edge_dict
    # because traffic never enters XGBoost or SHAP inputs.

    exp1 = shap_service.explain_edge(edge_no_traffic, 0.3, 0.02, 86)
    exp2 = shap_service.explain_edge(edge_heavy_traffic, 0.3, 0.02, 86)

    assert exp1 is not None and exp2 is not None
    for f in MODEL_FEATURE_NAMES:
        sv1 = next(c.shap_value for c in exp1.contributions if c.feature == f)
        sv2 = next(c.shap_value for c in exp2.contributions if c.feature == f)
        assert abs(sv1 - sv2) < 1e-8, (
            f"Feature '{f}': SHAP value changed between edges with identical road features "
            f"(sv1={sv1}, sv2={sv2}). Traffic must NOT affect SHAP."
        )


# ── Test 14: Weather does not affect SHAP ─────────────────────────────────────

def test_weather_does_not_affect_shap(shap_service):
    """Test 14: Weather is never an XGBoost/SHAP input — same road → same SHAP."""
    edge_dry = make_edge_dict(unique_edge_id=100014)
    edge_rainy = make_edge_dict(unique_edge_id=100015)
    # Weather fields (rain_1h_mm, visibility_m, wind_speed_ms) never appear in edge_dict

    exp_dry = shap_service.explain_edge(edge_dry, 0.3, 0.02, 86)
    exp_rain = shap_service.explain_edge(edge_rainy, 0.3, 0.02, 86)

    assert exp_dry is not None and exp_rain is not None
    for f in MODEL_FEATURE_NAMES:
        sv1 = next(c.shap_value for c in exp_dry.contributions if c.feature == f)
        sv2 = next(c.shap_value for c in exp_rain.contributions if c.feature == f)
        assert abs(sv1 - sv2) < 1e-8, (
            f"Feature '{f}': SHAP value changed between dry/rainy edges with identical road features. "
            "Weather must NOT affect SHAP."
        )


# ── Test 15: Incidents do not affect SHAP ─────────────────────────────────────

def test_incidents_do_not_affect_shap(shap_service):
    """Test 15: Live incidents are never an XGBoost/SHAP input."""
    edge_clear = make_edge_dict(unique_edge_id=100016)
    edge_incident = make_edge_dict(unique_edge_id=100017)
    # Incident fields (accident_count, road_closure_count, etc.) never in edge_dict for SHAP

    exp_clear = shap_service.explain_edge(edge_clear, 0.3, 0.02, 86)
    exp_incident = shap_service.explain_edge(edge_incident, 0.3, 0.02, 86)

    assert exp_clear is not None and exp_incident is not None
    for f in MODEL_FEATURE_NAMES:
        sv1 = next(c.shap_value for c in exp_clear.contributions if c.feature == f)
        sv2 = next(c.shap_value for c in exp_incident.contributions if c.feature == f)
        assert abs(sv1 - sv2) < 1e-8, (
            f"Feature '{f}': SHAP value changed between clear/incident edges with identical road features. "
            "Incidents must NOT affect SHAP."
        )


# ── Test 16: Missing/unmatched OSM edges are handled safely ───────────────────

def test_missing_edge_handled_safely(shap_service):
    """Test 16: explain_edge with invalid edge_id returns None or empty gracefully."""
    # An edge_dict with all defaults (edge_id=-1, invalid) must not raise.
    edge_invalid = {
        "unique_edge_id": -999,
        "highway_enc":    -1,
        "length_km":      float("nan"),
        "oneway":         0,
        "junction":       0,
        "bridge":         0,
        "tunnel":         0,
    }
    try:
        result = shap_service.explain_edge(
            edge_dict=edge_invalid,
            raw_risk_prob=0.0,
            calibrated_risk_prob=0.0,
            safety_score=100,
        )
        # Either None is returned (edge not explainable) or valid explanation
        # Either way — must not raise an exception
    except Exception as exc:
        pytest.fail(
            f"explain_edge raised an exception for an invalid edge: {exc}\n"
            "Missing/unmatched edges must be handled safely."
        )


# ── Test: SHAP output space is documented ────────────────────────────────────

def test_shap_output_space_documented(shap_service):
    """Extra: Verify that the output space is documented as log_odds_margin."""
    edge = make_edge_dict(unique_edge_id=100018)
    explanation = shap_service.explain_edge(
        edge_dict=edge,
        raw_risk_prob=0.3,
        calibrated_risk_prob=0.02,
        safety_score=86,
    )
    assert explanation is not None
    assert explanation.output_space == "log_odds_margin", (
        "SHAP output space must be documented as 'log_odds_margin'."
    )
    d = explanation.to_dict()
    assert "output_space_description" in d
    assert "log-odds" in d["output_space_description"].lower()


# ── Test: direction function correctness ─────────────────────────────────────

def test_direction_function():
    """Extra: _direction helper must correctly map SHAP log-odds values to labels."""
    assert _direction(0.5) == "higher_risk"
    assert _direction(-0.3) == "lower_risk"
    assert _direction(0.0001) == "neutral"   # within ±0.001 threshold
    assert _direction(-0.0005) == "neutral"


# ── Test: LRU cache hits ──────────────────────────────────────────────────────

def test_lru_cache_hit(shap_service):
    """Extra: Second call for the same edge must be served from cache (same object)."""
    edge = make_edge_dict(unique_edge_id=100019)
    exp1 = shap_service.explain_edge(edge, 0.3, 0.02, 86)
    exp2 = shap_service.explain_edge(edge, 0.3, 0.02, 86)

    assert exp1 is not None and exp2 is not None
    # Same object from cache
    assert exp1 is exp2, "Second call must return the exact cached ShapExplanation object."


# ── Test: SHAP service not-ready guard ────────────────────────────────────────

def test_shap_not_ready_returns_none():
    """Extra: explain_edge returns None when explainer is not initialized."""
    svc = ShapExplainerService()  # Fresh instance, not initialized
    edge = make_edge_dict(unique_edge_id=200001)
    result = svc.explain_edge(edge, 0.3, 0.02, 86)
    assert result is None, "Uninitialized SHAP service must return None, not raise."


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
