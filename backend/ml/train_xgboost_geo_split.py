"""
ml/train_xgboost_geo_split.py
================================
SafeRoute AI — XGBoost Experiment 3: Geographic Block-Split
============================================================

Replaces the random stratified split with a reproducible spatial grid.
Every road edge belonging to the same geographic grid cell stays in
exactly ONE partition (train / val / test).

Geographic grid:
    Bengaluru extent:  Lat [12.70, 13.30]  Lon [77.30, 77.90]
    Grid resolution:   0.05° × 0.05°  (≈ 5.5 km per cell at this latitude)
    Expected cells:    12 × 12 = 144

Partition strategy:
    Sort cells by (lat_bin, lon_bin) for reproducibility.
    Assign first 70% of cells → train
    Next 15% of cells        → validation
    Last 15% of cells        → test

Run from backend/ directory:
    python ml/train_xgboost_geo_split.py
"""

from __future__ import annotations

import json
import sys
import io
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_score, recall_score, f1_score, confusion_matrix,
)
from xgboost import XGBClassifier

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR    = BACKEND_DIR / "data" / "processed"
MODEL_DIR   = BACKEND_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

ROADS_GPKG    = DATA_DIR / "osm_roads_with_accidents.gpkg"
GEO_MODEL     = MODEL_DIR / "xgboost_geo_split.json"
GEO_PRED_CSV  = DATA_DIR / "xgboost_geo_split_predictions.csv"

GRID_DEG = 0.05     # cell size in degrees

LEAKAGE_COLUMNS = {
    "accident_count", "fatal_accident_count", "nonfatal_accident_count",
    "fatal_rate", "accident_density_per_km", "has_accident",
    "Severity", "severity_normalised", "is_fatal",
}

XGBOOST_CONFIG = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "eval_metric": "aucpr",
    "random_state": 42,
    "tree_method": "hist",
}

FEATURES = ["highway_enc", "length_km", "oneway", "junction", "bridge", "tunnel"]

def hr(title=""):
    print(f"\n{'='*55}\n{title}\n{'='*55}")


# ── Preprocessing (identical to baseline) ────────────────────────────────────
def clean_highway(hw):
    hw = str(hw)
    if hw.startswith("["):
        hw = hw.replace("[","").replace("]","").replace("'","")
        return hw.split(",")[0].strip()
    return hw.strip()

HIGHWAY_RISK = {
    "residential":0,"living_street":1,"unclassified":2,"road":3,
    "tertiary_link":4,"tertiary":5,"secondary_link":6,"secondary":7,
    "primary_link":8,"primary":9,"motorway_link":10,"trunk_link":11,
    "trunk":12,"motorway":13,
}

from typing import Any

def prepare_features(gdf: Any) -> pd.DataFrame:
    df = gdf.copy()
    df["has_accident"]  = (df["accident_count"] > 0).astype(int)
    df["highway"]       = df["highway"].apply(clean_highway)
    df["highway_enc"]   = df["highway"].map(HIGHWAY_RISK).fillna(-1).astype(int)
    df["oneway"]        = df["oneway"].map(
        {True:1, False:0, "True":1, "False":0}).fillna(0).astype(int)
    df["junction"]      = df["junction"].notna().astype(int)
    df["bridge"]        = df["bridge"].notna().astype(int)
    df["tunnel"]        = df["tunnel"].notna().astype(int)
    return df


# ── Evaluation helper ─────────────────────────────────────────────────────────
def evaluate(name, model, X, y_true):
    prob = model.predict_proba(X)[:, 1]
    pred = (prob >= 0.5).astype(int)
    roc  = roc_auc_score(y_true, prob)
    pr   = average_precision_score(y_true, prob)
    prec = precision_score(y_true, pred, zero_division=0)
    rec  = recall_score(y_true, pred, zero_division=0)
    f1   = f1_score(y_true, pred, zero_division=0)
    cm   = confusion_matrix(y_true, pred)
    print(f"\n{'─'*45}\n  {name}\n{'─'*45}")
    print(f"  ROC-AUC  : {roc:.4f}")
    print(f"  PR-AUC   : {pr:.4f}")
    print(f"  Precision: {prec:.4f}")
    print(f"  Recall   : {rec:.4f}")
    print(f"  F1-Score : {f1:.4f}")
    print(f"  CM  TN={cm[0,0]:,}  FP={cm[0,1]:,}")
    print(f"      FN={cm[1,0]:,}  TP={cm[1,1]:,}")
    print(f"  Positive predictions : {pred.sum():,}")
    print(f"  Actual positives     : {y_true.sum():,}")
    print(f"  Actual negatives     : {(y_true==0).sum():,}")
    pos_prev = y_true.mean()
    print(f"  Positive prevalence  : {pos_prev*100:.3f}%")
    print(f"  Trivial PR-AUC (prev): {pos_prev:.4f}")
    print(f"  PR-AUC lift          : +{pr - pos_prev:.4f}")
    return {"roc_auc":roc,"pr_auc":pr,"precision":prec,"recall":rec,"f1":f1,"cm":cm.tolist()}, prob, pred


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    hr("SafeRoute AI — Experiment 3: Geographic Block-Split")

    # 1. Load road network WITH geometry (needed for centroid)
    hr("STEP 1 — Load OSM Roads with Geometry")
    gdf_raw = gpd.read_file(ROADS_GPKG)
    print(f"  Loaded {len(gdf_raw):,} road edges from {ROADS_GPKG.name}")

    # 2. Preprocess features (same as baseline)
    hr("STEP 2 — Preprocess Features")
    df = prepare_features(gdf_raw)

    # Leakage check
    leaked = LEAKAGE_COLUMNS.intersection(set(FEATURES))
    if leaked:
        print(f"CRITICAL LEAKAGE: {leaked}")
        sys.exit(1)
    print(f"  Leakage check: PASS")
    print(f"  Feature list : {FEATURES}")
    n_pos   = df["has_accident"].sum()
    n_total = len(df)
    print(f"  Total roads  : {n_total:,}")
    print(f"  Positives    : {n_pos:,} ({n_pos/n_total*100:.2f}%)")

    # 3. Compute road centroids in WGS-84 to get lat/lon for grid assignment
    hr("STEP 3 — Compute Road Centroids and Assign Grid Cells")
    # Source geometry is in EPSG:32643 (UTM); reproject to WGS-84 for grid
    gdf_wgs = gdf_raw.to_crs("EPSG:4326")
    centroids = gdf_wgs.geometry.centroid
    df["centroid_lat"] = centroids.y.values
    df["centroid_lon"] = centroids.x.values

    # Assign each road to a grid cell
    df["lat_bin"] = np.floor(df["centroid_lat"] / GRID_DEG).astype(int)
    df["lon_bin"] = np.floor(df["centroid_lon"] / GRID_DEG).astype(int)
    df["grid_cell"] = df["lat_bin"].astype(str) + "_" + df["lon_bin"].astype(str)

    total_cells = df["grid_cell"].nunique()
    print(f"  Grid resolution : {GRID_DEG}° × {GRID_DEG}° per cell")
    print(f"  Total grid cells: {total_cells}")
    print(f"  Roads per cell  : min={df.groupby('grid_cell').size().min()}  "
          f"max={df.groupby('grid_cell').size().max()}  "
          f"mean={df.groupby('grid_cell').size().mean():.0f}")

    # Lat/lon extent
    print(f"  Centroid lat range: [{df['centroid_lat'].min():.4f}, {df['centroid_lat'].max():.4f}]")
    print(f"  Centroid lon range: [{df['centroid_lon'].min():.4f}, {df['centroid_lon'].max():.4f}]")

    # 4. Sort cells reproducibly and split 70 / 15 / 15
    hr("STEP 4 — Geographic Block Split (70 / 15 / 15)")
    all_cells = sorted(df["grid_cell"].unique())
    n_cells   = len(all_cells)

    n_train_cells = int(n_cells * 0.70)
    n_val_cells   = int(n_cells * 0.15)
    # test gets remainder
    train_cells = set(all_cells[:n_train_cells])
    val_cells   = set(all_cells[n_train_cells : n_train_cells + n_val_cells])
    test_cells  = set(all_cells[n_train_cells + n_val_cells:])

    # Verify zero overlap
    assert len(train_cells & val_cells)  == 0, "train ∩ val overlap!"
    assert len(train_cells & test_cells) == 0, "train ∩ test overlap!"
    assert len(val_cells   & test_cells) == 0, "val ∩ test overlap!"
    assert len(train_cells) + len(val_cells) + len(test_cells) == n_cells

    print(f"  Total cells    : {n_cells}")
    print(f"  Train cells    : {len(train_cells)} ({len(train_cells)/n_cells*100:.1f}%)")
    print(f"  Val cells      : {len(val_cells)} ({len(val_cells)/n_cells*100:.1f}%)")
    print(f"  Test cells     : {len(test_cells)} ({len(test_cells)/n_cells*100:.1f}%)")
    print(f"  Zero overlap   : ✓ VERIFIED")

    train_mask = df["grid_cell"].isin(train_cells)
    val_mask   = df["grid_cell"].isin(val_cells)
    test_mask  = df["grid_cell"].isin(test_cells)

    def part_stats(name, mask):
        sub = df[mask]
        pos = sub["has_accident"].sum()
        neg = len(sub) - pos
        print(f"  {name:<12}: {len(sub):>7,} roads   pos={pos:,} ({pos/len(sub)*100:.2f}%)   neg={neg:,}")

    part_stats("Train",      train_mask)
    part_stats("Validation", val_mask)
    part_stats("Test",       test_mask)

    # 5. Prepare X / y
    X_train = df.loc[train_mask, FEATURES]
    y_train = df.loc[train_mask, "has_accident"]
    X_val   = df.loc[val_mask,   FEATURES]
    y_val   = df.loc[val_mask,   "has_accident"]
    X_test  = df.loc[test_mask,  FEATURES]
    y_test  = df.loc[test_mask,  "has_accident"]

    # 6. scale_pos_weight from TRAIN only
    hr("STEP 5 — Class Imbalance (Training Partition Only)")
    t_neg = (y_train == 0).sum()
    t_pos = y_train.sum()
    spw   = t_neg / t_pos
    print(f"  Train negatives      : {t_neg:,}")
    print(f"  Train positives      : {t_pos:,}")
    print(f"  scale_pos_weight     : {spw:.4f}")

    # 7. Train
    hr("STEP 6 — Train XGBoost (same config as baseline)")
    cfg = {**XGBOOST_CONFIG, "scale_pos_weight": round(spw, 4)}
    print(f"  Config: {json.dumps({k:v for k,v in cfg.items()}, indent=4)}")
    model = XGBClassifier(**cfg, verbosity=0)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # 8. Evaluate
    hr("STEP 7 — Evaluation")
    val_m, _, _   = evaluate("VALIDATION (geographic)", model, X_val, y_val)
    test_m, test_prob, test_pred = evaluate("TEST (geographic, untouched)", model, X_test, y_test)

    # 9. Baseline comparison
    hr("STEP 8 — Comparison: Random Split vs Geographic Split (Test Set)")
    print(f"  {'Metric':<20} {'Random Split':>15} {'Geo Split':>15}")
    print(f"  {'-'*50}")
    comparisons = [
        ("ROC-AUC",   0.8732, test_m["roc_auc"]),
        ("PR-AUC",    0.2627, test_m["pr_auc"]),
        ("Precision", 0.0829, test_m["precision"]),
        ("Recall",    0.7312, test_m["recall"]),
        ("F1",        0.1490, test_m["f1"]),
    ]
    for metric, old, new in comparisons:
        delta = new - old
        sign  = "+" if delta >= 0 else ""
        print(f"  {metric:<20} {old:>15.4f} {new:>15.4f}   ({sign}{delta:.4f})")

    # Feature importance
    hr("FEATURE IMPORTANCE (gain)")
    feat_names   = FEATURES
    importances  = model.get_booster().get_score(importance_type="gain")
    for i, feat in enumerate(feat_names):
        score = importances.get(f"f{i}", importances.get(feat, 0))
        print(f"  {feat:<20} {score:.4f}")

    # 10. Save model
    model.save_model(str(GEO_MODEL))
    print(f"\nModel saved → {GEO_MODEL}")

    # 11. Save predictions (separate file — does NOT overwrite random-split predictions)
    pred_df = df.loc[test_mask, ["unique_edge_id", "highway", "length_km", "grid_cell"]].copy()
    pred_df["actual_has_accident"]   = y_test.values
    pred_df["predicted_probability"] = test_prob
    pred_df["predicted_class"]       = test_pred
    pred_df.to_csv(GEO_PRED_CSV, index=False)
    print(f"Predictions saved → {GEO_PRED_CSV}")
    print("\nNote: random-split baseline predictions preserved at xgboost_test_predictions.csv")

    hr("DONE — Experiment 3 Complete")
    print("  Do NOT tune threshold or hyperparameters yet.")
    print("  Next: review spatial leakage reduction from this result.")


if __name__ == "__main__":
    main()
