"""
backend/scripts/validate_calibration.py
=======================================
RouteGuard AI — Calibration Validation Script

Performs rigorous statistical calibration validation on the untouched held-out test set:
1. Raw XGBoost probability
2. Bayes-unbiased probability (scale_pos_weight = 67.53)
3. Platt-scaled probability (fitted strictly on held-out validation set)

Computes:
- Brier Score
- Log Loss
- Expected Calibration Error (ECE)
- Calibration Slope and Intercept
- 10-bin reliability tables (equal-width and quantile bins)
- Reliability diagram plot saved to artifact directory
"""

from __future__ import annotations

import sys
import io
from pathlib import Path

# Fix Windows console encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import _SigmoidCalibration
from xgboost import XGBClassifier

from typing import Any

from ml.train_xgboost_baseline import load_and_prepare, split_data, CSV_PATH, MODEL_PATH
from app.calibration import calibrate_probability

ARTIFACT_DIR = Path(r"C:\Users\Madhan\.gemini\antigravity-ide\brain\65599cee-af81-469e-8dcc-60bfa6ddb694")


def compute_calibration_curve(
    y_true: Any,
    y_prob: Any,
    n_bins: int = 10,
    strategy: str = "quantile",
) -> tuple[Any, ...]:
    """
    Compute calibration curve bins.
    Returns:
        prob_pred_means: mean predicted probability in each bin
        prob_true_means: observed accident frequency in each bin
        bin_counts: number of samples in each bin
        bin_ranges: (lower, upper) for each bin
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_prob_arr = np.asarray(y_prob, dtype=float)

    if strategy == "quantile":
        # Quantile binning ensures equal sample sizes per bin
        quantiles = np.linspace(0, 1, n_bins + 1)
        bin_edges = np.quantile(y_prob_arr, quantiles)
        # Avoid duplicate edges due to tied values
        bin_edges = np.unique(bin_edges)
        if len(bin_edges) <= 2:
            bin_edges = np.linspace(y_prob_arr.min(), y_prob_arr.max(), n_bins + 1)
    else:
        # Uniform equal-width binning
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)

    bin_indices = np.digitize(y_prob_arr, bin_edges, right=True)
    # digitize right=True puts values <= bin_edges[i] into i
    # clamp 0 to 1, and max bin to n_bins
    bin_indices = np.clip(bin_indices, 1, len(bin_edges) - 1)

    prob_pred_means: list[float] = []
    prob_true_means: list[float] = []
    bin_counts: list[int] = []
    bin_ranges: list[tuple[float, float]] = []

    for b in range(1, len(bin_edges)):
        mask = (bin_indices == b)
        count = int(np.sum(mask))
        low = float(bin_edges[b - 1])
        high = float(bin_edges[b])
        bin_ranges.append((low, high))

        if count > 0:
            prob_pred_means.append(float(np.mean(y_prob_arr[mask])))
            prob_true_means.append(float(np.mean(y_true_arr[mask])))
            bin_counts.append(count)
        else:
            prob_pred_means.append(float((low + high) / 2.0))
            prob_true_means.append(0.0)
            bin_counts.append(0)

    return (
        np.asarray(prob_pred_means, dtype=float),
        np.asarray(prob_true_means, dtype=float),
        np.asarray(bin_counts, dtype=int),
        bin_ranges,
    )


def compute_ece(
    y_true: Any,
    y_prob: Any,
    n_bins: int = 10,
    strategy: str = "uniform",
) -> float:
    """Expected Calibration Error."""
    prob_pred, prob_true, counts, _ = compute_calibration_curve(
        y_true, y_prob, n_bins=n_bins, strategy=strategy
    )
    p_true = np.asarray(prob_true, dtype=float)
    p_pred = np.asarray(prob_pred, dtype=float)
    c_arr = np.asarray(counts, dtype=float)
    total = float(np.sum(c_arr))
    if total == 0:
        return 0.0
    ece = np.sum(c_arr * np.abs(p_true - p_pred)) / total
    return float(ece)


def compute_calibration_slope_intercept(
    y_true: Any,
    y_prob: Any,
) -> tuple[float, float]:
    """
    Fit logistic regression of y_true onto logit(y_prob).
    Ideal calibration: slope = 1.0, intercept = 0.0.
    """
    y_t = np.asarray(y_true, dtype=float)
    y_p = np.asarray(y_prob, dtype=float)
    eps = 1e-12
    p_clipped = np.clip(y_p, eps, 1.0 - eps)
    logit_p = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)

    lr = LogisticRegression(solver="lbfgs", C=1e6)  # unregularized
    lr.fit(logit_p, y_t)
    slope = float(lr.coef_[0, 0])
    intercept = float(lr.intercept_[0])
    return slope, intercept


def main():
    print("=" * 80)
    print("RouteGuard AI — Calibration Validation on Untouched Held-Out Test Set")
    print("=" * 80)

    # 1. Load data and split
    print("\nLoading dataset and recreating exact train/val/test splits...")
    df = load_and_prepare(CSV_PATH)
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(df)

    y_val_arr = y_val.values
    y_test_arr = y_test.values

    N_test = len(y_test_arr)
    N_pos_test = int(np.sum(y_test_arr))
    N_neg_test = N_test - N_pos_test
    base_rate_test = N_pos_test / N_test

    print(f"Test Set Total Road Edges: {N_test:,}")
    print(f"Test Positives (Accident): {N_pos_test:,} ({base_rate_test*100:.3f}%)")
    print(f"Test Negatives (No Acc):   {N_neg_test:,} ({(1-base_rate_test)*100:.3f}%)")

    # 2. Load model
    print(f"\nLoading trained baseline model from {MODEL_PATH}...")
    model = XGBClassifier()
    model.load_model(str(MODEL_PATH))

    # 3. Generate predictions
    # Prediction on validation set (used ONLY for fitting Platt scaling)
    p_val_raw = model.predict_proba(X_val)[:, 1]

    # Predictions on test set (UNTOUCHED evaluation set)
    p_test_raw = model.predict_proba(X_test)[:, 1]

    # Verify with saved predictions CSV
    pred_csv_path = BACKEND_DIR / "data" / "processed" / "xgboost_test_predictions.csv"
    if pred_csv_path.exists():
        saved_df = pd.read_csv(pred_csv_path)
        np.testing.assert_allclose(
            p_test_raw, saved_df["predicted_probability"].values, atol=1e-5
        )
        print("✓ Verified: p_test_raw matches saved xgboost_test_predictions.csv exactly.")

    # Method 2: Bayes-unbiased probability (spw=67.53)
    p_test_bayes = calibrate_probability(p_test_raw, scale_pos_weight=67.53)

    # Method 3: Platt scaling fitted on validation set
    print("\nFitting Platt scaling on held-out validation set (59,124 samples)...")
    # A) Standard Sigmoid calibration (Platt 1999: 1 / (1 + exp(A*f + B)))
    sig_calibrator = _SigmoidCalibration()
    sig_calibrator.fit(p_val_raw, y_val_arr)
    p_test_platt_sig = sig_calibrator.predict(p_test_raw)
    print(f"  Platt Sigmoid (prob-based) parameters: a = {sig_calibrator.a_:.4f}, b = {sig_calibrator.b_:.4f}")

    # B) Logistic regression on log-odds (standard Platt scaling formulation)
    eps = 1e-12
    logit_val = np.log(np.clip(p_val_raw, eps, 1 - eps) / (1 - np.clip(p_val_raw, eps, 1 - eps))).reshape(-1, 1)
    logit_test = np.log(np.clip(p_test_raw, eps, 1 - eps) / (1 - np.clip(p_test_raw, eps, 1 - eps))).reshape(-1, 1)

    lr_platt = LogisticRegression(solver="lbfgs", C=1e6)
    lr_platt.fit(logit_val, y_val_arr)
    p_test_platt_logit = lr_platt.predict_proba(logit_test)[:, 1]
    platt_slope_fit = lr_platt.coef_[0, 0]
    platt_intercept_fit = lr_platt.intercept_[0]
    print(f"  Platt Logit (log-odds) parameters: slope = {platt_slope_fit:.4f}, intercept = {platt_intercept_fit:.4f}")

    # 4. Evaluation of all methods
    methods: dict[str, Any] = {
        "Raw XGBoost": p_test_raw,
        "Bayes Unbiased (spw=67.53)": p_test_bayes,
        "Platt Scaling (Logit-fit)": p_test_platt_logit,
        "Platt Scaling (Sigmoid-fit)": p_test_platt_sig,
    }

    results = []

    print("\n" + "=" * 80)
    print("CALIBRATION METRICS ON UNTOUCHED TEST SET")
    print("=" * 80)

    for name, p_pred in methods.items():
        p_arr: Any = np.asarray(p_pred, dtype=float)
        brier = brier_score_loss(y_test_arr, p_arr)
        # Avoid log(0) in log_loss
        p_clipped = np.clip(p_arr, 1e-15, 1 - 1e-15)
        ll = log_loss(y_test_arr, p_clipped)
        ece_uniform = compute_ece(y_test_arr, p_arr, n_bins=10, strategy="uniform")
        ece_quantile = compute_ece(y_test_arr, p_arr, n_bins=10, strategy="quantile")
        slope, intercept = compute_calibration_slope_intercept(y_test_arr, p_arr)

        results.append({
            "Method": name,
            "Brier Score": brier,
            "Log Loss": ll,
            "ECE (Quantile)": ece_quantile,
            "ECE (Uniform)": ece_uniform,
            "Calib Slope (Ideal=1.0)": slope,
            "Calib Intercept (Ideal=0.0)": intercept,
            "Mean Pred Prob": float(np.mean(p_arr)),
            "Median Pred Prob": float(np.median(p_arr)),
        })

    results_df = pd.DataFrame(results)
    print(results_df.to_string(index=False))

    # 5. Calibration / Reliability Bins Table (Quantile Bins — statistically valid for imbalanced data)
    print("\n" + "=" * 80)
    print("RELIABILITY BINS: QUANTILE DECILES (10 Bins, ~5,912 edges per bin)")
    print("=" * 80)

    for name, p_pred in [
        ("Raw XGBoost", p_test_raw),
        ("Bayes Unbiased (spw=67.53)", p_test_bayes),
        ("Platt Scaling (Logit-fit)", p_test_platt_logit),
    ]:
        print(f"\n--- {name} ---")
        pred_means, true_means, counts, ranges = compute_calibration_curve(
            y_test_arr, p_pred, n_bins=10, strategy="quantile"
        )
        bin_table = []
        for b_idx in range(len(counts)):
            low, high = ranges[b_idx]
            abs_err = abs(true_means[b_idx] - pred_means[b_idx])
            bin_table.append({
                "Bin": b_idx + 1,
                "Range": f"[{low:.4f}, {high:.4f}]",
                "Count": counts[b_idx],
                "Mean Pred (Conf)": f"{pred_means[b_idx]:.4f}",
                "Observed Freq (Acc)": f"{true_means[b_idx]:.4f}",
                "Abs Error": f"{abs_err:.4f}",
            })
        print(pd.DataFrame(bin_table).to_string(index=False))

    # Also compute Uniform bins for reference
    print("\n" + "=" * 80)
    print("RELIABILITY BINS: UNIFORM (10 Equal-Width Bins [0.0, 0.1, ..., 1.0])")
    print("=" * 80)

    for name, p_pred in [
        ("Raw XGBoost", p_test_raw),
        ("Bayes Unbiased (spw=67.53)", p_test_bayes),
        ("Platt Scaling (Logit-fit)", p_test_platt_logit),
    ]:
        print(f"\n--- {name} ---")
        pred_means, true_means, counts, ranges = compute_calibration_curve(
            y_test_arr, p_pred, n_bins=10, strategy="uniform"
        )
        bin_table = []
        for b_idx in range(len(counts)):
            low, high = ranges[b_idx]
            abs_err = abs(true_means[b_idx] - pred_means[b_idx])
            bin_table.append({
                "Bin": b_idx + 1,
                "Range": f"[{low:.1f}, {high:.1f}]",
                "Count": counts[b_idx],
                "Mean Pred (Conf)": f"{pred_means[b_idx]:.4f}",
                "Observed Freq (Acc)": f"{true_means[b_idx]:.4f}",
                "Abs Error": f"{abs_err:.4f}" if counts[b_idx] > 0 else "N/A",
            })
        print(pd.DataFrame(bin_table).to_string(index=False))

    # 6. Generate Reliability Diagram
    print("\nGenerating Reliability Diagram...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=300)

    # Plot 1: Quantile Deciles (statistically robust for rare events)
    ax1 = axes[0]
    ax1.plot([0, 0.15], [0, 0.15], "k--", label="Perfect Calibration (y = x)", alpha=0.7, lw=2)

    # We plot the calibrated methods on the 0-0.15 range
    for name, p_pred, color, marker in [
        ("Bayes Unbiased (spw=67.53)", p_test_bayes, "#2563eb", "o"),
        ("Platt Scaling (Logit)", p_test_platt_logit, "#10b981", "s"),
    ]:
        pred_m, true_m, _, _ = compute_calibration_curve(y_test_arr, p_pred, n_bins=10, strategy="quantile")
        ax1.plot(pred_m, true_m, f"-{marker}", label=name, color=color, lw=2, markersize=7)

    ax1.set_title("Reliability Diagram — Quantile Deciles (Zoomed: 0.0 to 0.15)", fontsize=13, fontweight="bold", pad=12)
    ax1.set_xlabel("Mean Predicted Probability", fontsize=11)
    ax1.set_ylabel("Observed Accident Frequency", fontsize=11)
    ax1.set_xlim(-0.005, 0.15)
    ax1.set_ylim(-0.005, 0.15)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", frameon=True)

    # Plot 2: Full Scale (0.0 to 1.0) showing Raw vs Calibrated
    ax2 = axes[1]
    ax2.plot([0, 1], [0, 1], "k--", label="Perfect Calibration (y = x)", alpha=0.7, lw=2)

    for name, p_pred, color, marker in [
        ("Raw XGBoost", p_test_raw, "#ef4444", "^"),
        ("Bayes Unbiased (spw=67.53)", p_test_bayes, "#2563eb", "o"),
        ("Platt Scaling (Logit)", p_test_platt_logit, "#10b981", "s"),
    ]:
        pred_m, true_m, _, _ = compute_calibration_curve(y_test_arr, p_pred, n_bins=10, strategy="quantile")
        ax2.plot(pred_m, true_m, f"-{marker}", label=name, color=color, lw=2, markersize=6)

    ax2.set_title("Reliability Diagram — Full Scale (0.0 to 1.0)", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xlabel("Mean Predicted Probability", fontsize=11)
    ax2.set_ylabel("Observed Accident Frequency", fontsize=11)
    ax2.set_xlim(-0.05, 1.05)
    ax2.set_ylim(-0.05, 1.05)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper left", frameon=True)

    plt.tight_layout()
    diagram_path = ARTIFACT_DIR / "calibration_reliability_diagram.png"
    plt.savefig(diagram_path, dpi=300)
    plt.close()
    print(f"✓ Reliability diagram saved to: {diagram_path}")


if __name__ == "__main__":
    main()
