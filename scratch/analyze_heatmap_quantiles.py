import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import pandas as pd
import numpy as np
from app.calibration import get_calibrator

csv_path = Path("backend/data/processed/xgboost_test_predictions.csv")
dfp = pd.read_csv(csv_path)

calibrator = get_calibrator()
dfp["cal_prob"] = calibrator.calibrate(dfp["predicted_probability"].values)
dfp["safety_score"] = (100.0 - np.sqrt(dfp["cal_prob"]) * 100.0).round()

def clean_hw(hw):
    hw = str(hw)
    if hw.startswith("["):
        hw = hw.replace("[", "").replace("]", "").replace("'", "")
        return hw.split(",")[0].strip()
    return hw.strip()

dfp["hw_clean"] = dfp["highway"].apply(clean_hw)
summary = dfp.groupby("hw_clean").agg(
    count=("cal_prob", "count"),
    mean_cal=("cal_prob", "mean"),
    median_cal=("cal_prob", "median"),
    min_cal=("cal_prob", "min"),
    max_cal=("cal_prob", "max"),
    mean_score=("safety_score", "mean"),
    median_score=("safety_score", "median")
).sort_values(by="mean_cal")

print(summary.to_string())

print("\n--- Network-wide quantiles (computed from test set N=59,124) ---")
q_levels = [0.10, 0.25, 0.50, 0.70, 0.80, 0.85, 0.90, 0.95, 0.975, 0.99]
for q in q_levels:
    val = float(np.percentile(dfp["cal_prob"].values, q * 100))
    score = 100.0 - np.sqrt(val) * 100.0
    print(f"Quantile P{int(q*100):02d}: cal_prob = {val:.5f} ({val*100:6.3f}%), Safety Score = {score:4.1f}")
