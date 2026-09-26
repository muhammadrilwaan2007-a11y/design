"""
scripts/process_accidents.py
============================
Module 6 -- Historical Accident Processing Pipeline
====================================================

Offline script to transform the raw Karnataka accident CSV into clean,
spatially-validated Bengaluru accident features and hotspots.

Run from the backend/ directory:
    python scripts/process_accidents.py

Outputs
-------
  data/processed/validated_accidents.csv
  data/processed/validated_accidents.geojson
  data/processed/accident_hotspots.csv
  data/processed/accident_hotspots.geojson
  data/processed/accident_processing_report.json

This script does NOT compute safety/risk scores.
That belongs to Module 8.
"""

from __future__ import annotations

import io
import logging
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Ensure 'backend/' is importable ──────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import get_settings
from app.features.accident_features import (
    load_accident_data,
    filter_bengaluru_accidents,
    validate_coordinates,
    remove_duplicates,
    clean_accident_data,
    extract_temporal_features,
    create_accident_geodataframe,
    detect_accident_hotspots,
    calculate_accident_features,
    save_processed_accidents,
    save_hotspots,
    generate_processing_report,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("process_accidents")


def _hr(label: str = "") -> None:
    print(f"\n{'-' * 60}  {label}")


def run_pipeline() -> None:
    """Execute the full Module 6 accident processing pipeline."""
    t0 = time.time()
    settings = get_settings()

    processed_dir = BACKEND_DIR / settings.processed_data_dir
    features_dir  = BACKEND_DIR / settings.features_data_dir

    # Bengaluru filter keywords
    blr_keywords = [k.strip().lower() for k in settings.bengaluru_filter_keywords.split(",")]

    # Collect statistics for the processing report
    report: dict = {
        "module": "Module 6 — Historical Accident Analysis",
        "csv_path": settings.accident_csv_path,
    }

    # ── Step 1: Load ──────────────────────────────────────────────────────────
    _hr("STEP 1 — Load CSV")
    try:
        df_raw = load_accident_data(settings.accident_csv_path)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    report["total_records"] = len(df_raw)
    report["total_columns"] = len(df_raw.columns)
    report["all_columns"] = df_raw.columns.tolist()
    print(f"  Total records loaded : {len(df_raw):,}")
    print(f"  Columns              : {len(df_raw.columns)}")

    # ── Step 2: Filter Bengaluru ──────────────────────────────────────────────
    _hr("STEP 2 — Filter Bengaluru")
    df_blr = filter_bengaluru_accidents(df_raw, keywords=blr_keywords)
    report["bengaluru_records_before_coord_filter"] = len(df_blr)
    print(f"  Bengaluru records    : {len(df_blr):,}")

    # District breakdown
    if "DISTRICTNAME" in df_blr.columns:
        dist_counts = df_blr["DISTRICTNAME"].value_counts().to_dict()
        report["district_breakdown"] = dist_counts
        for dist, cnt in dist_counts.items():
            print(f"    {dist:<30} {cnt:,}")

    # ── Step 3: Validate Coordinates ──────────────────────────────────────────
    _hr("STEP 3 — Validate Coordinates")
    df_valid, coord_stats = validate_coordinates(
        df_blr,
        lat_min=settings.blr_lat_min,
        lat_max=settings.blr_lat_max,
        lon_min=settings.blr_lon_min,
        lon_max=settings.blr_lon_max,
    )
    report.update(coord_stats)
    print(f"  Missing coordinates  : {coord_stats['missing_coordinates']:,}")
    print(f"  Zero  coordinates    : {coord_stats['zero_coordinates']:,}")
    print(f"  Outside bounding box : {coord_stats['outside_bounding_box']:,}")
    print(f"  Outside poly boundary: {coord_stats['outside_boundary_polygon']:,}")
    print(f"  Valid records        : {coord_stats['valid_after_coordinate_check']:,}")

    # ── Step 4: Remove Duplicates ─────────────────────────────────────────────
    _hr("STEP 4 — Remove Duplicates")
    df_deduped, dedup_stats = remove_duplicates(df_valid)
    report.update(dedup_stats)
    print(f"  Deduplication key    : {dedup_stats['deduplication_key']}")
    print(f"  Duplicates removed   : {dedup_stats['duplicates_removed']:,}")
    print(f"  Records remaining    : {dedup_stats['records_after_deduplication']:,}")

    # ── Step 5: Clean & Normalise ─────────────────────────────────────────────
    _hr("STEP 5 — Clean & Normalise")
    df_clean = clean_accident_data(df_deduped)
    sev_counts = df_clean["severity_normalised"].value_counts().to_dict()
    report["severity_distribution"] = sev_counts
    print(f"  Severity distribution:")
    for k, v in sev_counts.items():
        print(f"    {k:<15} {v:,}")

    # ── Step 6: Temporal Features ─────────────────────────────────────────────
    _hr("STEP 6 — Temporal Features")
    df_temporal = extract_temporal_features(df_clean)
    yr = df_temporal.get("accident_year", df_temporal.get("Year"))
    if yr is not None and hasattr(yr, "dropna"):
        y_min = df_temporal["accident_year"].min(skipna=True)
        y_max = df_temporal["accident_year"].max(skipna=True)
        report["year_range"] = [int(y_min), int(y_max)]
        print(f"  Year range           : {y_min} – {y_max}")

    yr_dist = df_temporal["accident_year"].value_counts().sort_index().to_dict()
    report["year_distribution"] = {str(k): int(v) for k, v in yr_dist.items()}
    for year, count in sorted(yr_dist.items()):
        print(f"    {year}  {count:,}")
    print("  NOTE: Only Year available — month/hour/day features not in dataset.")

    # ── Step 7: Create GeoDataFrame ───────────────────────────────────────────
    _hr("STEP 7 — Create GeoDataFrame")
    gdf = create_accident_geodataframe(df_temporal)
    report["final_valid_records"] = len(gdf)
    report["fatal_accidents"] = int(gdf["is_fatal"].sum())
    report["nonfatal_accidents"] = int((~gdf["is_fatal"]).sum())
    print(f"  Final valid records  : {len(gdf):,}")
    print(f"  Fatal accidents      : {report['fatal_accidents']:,}")
    print(f"  Non-fatal accidents  : {report['nonfatal_accidents']:,}")
    print(f"  CRS                  : {gdf.crs}")

    # ── Step 8: Detect Hotspots ───────────────────────────────────────────────
    _hr("STEP 8 — Detect Accident Hotspots (DBSCAN)")
    print(f"  eps={settings.hotspot_eps_meters:.0f}m  min_samples={settings.hotspot_min_samples}")
    hotspots_gdf = detect_accident_hotspots(
        gdf,
        eps_meters=settings.hotspot_eps_meters,
        min_samples=settings.hotspot_min_samples,
    )
    report["hotspots_detected"] = len(hotspots_gdf)
    report["hotspot_eps_meters"] = settings.hotspot_eps_meters
    report["hotspot_min_samples"] = settings.hotspot_min_samples
    print(f"  Hotspots detected    : {len(hotspots_gdf):,}")
    if len(hotspots_gdf) > 0:
        print(f"  Largest hotspot      : {hotspots_gdf['accident_count'].max()} accidents")
        print(f"  Hotspot fatal total  : {hotspots_gdf['fatal_accident_count'].sum()}")

    # ── Step 9: Save Outputs ──────────────────────────────────────────────────
    _hr("STEP 9 — Save Outputs")
    csv_path, geojson_path = save_processed_accidents(gdf, processed_dir)
    hs_csv_path, hs_geojson_path = save_hotspots(hotspots_gdf, processed_dir)

    report["output_files"] = {
        "validated_accidents_csv": str(csv_path),
        "validated_accidents_geojson": str(geojson_path),
        "accident_hotspots_csv": str(hs_csv_path),
        "accident_hotspots_geojson": str(hs_geojson_path),
    }
    print(f"  validated_accidents.csv     → {csv_path}")
    print(f"  validated_accidents.geojson → {geojson_path}")
    print(f"  accident_hotspots.csv       → {hs_csv_path}")
    print(f"  accident_hotspots.geojson   → {hs_geojson_path}")

    # ── Step 10: Processing Report ────────────────────────────────────────────
    _hr("STEP 10 — Save Processing Report")
    report["processing_time_seconds"] = round(time.time() - t0, 2)
    report_path = generate_processing_report(report, processed_dir)
    report["output_files"]["processing_report"] = str(report_path)
    print(f"  Report saved → {report_path}")

    # ── Final Summary ─────────────────────────────────────────────────────────
    _hr("PIPELINE COMPLETE")
    print(f"  +----------------------------------------------+")
    print(f"  |     Module 6 -- Processing Summary           |")
    print(f"  +----------------------------------------------+")
    print(f"  | Total records loaded    : {report['total_records']:>10,}         |")
    print(f"  | Bengaluru records       : {report['bengaluru_records_before_coord_filter']:>10,}         |")
    print(f"  | Missing coordinates     : {report.get('missing_coordinates', 0):>10,}         |")
    print(f"  | Zero coordinates        : {report.get('zero_coordinates', 0):>10,}         |")
    print(f"  | Outside bounding box    : {report.get('outside_bounding_box', 0):>10,}         |")
    print(f"  | Duplicates removed      : {report.get('duplicates_removed', 0):>10,}         |")
    print(f"  | Final valid records     : {report['final_valid_records']:>10,}         |")
    print(f"  | Fatal accidents         : {report['fatal_accidents']:>10,}         |")
    print(f"  | Hotspots detected       : {report['hotspots_detected']:>10,}         |")
    print(f"  | Processing time (s)     : {report['processing_time_seconds']:>10.1f}         |")
    print(f"  +----------------------------------------------+\n")

    print("  NOTE: Module 6 output is historical accident evidence only.")
    print("  Risk scoring belongs to Module 8.\n")


if __name__ == "__main__":
    run_pipeline()
