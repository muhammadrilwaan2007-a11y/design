"""
backend/app/shap_explainer.py
==============================
SafeRoute AI — Local SHAP Explanation Layer

Architecture position
---------------------
This module is an EXPLANATION LAYER ONLY.

It does NOT:
  - retrain the XGBoost model
  - change raw_risk_prob, calibrated_risk_prob, or safety_score
  - feed live traffic / weather / incidents into the model
  - color the heatmap
  - determine the Safety Score

It only answers the question:
  "For this specific OSM edge, which of the six structural features pushed
   the XGBoost prediction higher or lower compared to the average road?"

Architecture
------------
OSM road features (six features)
       ↓
XGBoost
       ↓
raw_risk_prob
       ↓
Bayes calibration
       ↓
calibrated_risk_prob  →  Safety Score
                           ↘
                            SHAP TreeExplainer  (explanation only, no score impact)
                                ↓
                        ShapExplanation (per-edge)

SHAP Output Space
-----------------
TreeSHAP with XGBClassifier uses the raw margin/log-odds space (model_output="raw").
Each shap_value represents the contribution of a feature to the model's
log-odds output (margin), NOT to the final probability.

The property that holds:
    base_value + sum(shap_values) ≈ model log-odds (for that observation)

This is documented in the API response. We do NOT convert SHAP values to
probability differences because the sigmoid transform is non-linear and the
relationship is not additive in probability space.

Six model features (must match training order exactly)
------------------------------------------------------
Source: backend/ml/train_xgboost_baseline.py, line ~179
    X = df[["highway_enc", "length_km", "oneway", "junction", "bridge", "tunnel"]]

Caching
-------
- The TreeExplainer is initialised once at module level and reused.
- Per-edge explanations are cached in a simple LRU dict keyed by
  (unique_edge_id, model_path) to avoid redundant SHAP computation.
- Cache capacity: 4096 edges.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# NOTE: We do NOT import from app.risk_engine at module level to avoid circular imports.
# (risk_engine imports from shap_explainer, shap_explainer used to import from risk_engine)
# Instead, we define the constants inline here — they are identical to what is in risk_engine.py.
# If you change the feature order or highway encoding in risk_engine.py, update here too.

# ── Six XGBoost model features (must match training order exactly) ────────────
# Source: backend/ml/train_xgboost_baseline.py
#    X = df[["highway_enc", "length_km", "oneway", "junction", "bridge", "tunnel"]]
MODEL_FEATURE_NAMES: list[str] = [
    "highway_enc",
    "length_km",
    "oneway",
    "junction",
    "bridge",
    "tunnel",
]

# ── Highway risk order encoding (must match risk_engine.py HIGHWAY_RISK_ORDER) ─
HIGHWAY_RISK_ORDER_LOCAL: dict[str, int] = {
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

logger = logging.getLogger(__name__)

# ── SHAP output space documentation ───────────────────────────────────────────
SHAP_OUTPUT_SPACE = "log_odds_margin"
SHAP_OUTPUT_DESCRIPTION = (
    "SHAP values are computed in the model margin / log-odds space. "
    "A positive shap_value means the feature pushed the model toward higher "
    "predicted risk (higher log-odds). "
    "base_value + sum(shap_values) approximates the model log-odds for this observation. "
    "SHAP values do NOT represent percentage-point changes in accident probability."
)

# ── Feature display labels (UI-facing) ────────────────────────────────────────
FEATURE_LABELS: dict[str, str] = {
    "highway_enc": "Road type",
    "length_km":   "Road segment length",
    "oneway":      "One-way road",
    "junction":    "Junction",
    "bridge":      "Bridge",
    "tunnel":      "Tunnel",
}

# ── Inverse highway encoding ──────────────────────────────────────────────────
# Built from the local copy of HIGHWAY_RISK_ORDER to avoid circular imports.
# Resolve duplicates by preferring the canonical class name (no _link suffix).
HIGHWAY_ENC_TO_CLASS: dict[int, str] = {}
for _cls, _enc in HIGHWAY_RISK_ORDER_LOCAL.items():
    if _enc not in HIGHWAY_ENC_TO_CLASS or not _cls.endswith("_link"):
        HIGHWAY_ENC_TO_CLASS[_enc] = _cls

# ── Maximum LRU cache size ────────────────────────────────────────────────────
_MAX_CACHE_SIZE = 4096


# ══════════════════════════════════════════════════════════════════════════════
# ShapContribution
# ══════════════════════════════════════════════════════════════════════════════

class ShapContribution:
    """Single feature contribution entry in a SHAP explanation."""

    __slots__ = ("feature", "label", "value", "display_value", "shap_value", "direction")

    def __init__(
        self,
        feature: str,
        label: str,
        value: Any,
        display_value: str,
        shap_value: float,
        direction: str,   # "higher_risk" | "lower_risk" | "neutral"
    ) -> None:
        self.feature = feature
        self.label = label
        self.value = value
        self.display_value = display_value
        self.shap_value = shap_value
        self.direction = direction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature":       self.feature,
            "label":         self.label,
            "value":         self.value,
            "display_value": self.display_value,
            "shap_value":    round(self.shap_value, 6),
            "direction":     self.direction,
        }


# ══════════════════════════════════════════════════════════════════════════════
# ShapExplanation
# ══════════════════════════════════════════════════════════════════════════════

class ShapExplanation:
    """
    Complete Local SHAP explanation for a single OSM road edge.

    The six contributions are sorted by absolute SHAP magnitude.
    top_factors = the three largest-magnitude contributors.
    """

    def __init__(
        self,
        osm_edge_id: int,
        raw_risk_prob: float,
        calibrated_risk_prob: float,
        safety_score: int,
        shap_base_value: float,
        shap_model_output: float,
        contributions: List[ShapContribution],
    ) -> None:
        self.osm_edge_id = osm_edge_id
        self.raw_risk_prob = raw_risk_prob
        self.calibrated_risk_prob = calibrated_risk_prob
        self.safety_score = safety_score
        self.shap_base_value = shap_base_value
        self.shap_model_output = shap_model_output
        self.output_space = SHAP_OUTPUT_SPACE
        # Sort all contributions by absolute magnitude (descending)
        self.contributions: List[ShapContribution] = sorted(
            contributions, key=lambda c: abs(c.shap_value), reverse=True
        )
        self.top_factors: List[ShapContribution] = self.contributions[:3]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "osm_edge_id":              self.osm_edge_id,
            "raw_risk_prob":            round(self.raw_risk_prob, 6),
            "calibrated_risk_prob":     round(self.calibrated_risk_prob, 6),
            "safety_score":             self.safety_score,
            "shap_base_value":          round(self.shap_base_value, 6),
            "shap_model_output":        round(self.shap_model_output, 6),
            "output_space":             self.output_space,
            "output_space_description": SHAP_OUTPUT_DESCRIPTION,
            "explanation":              [c.to_dict() for c in self.contributions],
            "top_factors":              [c.to_dict() for c in self.top_factors],
        }


# ══════════════════════════════════════════════════════════════════════════════
# Feature display helpers
# ══════════════════════════════════════════════════════════════════════════════

def _display_value(feature: str, raw_value: Any) -> str:
    """Convert a raw feature value to a human-readable display string."""
    if feature == "highway_enc":
        road_class = HIGHWAY_ENC_TO_CLASS.get(int(raw_value), "unknown")
        return road_class.replace("_", " ").title()

    if feature in ("oneway", "junction", "bridge", "tunnel"):
        return "Yes" if int(raw_value) == 1 else "No"

    if feature == "length_km":
        km = float(raw_value)
        if km < 1.0:
            return f"{round(km * 1000)} m"
        return f"{round(km, 3)} km"

    return str(raw_value)


def _direction(shap_val: float) -> str:
    """Map a SHAP log-odds contribution to a directional label."""
    if shap_val > 0.001:
        return "higher_risk"
    if shap_val < -0.001:
        return "lower_risk"
    return "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# ShapExplainerService
# ══════════════════════════════════════════════════════════════════════════════

class ShapExplainerService:
    """
    Singleton service wrapping shap.TreeExplainer on the XGBoost baseline model.

    - Initialized ONCE after RiskEngine loads the model.
    - TreeExplainer is kept in memory and reused for all requests.
    - Per-edge results are cached in an LRU dict (capacity: 4096 entries).
    - Key per entry: (unique_edge_id, model_path).

    IMPORTANT:
    This service NEVER modifies raw_risk_prob, calibrated_risk_prob, or safety_score.
    It only computes the explanation for an existing prediction.
    """

    def __init__(self) -> None:
        self._explainer: Any = None
        self._model_path: Optional[str] = None
        self._cache: Dict[tuple, ShapExplanation] = {}
        self._cache_order: List[tuple] = []

    def initialize(self, model: Any, model_path: str) -> None:
        """
        Initialize (or re-initialize) the TreeExplainer with a loaded XGBClassifier.

        Safe to call multiple times — no-op if model_path has not changed.

        Parameters
        ----------
        model : XGBClassifier
            The loaded XGBoost model (must NOT be reloaded or modified here).
        model_path : str
            Path string used as cache key and for logging.
        """
        if self._explainer is not None and self._model_path == model_path:
            return  # Already initialized with the same model

        try:
            import shap  # deferred import — only needed when SHAP is requested
            logger.info("[SHAP] Initializing TreeExplainer for model: %s", model_path)

            # model_output="raw" → explanations in log-odds (margin) space.
            # This is mathematically consistent: base_value + sum(shaps) = model log-odds.
            self._explainer = shap.TreeExplainer(model, model_output="raw")
            self._model_path = model_path
            self._cache.clear()
            self._cache_order.clear()

            # Log the base value for transparency
            ev = self._explainer.expected_value
            if isinstance(ev, (list, np.ndarray)):
                ev_arr = np.asarray(ev)
                ev_scalar = float(ev_arr[-1]) if len(ev_arr) > 1 else float(ev_arr[0])
            else:
                ev_scalar = float(ev)
            logger.info(
                "[SHAP] TreeExplainer ready. Base value (expected log-odds): %.6f | "
                "SHAP output space: %s",
                ev_scalar,
                SHAP_OUTPUT_SPACE,
            )
        except Exception as exc:
            logger.error("[SHAP] Failed to initialize TreeExplainer: %s", exc, exc_info=True)
            self._explainer = None

    @property
    def is_ready(self) -> bool:
        """True if the TreeExplainer is initialized and ready."""
        return self._explainer is not None

    # ── LRU helpers ────────────────────────────────────────────────────────────

    def _lru_get(self, key: tuple) -> Optional[ShapExplanation]:
        if key in self._cache:
            self._cache_order.remove(key)
            self._cache_order.append(key)
            return self._cache[key]
        return None

    def _lru_put(self, key: tuple, value: ShapExplanation) -> None:
        if key in self._cache:
            self._cache_order.remove(key)
        elif len(self._cache) >= _MAX_CACHE_SIZE:
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]
        self._cache[key] = value
        self._cache_order.append(key)

    # ── Core explanation method ─────────────────────────────────────────────────

    def explain_edge(
        self,
        edge_dict: Dict[str, Any],
        raw_risk_prob: float,
        calibrated_risk_prob: float,
        safety_score: int,
    ) -> Optional[ShapExplanation]:
        """
        Compute (or retrieve from LRU cache) Local SHAP explanation for one OSM edge.

        Parameters
        ----------
        edge_dict : dict
            Must contain the six model features (same dict format as RiskEngine):
              unique_edge_id, highway_enc, length_km, oneway, junction, bridge, tunnel
            CRITICAL: length_km must be the ORIGINAL OSM training-edge length,
            NOT the 500m UI visualization segment length.
        raw_risk_prob : float
            Raw XGBoost probability for this edge (from RiskEngine cache).
            NOT modified by this method.
        calibrated_risk_prob : float
            Bayes-calibrated probability (from RiskEngine cache).
            NOT modified by this method.
        safety_score : int
            Historical Safety Score 0-100 (from RiskEngine cache).
            NOT modified by this method.

        Returns
        -------
        ShapExplanation | None
            None if the explainer is not ready or computation fails.
        """
        if not self.is_ready:
            logger.warning("[SHAP] Explainer not ready — cannot explain edge.")
            return None

        edge_id = int(edge_dict.get("unique_edge_id", -1))
        cache_key = (edge_id, self._model_path)

        cached = self._lru_get(cache_key)
        if cached is not None:
            logger.debug("[SHAP] Cache hit for edge_id=%d", edge_id)
            return cached

        # Build the exact six-feature row — original OSM training-edge length
        feature_row = {
            "highway_enc": int(edge_dict.get("highway_enc", -1)),
            "length_km":   float(edge_dict.get("length_km", float("nan"))),
            "oneway":      int(edge_dict.get("oneway", 0)),
            "junction":    int(edge_dict.get("junction", 0)),
            "bridge":      int(edge_dict.get("bridge", 0)),
            "tunnel":      int(edge_dict.get("tunnel", 0)),
        }

        try:
            X_single = pd.DataFrame([feature_row], columns=MODEL_FEATURE_NAMES)  # pyright: ignore[reportArgumentType]
            raw_shap = self._explainer.shap_values(X_single)

            # Normalise output shape across SHAP versions
            # XGBClassifier with model_output="raw":
            #   SHAP >=0.42: 2D ndarray shape (1, n_features)
            #   SHAP <0.42 binary: list of [neg_class, pos_class] each (1, n_features)
            if isinstance(raw_shap, list):
                sv_raw = raw_shap[-1] if len(raw_shap) > 1 else raw_shap[0]
            else:
                sv_raw = raw_shap

            sv = np.asarray(sv_raw, dtype=float).reshape(-1)  # shape (6,)

            # Base value normalisation
            ev = self._explainer.expected_value
            if isinstance(ev, (list, np.ndarray)):
                ev_arr = np.asarray(ev, dtype=float)
                base_value = float(ev_arr[-1]) if len(ev_arr) > 1 else float(ev_arr[0])
            else:
                base_value = float(ev)

            model_output = base_value + float(sv.sum())

            # Build feature contributions
            contributions: List[ShapContribution] = []
            row_values = X_single.iloc[0]
            for feat_name, shap_val in zip(MODEL_FEATURE_NAMES, sv):
                raw_val = row_values[feat_name]
                contributions.append(
                    ShapContribution(
                        feature=feat_name,
                        label=FEATURE_LABELS.get(feat_name, feat_name),
                        value=raw_val,
                        display_value=_display_value(feat_name, raw_val),
                        shap_value=float(shap_val),
                        direction=_direction(float(shap_val)),
                    )
                )

            explanation = ShapExplanation(
                osm_edge_id=edge_id,
                raw_risk_prob=raw_risk_prob,
                calibrated_risk_prob=calibrated_risk_prob,
                safety_score=safety_score,
                shap_base_value=base_value,
                shap_model_output=model_output,
                contributions=contributions,
            )

            self._lru_put(cache_key, explanation)
            logger.debug(
                "[SHAP] Edge %d explained: base=%.4f output=%.4f top=%s (dir=%s)",
                edge_id,
                base_value,
                model_output,
                explanation.top_factors[0].feature if explanation.top_factors else "none",
                explanation.top_factors[0].direction if explanation.top_factors else "none",
            )
            return explanation

        except Exception as exc:
            logger.error("[SHAP] Failed to explain edge_id=%d: %s", edge_id, exc, exc_info=True)
            return None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return LRU cache statistics."""
        return {
            "cache_size":      len(self._cache),
            "cache_capacity":  _MAX_CACHE_SIZE,
            "model_path":      self._model_path,
            "explainer_ready": self.is_ready,
        }

    def clear_cache(self) -> None:
        """Clear the LRU cache (e.g., after a model reload)."""
        self._cache.clear()
        self._cache_order.clear()
        logger.info("[SHAP] Explanation LRU cache cleared.")


# ── Module-level singleton ─────────────────────────────────────────────────────
_shap_service_instance: Optional[ShapExplainerService] = None


def get_shap_service() -> ShapExplainerService:
    """Return the module-level ShapExplainerService singleton (lazy init)."""
    global _shap_service_instance
    if _shap_service_instance is None:
        _shap_service_instance = ShapExplainerService()
    return _shap_service_instance


def initialize_shap_service(model: Any, model_path: str) -> None:
    """
    Initialize the module-level SHAP service with the already-loaded XGBoost model.
    Called ONCE from RiskEngine after the model is loaded from disk.
    """
    get_shap_service().initialize(model, model_path)
