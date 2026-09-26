"""
scripts/validate_module6.py
============================
Module 6 — Validation & Test Suite
=====================================

Runs 10 validation checks against Module 6 outputs and functions.

Run from the backend/ directory:
    python scripts/validate_module6.py

All checks must pass before Module 6 is considered complete.
"""

from __future__ import annotations

import io
import json
import sys
import traceback
from pathlib import Path

import geopandas as gpd
import pandas as pd

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Ensure 'backend/' is importable ──────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.features.accident_features import (
    filter_bengaluru_accidents,
    validate_coordinates,
    remove_duplicates,
    normalize_severity,
    create_accident_geodataframe,
    detect_accident_hotspots,
    calculate_segment_accident_features,
    GEOGRAPHIC_CRS,
)

PROCESSED_DIR = BACKEND_DIR / "data" / "processed"

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    print(f"  {status}  {name}")
    if detail:
        print(f"          {detail}")


def _load_validated_csv() -> pd.DataFrame | None:
    path = PROCESSED_DIR / "validated_accidents.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def _load_hotspots_csv() -> pd.DataFrame | None:
    path = PROCESSED_DIR / "accident_hotspots.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


# ===============================================================================

print("\n" + "=" * 65)
print("  Module 6 Validation Suite")
print("=" * 65 + "\n")

# -- Check 1: (0,0) coordinates are removed -----------------------------------
print("Check 1 - (0,0) coordinates are removed")
try:
    sample = pd.DataFrame({
        "DISTRICTNAME": ["Bengaluru City", "Bengaluru City", "Bengaluru City"],
        "Latitude":     [0.0, 12.97, 13.0],
        "Longitude":    [0.0, 77.59, 77.6],
        "Year":         [2022, 2022, 2021],
        "Severity":     ["Fatal", "Simple Injury", "Grievous Injury"],
        "Accident_Road": ["Road A", "Road B", "Road C"],
    })
    df_filtered, stats = validate_coordinates(sample)
    check(
        "Zero coordinates removed",
        stats["zero_coordinates"] == 1 and len(df_filtered) == 2,
        f"zeros_removed={stats['zero_coordinates']}, remaining={len(df_filtered)}",
    )
except Exception as e:
    check("Zero coordinates removed", False, str(e))

# -- Check 2: Missing coordinates are removed ---------------------------------
print("\nCheck 2 - Missing coordinates are removed")
try:
    sample_missing = pd.DataFrame({
        "DISTRICTNAME": ["Bengaluru City", "Bengaluru City"],
        "Latitude":     [None, 12.97],
        "Longitude":    [77.59, 77.59],
        "Year":         [2022, 2022],
        "Severity":     ["Fatal", "Simple Injury"],
        "Accident_Road": ["Road A", "Road B"],
    })
    df_filtered2, stats2 = validate_coordinates(sample_missing)
    check(
        "Missing coordinates removed",
        stats2["missing_coordinates"] == 1 and len(df_filtered2) == 1,
        f"missing_removed={stats2['missing_coordinates']}, remaining={len(df_filtered2)}",
    )
except Exception as e:
    check("Missing coordinates removed", False, str(e))

# -- Check 3: Bengaluru filtering works ---------------------------------------
print("\nCheck 3 - Bengaluru filtering")
try:
    sample_all = pd.DataFrame({
        "DISTRICTNAME": ["Bengaluru City", "Bengaluru Dist", "Mysuru Dist", "  bengaluru city  "],
    })
    result = filter_bengaluru_accidents(sample_all, keywords=["bengaluru"])
    check(
        "Bengaluru filter keeps Bengaluru City, Dist and normalised variants",
        len(result) == 3,
        f"kept={len(result)} (expected 3)",
    )
    check(
        "Mysuru not included",
        "mysuru" not in result["DISTRICTNAME"].str.lower().values,
    )
except Exception as e:
    check("Bengaluru filtering", False, str(e))
    check("Mysuru not included", False, str(e))

# -- Check 4: Duplicate detection works ---------------------------------------
print("\nCheck 4 - Duplicate detection")
try:
    sample_dupes = pd.DataFrame({
        "Year":         [2022, 2022, 2021],
        "Latitude":     [12.97, 12.97, 12.95],
        "Longitude":    [77.59, 77.59, 77.55],
        "Accident_Road": ["NH 44", "NH 44", "Ring Road"],
        "Severity":     ["Fatal", "Fatal", "Simple Injury"],
    })
    df_dd, dedup_stats = remove_duplicates(sample_dupes)
    check(
        "Exact duplicate removed",
        dedup_stats["duplicates_removed"] == 1 and len(df_dd) == 2,
        f"removed={dedup_stats['duplicates_removed']}, remaining={len(df_dd)}",
    )
except Exception as e:
    check("Duplicate detection", False, str(e))

# -- Check 5: Severity normalisation ------------------------------------------
print("\nCheck 5 - Severity normalisation")
try:
    sample_sev = pd.DataFrame({
        "Severity": ["Fatal", "Grievous Injury", "Simple Injury", "Damage Only", "Not Applicable", "BUDDISTS"]
    })
    df_sev = normalize_severity(sample_sev)
    mapping = df_sev.set_index("Severity")["severity_normalised"].to_dict()
    check("Fatal → fatal", mapping.get("Fatal") == "fatal", str(mapping.get("Fatal")))
    check("Grievous Injury → serious", mapping.get("Grievous Injury") == "serious", str(mapping.get("Grievous Injury")))
    check("Simple Injury → minor", mapping.get("Simple Injury") == "minor", str(mapping.get("Simple Injury")))
    check("Damage Only → minor", mapping.get("Damage Only") == "minor", str(mapping.get("Damage Only")))
    check("Not Applicable → unknown", mapping.get("Not Applicable") == "unknown", str(mapping.get("Not Applicable")))
except Exception as e:
    check("Severity normalisation", False, str(e))

# -- Check 6: GeoDataFrame is EPSG:4326 ---------------------------------------
print("\nCheck 6 - GeoDataFrame CRS")
try:
    sample_geo = pd.DataFrame({
        "Latitude":  [12.97, 13.0],
        "Longitude": [77.59, 77.6],
        "Year":      [2022, 2021],
    })
    gdf = create_accident_geodataframe(sample_geo)
    check(
        "GeoDataFrame CRS is EPSG:4326",
        str(gdf.crs) == "EPSG:4326",
        f"actual CRS={gdf.crs}",
    )
    check(
        "GeoDataFrame has geometry column",
        "geometry" in gdf.columns,
    )
except Exception as e:
    check("GeoDataFrame EPSG:4326", False, str(e))
    check("GeoDataFrame geometry column", False, str(e))

# -- Check 7: Hotspot detection with insufficient data does not crash ----------
print("\nCheck 7 - Hotspot detection: insufficient data")
try:
    tiny_df = pd.DataFrame({
        "Latitude":  [12.97],
        "Longitude": [77.59],
        "is_fatal":  [True],
        "Year":      [2022],
    })
    tiny_gdf = create_accident_geodataframe(tiny_df)
    hs = detect_accident_hotspots(tiny_gdf, eps_meters=300, min_samples=5)
    check(
        "Hotspot detection returns empty GDF with insufficient data",
        isinstance(hs, gpd.GeoDataFrame) and len(hs) == 0,
        f"hotspot count={len(hs)}",
    )
except Exception as e:
    check("Hotspot detection insufficient data", False, str(e))

# -- Check 8: Accident feature columns are present ----------------------------
print("\nCheck 8 - Segment accident feature columns")
try:
    acc_df = pd.DataFrame({
        "Latitude":  [12.97, 12.971, 12.972],
        "Longitude": [77.59, 77.591, 77.592],
        "is_fatal":  [True, False, False],
        "accident_year": [2022, 2021, 2020],
    })
    acc_gdf = create_accident_geodataframe(acc_df)
    # Empty hotspots for this test
    hs_gdf = gpd.GeoDataFrame(
        {"hotspot_id": [], "latitude": [], "longitude": [], "geometry": []},
        crs=GEOGRAPHIC_CRS,
    )
    feats = calculate_segment_accident_features(
        12.970, 77.590, acc_gdf, hs_gdf, radius_meters=500
    )
    expected_keys = [
        "accident_count", "fatal_accident_count", "nonfatal_accident_count",
        "accident_density_per_km2", "fatal_accident_density_per_km2",
        "distance_to_nearest_hotspot_m", "year_range", "search_radius_m",
        "night_accident_count", "weekend_accident_count", "accidents_at_similar_hour",
    ]
    missing = [k for k in expected_keys if k not in feats]
    check(
        "Segment features contain all expected keys",
        len(missing) == 0,
        f"missing={missing}",
    )
    check(
        "Time-aware features correctly None (no time data)",
        feats["night_accident_count"] is None and feats["weekend_accident_count"] is None,
    )
    check(
        "accident_count is an integer",
        isinstance(feats["accident_count"], int),
        f"type={type(feats['accident_count']).__name__}",
    )
except Exception as e:
    check("Segment feature columns", False, traceback.format_exc())

# -- Check 9: Missing optional columns don't crash pipeline -------------------
print("\nCheck 9 - Missing optional columns")
try:
    sparse_df = pd.DataFrame({
        "DISTRICTNAME": ["Bengaluru City", "Bengaluru City"],
        "Latitude":     [12.97, 13.0],
        "Longitude":    [77.59, 77.6],
        "Year":         [2022, 2021],
        # No Severity, No Collision_Type, No Road_Type, etc.
    })
    from app.features.accident_features import clean_accident_data, extract_temporal_features
    df_c = clean_accident_data(sparse_df)
    df_t = extract_temporal_features(df_c)
    check(
        "Pipeline handles missing optional columns without crash",
        True,
        f"Columns present: {df_t.columns.tolist()}",
    )
    check(
        "severity_normalised column added even when Severity absent",
        "severity_normalised" in df_c.columns,
    )
except Exception as e:
    check("Missing optional columns", False, traceback.format_exc())

# -- Check 10: No risk scores generated by Module 6 ---------------------------
print("\nCheck 10 - No risk/safety scores in Module 6")
try:
    import app.features.accident_features as af_module
    import ast, inspect, textwrap
    source = inspect.getsource(af_module)
    # Parse AST to extract only executable code lines (not docstrings/comments)
    tree = ast.parse(textwrap.dedent(source))
    code_lines = []
    for node in ast.walk(tree):
        # Collect actual import, call, and assignment statements — not string literals
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Call, ast.Assign, ast.FunctionDef, ast.ClassDef)):
            if hasattr(node, "lineno"):
                code_lines.append(source.splitlines()[node.lineno - 1].lower())
    code_text = "\n".join(code_lines)
    # Terms forbidden in actual code (not documentation)
    forbidden = ["import xgboost", "import shap", "import random_forest",
                 "risk_score =", "safety_score =", "route_ranking", "safest_route"]
    found = [f for f in forbidden if f.lower() in code_text]
    check(
        "No risk/safety score logic in accident_features.py",
        len(found) == 0,
        f"Found forbidden terms in code: {found}" if found else "Clean (docstring mentions excluded)",
    )
except Exception as e:
    check("No risk scores in Module 6", False, str(e))

# -- Check 11: Processed output files exist -----------------------------------
print("\nCheck 11 - Output files exist")
output_files = [
    "validated_accidents.csv",
    "validated_accidents.geojson",
    "accident_hotspots.csv",
    "accident_hotspots.geojson",
    "accident_processing_report.json",
]
for fname in output_files:
    fpath = PROCESSED_DIR / fname
    check(
        f"Output file exists: {fname}",
        fpath.exists(),
        f"path={fpath}",
    )

# Check report has expected keys
report_path = PROCESSED_DIR / "accident_processing_report.json"
if report_path.exists():
    with open(report_path) as f:
        report = json.load(f)
    expected_report_keys = [
        "total_records", "bengaluru_records_before_coord_filter",
        "final_valid_records", "fatal_accidents", "hotspots_detected",
    ]
    missing_rk = [k for k in expected_report_keys if k not in report]
    check(
        "Processing report has expected keys",
        len(missing_rk) == 0,
        f"missing keys={missing_rk}",
    )

# -- Summary -------------------------------------------------------------------
print("\n" + "=" * 65)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n  Result: {passed}/{total} checks passed\n")

if passed == total:
    print("  PASS  All validation checks passed. Module 6 is complete.")
else:
    failed = [(n, d) for n, ok, d in results if not ok]
    print("  FAIL  Some checks failed:")
    for name, detail in failed:
        print(f"       * {name}: {detail}")

print()
sys.exit(0 if passed == total else 1)
