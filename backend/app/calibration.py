"""
backend/app/calibration.py
==========================
RouteGuard AI — Probability Calibration Layer (Module 8).

Production Calibration Method:
------------------------------
LOCKED: Theoretical Bayes class-weight unbiasing:
    p_calibrated = p_raw / (p_raw + (1 - p_raw) * scale_pos_weight)

Rationale & Validation:
-----------------------
The XGBoost baseline model was trained with `scale_pos_weight = 67.53`
to handle severe class imbalance (330,718 negatives vs 4,897 positives).
This imbalance correction causes `predict_proba()` to output shifted odds:
    Odds_model = scale_pos_weight * Odds_true

The theoretical Bayes correction exactly reverses this known synthetic odds shift:
    Odds_calibrated = Odds_model / scale_pos_weight

Validation on Untouched Held-Out Test Set (N = 59,124 road edges, 1.460% prevalence):
- Brier Score: 0.012235 (vs 0.115442 raw, 89.4% reduction)
- Log Loss: 0.054534 (vs 0.399213 raw, 86.3% reduction)
- Quantile ECE: 0.000475 (0.048% average calibration error across deciles)
- Calibration Slope: 0.9880 (ideal: 1.0000)
- Calibration Intercept: -0.0190 (ideal: 0.0000)
- Mean Predicted Probability: 1.439% (vs 1.460% ground-truth test prevalence)

Terminology:
------------
The output is formally named and documented as:
    "Historical Risk Probability" or "Calibrated Historical Risk"
It represents the model's calibrated historical/structural accident risk
prediction for an edge or segment, not simply a literal future accident occurrence.

Key guarantees:
- Keeps raw_probability available for diagnostics; never overwrites it.
- Monotonically increasing across [0, 1].
- Exact boundary handling: p_raw=0 -> 0, p_raw=1 -> 1.
- All calibrated probabilities strictly bounded in [0.0, 1.0].
- scale_pos_weight is configurable (default 67.53 from settings).
"""

from __future__ import annotations

import logging
from typing import Union, overload, Any

import numpy as np

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@overload
def calibrate_probability(p_raw: float, scale_pos_weight: float | None = None) -> float: ...

@overload
def calibrate_probability(p_raw: Any, scale_pos_weight: float | None = None) -> Any: ...

def calibrate_probability(
    p_raw: Any,
    scale_pos_weight: float | None = None,
) -> Any:
    """
    Apply theoretical class-weight unbiasing to raw XGBoost probabilities.

    Parameters
    ----------
    p_raw : float or np.ndarray
        Raw probability output from XGBoost predict_proba()[:, 1].
    scale_pos_weight : float, optional
        Imbalance weighting factor used during training. Defaults to 67.53.

    Returns
    -------
    float or np.ndarray
        Calibrated Historical Risk probability in [0.0, 1.0].
    """
    spw = scale_pos_weight if scale_pos_weight is not None else get_settings().calibration_scale_pos_weight

    is_scalar = np.isscalar(p_raw) or (isinstance(p_raw, np.ndarray) and p_raw.ndim == 0)
    p = np.asarray(p_raw, dtype=float)

    # Output array
    calibrated = np.zeros_like(p)

    # Exact boundary handling
    mask_zero = p <= 0.0
    mask_one = p >= 1.0
    mask_mid = ~mask_zero & ~mask_one

    calibrated[mask_zero] = 0.0
    calibrated[mask_one] = 1.0

    if np.any(mask_mid):
        p_mid = p[mask_mid]
        # p_cal = p / (p + (1 - p) * spw)
        calibrated[mask_mid] = p_mid / (p_mid + (1.0 - p_mid) * spw)

    # Final sanity clamp to [0.0, 1.0]
    calibrated = np.clip(calibrated, 0.0, 1.0)

    if is_scalar:
        return float(calibrated.item() if hasattr(calibrated, "item") else calibrated)
    return calibrated


class ProbabilityCalibrator:
    """
    Stateful probability calibrator supporting configurable scale_pos_weight.
    """

    def __init__(self, scale_pos_weight: float | None = None) -> None:
        self._spw = scale_pos_weight if scale_pos_weight is not None else get_settings().calibration_scale_pos_weight

    @property
    def scale_pos_weight(self) -> float:
        return self._spw

    @overload
    def calibrate(self, p_raw: float) -> float: ...

    @overload
    def calibrate(self, p_raw: Any) -> Any: ...

    def calibrate(self, p_raw: Any) -> Any:
        """Calibrate raw probability/probabilities using the configured scale_pos_weight."""
        return calibrate_probability(p_raw, scale_pos_weight=self._spw)


# ── Global singleton ──────────────────────────────────────────────────────────
_calibrator_instance: ProbabilityCalibrator | None = None


def get_calibrator() -> ProbabilityCalibrator:
    """Return the module-level ProbabilityCalibrator singleton."""
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = ProbabilityCalibrator()
    return _calibrator_instance
