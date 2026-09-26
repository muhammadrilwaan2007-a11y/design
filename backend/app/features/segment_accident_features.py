"""
backend/app/features/segment_accident_features.py
Module 7 — Historical Accident Feature Extractor

Computes per-segment historical accident features using Module 6 hotspot data.

Design decisions:
  - Hotspot GeoDataFrame is loaded ONCE at module import and cached in memory.
    This avoids repeated disk I/O on every API request.
  - All spatial operations use UTM Zone 43N (EPSG:32643) — correct projected
    CRS for Bengaluru — never raw lat/lon degrees.
  - Spatial matching: buffer the segment geometry and intersect with hotspot
    points. This correctly handles curves, not just bounding boxes.
  - Does NOT re-run DBSCAN. Consumes the already-computed Module 6 output.

NOTE: This file is named segment_accident_features.py (not accident_features.py)
to avoid collision with the existing app/features/accident_features.py (Module 6 ETL).
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import pandas as pd
import pyproj
from shapely.geometry import Point
from shapely.ops import transform

from app.config.settings import get_settings
from app.schemas.features import SegmentFeatureVector

logger = logging.getLogger(__name__)

# ── UTM transformer (built once) ───────────────────────────────────────────────
_wgs84 = pyproj.CRS("EPSG:4326")


def _get_to_utm(utm_epsg: int):
    utm_crs = pyproj.CRS(f"EPSG:{utm_epsg}")
    return pyproj.Transformer.from_crs(_wgs84, utm_crs, always_xy=True).transform


# ── Hotspot loader (cached — loaded once per process) ─────────────────────────

@lru_cache(maxsize=1)
def _load_hotspot_gdf(utm_epsg: int) -> Optional[gpd.GeoDataFrame]:
    """
    Load Module 6 accident hotspots from disk and return a GeoDataFrame
    projected to UTM for metric spatial operations.

    Returns None if the file is missing or cannot be loaded.
    """
    settings = get_settings()
    backend_dir = Path(__file__).resolve().parent.parent.parent
    hotspot_path = backend_dir / settings.processed_data_dir / "accident_hotspots.csv"

    if not hotspot_path.exists():
        logger.error(
            "Module 6 hotspot file not found at %s. "
            "Run scripts/process_accidents.py first.",
            hotspot_path,
        )
        return None

    try:
        df = pd.read_csv(hotspot_path)
        required = {"hotspot_id", "latitude", "longitude", "accident_count", "fatal_accident_count"}
        missing = required - set(df.columns)
        if missing:
            logger.error("Hotspot CSV is missing columns: %s", missing)
            return None

        gdf = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326",
        )

        # Project to UTM for metric buffer/distance operations
        gdf_utm = gdf.to_crs(epsg=utm_epsg)

        logger.info(
            "Loaded %d hotspots from Module 6 output (projected to EPSG:%d).",
            len(gdf_utm),
            utm_epsg,
        )
        return gdf_utm

    except Exception as exc:
        logger.error("Failed to load hotspot GeoDataFrame: %s", exc, exc_info=True)
        return None


# ── Feature computation ────────────────────────────────────────────────────────

def compute_segment_accident_features(
    segments: List[SegmentFeatureVector],
    utm_epsg: int | None = None,
    hotspot_buffer_m: float | None = None,
) -> List[SegmentFeatureVector]:
    """
    Populate historical accident fields on each SegmentFeatureVector in-place.

    For each segment:
      1. Buffer the segment geometry by `hotspot_buffer_m` metres (UTM).
      2. Spatial-intersect the buffer with the hotspot GeoDataFrame.
      3. Aggregate: hotspot_count, fatal_hotspot_count, accidents_per_km,
         hotspot_density, nearest_hotspot_distance_m.

    Parameters
    ----------
    segments : list[SegmentFeatureVector]
        Segments produced by route_segmentation.segment_route().
    utm_epsg : int, optional
        EPSG code for UTM CRS. Defaults to settings.utm_epsg.
    hotspot_buffer_m : float, optional
        Buffer radius in metres. Defaults to settings.hotspot_buffer_m.

    Returns
    -------
    list[SegmentFeatureVector]
        Same list with accident fields updated.
    """
    settings = get_settings()
    epsg = utm_epsg or settings.utm_epsg
    buffer_m = hotspot_buffer_m or settings.hotspot_buffer_m

    hotspot_gdf = _load_hotspot_gdf(epsg)
    if hotspot_gdf is None or hotspot_gdf.empty:
        logger.warning("Hotspot GeoDataFrame unavailable — accident features will be zero.")
        return segments

    to_utm = _get_to_utm(epsg)

    for seg in segments:
        try:
            _enrich_segment(seg, hotspot_gdf, to_utm, buffer_m)
        except Exception as exc:
            logger.warning(
                "Failed to compute accident features for segment %s: %s",
                seg.segment_id,
                exc,
            )
            # Leave defaults (0 values) — do not crash the pipeline

    return segments


def _enrich_segment(
    seg: SegmentFeatureVector,
    hotspot_gdf: gpd.GeoDataFrame,
    to_utm,
    buffer_m: float,
) -> None:
    """Compute and set accident features on a single segment."""
    from shapely.geometry import LineString

    # Rebuild the segment LineString from its stored GeoJSON coordinates
    if seg.geometry is None or not seg.geometry.coordinates:
        return

    coords = seg.geometry.coordinates  # [[lon, lat], ...]
    seg_line_wgs84 = LineString(coords)

    # Project to UTM
    seg_line_utm = transform(to_utm, seg_line_wgs84)

    # Buffer the segment
    seg_buffer_utm = seg_line_utm.buffer(buffer_m)

    # Spatial intersection
    nearby_mask = hotspot_gdf.geometry.intersects(seg_buffer_utm)
    nearby = hotspot_gdf[nearby_mask]

    if nearby.empty:
        # No hotspots near this segment — all counts remain 0
        seg.nearest_hotspot_distance_m = None
        return

    # ── Aggregate features ─────────────────────────────────────────────────────
    seg.hotspot_count = len(nearby)
    seg.fatal_hotspot_count = int((nearby["fatal_accident_count"] > 0).sum())

    total_accidents_in_buffer = int(nearby["accident_count"].sum())
    km = max(seg.segment_length_km, 0.001)  # guard against near-zero segment
    seg.accidents_per_km = round(total_accidents_in_buffer / km, 2)
    seg.hotspot_density = round(seg.hotspot_count / km, 2)

    # ── Nearest hotspot distance ───────────────────────────────────────────────
    # Use the midpoint of the segment for nearest-distance calculation
    midpoint_utm = transform(
        to_utm,
        Point(seg.midpoint_coord.longitude, seg.midpoint_coord.latitude),
    )
    distances = nearby.geometry.distance(midpoint_utm)
    seg.nearest_hotspot_distance_m = round(float(distances.min()), 1)
