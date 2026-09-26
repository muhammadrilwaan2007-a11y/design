"""
backend/app/features/accident_features.py
==========================================
Module 6 — Historical Accident Analysis
========================================

This module transforms the raw Karnataka accident dataset into clean,
validated, spatially-indexed accident features for Bengaluru.

Responsibilities
----------------
- Load and filter Bengaluru accident records from the CSV
- Clean and normalise all categorical/numeric fields
- Validate geographic coordinates
- Remove duplicate records
- Build a GeoPandas GeoDataFrame in EPSG:4326
- Detect historical accident hotspots via DBSCAN
- Expose reusable functions for segment-level feature extraction
  (consumed by Module 7 / Module 8)

This module does NOT:
- Compute final risk/safety scores
- Use live traffic, incidents, or weather data
- Train any ML model

Outputs (written by scripts/process_accidents.py)
-------------------------------------------------
  data/processed/validated_accidents.csv
  data/processed/validated_accidents.geojson
  data/processed/accident_hotspots.csv
  data/processed/accident_hotspots.geojson
  data/processed/accident_processing_report.json
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# ── Constants / defaults (override via Settings) ─────────────────────────────
DEFAULT_CSV_ENCODING: str = "latin-1"

# Bengaluru bounding box (WGS84) — used when no polygon boundary is provided
DEFAULT_BLR_LAT_MIN: float = 12.7
DEFAULT_BLR_LAT_MAX: float = 13.3
DEFAULT_BLR_LON_MIN: float = 77.3
DEFAULT_BLR_LON_MAX: float = 77.9

# Keyword filter for DISTRICTNAME column
DEFAULT_BLR_KEYWORDS: list[str] = ["bengaluru"]

# DBSCAN defaults
DEFAULT_HOTSPOT_EPS_M: float = 300.0   # metres
DEFAULT_HOTSPOT_MIN_SAMPLES: int = 5

# Segment feature association radius (metres)
DEFAULT_SEGMENT_RADIUS_M: float = 500.0

# UTM Zone 43N — appropriate projected CRS for Bengaluru / Karnataka
# Used for metre-based distance calculations
PROJECTED_CRS: str = "EPSG:32643"
GEOGRAPHIC_CRS: str = "EPSG:4326"

# ── Severity normalisation map ────────────────────────────────────────────────
# Inspect dataset: Fatal, Grievous Injury, Simple Injury, Damage Only, Not Applicable
SEVERITY_MAP: dict[str, str] = {
    "fatal": "fatal",
    "grievous injury": "serious",
    "serious injury": "serious",
    "simple injury": "minor",
    "minor injury": "minor",
    "damage only": "minor",
    "not applicable": "unknown",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  1. DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_accident_data(
    csv_path: str | Path,
    encoding: str = DEFAULT_CSV_ENCODING,
) -> pd.DataFrame:
    """
    Load the raw accident CSV into a DataFrame.

    Parameters
    ----------
    csv_path : path to the raw CSV file
    encoding : file encoding (default 'latin-1')

    Returns
    -------
    DataFrame with all original columns intact.

    Raises
    ------
    FileNotFoundError  — if csv_path does not exist
    ValueError         — if the file is empty or cannot be parsed
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Accident CSV not found: {path}\n"
            "Update accident_csv_path in settings.py or the .env file."
        )

    logger.info("Loading accident data from %s …", path)
    try:
        df = pd.read_csv(path, encoding=encoding, low_memory=False)
    except UnicodeDecodeError:
        # Fallback: try cp1252 then utf-8 with errors replaced
        logger.warning("latin-1 failed, retrying with cp1252 …")
        df = pd.read_csv(path, encoding="cp1252", low_memory=False)

    if df.empty:
        raise ValueError("Accident CSV loaded but is empty.")

    logger.info("Loaded %d records, %d columns.", len(df), len(df.columns))
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  2. BENGALURU FILTERING
# ═══════════════════════════════════════════════════════════════════════════════

def filter_bengaluru_accidents(
    df: pd.DataFrame,
    keywords: list[str] = DEFAULT_BLR_KEYWORDS,
    district_col: str = "DISTRICTNAME",
) -> pd.DataFrame:
    """
    Filter records to Bengaluru using DISTRICTNAME column.

    Normalises values (lowercase + strip) before matching.
    Matches any row whose district name contains at least one keyword.

    Parameters
    ----------
    df        : full accident DataFrame
    keywords  : list of lowercase substrings to match (e.g. ['bengaluru'])
    district_col : column to filter on

    Returns
    -------
    Filtered DataFrame of Bengaluru accident records.
    """
    if district_col not in df.columns:
        raise KeyError(
            f"Column '{district_col}' not found. Available: {df.columns.tolist()}"
        )

    normalised = df[district_col].astype(str).str.lower().str.strip()
    mask = normalised.apply(lambda v: any(kw in v for kw in keywords))
    result = df[mask].copy()

    logger.info(
        "Bengaluru filter: %d / %d records match keywords %s",
        len(result), len(df), keywords,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  3. COORDINATE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def validate_coordinates(
    df: pd.DataFrame,
    lat_col: str = "Latitude",
    lon_col: str = "Longitude",
    lat_min: float = DEFAULT_BLR_LAT_MIN,
    lat_max: float = DEFAULT_BLR_LAT_MAX,
    lon_min: float = DEFAULT_BLR_LON_MIN,
    lon_max: float = DEFAULT_BLR_LON_MAX,
    boundary_polygon=None,
) -> tuple[pd.DataFrame, dict]:
    """
    Remove records with missing, zero, invalid, or out-of-bounds coordinates.

    Steps
    -----
    1. Convert lat/lon to numeric (coerce errors → NaN)
    2. Drop rows where lat or lon is NaN
    3. Drop rows where lat == 0 or lon == 0 (sentinel zeros)
    4. Drop rows outside the Bengaluru bounding box
    5. (Optional) Drop rows outside a Bengaluru boundary polygon

    Parameters
    ----------
    df               : Bengaluru-filtered DataFrame
    lat_col / lon_col: column names for coordinates
    lat_min/max      : bounding box latitude range
    lon_min/max      : bounding box longitude range
    boundary_polygon : optional Shapely Polygon for precise city boundary

    Returns
    -------
    (clean_df, stats_dict) where stats_dict contains per-step removal counts.
    """
    stats: dict[str, int] = {}
    n_start = len(df)

    # Step 1 — Convert to numeric
    df = df.copy()
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    # Step 2 — Remove NaN
    missing_mask = df[lat_col].isna() | df[lon_col].isna()
    stats["missing_coordinates"] = int(missing_mask.sum())
    df = df[~missing_mask]

    # Step 3 — Remove (0, 0) sentinel zeros
    zero_mask = (df[lat_col] == 0) | (df[lon_col] == 0)
    stats["zero_coordinates"] = int(zero_mask.sum())
    df = df[~zero_mask]

    # Step 4 — Bounding box
    bbox_mask = (
        df[lat_col].between(lat_min, lat_max) &
        df[lon_col].between(lon_min, lon_max)
    )
    stats["outside_bounding_box"] = int((~bbox_mask).sum())
    df = df[bbox_mask]

    # Step 5 — Optional precise boundary
    stats["outside_boundary_polygon"] = 0
    if boundary_polygon is not None:
        inside = df.apply(
            lambda row: boundary_polygon.contains(
                Point(row[lon_col], row[lat_col])
            ),
            axis=1,
        )
        stats["outside_boundary_polygon"] = int((~inside).sum())
        df = df[inside]
        logger.info(
            "Boundary polygon filter removed %d records.",
            stats["outside_boundary_polygon"],
        )

    stats["valid_after_coordinate_check"] = len(df)
    logger.info(
        "Coordinate validation: %d → %d valid records  "
        "(missing=%d, zeros=%d, outside_bbox=%d, outside_poly=%d)",
        n_start,
        len(df),
        stats["missing_coordinates"],
        stats["zero_coordinates"],
        stats["outside_bounding_box"],
        stats["outside_boundary_polygon"],
    )
    return df, stats


# ═══════════════════════════════════════════════════════════════════════════════
#  4. DUPLICATE REMOVAL
# ═══════════════════════════════════════════════════════════════════════════════

def remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Remove duplicate accident records.

    Strategy
    --------
    Crime_No is not a reliable unique identifier in this dataset
    (only ~4 unique values observed across 18k Bengaluru records).

    Instead, use a composite key:
        Year + Latitude + Longitude + Accident_Road + Severity

    Only exact matches across all five fields are considered duplicates.
    Records with the same coordinates but different severity/year/road
    are intentionally kept.

    Returns
    -------
    (deduplicated_df, stats_dict)
    """
    n_before = len(df)

    # Build composite key from available columns
    key_cols = []
    for col in ["Year", "Latitude", "Longitude", "Accident_Road", "Severity"]:
        if col in df.columns:
            key_cols.append(col)

    if not key_cols:
        logger.warning("No suitable deduplication columns found — skipping.")
        return df, {"duplicates_detected": 0, "duplicates_removed": 0}

    df = df.copy()
    dupes_mask = df.duplicated(subset=key_cols, keep="first")
    n_dupes = int(dupes_mask.sum())
    df = df[~dupes_mask]

    stats = {
        "deduplication_key": key_cols,
        "duplicates_detected": n_dupes,
        "duplicates_removed": n_dupes,
        "records_after_deduplication": len(df),
    }
    logger.info(
        "Deduplication (key=%s): removed %d duplicates, %d records remain.",
        key_cols, n_dupes, len(df),
    )
    return df, stats


# ═══════════════════════════════════════════════════════════════════════════════
#  5. DATA CLEANING
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise_text(series: pd.Series) -> pd.Series:
    """Lowercase + strip a string Series; fill NaN with 'unknown'."""
    return series.astype(str).str.lower().str.strip().replace(
        {"nan": "unknown", "not applicable": "unknown", "": "unknown"}
    )


def normalize_severity(df: pd.DataFrame, col: str = "Severity") -> pd.DataFrame:
    """
    Map raw severity values to canonical categories:
        fatal / serious / minor / unknown

    Inspects the actual values in the column before mapping.
    Preserves the original column as 'Severity_original'.

    Parameters
    ----------
    df  : DataFrame containing the Severity column
    col : name of the severity column

    Returns
    -------
    DataFrame with added 'severity_normalised' column.
    """
    df = df.copy()
    if col not in df.columns:
        logger.warning("Severity column '%s' not found — skipping normalisation.", col)
        df["severity_normalised"] = "unknown"
        return df

    df["Severity_original"] = df[col].copy()
    normalised_raw = _normalise_text(df[col])

    def _map(value: str) -> str:
        for key, category in SEVERITY_MAP.items():
            if key in value:
                return category
        return "unknown"

    df["severity_normalised"] = normalised_raw.apply(_map)

    counts = df["severity_normalised"].value_counts().to_dict()
    logger.info("Severity normalisation result: %s", counts)
    return df


def clean_accident_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalise all available columns.

    Operations
    ----------
    - Year: convert to integer (invalid → NaN)
    - Latitude / Longitude: ensure float
    - Text fields: normalise (lowercase, strip, replace known nulls)
    - Severity: delegate to normalize_severity()
    - Unknown/missing represented consistently as 'unknown'

    Returns
    -------
    Cleaned DataFrame. No values are invented.
    """
    df = df.copy()

    # Numeric conversions
    if "Year" in df.columns:
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")

    for coord_col in ("Latitude", "Longitude"):
        if coord_col in df.columns:
            df[coord_col] = pd.to_numeric(df[coord_col], errors="coerce")

    if "Noofvehicle_involved" in df.columns:
        df["Noofvehicle_involved"] = pd.to_numeric(
            df["Noofvehicle_involved"], errors="coerce"
        ).astype("Int64")

    # Text normalisation for categorical columns
    text_cols = [
        "DISTRICTNAME", "UNITNAME", "Accident_Classification", "Accident_Spot",
        "Accident_Location", "Main_Cause", "Hit_Run", "Collision_Type",
        "Junction_Control", "Road_Character", "Road_Type", "Surface_Type",
        "Surface_Condition", "Road_Condition", "Weather", "Lane_Type",
        "Accident_Road",
    ]
    for col in text_cols:
        if col in df.columns:
            df[col] = _normalise_text(df[col])

    # Severity normalisation
    df = normalize_severity(df)

    # Derived convenience columns
    df["is_fatal"] = df["severity_normalised"] == "fatal"

    logger.info("Data cleaning complete: %d records, %d columns.", len(df), len(df.columns))
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  6. TEMPORAL FEATURES
# ═══════════════════════════════════════════════════════════════════════════════

def extract_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract temporal features from the available data.

    Dataset Reality
    ---------------
    This dataset contains only a 'Year' column.
    No date, month, hour, or time-of-day fields exist.

    Therefore only year-based features are generated:
        - accident_year (integer)
        - year_relative (years before the latest year in dataset)

    Features that require date/time (month, hour, is_weekend, is_night)
    are NOT generated to avoid fabricating data.

    Returns
    -------
    DataFrame with added temporal columns.
    """
    df = df.copy()

    if "Year" not in df.columns:
        logger.warning("No Year column found — temporal features not available.")
        return df

    df["accident_year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")

    # Year relative to dataset max — useful for recency weighting
    year_max = df["accident_year"].max(skipna=True)
    if pd.notna(year_max):
        df["year_relative"] = year_max - df["accident_year"]
    else:
        df["year_relative"] = pd.NA

    # Year range info
    year_min = df["accident_year"].min(skipna=True)
    logger.info(
        "Temporal features: year range %s–%s",
        year_min, year_max,
    )

    # NOTE: month, hour, is_weekend, is_night are NOT available in this dataset.
    # These fields will be None when Module 7/8 queries segment features.
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  7. GEODATAFRAME CREATION
# ═══════════════════════════════════════════════════════════════════════════════

def create_accident_geodataframe(
    df: pd.DataFrame,
    lat_col: str = "Latitude",
    lon_col: str = "Longitude",
) -> gpd.GeoDataFrame:
    """
    Convert a cleaned, validated DataFrame into a GeoDataFrame.

    Uses WGS84 / EPSG:4326 for geographic coordinates.

    Parameters
    ----------
    df      : cleaned DataFrame with numeric Latitude/Longitude
    lat_col : latitude column name
    lon_col : longitude column name

    Returns
    -------
    GeoDataFrame in EPSG:4326 with Point geometry.
    """
    geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=GEOGRAPHIC_CRS)
    logger.info(
        "GeoDataFrame created: %d records, CRS=%s", len(gdf), gdf.crs
    )
    return gdf


# ═══════════════════════════════════════════════════════════════════════════════
#  8. HOTSPOT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_accident_hotspots(
    gdf: gpd.GeoDataFrame,
    eps_meters: float = DEFAULT_HOTSPOT_EPS_M,
    min_samples: int = DEFAULT_HOTSPOT_MIN_SAMPLES,
    lat_col: str = "Latitude",
    lon_col: str = "Longitude",
) -> gpd.GeoDataFrame:
    """
    Detect historical accident hotspots using DBSCAN clustering.

    Method
    ------
    1. Project coordinates to EPSG:32643 (UTM Zone 43N) for metre-accurate distances.
    2. Run DBSCAN with eps in metres and configurable min_samples.
    3. Noise points (cluster = -1) are excluded from hotspot summary.
    4. For each cluster, compute centroid, accident count, fatal count.

    Hotspot Semantics
    -----------------
    These represent areas with HISTORICALLY CONCENTRATED accidents.
    They do NOT indicate current road danger.

    Parameters
    ----------
    gdf         : GeoDataFrame with accident points (EPSG:4326)
    eps_meters  : DBSCAN neighbourhood radius in metres
    min_samples : minimum accidents to form a cluster
    lat_col / lon_col : coordinate column names

    Returns
    -------
    GeoDataFrame of hotspot centroids with summary statistics.
    """
    if len(gdf) < min_samples:
        logger.warning(
            "Insufficient records (%d) for hotspot detection (min_samples=%d).",
            len(gdf), min_samples,
        )
        return gpd.GeoDataFrame(
            columns=[
                "hotspot_id", "accident_count", "fatal_accident_count",
                "nonfatal_accident_count", "latitude", "longitude", "geometry"
            ],
            crs=GEOGRAPHIC_CRS,
        )

    # Project to UTM for metre-based distances
    gdf_proj = gdf.to_crs(PROJECTED_CRS)
    coords = np.column_stack([
        gdf_proj.geometry.x,
        gdf_proj.geometry.y,
    ])

    logger.info(
        "Running DBSCAN: eps=%.1fm, min_samples=%d on %d points …",
        eps_meters, min_samples, len(coords),
    )

    # eps in metres (same unit as projected CRS)
    db = DBSCAN(eps=eps_meters, min_samples=min_samples, algorithm="ball_tree", n_jobs=-1)
    labels = db.fit_predict(coords)
    gdf = gdf.copy()
    gdf["_cluster"] = labels

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    logger.info(
        "DBSCAN result: %d hotspot clusters, %d noise points.",
        n_clusters, n_noise,
    )

    if n_clusters == 0:
        logger.warning("No hotspot clusters formed — try lowering eps or min_samples.")
        return gpd.GeoDataFrame(
            columns=[
                "hotspot_id", "accident_count", "fatal_accident_count",
                "nonfatal_accident_count", "latitude", "longitude", "geometry"
            ],
            crs=GEOGRAPHIC_CRS,
        )

    # Build hotspot summary DataFrame
    cluster_df = gdf[gdf["_cluster"] != -1]
    rows = []
    for cluster_id in sorted(cluster_df["_cluster"].unique()):
        subset = cluster_df[cluster_df["_cluster"] == cluster_id]
        centroid_lat = subset["Latitude"].mean()
        centroid_lon = subset["Longitude"].mean()
        fatal_count = int(subset["is_fatal"].sum()) if "is_fatal" in subset else 0
        total_count = len(subset)
        rows.append({
            "hotspot_id": int(cluster_id),
            "accident_count": total_count,
            "fatal_accident_count": fatal_count,
            "nonfatal_accident_count": total_count - fatal_count,
            "latitude": round(centroid_lat, 6),
            "longitude": round(centroid_lon, 6),
        })

    hotspots_df = pd.DataFrame(rows)
    hotspots_gdf = gpd.GeoDataFrame(
        hotspots_df,
        geometry=gpd.points_from_xy(hotspots_df["longitude"], hotspots_df["latitude"]),
        crs=GEOGRAPHIC_CRS,
    )

    logger.info(
        "Hotspot summary: %d clusters, total accidents=%d, fatal=%d",
        len(hotspots_gdf),
        hotspots_gdf["accident_count"].sum(),
        hotspots_gdf["fatal_accident_count"].sum(),
    )
    return hotspots_gdf


# ═══════════════════════════════════════════════════════════════════════════════
#  9. SEGMENT-LEVEL ACCIDENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_segment_accident_features(
    point_lat: float,
    point_lon: float,
    accidents_gdf: gpd.GeoDataFrame,
    hotspots_gdf: gpd.GeoDataFrame,
    radius_meters: float = DEFAULT_SEGMENT_RADIUS_M,
) -> dict:
    """
    Calculate historical accident features for a geographic point (route segment).

    This function is the primary interface for Module 7 / Module 8.
    Call it for each ~500m segment of a candidate route.

    Features Returned
    -----------------
    accident_count          : total historical accidents within radius
    fatal_accident_count    : fatal accidents within radius
    nonfatal_accident_count : non-fatal accidents within radius
    accident_density        : accidents per km² of search area
    fatal_accident_density  : fatal accidents per km²
    distance_to_nearest_hotspot_m : metres to nearest hotspot centroid
    year_range              : [min_year, max_year] of accidents in radius

    Time-aware features (night/weekend/hour) are NOT returned because
    the dataset contains only Year — no time-of-day information.

    Parameters
    ----------
    point_lat, point_lon : WGS84 coordinates of the segment midpoint
    accidents_gdf        : validated Bengaluru accidents GeoDataFrame
    hotspots_gdf         : accident hotspots GeoDataFrame
    radius_meters        : search radius in metres

    Returns
    -------
    dict of feature values. All fields are present; unavailable = None.
    """
    # Project all points to UTM for metre-based distance calculation
    query_point = gpd.GeoDataFrame(
        {"geometry": [Point(point_lon, point_lat)]}, crs=GEOGRAPHIC_CRS
    ).to_crs(PROJECTED_CRS)
    qx = query_point.geometry.x.iloc[0]
    qy = query_point.geometry.y.iloc[0]

    # --- Accidents within radius ---
    acc_proj = accidents_gdf.to_crs(PROJECTED_CRS).copy()
    distances_acc = np.sqrt(
        (acc_proj.geometry.x - qx) ** 2 +
        (acc_proj.geometry.y - qy) ** 2
    )
    nearby_mask = distances_acc <= radius_meters
    nearby = accidents_gdf[nearby_mask]

    accident_count = len(nearby)
    fatal_count = int(nearby["is_fatal"].sum()) if "is_fatal" in nearby.columns else 0
    nonfatal_count = accident_count - fatal_count

    # Area of search circle in km²
    area_km2 = math.pi * (radius_meters / 1000) ** 2
    accident_density = round(accident_count / area_km2, 4) if area_km2 > 0 else 0.0
    fatal_density = round(fatal_count / area_km2, 4) if area_km2 > 0 else 0.0

    # Year range of nearby accidents
    year_range: Optional[list] = None
    if accident_count > 0 and "accident_year" in nearby.columns:
        y_min = nearby["accident_year"].min(skipna=True)
        y_max = nearby["accident_year"].max(skipna=True)
        year_range = [int(y_min) if pd.notna(y_min) else None,
                      int(y_max) if pd.notna(y_max) else None]

    # --- Distance to nearest hotspot ---
    dist_to_nearest_hotspot: Optional[float] = None
    if hotspots_gdf is not None and len(hotspots_gdf) > 0:
        hs_proj = hotspots_gdf.to_crs(PROJECTED_CRS)
        hs_dists = np.sqrt(
            (hs_proj.geometry.x - qx) ** 2 +
            (hs_proj.geometry.y - qy) ** 2
        )
        dist_to_nearest_hotspot = round(float(hs_dists.min()), 2)

    # NOTE: night_accident_count, weekend_accident_count, accidents_at_similar_hour
    # are NOT available — the dataset contains only Year, no time-of-day data.
    return {
        "accident_count": accident_count,
        "fatal_accident_count": fatal_count,
        "nonfatal_accident_count": nonfatal_count,
        "accident_density_per_km2": accident_density,
        "fatal_accident_density_per_km2": fatal_density,
        "distance_to_nearest_hotspot_m": dist_to_nearest_hotspot,
        "year_range": year_range,
        "search_radius_m": radius_meters,
        # Time-aware features — unavailable (no time-of-day data in dataset)
        "night_accident_count": None,
        "weekend_accident_count": None,
        "accidents_at_similar_hour": None,
    }


def calculate_accident_features(
    accidents_gdf: gpd.GeoDataFrame,
    hotspots_gdf: gpd.GeoDataFrame,
    radius_meters: float = DEFAULT_SEGMENT_RADIUS_M,
) -> dict:
    """
    Convenience alias returning dataset-level statistics.
    Useful for health checks and report generation.
    """
    total = len(accidents_gdf)
    fatal = int(accidents_gdf["is_fatal"].sum()) if "is_fatal" in accidents_gdf.columns else 0
    return {
        "total_valid_accidents": total,
        "fatal_accidents": fatal,
        "nonfatal_accidents": total - fatal,
        "hotspot_count": len(hotspots_gdf),
        "year_range": _year_range(accidents_gdf),
    }


def _year_range(gdf: gpd.GeoDataFrame) -> list:
    if "accident_year" in gdf.columns:
        y = gdf["accident_year"].dropna()
        if len(y):
            return [int(y.min()), int(y.max())]
    return []


# ═══════════════════════════════════════════════════════════════════════════════
#  10. SAVE OUTPUTS
# ═══════════════════════════════════════════════════════════════════════════════

def save_processed_accidents(
    gdf: gpd.GeoDataFrame,
    out_dir: str | Path,
) -> tuple[Path, Path]:
    """
    Save the validated accident GeoDataFrame to CSV and GeoJSON.

    Returns
    -------
    (csv_path, geojson_path)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "validated_accidents.csv"
    geojson_path = out_dir / "validated_accidents.geojson"

    # CSV — drop geometry column for plain CSV
    df_csv = pd.DataFrame(gdf.drop(columns="geometry"))
    df_csv.to_csv(csv_path, index=False)
    logger.info("Saved validated accidents CSV: %s (%d rows)", csv_path, len(df_csv))

    gdf.to_file(geojson_path, driver="GeoJSON")
    logger.info("Saved validated accidents GeoJSON: %s", geojson_path)

    return csv_path, geojson_path


def save_hotspots(
    hotspots_gdf: gpd.GeoDataFrame,
    out_dir: str | Path,
) -> tuple[Path, Path]:
    """
    Save hotspot GeoDataFrame to CSV and GeoJSON.

    Returns
    -------
    (csv_path, geojson_path)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "accident_hotspots.csv"
    geojson_path = out_dir / "accident_hotspots.geojson"

    df_csv = pd.DataFrame(hotspots_gdf.drop(columns="geometry"))
    df_csv.to_csv(csv_path, index=False)
    logger.info("Saved hotspots CSV: %s (%d rows)", csv_path, len(df_csv))

    if len(hotspots_gdf) > 0:
        hotspots_gdf.to_file(geojson_path, driver="GeoJSON")
        logger.info("Saved hotspots GeoJSON: %s", geojson_path)

    return csv_path, geojson_path


# ═══════════════════════════════════════════════════════════════════════════════
#  11. PROCESSING REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def generate_processing_report(
    stats: dict,
    out_dir: str | Path,
) -> Path:
    """
    Write a JSON processing report summarising the pipeline run.

    Parameters
    ----------
    stats   : dict of statistics collected during processing
    out_dir : output directory

    Returns
    -------
    Path to the written JSON report.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "accident_processing_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)

    logger.info("Processing report saved: %s", report_path)
    return report_path
