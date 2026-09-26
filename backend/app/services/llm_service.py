"""
backend/app/services/llm_service.py
===================================
SafeRoute AI — AI Safety Assistant Service (Groq API + GPT-OSS 120B)

Architecture Position:
----------------------
The LLM is an EXPLANATION AND REASONING LAYER ONLY.
It is NOT the safety prediction model.

The LLM must NEVER calculate or modify:
  - XGBoost risk probability
  - calibrated risk probability
  - Safety Score
  - SHAP values
  - route geometry
  - incident matching

The backend remains the source of truth for all numerical results.
All numbers returned in API responses originate from XGBoost, Bayes calibration,
and the local SHAP TreeExplainer.

Model:
  openai/gpt-oss-120b through the Groq API.
  API key loaded strictly from environment variable (GROQ_API_KEY).
  Never exposed to the frontend or logged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# ── Dedicated System Prompt for GPT-OSS ─────────────────────────────────────────
SYSTEM_PROMPT = """You are SafeRoute AI's safety explanation assistant.

Your job is to explain structured evidence produced by SafeRoute AI.

The historical Safety Score is calculated by the backend using XGBoost and calibrated historical risk.

SHAP values explain the contribution of model features.

Traffic, incidents, road closures and weather are live conditions and are separate from the historical Safety Score.

Never invent numerical values.

Never calculate a new Safety Score.

Never modify the Safety Score.

Never claim that SHAP proves causation.

Use phrases such as:
- 'contributed to higher modeled historical risk'
- 'contributed to lower modeled historical risk'
- 'the model places more weight on...'

Do not claim:
- 'this feature caused the accident'
- 'this road will have an accident'
- 'this road is guaranteed to be safe'

Clearly distinguish historical modeled risk from current live conditions.

When information is unavailable, explicitly say that it is unavailable.

Format all responses as short, clean bullet points using a simple dash (- ).
Do NOT use markdown bold stars (**) or asterisks (*).
Do NOT write long narrative paragraphs.
Never include intro headers or title banners like 'AI Route Summary'."""

# Fallback response message when Groq API is unavailable or unconfigured
FALLBACK_EXPLANATION = "AI explanation temporarily unavailable."

# ── Directional statements mapping (SHAP values are log-odds, NOT percentages) ─
FEATURE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "highway_enc": {
        "higher_risk": "Road type pushed the model toward higher historical risk.",
        "lower_risk": "Road type pushed the model toward lower historical risk.",
        "neutral": "Road type had minimal influence on historical risk.",
        "name": "Road type",
    },
    "junction": {
        "higher_risk": "Junction characteristics pushed the model toward higher historical risk.",
        "lower_risk": "Lack of junction complexity pushed the model toward lower historical risk.",
        "neutral": "Junction characteristics had minimal influence on historical risk.",
        "name": "Junction",
    },
    "length_km": {
        "higher_risk": "Road segment length pushed the model toward higher historical risk.",
        "lower_risk": "Road segment length pushed the model toward lower historical risk.",
        "neutral": "Road segment length had minimal influence on historical risk.",
        "name": "Road segment length",
    },
    "oneway": {
        "higher_risk": "One-way street design pushed the model toward higher historical risk.",
        "lower_risk": "Two-way street design pushed the model toward lower historical risk.",
        "neutral": "Street directionality had minimal influence on historical risk.",
        "name": "One-way road",
    },
    "bridge": {
        "higher_risk": "Bridge infrastructure pushed the model toward higher historical risk.",
        "lower_risk": "Non-bridge roadway pushed the model toward lower historical risk.",
        "neutral": "Bridge presence had minimal influence on historical risk.",
        "name": "Bridge",
    },
    "tunnel": {
        "higher_risk": "Tunnel infrastructure pushed the model toward higher historical risk.",
        "lower_risk": "Open roadway design pushed the model toward lower historical risk.",
        "neutral": "Tunnel presence had minimal influence on historical risk.",
        "name": "Tunnel",
    },
}


def format_shap_statement(feature_name: str, direction: str) -> str:
    """Convert technical feature name and direction into human-readable statement."""
    feat_entry = FEATURE_DESCRIPTIONS.get(feature_name)
    if feat_entry:
        return feat_entry.get(direction, f"{feat_entry['name']} influenced the historical risk model.")
    return f"{feature_name} influenced the model ({direction.replace('_', ' ')})."


class LLMSafetyService:
    """
    Dedicated LLM Service interfacing with Groq API and GPT-OSS 120B.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._last_api_key: str = ""
        self._init_client()

    def _load_active_api_key(self) -> str:
        """
        Check os.environ, settings, and .env files directly so modifications
        to .env take effect immediately without requiring a full server reboot.
        """
        # 1. os.environ explicitly set (supports mock and patch in tests)
        if "GROQ_API_KEY" in os.environ:
            return os.environ.get("GROQ_API_KEY", "").strip()

        # 2. Settings instance
        try:
            settings_key = get_settings().groq_api_key.strip()
            if settings_key:
                return settings_key
        except Exception:
            pass

        # 3. Read .env file directly if available
        try:
            from pathlib import Path
            from dotenv import dotenv_values
            for env_path in [Path("../.env"), Path(".env"), Path("../../.env")]:
                if env_path.exists():
                    vals = dotenv_values(env_path)
                    v = vals.get("GROQ_API_KEY", "")
                    if v and v.strip():
                        return v.strip()
        except Exception:
            pass

        return ""

    def _init_client(self) -> None:
        """Initialize or refresh Groq client using the active API key."""
        self._get_client()

    def _get_client(self) -> Any:
        """Return the Groq client, dynamically re-initializing if key changed."""
        api_key = self._load_active_api_key()
        if not api_key:
            self._client = None
            self._last_api_key = ""
            return None

        if self._client is None or api_key != self._last_api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=api_key)
                self._last_api_key = api_key
                logger.info("[LLM] Groq client initialized with active API key.")
            except Exception as exc:
                logger.warning("[LLM] Failed to initialize Groq client: %s", exc)
                self._client = None
                self._last_api_key = ""

        return self._client

    @property
    def is_available(self) -> bool:
        """True if the Groq client is initialized with an active API key."""
        return self._get_client() is not None

    @property
    def model_name(self) -> str:
        """Return the configured Groq model (openai/gpt-oss-120b)."""
        return get_settings().groq_model

    def build_section_context(
        self,
        osm_edge_id: Optional[int],
        road_class: Optional[str],
        length_km: Optional[float],
        safety_score: Optional[int],
        calibrated_risk_prob: Optional[float],
        raw_risk_prob: Optional[float],
        top_shap_factors: List[Dict[str, Any]],
        traffic_condition: Optional[str] = None,
        incidents: Optional[List[Dict[str, Any]]] = None,
        weather: Optional[Dict[str, Any]] = None,
        user_question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build structured context object for a section explanation.
        All numerical values come directly from backend sources of truth.
        """
        # Format SHAP factors into non-percentage directional statements
        formatted_shap = []
        for factor in top_shap_factors:
            feat_key = factor.get("feature", "")
            direction = factor.get("direction", "neutral")
            label = factor.get("label", feat_key)
            shap_val = factor.get("shap_value", 0.0)
            formatted_shap.append({
                "feature": label,
                "direction": direction,
                "shap_value": round(float(shap_val), 4) if shap_val is not None else 0.0,
                "explanation_phrase": format_shap_statement(feat_key, direction),
            })

        # Structured context
        context = {
            "section": {
                "osm_edge_id": osm_edge_id if osm_edge_id is not None else "unavailable",
                "road_type": road_class or "standard roadway",
                "length_km": round(length_km, 3) if length_km is not None else "unavailable",
                "safety_score": safety_score if safety_score is not None else "unavailable",
                "calibrated_historical_risk": round(calibrated_risk_prob, 4) if calibrated_risk_prob is not None else "unavailable",
                "raw_risk_prob": round(raw_risk_prob, 4) if raw_risk_prob is not None else "unavailable",
            },
            "top_shap_factors": formatted_shap,
            "live_conditions": {
                "traffic": traffic_condition or "Normal flowing traffic",
                "incidents": [
                    {
                        "type": inc.get("type", "Incident"),
                        "distance_m": round(inc.get("distance_to_route_m", 0), 1) if inc.get("distance_to_route_m") is not None else "near section",
                    }
                    for inc in (incidents or [])
                ],
                "weather": weather or {"condition": "Clear / Normal conditions"},
            },
        }

        if user_question:
            context["user_question"] = user_question

        return context

    def build_route_context(
        self,
        route_id: str,
        distance_km: float,
        duration_minutes: float,
        safety_score: Optional[int],
        calibrated_risk_prob: Optional[float],
        top_shap_factors: List[Dict[str, Any]],
        live_conditions: Dict[str, Any],
        notable_segments: Optional[List[Dict[str, Any]]] = None,
        alternative_routes: Optional[List[Dict[str, Any]]] = None,
        user_question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build structured context object for an overall route summary.
        """
        formatted_shap = []
        for factor in top_shap_factors:
            feat_key = factor.get("feature", "")
            direction = factor.get("direction", "neutral")
            label = factor.get("label", feat_key)
            shap_val = factor.get("shap_value", 0.0)
            formatted_shap.append({
                "feature": label,
                "direction": direction,
                "shap_value": round(float(shap_val), 4) if shap_val is not None else 0.0,
                "explanation_phrase": format_shap_statement(feat_key, direction),
            })

        context = {
            "route": {
                "route_id": route_id,
                "distance_km": round(distance_km, 2),
                "duration_minutes": round(duration_minutes, 1),
                "safety_score": safety_score if safety_score is not None else "unavailable",
                "calibrated_historical_risk": round(calibrated_risk_prob, 4) if calibrated_risk_prob is not None else "unavailable",
            },
            "top_shap_factors": formatted_shap,
            "live_conditions": live_conditions,
            "notable_segments": notable_segments or [],
        }

        if alternative_routes:
            context["alternative_routes"] = alternative_routes

        if user_question:
            context["user_question"] = user_question

        return context

    def _build_deterministic_bullets(self, context: Dict[str, Any]) -> str:
        """Construct structured bullet points directly from context when LLM is unavailable or times out."""
        bullets = []
        route_info = context.get("route") or context.get("section") or {}
        score = route_info.get("safety_score")
        if score is not None and str(score).lower() != "unavailable":
            bullets.append(f"- Route Safety Score is {score}/100 based on historical road characteristics.")
        else:
            bullets.append("- Historical safety scoring is based on road infrastructure features.")

        factors = context.get("top_shap_factors") or []
        if factors:
            factor_names = [f.get("feature") for f in factors if f.get("feature")]
            if factor_names:
                bullets.append(f"- Key model factors influencing this score include {', '.join(factor_names[:3])}.")

        live = context.get("live_conditions") or {}
        traffic = live.get("traffic") or "Normal flowing traffic"
        incidents = live.get("incidents") or []
        inc_count = len(incidents)
        inc_str = f"with {inc_count} active incident(s) reported" if inc_count > 0 else "with no major incidents"
        bullets.append(f"- Current live conditions: {traffic} {inc_str}.")

        weather = live.get("weather") or {}
        w_desc = weather.get("description") or weather.get("condition") or "Clear conditions"
        temp = weather.get("temp_c")
        temp_str = f" at {temp}°C" if temp is not None else ""
        bullets.append(f"- Current weather is {w_desc.lower()}{temp_str}, separate from the historical model.")

        return "\n".join(bullets[:4])

    def generate_explanation(
        self,
        structured_context: Dict[str, Any],
        task_prompt: str,
        max_tokens: int = 800,
    ) -> str:
        """
        Call Groq GPT-OSS 120B with the structured evidence and task instruction.
        Uses max_tokens=800 to ensure reasoning models do not exhaust the token budget.
        Falls back to deterministic structured bullets if the API call ever fails.
        """
        client = self._get_client()
        if client is None:
            return self._build_deterministic_bullets(structured_context)

        settings = get_settings()
        user_message_content = (
            f"STRUCTURED EVIDENCE FROM SAFEROUTE AI:\n"
            f"```json\n{json.dumps(structured_context, indent=2)}\n```\n\n"
            f"TASK:\n{task_prompt}\n\n"
            f"Remember: Do not invent numbers, do not recalculate scores, and keep the explanation concise and clear."
        )

        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message_content},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                timeout=settings.groq_timeout_seconds,
            )

            if response.choices and len(response.choices) > 0:
                msg = response.choices[0].message
                answer = msg.content
                if not answer or not answer.strip():
                    # If model spent all tokens in reasoning, fallback to structured evidence
                    return self._build_deterministic_bullets(structured_context)

                cleaned = unicodedata.normalize("NFKC", answer.strip()).replace("**", "")
                cleaned = cleaned.replace("\u202f", " ").replace("\u00a0", " ")
                # Convert bullet sequences (*, -, •) into newline + dash
                cleaned = re.sub(r"(?:\r?\n|\s+)(?:[*•-]\s*)+", "\n- ", cleaned)
                # Strip section titles/headers
                cleaned = re.sub(r"(?i)AI Route Summary\s*[-–:]*\s*", "", cleaned)
                cleaned = re.sub(r"(?i)Historical safety information\s*[-–:]*\s*", "", cleaned)
                cleaned = re.sub(r"(?i)Key modeled risk contributors(?:\s*\([^)]*\))?\s*[-–:]*\s*", "", cleaned)

                raw_lines = re.split(r"[\r\n]+", cleaned)
                filtered_lines = []
                header_terms = {
                    "ai route summary",
                    "summary",
                    "historical safety information",
                    "key modeled risk contributors",
                    "shap analysis",
                }
                for ln in raw_lines:
                    p = ln.strip().lstrip("-–•: *").strip()
                    if not p:
                        continue
                    p_lower = p.lower().rstrip(":")
                    if any(p_lower == term or p_lower.startswith(term + ":") for term in header_terms):
                        continue
                    # If a line is too long and contains multiple sentences, split into individual bullet points
                    if len(p) > 140 and "." in p:
                        sentences = re.split(r"(?<=[.!?])\s+", p)
                        for s in sentences:
                            sc = s.strip().lstrip("-–•: *").strip()
                            if len(sc) > 10:
                                sc = sc[0].upper() + sc[1:]
                                filtered_lines.append(f"- {sc}")
                    else:
                        if len(p) > 10:
                            p = p[0].upper() + p[1:]
                            filtered_lines.append(f"- {p}")

                return "\n".join(filtered_lines[:4]) if filtered_lines else cleaned

            return self._build_deterministic_bullets(structured_context)

        except Exception as exc:
            err_type = exc.__class__.__name__
            err_str = str(exc)
            if "invalid_api_key" in err_str.lower() or "authenticationerror" in err_type.lower():
                logger.warning("[LLM] Groq authentication failed: 401 Invalid API Key. Please verify GROQ_API_KEY in .env.")
            else:
                logger.warning("[LLM] Groq API call failed: %s (%s). Generating structured fallback.", err_type, err_str[:100])
            return self._build_deterministic_bullets(structured_context)

    def explain_section(
        self,
        context: Dict[str, Any],
        user_question: Optional[str] = None,
    ) -> str:
        """Explain why a specific section has its historical score and summarize conditions."""
        if user_question:
            task_prompt = f"Answer the user's specific question in 2-3 short bullet points (using simple '- ' prefix, no asterisks): '{user_question}' using only the provided structured evidence."
        else:
            task_prompt = (
                "Provide a concise section summary in 2-3 short bullet points (using simple '- ' prefix, no asterisks, no headers). "
                "Explain why this road section received its historical Safety Score using the top SHAP factors, "
                "and briefly summarize live conditions (traffic, incidents, weather) keeping them clearly separated. "
                "Keep each bullet to 1 clear, direct sentence."
            )
        return self.generate_explanation(context, task_prompt, max_tokens=800)

    def explain_route_summary(
        self,
        context: Dict[str, Any],
        user_question: Optional[str] = None,
    ) -> str:
        """Generate concise AI Route Summary in clean bullet points without asterisks."""
        if user_question:
            task_prompt = f"Answer the user question about the route in 2-3 short bullet points (using simple '- ' prefix, no asterisks, no headers): '{user_question}' using only the provided evidence."
        else:
            task_prompt = (
                "Provide a concise route summary in 3-4 short bullet points (using simple '- ' prefix). "
                "FORMAT RULES: "
                "1. Do NOT write long paragraphs. "
                "2. Do NOT use markdown bold stars (**) or asterisks (*). "
                "3. Do NOT include section titles or headers like 'AI Route Summary'. "
                "4. Bullet 1: Route Safety Score rating and primary road factors. "
                "5. Bullet 2: Current traffic and active incidents (separate from score). "
                "6. Bullet 3: Current weather and driving conditions. "
                "7. If alternative_routes are provided, briefly compare this route's safety score to the alternatives in an additional bullet point. "
                "Keep each bullet to 1 clear, direct sentence."
            )
        return self.generate_explanation(context, task_prompt, max_tokens=800)

    def answer_question(
        self,
        context: Dict[str, Any],
        question: str,
    ) -> str:
        """Answer a user query strictly using the provided structured evidence."""
        task_prompt = f"Answer the user query: '{question}' using strictly the evidence provided. If information is unavailable, say so clearly."
        return self.generate_explanation(context, task_prompt, max_tokens=800)


# ── Module-level singleton ─────────────────────────────────────────────────────
_llm_service: Optional[LLMSafetyService] = None


def get_llm_service() -> LLMSafetyService:
    """Return singleton instance of LLMSafetyService."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMSafetyService()
    return _llm_service
