import pandas as pd
import numpy as np
import xgboost as xgb
from pathlib import Path

csv_path = Path("backend/data/processed/osm_road_accident_features.csv")
model_path = Path("backend/models/xgboost_baseline.json")

df = pd.read_csv(csv_path, low_memory=False)

HIGHWAY_RISK_ORDER = {
    "motorway": 8, "trunk": 7, "primary": 6, "secondary": 5,
    "tertiary": 4, "unclassified": 3, "residential": 2, "service": 1, "living_street": 0
}

def clean_hw(hw):
    hw = str(hw)
    if hw.startswith("["):
        hw = hw.replace("[", "").replace("]", "").replace("'", "")
        return hw.split(",")[0].strip()
    return hw.strip()

if "highway_enc" not in df.columns:
    df["highway_clean"] = df["highway"].apply(clean_hw)
    df["highway_enc"] = df["highway_clean"].map(HIGHWAY_RISK_ORDER).fillna(-1).astype(int)

df["oneway"] = df["oneway"].map({True: 1, False: 0, "True": 1, "False": 0}).fillna(0).astype(int)
df["junction"] = df["junction"].notna().astype(int)
df["bridge"] = df["bridge"].notna().astype(int)
df["tunnel"] = df["tunnel"].notna().astype(int)

features = ["highway_enc", "length_km", "oneway", "junction", "bridge", "tunnel"]
X = df[features].copy()

booster = xgb.Booster()
booster.load_model(str(model_path))

dmatrix = xgb.DMatrix(X)
shap_values = booster.predict(dmatrix, pred_contribs=True)

bias = shap_values[:, -1]
shap_feats = shap_values[:, :-1]

mean_abs_shap = np.mean(np.abs(shap_feats), axis=0)
mean_shap = np.mean(shap_feats, axis=0)

summary_df = pd.DataFrame({
    "feature": features,
    "mean_abs_shap": mean_abs_shap,
    "mean_shap": mean_shap,
    "min_shap": np.min(shap_feats, axis=0),
    "max_shap": np.max(shap_feats, axis=0)
}).sort_values(by="mean_abs_shap", ascending=False)

print("BASE MARGIN (bias):", float(np.mean(bias)))
print(summary_df.to_string(index=False))

print("\n--- SHAP IMPACT BY FEATURE VALUE ---")
for i, feat in enumerate(features):
    corr = np.corrcoef(X[feat].values, shap_feats[:, i])[0, 1]
    print(f"\nFeature: {feat} (Correlation with SHAP: {corr:+.4f})")
    if feat in ["highway_enc", "oneway", "junction", "bridge", "tunnel"]:
        group_df = pd.DataFrame({"val": X[feat], "shap": shap_feats[:, i]})
        agg = group_df.groupby("val")["shap"].agg(["count", "mean", "min", "max"])
        print(agg.to_string())
    else:
        # Continuous feature length_km
        q_bins = pd.qcut(X[feat], q=5, duplicates="drop")
        group_df = pd.DataFrame({"bin": q_bins, "shap": shap_feats[:, i]})
        print(group_df.groupby("bin")["shap"].agg(["count", "mean", "min", "max"]).to_string())
