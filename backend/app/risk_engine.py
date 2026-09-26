"""
backend/app/risk_engine.py
==========================
SafeRoute AI — Module 8: Historical Risk Engine

Architecture
------------
This module is the ONLY place where the XGBoost model is loaded and called.

Two-stage design (keeping concerns cleanly separated):

  Stage 1 — XGBoost historical risk & locked Bayes probability calibration
    OSM structural features → model.predict_proba() → raw_risk_prob [0, 1]
    raw_risk_prob → Bayes unbiasing (scale_pos_weight=67.53) → calibrated_risk_prob [0, 1]
    Features: highway_enc, length_km, oneway, junction, bridge, tunnel
    These are the EXACT features the model was trained on (xgboost_baseline.json).
    The theoretical Bayes correction exactly reverses the training scale_pos_weight odds
    shift and was statistically validated on the untouched held-out test set (ECE=0.048%,
    Brier=0.012235, Log Loss=0.054534, Slope=0.9880, Intercept=-0.0190).

  Stage 2 — Live-condition adjustment (isolated diagnostics)
    Live conditions (rain, low-vis, wind, TomTom incidents, congestion) are NEVER
    fed into XGBoost and do NOT modify the historical Safety Score.
    Deductions are computed solely as separate diagnostic annotations.

  Final → Safety Score [0, 100]
    score = 100 - sqrt(calibrated_risk_prob) * 100
    100 = lowest estimated structural risk (safest)
      0 = highest estimated structural risk (most dangerous)

Important design constraints
-----------------------------
- The model is loaded ONCE at class initialization and reused for all requests.
- The XGBoost model was trained on OSM structural features only. No live data
  was used during training. Live data must not silently become model inputs.
- The SegmentFeatureVector schema already carries all live data (incidents,
  traffic, weather) from upstream pipeline steps. The adjustment layer reads
  those fields but does not pass them to XGBoost.
- All score values are clamped to [0, 100]. No score can underflow or overflow.

Road closures
-------------
TomTom's calculateRoute API (traffic=true) already refuses to route through
closed roads. If a road is fully closed, it will not appear in the route at all.
Partial closures (lane closures) may appear in `road_closure_count`; we do
NOT further penalize for these in the XGBoost stage because the historical
model already encodes road-type risk. Any additional navigation-layer logic
(e.g., warning text) is handled by the frontend consuming the incidents array,
not by the Safety Score.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from app.config.settings import get_settings
from app.schemas.features import SegmentFeatureVector, OSMHeatmapEdge, SegmentGeometry
from app.features.osm_matcher import get_osm_matcher
from app.calibration import get_calibrator
# NOTE: app.shap_explainer is imported lazily inside _load_model() to avoid
# circular imports (shap_explainer needs MODEL_FEATURE_NAMES from this module).

logger = logging.getLogger(__name__)

# ── XGBoost feature names (must match training script exactly) ─────────────────
# Source: backend/ml/train_xgboost_baseline.py — line 179
# X = df[["highway_enc", "length_km", "oneway", "junction", "bridge", "tunnel"]]
MODEL_FEATURE_NAMES: list[str] = [
    "highway_enc",
    "length_km",
    "oneway",
    "junction",
    "bridge",
    "tunnel",
]

# ── Highway → ordinal encoding (must be identical to training preprocessing) ───
# Source: backend/ml/train_xgboost_baseline.py — lines 139-155
HIGHWAY_RISK_ORDER: dict[str, int] = {
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

# Severe congestion threshold — below this speed-ratio we apply a small deduction
_SEVERE_CONGESTION_RATIO = 0.7  # congestion_ratio = 1 - (current_speed / free_flow)


# ══════════════════════════════════════════════════════════════════════════════
# Feature extraction helpers
# ══════════════════════════════════════════════════════════════════════════════

def _clean_highway(raw_value: object) -> str:
    """
    Normalize the highway tag from SegmentFeatureVector.road_class.

    The field is currently None in V1 (OSM road_class is not yet propagated
    from the OSM network into the route segments). When unavailable, we fall
    back to an 'unknown' token which maps to -1 (the fillna sentinel used
    during training).

    Source transform mirrors train_xgboost_baseline.py clean_highway().
    """
    if raw_value is None:
        return "unknown"
    hw = str(raw_value)
    if hw.startswith("["):
        hw = hw.replace("[", "").replace("]", "").replace("'", "")
        return hw.split(",")[0].strip()
    return hw.strip()


def _encode_highway(highway_str: str) -> int:
    """Return ordinal encoding for a highway string; -1 for unknown types."""
    return HIGHWAY_RISK_ORDER.get(highway_str, -1)


def _segment_to_feature_row(seg: SegmentFeatureVector) -> dict:
    """
    Convert a SegmentFeatureVector into the exact dict of features expected
    by the XGBoost model (MODEL_FEATURE_NAMES order).

    Missing or None values use the XGBoost native missing-value sentinel (NaN).
    XGBoost handles NaN natively via its missing-value split logic.

    Road-class and speed-limit fields are None in V1 (future extension).
    highway_enc falls back to -1 (unknown) — the model's catch-all bucket for
    road types not seen during training.
    """
    hw_str = _clean_highway(seg.road_class)  # None → "unknown" in V1
    hw_enc = _encode_highway(hw_str)

    length_km = seg.segment_length_km if seg.segment_length_km is not None else float("nan")

    # oneway: SegmentFeatureVector does not carry this directly from OSM.
    # Default to 0 (two-way) when unknown — conservative, does not inflate risk.
    oneway = 0

    # junction, bridge, tunnel: not yet in SegmentFeatureVector from live routing.
    # Default to 0 (absent) — consistent with training where missing = not tagged.
    junction = 0
    bridge   = 0
    tunnel   = 0

    return {
        "highway_enc": hw_enc,
        "length_km":   length_km,
        "oneway":      oneway,
        "junction":    junction,
        "bridge":      bridge,
        "tunnel":      tunnel,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Live-condition adjustment
# ══════════════════════════════════════════════════════════════════════════════

def _compute_live_deduction(seg: SegmentFeatureVector) -> int:
    """
    Compute a bounded integer deduction [0, 20] to subtract from the
    XGBoost-derived base Safety Score.

    Rules are deterministic, documented, and additive up to the cap.

    IMPORTANT: this function reads ONLY from the live-data fields that were
    already populated by the upstream Module 7 pipeline. It does NOT call any
    external API, and does NOT modify the XGBoost input features.

    Returns
    -------
    int
        Total deduction to apply to the base Safety Score (capped at 20).
    """
    s = get_settings()
    total = 0

    # ── Weather (OpenWeather) ──────────────────────────────────────────────────
    if seg.weather_data_available:
        wr = seg.weather_risk or 0
        if wr >= 2:          # heavy rain (weather_risk == 2 or 3)
            total += s.live_adjustment_rain_heavy
        elif wr == 1:        # light rain
            total += s.live_adjustment_rain_light
        if wr == 3:          # heavy rain + low visibility
            total += s.live_adjustment_low_vis

        wind = seg.wind_speed_ms
        if wind is not None and wind >= get_settings().strong_wind_threshold_ms:
            total += s.live_adjustment_strong_wind

    # ── Live TomTom incidents (only if data was available) ────────────────────
    if seg.incidents_data_available:
        # Live accident on or near this segment
        acc_ct = seg.accident_count or 0
        if acc_ct > 0:
            total += s.live_adjustment_accident_incident

        # Dangerous condition (e.g., fog, flood, debris) flagged by TomTom
        danger_ct = seg.dangerous_condition_count or 0
        if danger_ct > 0:
            total += s.live_adjustment_dangerous_condition

    # ── Traffic congestion (TomTom Flow) ──────────────────────────────────────
    if seg.traffic_data_available:
        cr = seg.congestion_ratio
        if cr is not None and cr >= _SEVERE_CONGESTION_RATIO:
            total += s.live_adjustment_severe_congestion

    # ── Hard cap ──────────────────────────────────────────────────────────────
    # Maximum deduction from live conditions is capped at 20 points so that
    # a structurally safe road is never pushed below 20 purely by live events.
    # Structural unsafety (from XGBoost) can still drive the score to 0.
    return min(total, 20)


# ══════════════════════════════════════════════════════════════════════════════
# Probability → Safety Score conversion
# ══════════════════════════════════════════════════════════════════════════════

def _prob_to_base_score(prob: float) -> int:
    """
    Convert XGBoost risk probability [0, 1] to a base Safety Score [0, 100].

    The XGBoost model is trained with scale_pos_weight ≈ 67.5 (heavily imbalanced
    dataset). This means raw probabilities cluster near 0.20-0.30 even for
    "risky" roads. A naive linear mapping would compress most scores into 70-80
    and leave the scale feeling unusable.

    We apply a square-root stretch to spread the probability mass more evenly:

        risk_index = sqrt(prob) * 100      # stretches 0-1 into a wider range
        safety_score = 100 - risk_index

    Worked examples (from actual model output statistics):
        prob = 0.05  → risk_index = 22 → safety_score = 78   (structurally safe road)
        prob = 0.27  → risk_index = 52 → safety_score = 48   (medium-risk road)
        prob = 0.72  → risk_index = 85 → safety_score = 15   (high-risk road)
        prob = 0.01  → risk_index =  10 → safety_score = 90  (very safe road)

    Bounds: always in [0, 100].
    """
    prob = max(0.0, min(1.0, prob))
    risk_index = math.sqrt(prob) * 100.0
    score = 100.0 - risk_index
    return max(0, min(100, round(score)))


# ══════════════════════════════════════════════════════════════════════════════
# Risk Engine
# ══════════════════════════════════════════════════════════════════════════════

class RiskEngine:
    """
    Module 8 — SafeRoute AI Risk Engine.

    Singleton-like service: instantiate once at startup and reuse across all
    API requests. The XGBoost model is loaded from disk in __init__() and kept
    in memory.

    Usage
    -----
    In FastAPI startup:
        risk_engine = RiskEngine()          # raises on model load failure

    In request handler:
        segments = risk_engine.score_segments(feature_segments)
    """

    def __init__(self) -> None:
        self._model: Optional[XGBClassifier] = None
        self._model_path: Optional[Path] = None
        self._edge_cache: dict[int, tuple[float, float, int]] = {}  # edge_id -> (raw_prob, cal_prob, safety_score)
        self._load_model()

    # ── Model loading ──────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """
        Load the XGBoost model from disk.

        Model path is resolved in order:
          1. settings.xgboost_model_path (relative to backend/ directory)
          2. Absolute path if settings value is absolute.

        Raises RuntimeError if the model cannot be loaded, so the FastAPI
        startup fails loudly rather than silently returning wrong scores.
        """
        settings = get_settings()
        raw_path = settings.xgboost_model_path

        # Resolve relative to backend/ directory
        backend_dir = Path(__file__).resolve().parent.parent
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = backend_dir / candidate

        if not candidate.exists():
            raise RuntimeError(
                f"[RiskEngine] XGBoost model file not found: {candidate}. "
                "Run ml/train_xgboost_baseline.py first."
            )

        try:
            model = XGBClassifier()
            model.load_model(str(candidate))
            self._model = model
            self._model_path = candidate
            logger.info(
                "[RiskEngine] XGBoost model loaded from %s (features: %s)",
                candidate,
                MODEL_FEATURE_NAMES,
            )
            # Initialize SHAP explainer with the same already-loaded model
            # Lazy import to avoid circular dependency with shap_explainer
            # (shap_explainer cannot import from risk_engine at module level)
            try:
                from app.shap_explainer import initialize_shap_service  # noqa: PLC0415
                initialize_shap_service(model, str(candidate))
            except Exception as shap_exc:
                logger.warning(
                    "[RiskEngine] SHAP explainer initialization failed (non-fatal): %s",
                    shap_exc,
                )
        except Exception as exc:
            raise RuntimeError(
                f"[RiskEngine] Failed to load XGBoost model from {candidate}: {exc}"
            ) from exc

    @property
    def is_ready(self) -> bool:
        """True if the model loaded successfully and is ready for inference."""
        return self._model is not None

    # ── Batch inference & Edge Caching ─────────────────────────────────────────

    def score_osm_edges(self, edge_dicts: List[Dict[str, Any]]) -> List[OSMHeatmapEdge]:
        """
        Score underlying OSM road edges with XGBoost and theoretical Bayes calibration.
        Reuses predictions from self._edge_cache to avoid recalculation.
        Returns deduplicated OSMHeatmapEdge objects with WGS84 geometries.
        """
        if not self._model or not edge_dicts:
            return []

        # Deduplicate incoming edges by unique_edge_id
        unique_edges: dict[int, dict] = {}
        for e in edge_dicts:
            eid = e.get("unique_edge_id", -1)
            if eid >= 0 and eid not in unique_edges:
                unique_edges[eid] = e

        # Determine which edges need XGBoost prediction
        uncached_rows: list[dict] = []
        uncached_ids: list[int] = []

        for eid, e in unique_edges.items():
            if eid not in self._edge_cache:
                uncached_rows.append({
                    "highway_enc": e["highway_enc"],
                    "length_km": float(e["length_km"]),
                    "oneway": e["oneway"],
                    "junction": e["junction"],
                    "bridge": e["bridge"],
                    "tunnel": e["tunnel"],
                })
                uncached_ids.append(eid)

        if uncached_rows:
            try:
                X_uncached = pd.DataFrame(uncached_rows, columns=MODEL_FEATURE_NAMES)
                raw_probs = self._model.predict_proba(X_uncached)[:, 1]
                calibrator = get_calibrator()
                cal_probs = calibrator.calibrate(raw_probs)

                for eid, r_p, c_p in zip(uncached_ids, raw_probs, cal_probs):
                    score = _prob_to_base_score(float(c_p))
                    self._edge_cache[eid] = (float(r_p), float(c_p), score)
            except Exception as exc:
                logger.error("[RiskEngine] Batch edge prediction failed: %s", exc, exc_info=True)

        # Build OSMHeatmapEdge objects
        heatmap_edges: List[OSMHeatmapEdge] = []
        for eid, e in unique_edges.items():
            if eid not in self._edge_cache:
                continue
            raw_p, cal_p, score = self._edge_cache[eid]
            coords = e.get("geometry_coords", [])
            if not coords:
                continue

            orig_len_km = float(e.get("length_km", 0.0))
            heatmap_edges.append(
                OSMHeatmapEdge(
                    edge_id=eid,
                    name=e.get("name", "") or "",
                    road_class=e.get("highway", "unknown"),
                    length_km=round(orig_len_km, 4),
                    length_m=round(orig_len_km * 1000.0, 1),
                    calibrated_risk_prob=round(cal_p, 4),
                    raw_risk_prob=round(raw_p, 4),
                    safety_score=score,
                    geometry=SegmentGeometry(type="LineString", coordinates=coords),
                )
            )

        return heatmap_edges

    def score_segments_with_heatmap(
        self,
        segments: List[SegmentFeatureVector],
        use_osm_matching: bool = True,
    ) -> tuple[List[SegmentFeatureVector], List[OSMHeatmapEdge]]:
        """
        Compute historical_risk_prob and safety_score for every segment,
        and extract deduplicated OSM road edges with calibrated risk for the heatmap.
        """
        if not self._model:
            logger.error("[RiskEngine] Model not loaded — skipping all segments.")
            return segments, []

        if not segments:
            return segments, []

        settings = get_settings()

        # ── Step 1: Match segments to underlying OSM road edges ────────────────
        seg_to_edges = {}
        all_matched_edges: list[dict] = []
        if use_osm_matching:
            try:
                matcher = get_osm_matcher()
                if matcher.is_ready:
                    seg_to_edges = matcher.match_route_segments(segments)
                    for edges in seg_to_edges.values():
                        all_matched_edges.extend(edges)
                else:
                    logger.warning("[RiskEngine] OSMMatcher not ready — falling back to direct feature extraction.")
            except Exception as exc:
                logger.error("[RiskEngine] OSM edge matching failed: %s", exc, exc_info=True)

        # ── Step 2: Score all matched edges via cache/XGBoost & extract heatmap edges ──
        heatmap_edges = self.score_osm_edges(all_matched_edges)

        # ── Step 3: Map edge predictions back to UI segments ───────────────────
        direct_segment_indices: list[int] = []
        direct_rows: list[dict] = []

        for i, seg in enumerate(segments):
            matched_edges = seg_to_edges.get(seg.segment_id, [])

            if matched_edges:
                cal_list: list[float] = []
                raw_list: list[float] = []
                w_list: list[float] = []

                for e in matched_edges:
                    eid = e.get("unique_edge_id", -1)
                    if eid in self._edge_cache:
                        r_p, c_p, _ = self._edge_cache[eid]
                        raw_list.append(r_p)
                        cal_list.append(c_p)
                        w = float(e.get("traversed_length_m", 5.0))
                        w_list.append(max(w, 1.0))

                if cal_list:
                    total_weight = sum(w_list)
                    weighted_raw_prob = sum(p * w for p, w in zip(raw_list, w_list)) / total_weight
                    weighted_cal_prob = sum(p * w for p, w in zip(cal_list, w_list)) / total_weight

                    base_score = _prob_to_base_score(weighted_cal_prob)
                    live_deduction = _compute_live_deduction(seg)

                    seg.raw_risk_prob = round(weighted_raw_prob, 4)
                    seg.calibrated_risk_prob = round(weighted_cal_prob, 4)
                    seg.historical_risk_prob = round(weighted_cal_prob, 4)
                    seg.safety_score = base_score
                    seg.live_condition_deduction = live_deduction
            else:
                if use_osm_matching and seg.geometry and len(seg.geometry.coordinates) >= 2:
                    logger.warning(
                        "[RiskEngine] Segment %s could not be matched to any OSM edge within %.1fm. "
                        "Marking historical risk unavailable.",
                        seg.segment_id,
                        settings.osm_max_match_distance_m,
                    )
                    seg.historical_risk_prob = None
                    seg.safety_score = None
                    seg.live_condition_deduction = _compute_live_deduction(seg)
                else:
                    # Legacy fallback for synthetic unit test segments that have no coordinates
                    row = _segment_to_feature_row(seg)
                    direct_rows.append(row)
                    direct_segment_indices.append(i)

        # ── Step 4: Handle direct test segments (legacy test fixtures) ────────
        if direct_rows:
            try:
                X_direct = pd.DataFrame(direct_rows, columns=MODEL_FEATURE_NAMES)
                direct_raw_probs: np.ndarray = self._model.predict_proba(X_direct)[:, 1]
                calibrator = get_calibrator()
                direct_cal_probs: np.ndarray = calibrator.calibrate(direct_raw_probs)

                for j, seg_idx in enumerate(direct_segment_indices):
                    seg = segments[seg_idx]
                    raw_prob = float(direct_raw_probs[j])
                    cal_prob = float(direct_cal_probs[j])
                    base_score = _prob_to_base_score(cal_prob)
                    live_deduction = _compute_live_deduction(seg)

                    seg.raw_risk_prob = round(raw_prob, 4)
                    seg.calibrated_risk_prob = round(cal_prob, 4)
                    seg.historical_risk_prob = round(cal_prob, 4)
                    seg.safety_score = base_score
                    seg.live_condition_deduction = live_deduction
            except Exception as exc:
                logger.error("[RiskEngine] Direct prediction failed: %s", exc, exc_info=True)

        scored_count = sum(1 for s in segments if s.safety_score is not None)
        logger.info(
            "[RiskEngine] Scored %d/%d segments using OSM road-edge features. "
            "Heatmap edges extracted: %d. Avg safety_score=%.1f",
            scored_count,
            len(segments),
            len(heatmap_edges),
            float(np.mean([s.safety_score for s in segments if s.safety_score is not None]))
            if scored_count else 0.0,
        )

        return segments, heatmap_edges

    def explain_edge(self, edge_id: int) -> Optional[Any]:
        """
        Return a Local SHAP explanation for a specific OSM edge ID.

        The edge must have already been scored (i.e., present in self._edge_cache).
        SHAP operates on the same six features used for XGBoost inference.

        IMPORTANT:
          - Does NOT modify raw_risk_prob, calibrated_risk_prob, or safety_score.
          - Uses the original OSM training-edge length (length_km), not 500m UI length.
          - Returns None if the edge has not been scored or explainer is not ready.

        Parameters
        ----------
        edge_id : int
            The unique_edge_id of an already-scored OSM road edge.

        Returns
        -------
        dict | None
            Serializable explanation dict, or None if not available.
        """
        if edge_id not in self._edge_cache:
            logger.warning(
                "[RiskEngine.explain_edge] Edge %d not in cache — must be scored first.",
                edge_id,
            )
            return None

        raw_p, cal_p, score = self._edge_cache[edge_id]

        # Retrieve the edge dict from the OSM matcher's known edges
        edge_dict = self._get_edge_dict_by_id(edge_id)
        if edge_dict is None:
            logger.warning(
                "[RiskEngine.explain_edge] Cannot retrieve feature dict for edge %d.",
                edge_id,
            )
            return None

        from app.shap_explainer import get_shap_service  # noqa: PLC0415
        shap_service = get_shap_service()
        explanation = shap_service.explain_edge(
            edge_dict=edge_dict,
            raw_risk_prob=raw_p,
            calibrated_risk_prob=cal_p,
            safety_score=score,
        )
        return explanation.to_dict() if explanation is not None else None

    def _get_edge_dict_by_id(self, edge_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a minimal edge feature dict for a scored edge by ID.

        We reconstruct it from self._edge_cache (probabilities and score) and
        get the structural features from the OSM matcher's GDF — this avoids
        storing the full edge dict in memory a second time.
        Returns None if edge cannot be resolved.
        """
        try:
            matcher = get_osm_matcher()
            if not matcher.is_ready:
                return None
            gdf = matcher._gdf
            if gdf is None:
                return None

            import pandas as pd
            matches = gdf[gdf["unique_edge_id"] == edge_id]
            if matches.empty:
                return None

            from app.features.osm_matcher import clean_highway, encode_highway
            row = matches.iloc[0]
            hw_clean = clean_highway(row.get("highway"))
            hw_enc = encode_highway(hw_clean)
            orig_len_km = float(row.get("length_km", 0.0))
            oneway = 1 if row.get("oneway") in (True, "True", 1, "1") else 0
            junction = 1 if pd.notna(row.get("junction")) else 0
            bridge = 1 if pd.notna(row.get("bridge")) else 0
            tunnel = 1 if pd.notna(row.get("tunnel")) else 0

            return {
                "unique_edge_id": edge_id,
                "highway":        hw_clean,
                "highway_enc":    hw_enc,
                "length_km":      orig_len_km,  # ORIGINAL training-edge length
                "oneway":         oneway,
                "junction":       junction,
                "bridge":         bridge,
                "tunnel":         tunnel,
            }
        except Exception as exc:
            logger.error(
                "[RiskEngine._get_edge_dict_by_id] Failed for edge %d: %s",
                edge_id,
                exc,
            )
            return None

    def score_segments(
        self,
        segments: List[SegmentFeatureVector],
        use_osm_matching: bool = True,
    ) -> List[SegmentFeatureVector]:
        """
        Compute historical_risk_prob and safety_score for every segment.
        Maintains 100% backward compatibility for callers expecting just the segment list.
        """
        scored, _ = self.score_segments_with_heatmap(segments, use_osm_matching=use_osm_matching)
        return scored


# ── Module-level singleton ─────────────────────────────────────────────────────
# Instantiated once when this module is first imported (i.e., at FastAPI startup).
# Raises RuntimeError on model load failure — caught in main.py startup event.

_risk_engine_instance: Optional[RiskEngine] = None


def get_risk_engine() -> RiskEngine:
    """
    Return the module-level RiskEngine singleton, initializing it on first call.

    This function is safe to call from multiple async handlers — initialization
    happens at import time and the resulting object is read-only for inference.
    """
    global _risk_engine_instance
    if _risk_engine_instance is None:
        _risk_engine_instance = RiskEngine()
    return _risk_engine_instance
