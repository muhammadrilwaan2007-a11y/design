"""
backend/app/features/osm_matcher.py
===================================
RouteGuard AI — Map matching layer between TomTom route segments and
the underlying OpenStreetMap (OSM) road network.

Purpose:
--------
Ensures the XGBoost Risk Engine (Module 8) receives road-edge features with the
EXACT same semantic unit as the training data (osm_road_accident_features.csv).

Training edge features:
  - highway_enc : ordinal encoding of OSM highway tag
  - length_km   : metric length of the original OSM road edge (EPSG:32643)
  - oneway      : 1 if one-way, 0 if two-way
  - junction    : 1 if junction tag present, 0 otherwise
  - bridge      : 1 if bridge tag present, 0 otherwise
  - tunnel      : 1 if tunnel tag present, 0 otherwise

Frontend/UI 500m segments are VISUALIZATION/AGGREGATION units only.
They are NEVER passed directly to XGBoost as a synthetic 0.50 km edge.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
from shapely.geometry import LineString, Point
from shapely.ops import transform

from app.config.settings import get_settings
from app.schemas.features import SegmentFeatureVector

logger = logging.getLogger(__name__)

# ── Exact highway risk encoding from ml/train_xgboost_baseline.py ─────────────
HIGHWAY_RISK_ORDER: dict[str, int] = {
    "residential":    0,
    "living_street":  1,
    "unclassified":   2,
    "road":           3,
    "tertiary_link":  4,
    "tertiary":       5,
    "secondary_link": 6,
    "secondary":      7,
    "primary_link":   8,
    "primary":        9,
    "motorway_link":  10,
    "trunk_link":     11,
    "trunk":          12,
    "motorway":       13,
}

# ── CRS Transformers ──────────────────────────────────────────────────────────
_wgs84 = pyproj.CRS("EPSG:4326")


def _get_to_utm(utm_epsg: int):
    utm_crs = pyproj.CRS(f"EPSG:{utm_epsg}")
    return pyproj.Transformer.from_crs(_wgs84, utm_crs, always_xy=True).transform


def clean_highway(raw_value: object) -> str:
    """Normalize highway string to match training preprocessing."""
    if raw_value is None or pd.isna(raw_value):
        return "unknown"
    hw = str(raw_value)
    if hw.startswith("["):
        hw = hw.replace("[", "").replace("]", "").replace("'", "")
        return hw.split(",")[0].strip()
    return hw.strip()


def encode_highway(highway_str: str) -> int:
    """Return ordinal encoding for a highway string; -1 for unknown types."""
    return HIGHWAY_RISK_ORDER.get(highway_str, -1)


class OSMMatcher:
    """
    Singleton service to map TomTom route polylines to underlying OSM road edges.
    Loads data/processed/osm_roads_with_accidents.gpkg into memory once with an R-tree index.
    """

    def __init__(self) -> None:
        self._gdf: Any = None
        self._sindex: Any = None
        self._load_roads()

    def _load_roads(self) -> None:
        """Load the processed OSM road network GeoPackage into memory."""
        settings = get_settings()
        backend_dir = Path(__file__).resolve().parent.parent.parent
        gpkg_path = backend_dir / settings.osm_roads_gpkg_path

        if not gpkg_path.exists():
            # Check relative to backend or project root
            alt_path = Path(settings.osm_roads_gpkg_path)
            if alt_path.exists():
                gpkg_path = alt_path
            else:
                logger.error("[OSMMatcher] Road network GPKG not found at %s", gpkg_path)
                return

        try:
            logger.info("[OSMMatcher] Loading OSM road network from %s...", gpkg_path.name)
            gdf = gpd.read_file(gpkg_path)

            # Preserve WGS84 geometry for Leaflet GeoJSON export before converting to UTM
            if gdf.crs is None or gdf.crs.to_epsg() == 4326:
                gdf["geometry_wgs84"] = gdf.geometry
            else:
                gdf["geometry_wgs84"] = gdf.to_crs(epsg=4326).geometry

            if gdf.crs is None or gdf.crs.to_epsg() != settings.utm_epsg:
                gdf = gdf.to_crs(epsg=settings.utm_epsg)

            self._gdf = gdf
            self._sindex = gdf.sindex
            if self._gdf is not None:
                logger.info(
                    "[OSMMatcher] Loaded %d OSM road edges with spatial index (CRS: EPSG:%d).",
                    len(self._gdf),
                    settings.utm_epsg,
                )
        except Exception as exc:
            logger.error("[OSMMatcher] Failed to load OSM road network: %s", exc, exc_info=True)
            self._gdf = None
            self._sindex = None

    @property
    def is_ready(self) -> bool:
        """True if the OSM road network is loaded and indexed."""
        return self._gdf is not None and self._sindex is not None

    def match_segment(
        self,
        seg_geom_utm: Any,
        seg_id: str = "unknown_seg",
    ) -> List[Dict[str, Any]]:
        """
        Match a single 500m segment polyline (in UTM EPSG:32643) to underlying OSM edges.

        Strict constraints enforced:
          - MATCH_BUFFER_M (default 15.0m from settings)
          - MAX_MATCH_DISTANCE_M (default 25.0m from settings)
          - Do NOT silently increase these values.
          - If no edge within MAX_MATCH_DISTANCE_M, return [] (unmatched) and log it.
          - Never invent a synthetic 500m edge.
          - length_km is the ORIGINAL OSM edge length from training.
        """
        if not self.is_ready or self._gdf is None or self._sindex is None:
            logger.warning("[OSMMatcher] Matcher not ready — skipping matching for %s", seg_id)
            return []

        settings = get_settings()
        match_buffer_m = settings.osm_match_buffer_m
        max_dist_m = settings.osm_max_match_distance_m

        seg_len = seg_geom_utm.length
        if seg_len <= 0:
            return []

        # 1. Query spatial index using lateral buffer
        seg_buf = seg_geom_utm.buffer(match_buffer_m)
        cand_indices = list(self._sindex.query(seg_buf, predicate="intersects"))

        if not cand_indices:
            logger.warning(
                "[OSMMatcher] Unmatched: segment %s has no candidate edges in %.1fm buffer",
                seg_id,
                match_buffer_m,
            )
            return []

        cands = self._gdf.iloc[cand_indices].copy()

        # 2. Strict distance filter: candidate must be within max_dist_m
        dists = cands.geometry.distance(seg_geom_utm)
        within_max_dist = dists <= max_dist_m
        cands = cands[within_max_dist].copy()

        if cands.empty:
            logger.warning(
                "[OSMMatcher] Unmatched: segment %s has no edge within MAX_MATCH_DISTANCE_M=%.1fm",
                seg_id,
                max_dist_m,
            )
            return []

        # 3. Calculate overlap length with segment buffer
        overlaps = cands.geometry.intersection(seg_buf).length
        overlap_mask = overlaps >= 5.0

        matched = cands[overlap_mask].copy()
        matched_traversed = overlaps[overlap_mask]

        # 4. If no edge had >= 5m overlap but candidates exist within max_dist_m,
        # fallback to the nearest edge within max_dist_m
        if matched.empty:
            nearest_idx = dists.idxmin()
            if dists[nearest_idx] <= max_dist_m:
                matched = cands.loc[[nearest_idx]].copy()
                matched_traversed = pd.Series([seg_len], index=[nearest_idx])
            else:
                logger.warning(
                    "[OSMMatcher] Unmatched: segment %s nearest edge dist=%.1fm exceeds max=%.1fm",
                    seg_id,
                    dists[nearest_idx],
                    max_dist_m,
                )
                return []

        # 5. Extract training features for each matched edge
        matched_features: List[Dict[str, Any]] = []

        for idx, row in matched.iterrows():
            hw_clean = clean_highway(row.get("highway"))
            hw_enc = encode_highway(hw_clean)
            orig_len_km = float(row.get("length_km", 0.0))
            traversed_m = float(matched_traversed.get(idx, 5.0))

            # Ensure valid traversed weight
            if traversed_m <= 0:
                traversed_m = 5.0

            oneway = 1 if row.get("oneway") in (True, "True", 1, "1") else 0
            junction = 1 if pd.notna(row.get("junction")) else 0
            bridge = 1 if pd.notna(row.get("bridge")) else 0
            tunnel = 1 if pd.notna(row.get("tunnel")) else 0

            # Extract WGS84 coordinates for Leaflet rendering
            geom_wgs = row.get("geometry_wgs84")
            coords: list[list[float]] = []
            if geom_wgs is not None:
                if hasattr(geom_wgs, "geom_type") and geom_wgs.geom_type == "LineString":
                    coords = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in geom_wgs.coords]
                elif hasattr(geom_wgs, "geom_type") and geom_wgs.geom_type == "MultiLineString":
                    longest_line = max(geom_wgs.geoms, key=lambda g: g.length, default=None)
                    if longest_line:
                        coords = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in longest_line.coords]

            edge_dict = {
                "unique_edge_id": int(row.get("unique_edge_id", -1)),
                "name": str(row.get("name", "")) if pd.notna(row.get("name")) else "",
                "highway": hw_clean,
                "highway_enc": hw_enc,
                "length_km": orig_len_km,  # ORIGINAL training edge length!
                "oneway": oneway,
                "junction": junction,
                "bridge": bridge,
                "tunnel": tunnel,
                "traversed_length_m": traversed_m,  # Traversed portion for aggregation
                "geometry_coords": coords,          # WGS84 [[lon, lat], ...]
            }
            matched_features.append(edge_dict)

        return matched_features

    def match_route_segments(
        self,
        segments: List[SegmentFeatureVector],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Match all segments of a route to their underlying OSM edges.

        Returns a dictionary mapping segment_id -> list of matched edge feature dicts.
        """
        settings = get_settings()
        to_utm = _get_to_utm(settings.utm_epsg)

        results: Dict[str, List[Dict[str, Any]]] = {}

        for seg in segments:
            if not seg.geometry or not seg.geometry.coordinates or len(seg.geometry.coordinates) < 2:
                results[seg.segment_id] = []
                continue

            # Convert segment geometry from WGS84 GeoJSON [[lon, lat], ...] to UTM LineString
            line_wgs84 = LineString(seg.geometry.coordinates)
            line_utm = transform(to_utm, cast(Any, line_wgs84))

            matched_edges = self.match_segment(line_utm, seg_id=seg.segment_id)
            results[seg.segment_id] = matched_edges

            if matched_edges:
                seg.matched_edges_count = len(matched_edges)
                seg.osm_edge_ids = [e["unique_edge_id"] for e in matched_edges]
                # Populate primary road_class
                seg.road_class = matched_edges[0]["highway"]
            else:
                seg.matched_edges_count = 0
                seg.osm_edge_ids = []

        return results

    def get_edges_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        limit: int = 500,
        allowed_highways: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query OSM road edges within a WGS84 bounding box.
        Used by the standalone Historical Risk Heatmap endpoint.
        """
        if not self.is_ready or self._gdf is None or self._sindex is None:
            return []

        settings = get_settings()
        to_utm = _get_to_utm(settings.utm_epsg)
        from shapely.geometry import box

        bbox_wgs = box(min_lon, min_lat, max_lon, max_lat)
        bbox_utm = transform(to_utm, cast(Any, bbox_wgs))

        cand_indices = list(self._sindex.query(bbox_utm, predicate="intersects"))
        if not cand_indices:
            return []

        # Query candidates
        cands = self._gdf.iloc[cand_indices].copy()

        # Clean highway for filtering
        cands["_hw_clean"] = cands["highway"].map(clean_highway)

        if allowed_highways:
            cands = cands[cands["_hw_clean"].isin(allowed_highways)].copy()
            if cands.empty:
                return []
            # Balanced selection across arterial classes to ensure rich city-wide distribution
            per_class_limit = max(limit // len(allowed_highways), 80)
            selected_subsets = []
            for hw in allowed_highways:
                hw_sub = cands[cands["_hw_clean"] == hw].head(per_class_limit)
                if not hw_sub.empty:
                    selected_subsets.append(hw_sub)
            if selected_subsets:
                cands = pd.concat(selected_subsets).head(limit)
        else:
            # Prioritize major road classes for visual clarity: motorway, trunk, primary, secondary, tertiary first
            priority_map = {
                "motorway": 0, "trunk": 1, "primary": 2, "secondary": 3,
                "tertiary": 4, "unclassified": 5, "residential": 6, "living_street": 7
            }
            cands["_prio"] = cands["_hw_clean"].map(lambda h: priority_map.get(h, 8))
            cands = cands.sort_values(by="_prio").head(limit)

        results: List[Dict[str, Any]] = []
        for _, row in cands.iterrows():
            hw_clean = row["_hw_clean"]
            hw_enc = encode_highway(hw_clean)
            orig_len_km = float(row.get("length_km", 0.0))

            geom_wgs = row.get("geometry_wgs84")
            coords: list[list[float]] = []
            if geom_wgs is not None:
                if hasattr(geom_wgs, "geom_type") and geom_wgs.geom_type == "LineString":
                    coords = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in geom_wgs.coords]
                elif hasattr(geom_wgs, "geom_type") and geom_wgs.geom_type == "MultiLineString":
                    longest_line = max(geom_wgs.geoms, key=lambda g: g.length, default=None)
                    if longest_line:
                        coords = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in longest_line.coords]

            if not coords:
                continue

            oneway = 1 if row.get("oneway") in (True, "True", 1, "1") else 0
            junction = 1 if pd.notna(row.get("junction")) else 0
            bridge = 1 if pd.notna(row.get("bridge")) else 0
            tunnel = 1 if pd.notna(row.get("tunnel")) else 0

            results.append({
                "unique_edge_id": int(row.get("unique_edge_id", -1)),
                "name": str(row.get("name", "")) if pd.notna(row.get("name")) else "",
                "highway": hw_clean,
                "highway_enc": hw_enc,
                "length_km": orig_len_km,
                "oneway": oneway,
                "junction": junction,
                "bridge": bridge,
                "tunnel": tunnel,
                "geometry_coords": coords,
            })
            if len(results) >= limit:
                break

        return results

    def get_key_corridor_edges(self, limit: int = 1200) -> List[Dict[str, Any]]:
        """
        Return key arterial road edges in Bengaluru for city-wide heatmap initialization.
        Balanced across major throughways and collectors (motorway, trunk, primary, secondary, tertiary)
        so the network view shows rich, cohesive corridors across all sectors of the city.
        """
        if not self.is_ready:
            return []

        # Central Bengaluru arterial corridors
        return self.get_edges_in_bbox(
            min_lat=12.8900,
            min_lon=77.5200,
            max_lat=13.0400,
            max_lon=77.7000,
            limit=limit,
            allowed_highways=["primary", "secondary", "tertiary", "trunk", "motorway", "primary_link", "secondary_link"],
        )


# ── Global Singleton ──────────────────────────────────────────────────────────
_osm_matcher_instance: Optional[OSMMatcher] = None


def get_osm_matcher() -> OSMMatcher:
    """Return the module-level OSMMatcher singleton, initializing it on first call."""
    global _osm_matcher_instance
    if _osm_matcher_instance is None:
        _osm_matcher_instance = OSMMatcher()
    return _osm_matcher_instance
