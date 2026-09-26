"""
backend/tests/test_ai_assistant.py
==================================
Comprehensive test suite for the LLM-powered AI Safety Assistant.

Validates the 15 critical requirements:
 1. Groq service initialization.
 2. Missing API key handling.
 3. Correct GPT-OSS model selection (openai/gpt-oss-120b).
 4. Structured context generation.
 5. Safety Score passed unchanged to LLM.
 6. SHAP values passed correctly.
 7. Live conditions passed separately.
 8. LLM cannot modify Safety Score.
 9. LLM cannot modify calibrated risk.
10. LLM cannot modify SHAP values.
11. Missing live data handled gracefully.
12. Groq API failure does not break routing.
13. "Why This Section?" receives the correct OSM edge.
14. 500m UI segment does not become a fake XGBoost observation.
15. No API key appears in frontend or logs.
"""

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.services.llm_service import (
    LLMSafetyService,
    SYSTEM_PROMPT,
    FALLBACK_EXPLANATION,
    format_shap_statement,
)
from app.config.settings import get_settings
from main import app


@pytest.fixture
def client():
    return TestClient(app)


# ── Test 1: Groq service initialization ─────────────────────────────────────────
def test_1_groq_service_initialization():
    """Test 1: LLMSafetyService initializes properly and exposes required attributes."""
    service = LLMSafetyService()
    assert hasattr(service, "is_available")
    assert hasattr(service, "model_name")
    assert hasattr(service, "generate_explanation")
    assert hasattr(service, "explain_section")
    assert hasattr(service, "explain_route_summary")


# ── Test 2: Missing API key handling ───────────────────────────────────────────
def test_2_missing_api_key_handling():
    """Test 2: When GROQ_API_KEY is missing/empty, service runs in fallback mode without crash."""
    with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
        with patch.object(get_settings(), "groq_api_key", ""):
            service = LLMSafetyService()
            assert service.is_available is False
            result = service.generate_explanation({"dummy": "data"}, "Explain this.")
            assert result == FALLBACK_EXPLANATION


# ── Test 3: Correct GPT-OSS model selection ────────────────────────────────────
def test_3_correct_gpt_oss_model_selection():
    """Test 3: Must use openai/gpt-oss-120b through the Groq API."""
    settings = get_settings()
    assert settings.groq_model == "openai/gpt-oss-120b"
    service = LLMSafetyService()
    assert service.model_name == "openai/gpt-oss-120b"


# ── Test 4: Structured context generation ─────────────────────────────────────
def test_4_structured_context_generation():
    """Test 4: Generates clean, structured context containing all backend evidence."""
    service = LLMSafetyService()
    context = service.build_section_context(
        osm_edge_id=12345,
        road_class="Primary",
        length_km=0.450,
        safety_score=78,
        calibrated_risk_prob=0.048,
        raw_risk_prob=0.312,
        top_shap_factors=[
            {"feature": "highway_enc", "label": "Road type", "direction": "higher_risk", "shap_value": 0.31},
            {"feature": "junction", "label": "Junction", "direction": "higher_risk", "shap_value": 0.18},
            {"feature": "length_km", "label": "Road segment length", "direction": "lower_risk", "shap_value": -0.08},
        ],
        traffic_condition="Heavy",
        incidents=[{"type": "Road Closure", "distance_to_route_m": 0.0}],
        weather={"condition": "Rain expected"},
        user_question="Why is this score 78?",
    )

    assert "section" in context
    assert context["section"]["osm_edge_id"] == 12345
    assert context["section"]["safety_score"] == 78
    assert context["section"]["calibrated_historical_risk"] == 0.048
    assert len(context["top_shap_factors"]) == 3
    assert "live_conditions" in context
    assert context["live_conditions"]["traffic"] == "Heavy"
    assert context["user_question"] == "Why is this score 78?"


# ── Test 5: Safety Score passed unchanged to LLM ──────────────────────────────
def test_5_safety_score_passed_unchanged():
    """Test 5: Safety score is passed verbatim to LLM context without alteration."""
    service = LLMSafetyService()
    original_score = 64
    context = service.build_section_context(
        osm_edge_id=999,
        road_class="Secondary",
        length_km=0.2,
        safety_score=original_score,
        calibrated_risk_prob=0.1296,
        raw_risk_prob=0.55,
        top_shap_factors=[],
    )
    assert context["section"]["safety_score"] == original_score
    assert context["section"]["safety_score"] == 64


# ── Test 6: SHAP values passed correctly ───────────────────────────────────────
def test_6_shap_values_passed_correctly():
    """Test 6: SHAP values passed directionally without percentage claims."""
    service = LLMSafetyService()
    factors = [
        {"feature": "highway_enc", "label": "Road type", "direction": "higher_risk", "shap_value": 0.31},
        {"feature": "length_km", "label": "Road segment length", "direction": "lower_risk", "shap_value": -0.08},
    ]
    context = service.build_section_context(
        osm_edge_id=1,
        road_class="Primary",
        length_km=0.5,
        safety_score=80,
        calibrated_risk_prob=0.04,
        raw_risk_prob=0.2,
        top_shap_factors=factors,
    )
    shap_list = context["top_shap_factors"]
    assert len(shap_list) == 2
    assert shap_list[0]["shap_value"] == 0.31
    assert "Road type pushed the model toward higher historical risk." in shap_list[0]["explanation_phrase"]
    assert "%" not in shap_list[0]["explanation_phrase"]


# ── Test 7: Live conditions passed separately ─────────────────────────────────
def test_7_live_conditions_passed_separately():
    """Test 7: Live conditions are in an isolated section separate from historical risk."""
    service = LLMSafetyService()
    context = service.build_section_context(
        osm_edge_id=10,
        road_class="Motorway",
        length_km=1.2,
        safety_score=85,
        calibrated_risk_prob=0.02,
        raw_risk_prob=0.1,
        top_shap_factors=[],
        traffic_condition="Severe Congestion",
        incidents=[{"type": "Accident", "distance_to_route_m": 50}],
        weather={"condition": "Heavy Rain", "rain_mm": 12.0},
    )
    # Historical risk must NOT contain live conditions
    assert "traffic" not in context["section"]
    assert "incidents" not in context["section"]
    assert "weather" not in context["section"]
    # Live conditions are in their own isolated container
    assert "live_conditions" in context
    assert context["live_conditions"]["traffic"] == "Severe Congestion"


# ── Test 8: LLM cannot modify Safety Score ────────────────────────────────────
def test_8_llm_cannot_modify_safety_score(client):
    """Test 8: Backend response guarantees Safety Score remains identical even if LLM hallucinated."""
    fake_llm_text = "I calculated your Safety Score and updated it to 99/100 because traffic is clear."
    
    with patch("app.services.llm_service.LLMSafetyService.generate_explanation", return_value=fake_llm_text):
        with patch("app.risk_engine.RiskEngine.explain_edge", return_value={
            "osm_edge_id": 9999,
            "raw_risk_prob": 0.35,
            "calibrated_risk_prob": 0.0625,
            "safety_score": 75,
            "top_factors": [
                {"feature": "highway_enc", "label": "Road type", "direction": "higher_risk", "shap_value": 0.25}
            ]
        }):
            # Set cache in risk engine
            from app.risk_engine import get_risk_engine
            engine = get_risk_engine()
            engine._edge_cache[9999] = (0.35, 0.0625, 75)

            resp = client.post("/api/ai/explain-section", json={"osm_edge_id": 9999})
            assert resp.status_code == 200
            data = resp.json()
            # Authoritative score MUST remain 75, NOT 99!
            assert data["safety_score"] == 75


# ── Test 9: LLM cannot modify calibrated risk ─────────────────────────────────
def test_9_llm_cannot_modify_calibrated_risk(client):
    """Test 9: Calibrated risk probability is returned strictly from the backend."""
    from app.risk_engine import get_risk_engine
    engine = get_risk_engine()
    engine._edge_cache[8888] = (0.42, 0.0784, 72)

    with patch("app.services.llm_service.LLMSafetyService.generate_explanation", return_value="Historical risk explanation"):
        with patch("app.risk_engine.RiskEngine.explain_edge", return_value={
            "osm_edge_id": 8888,
            "raw_risk_prob": 0.42,
            "calibrated_risk_prob": 0.0784,
            "safety_score": 72,
            "top_factors": []
        }):
            resp = client.post("/api/ai/explain-section", json={"osm_edge_id": 8888})
            assert resp.status_code == 200
            data = resp.json()
            assert data["calibrated_historical_risk"] == 0.0784


# ── Test 10: LLM cannot modify SHAP values ────────────────────────────────────
def test_10_llm_cannot_modify_shap_values(client):
    """Test 10: SHAP values returned in top_factors come from TreeExplainer, not LLM."""
    from app.risk_engine import get_risk_engine
    engine = get_risk_engine()
    engine._edge_cache[7777] = (0.3, 0.04, 80)

    expected_shap = [
        {"feature": "junction", "label": "Junction", "direction": "higher_risk", "shap_value": 0.2234}
    ]

    with patch("app.services.llm_service.LLMSafetyService.generate_explanation", return_value="Explanation"):
        with patch("app.risk_engine.RiskEngine.explain_edge", return_value={
            "osm_edge_id": 7777,
            "raw_risk_prob": 0.3,
            "calibrated_risk_prob": 0.04,
            "safety_score": 80,
            "top_factors": expected_shap,
        }):
            resp = client.post("/api/ai/explain-section", json={"osm_edge_id": 7777})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["top_factors"]) == 1
            assert data["top_factors"][0]["shap_value"] == 0.2234
            assert data["top_factors"][0]["direction"] == "higher_risk"


# ── Test 11: Missing live data handled gracefully ──────────────────────────────
def test_11_missing_live_data_handled_gracefully():
    """Test 11: When live traffic/weather/incidents are None or unavailable, no crash."""
    service = LLMSafetyService()
    context = service.build_section_context(
        osm_edge_id=1,
        road_class=None,
        length_km=None,
        safety_score=None,
        calibrated_risk_prob=None,
        raw_risk_prob=None,
        top_shap_factors=[],
        traffic_condition=None,
        incidents=None,
        weather=None,
    )
    assert context["section"]["safety_score"] == "unavailable"
    assert context["live_conditions"]["traffic"] == "Normal flowing traffic"
    assert context["live_conditions"]["incidents"] == []


# ── Test 12: Groq API failure does not break routing ───────────────────────────
def test_12_groq_api_failure_does_not_break_routing(client):
    """Test 12: Groq API exception results in fallback explanation; does NOT raise 500."""
    service = LLMSafetyService()
    service._client = MagicMock()
    service._client.chat.completions.create.side_effect = Exception("Groq Connection Error")

    result = service.generate_explanation({"dummy": 1}, "Test prompt")
    assert result == FALLBACK_EXPLANATION

    # Test API endpoint handles failure gracefully
    with patch("app.services.llm_service.LLMSafetyService.generate_explanation", return_value=FALLBACK_EXPLANATION):
        resp = client.post("/api/ai/explain-section", json={"osm_edge_id": 9999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == FALLBACK_EXPLANATION
        assert data["status"] == "fallback"


# ── Test 13: "Why This Section?" receives correct OSM edge ────────────────────
def test_13_why_this_section_receives_correct_edge(client):
    """Test 13: explain-section with edge_id correctly routes to that specific OSM edge."""
    from app.risk_engine import get_risk_engine
    engine = get_risk_engine()
    target_edge_id = 55555
    engine._edge_cache[target_edge_id] = (0.25, 0.03, 83)

    with patch("app.risk_engine.RiskEngine.explain_edge") as mock_explain:
        mock_explain.return_value = {
            "osm_edge_id": target_edge_id,
            "raw_risk_prob": 0.25,
            "calibrated_risk_prob": 0.03,
            "safety_score": 83,
            "top_factors": [],
        }
        with patch("app.services.llm_service.LLMSafetyService.generate_explanation", return_value="Valid explanation"):
            resp = client.post("/api/ai/explain-section", json={"osm_edge_id": target_edge_id})
            assert resp.status_code == 200
            mock_explain.assert_called_once_with(target_edge_id)
            data = resp.json()
            assert data["osm_edge_id"] == target_edge_id
            assert data["safety_score"] == 83


# ── Test 14: 500m UI segment does not become a fake XGBoost observation ───────
def test_14_ui_segment_not_fake_xgboost_observation(client):
    """
    Test 14: 500m UI segment with coordinates queries underlying OSM edges
    and aggregates their original training-edge SHAP and risk values.
    """
    sample_coords = [
        [77.5946, 12.9716],
        [77.5950, 12.9720],
        [77.5955, 12.9725],
    ]

    with patch("app.features.osm_matcher.OSMMatcher.match_segment") as mock_match:
        # Mock two underlying OSM edges
        mock_match.return_value = [
            {"unique_edge_id": 101, "highway": "primary", "length_km": 0.120, "traversed_length_m": 60.0},
            {"unique_edge_id": 102, "highway": "secondary", "length_km": 0.080, "traversed_length_m": 40.0},
        ]
        with patch("app.risk_engine.RiskEngine.score_osm_edges") as mock_score:
            mock_score.return_value = []
            from app.risk_engine import get_risk_engine
            engine = get_risk_engine()
            engine._edge_cache[101] = (0.2, 0.02, 86)
            engine._edge_cache[102] = (0.3, 0.04, 80)

            with patch("app.services.llm_service.LLMSafetyService.generate_explanation", return_value="Segment explanation"):
                resp = client.post("/api/ai/explain-section", json={
                    "segment_id": "route_1_seg_001",
                    "segment_coords": sample_coords,
                })
                assert resp.status_code == 200
                data = resp.json()
                # Underlying edges were matched
                mock_match.assert_called_once()
                # Length-weighted score between 80 and 86
                assert data["safety_score"] is not None
                assert 80 <= data["safety_score"] <= 86


# ── Test 15: No API key appears in frontend or logs ────────────────────────────
def test_15_no_api_key_in_responses(client):
    """Test 15: API responses from AI endpoints NEVER include the Groq API key."""
    fake_key = "gsk_super_secret_test_key_123456789"
    with patch.dict(os.environ, {"GROQ_API_KEY": fake_key}):
        resp = client.post("/api/ai/explain-section", json={"osm_edge_id": 9999})
        assert fake_key not in resp.text

        resp_route = client.post("/api/ai/explain-route", json={"route_id": "route_1", "safety_score": 75})
        assert fake_key not in resp_route.text

        resp_ask = client.post("/api/ai/ask", json={"question": "What is this score?"})
        assert fake_key not in resp_ask.text

        resp_health = client.get("/health")
        assert fake_key not in resp_health.text
