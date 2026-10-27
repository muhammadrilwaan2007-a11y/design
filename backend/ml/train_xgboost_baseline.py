"""
ml/train_xgboost_baseline.py
============================
RouteGuard AI — XGBoost V2 Baseline Classifier
==============================================

Target:
  has_accident = 1 if accident_count > 0 else 0

Input features (OSM structural only):
  length_km, highway, oneway, junction, bridge, tunnel

This is a BASELINE experiment for historical road-edge accident presence.
It does NOT predict real-world accident probability for live routing.

Run from the backend/ directory:
    python ml/train_xgboost_baseline.py
"""

from __future__ import annotations

import json
import sys
import io
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)
from xgboost import XGBClassifier

# ── Fix Windows console encoding ──────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR    = BACKEND_DIR / "data" / "processed"
MODEL_DIR   = BACKEND_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

CSV_PATH    = DATA_DIR / "osm_road_accident_features.csv"
MODEL_PATH  = MODEL_DIR / "xgboost_baseline.json"
PRED_PATH   = DATA_DIR / "xgboost_test_predictions.csv"

# ──────────────────────────────────────────────────────────────────────────────
# STRICTLY FORBIDDEN LEAKAGE COLUMNS — halt if any appear in X
# ──────────────────────────────────────────────────────────────────────────────
LEAKAGE_COLUMNS = {
    "accident_count", "fatal_accident_count", "nonfatal_accident_count",
    "fatal_rate", "accident_density_per_km", "has_accident",
    "Severity", "severity_normalised", "is_fatal", "Collision_Type",
    "Main_Cause", "Accident_Description",
}

# ──────────────────────────────────────────────────────────────────────────────
# BASELINE XGBoost CONFIGURATION (conservative)
# ──────────────────────────────────────────────────────────────────────────────
XGBOOST_CONFIG = {
    "n_estimators":      300,
    "max_depth":         4,
    "learning_rate":     0.05,
    "subsample":         0.8,
    "colsample_bytree":  0.8,
    "use_label_encoder": False,
    "eval_metric":       "aucpr",
    "random_state":      42,
    "tree_method":       "hist",   # fast on CPU
}

# Probability threshold for binary prediction (default 0.5 is fair to report)
DECISION_THRESHOLD = 0.5


def _hr(title: str = "") -> None:
    print(f"\n{'=' * 50}")
    print(title)
    print('=' * 50)


# ──────────────────────────────────────────────────────────────────────────────
# 1. LOAD AND PREPARE DATA
# ──────────────────────────────────────────────────────────────────────────────
def load_and_prepare(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)

    # ── TARGET ────────────────────────────────────────────────────────────────
    df["has_accident"] = (df["accident_count"] > 0).astype(int)

    # ── FEATURES ──────────────────────────────────────────────────────────────
    # Only use OSM structural features
    FEATURES = ["length_km", "highway", "oneway", "junction", "bridge", "tunnel"]

    # ── LEAKAGE CHECK ─────────────────────────────────────────────────────────
    _hr("LEAKAGE CHECK")
    leaked = LEAKAGE_COLUMNS.intersection(set(FEATURES))
    if leaked:
        print(f"CRITICAL: Leakage columns detected in features: {leaked}")
        sys.exit(1)
    print("PASS — No leakage columns in feature set.")
    print(f"Final feature list: {FEATURES}")

    # ── PREPROCESSING ─────────────────────────────────────────────────────────

    # length_km: numeric, no transformation needed for XGBoost
    # Already float64

    # highway: extract first type from list-strings
    def clean_highway(hw):
        hw = str(hw)
        if hw.startswith("["):
            hw = hw.replace("[", "").replace("]", "").replace("'", "")
            return hw.split(",")[0].strip()
        return hw.strip()

    df["highway"] = df["highway"].apply(clean_highway)

    # oneway: bool → 0/1
    df["oneway"] = df["oneway"].map({True: 1, False: 0, "True": 1, "False": 0}).fillna(0).astype(int)

    # junction: binary flag — present (not null) means some junction tag exists
    df["junction"] = df["junction"].notna().astype(int)

    # bridge: binary flag
    df["bridge"] = df["bridge"].notna().astype(int)

    # tunnel: binary flag
    df["tunnel"] = df["tunnel"].notna().astype(int)

    # highway → ordinal encoding by increasing risk tier (from exposure analysis)
    highway_risk_order = {
        "residential":   0,
        "living_street": 1,
        "unclassified":  2,
        "road":          3,
        "tertiary_link": 4,
        "tertiary":      5,
        "secondary_link":6,
        "secondary":     7,
        "primary_link":  8,
        "primary":       9,
        "motorway_link": 10,
        "trunk_link":    11,
        "trunk":         12,
        "motorway":      13,
    }
    df["highway_enc"] = df["highway"].map(highway_risk_order).fillna(-1).astype(int)

    df_out = df[["unique_edge_id", "highway", "length_km",
                 "highway_enc", "oneway", "junction", "bridge", "tunnel",
                 "has_accident"]].copy()

    print(f"\nDataset shape after preprocessing: {df_out.shape}")
    return df_out


# ──────────────────────────────────────────────────────────────────────────────
# 2. TRAIN / VALIDATION / TEST SPLIT
# ──────────────────────────────────────────────────────────────────────────────
def split_data(df: pd.DataFrame):
    """
    70 / 15 / 15 stratified random split.

    Spatial limitation note:
    A geographically-blocked split would be more rigorous because adjacent OSM
    road edges share the same physical neighbourhood and hence the same accident
    environment.  That is deferred to the next experiment.  This baseline uses a
    stratified random split so that the positive-class ratio is preserved across
    all three partitions.
    """
    X = df[["highway_enc", "length_km", "oneway", "junction", "bridge", "tunnel"]]
    y = df["has_accident"]

    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X, y, test_size=0.15, stratify=y, random_state=42
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_trainval, y_trainval,
        test_size=0.15 / 0.85,   # ≈ 17.6 % of remaining → 15 % of total
        stratify=y_trainval,
        random_state=42,
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


# ──────────────────────────────────────────────────────────────────────────────
# 3. METRICS HELPER
# ──────────────────────────────────────────────────────────────────────────────
def evaluate(name: str, model, X, y_true, threshold=DECISION_THRESHOLD) -> dict:
    prob = model.predict_proba(X)[:, 1]
    pred = (prob >= threshold).astype(int)

    roc  = roc_auc_score(y_true, prob)
    pr   = average_precision_score(y_true, prob)
    prec = precision_score(y_true, pred, zero_division=0)
    rec  = recall_score(y_true, pred, zero_division=0)
    f1   = f1_score(y_true, pred, zero_division=0)
    cm   = confusion_matrix(y_true, pred)

    print(f"\n{'─'*40}")
    print(f"  {name}")
    print(f"{'─'*40}")
    print(f"  ROC-AUC  : {roc:.4f}")
    print(f"  PR-AUC   : {pr:.4f}")
    print(f"  Precision: {prec:.4f}")
    print(f"  Recall   : {rec:.4f}")
    print(f"  F1-Score : {f1:.4f}")
    print(f"  Confusion Matrix:")
    print(f"    TN={cm[0,0]:,}  FP={cm[0,1]:,}")
    print(f"    FN={cm[1,0]:,}  TP={cm[1,1]:,}")
    print(f"  Positive predictions : {pred.sum():,}")
    print(f"  Actual positives     : {y_true.sum():,}")
    print(f"  Actual negatives     : {(y_true == 0).sum():,}")

    print(f"\n  Probability distribution:")
    print(f"    Min    : {prob.min():.4f}")
    print(f"    Max    : {prob.max():.4f}")
    print(f"    Mean   : {prob.mean():.4f}")
    print(f"    Median : {np.median(prob):.4f}")

    pos_probs = prob[y_true == 1]
    neg_probs = prob[y_true == 0]
    if len(pos_probs):
        print(f"    Mean prob (actual positives): {pos_probs.mean():.4f}")
    if len(neg_probs):
        print(f"    Mean prob (actual negatives): {neg_probs.mean():.4f}")

    return {"roc_auc": roc, "pr_auc": pr, "precision": prec, "recall": rec, "f1": f1, "cm": cm.tolist()}


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    _hr("RouteGuard AI — XGBoost Baseline Training")

    # 1. Load
    df = load_and_prepare(CSV_PATH)

    _hr("DATASET OVERVIEW")
    total = len(df)
    n_pos = df["has_accident"].sum()
    n_neg = total - n_pos
    print(f"  Total road edges       : {total:,}")
    print(f"  Positive (has_accident): {n_pos:,} ({n_pos/total*100:.2f}%)")
    print(f"  Negative (no accident) : {n_neg:,} ({n_neg/total*100:.2f}%)")

    # 2. Split
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(df)

    _hr("SPLIT SIZES")
    print(f"  Train : {len(X_train):,} rows  "
          f"(pos={y_train.sum():,}, neg={(y_train==0).sum():,})")
    print(f"  Val   : {len(X_val):,}  rows  "
          f"(pos={y_val.sum():,}, neg={(y_val==0).sum():,})")
    print(f"  Test  : {len(X_test):,}  rows  "
          f"(pos={y_test.sum():,}, neg={(y_test==0).sum():,})")
    print("\n  Spatial limitation: This is a stratified random split.")
    print("  Nearby OSM edges share the same physical neighbourhood.")
    print("  Geographic block-split is deferred to the next experiment.")

    # 3. scale_pos_weight
    train_neg = (y_train == 0).sum()
    train_pos = y_train.sum()
    spw = train_neg / train_pos
    _hr("CLASS IMBALANCE HANDLING")
    print(f"  Training negatives     : {train_neg:,}")
    print(f"  Training positives     : {train_pos:,}")
    print(f"  scale_pos_weight       : {spw:.4f}")

    # 4. Train
    _hr("TRAINING XGBoost BASELINE")
    cfg = {**XGBOOST_CONFIG, "scale_pos_weight": round(spw, 4)}
    print(f"  Configuration: {json.dumps({k:v for k,v in cfg.items() if k != 'use_label_encoder'}, indent=4)}")

    model = XGBClassifier(**cfg, verbosity=0)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # 5. Evaluate
    _hr("EVALUATION")
    val_metrics  = evaluate("VALIDATION SET", model, X_val, y_val)
    test_metrics = evaluate("TEST SET (untouched)", model, X_test, y_test)

    # 6. Feature importance
    _hr("FEATURE IMPORTANCE (gain)")
    feat_names = X_train.columns.tolist()
    importances = model.get_booster().get_score(importance_type="gain")
    for feat in feat_names:
        score = importances.get(f"f{feat_names.index(feat)}", importances.get(feat, 0))
        print(f"  {feat:<20} {score:.4f}")

    # 7. Majority-class baseline
    _hr("MAJORITY-CLASS BASELINE (trivial predictor)")
    # Always predict 0
    trivial_roc = 0.5   # defined
    trivial_pr  = y_test.mean()  # always-negative precision = 0
    trivial_pred = np.zeros(len(y_test))
    trivial_rec  = 0.0
    trivial_prec = 0.0
    trivial_f1   = 0.0
    print(f"  Trivial baseline (always predict 0):")
    print(f"    ROC-AUC  : {trivial_roc:.4f}  (random)")
    print(f"    PR-AUC   : ~{trivial_pr:.4f}  (= positive class rate)")
    print(f"    Precision: {trivial_prec:.4f}")
    print(f"    Recall   : {trivial_rec:.4f}")
    print(f"    F1       : {trivial_f1:.4f}")
    print(f"  XGBoost vs trivial on test:")
    print(f"    ROC-AUC lift : +{test_metrics['roc_auc'] - trivial_roc:.4f}")
    print(f"    PR-AUC  lift : +{test_metrics['pr_auc'] - trivial_pr:.4f}")

    # 8. Save model
    model.save_model(str(MODEL_PATH))
    print(f"\nModel saved → {MODEL_PATH}")

    # 9. Save predictions on test set
    test_prob = model.predict_proba(X_test)[:, 1]
    test_pred = (test_prob >= DECISION_THRESHOLD).astype(int)
    test_idx  = X_test.index

    pred_df = df.loc[test_idx, ["unique_edge_id", "highway", "length_km"]].copy()
    pred_df["actual_has_accident"]  = y_test.values
    pred_df["predicted_probability"] = test_prob
    pred_df["predicted_class"]       = test_pred
    pred_df.to_csv(PRED_PATH, index=False)
    print(f"Predictions saved → {PRED_PATH}")

    _hr("DONE")
    print("  XGBoost baseline experiment complete.")
    print("  Do NOT convert these probabilities to a SafeRoute Safety Score yet.")
    print("  Next step: inspect predictions and decide whether spatial validation")
    print("  or Two-Stage approach is warranted.")


if __name__ == "__main__":
    main()
