"""
backend/app/features/route_segmentation.py
Module 7 — Route Segmentation

Splits a GeoJSON LineString route geometry into consecutive segments
targeting `segment_length_m` metres each (default: 500 m).

CRS Strategy:
  - Input/output: WGS-84 (EPSG:4326) — standard GeoJSON
  - Internal calculations: UTM Zone 43N (EPSG:32643) — correct projected CRS
    for Bengaluru (77–78°E, 12–14°N). Uses metres natively, avoiding the
    error of treating lat/lon degrees as metres.

Key guarantee: segment_length_m is GEOMETRY-DERIVED (real distance along the
actual polyline, including curves) — never just straight-line Euclidean distance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pyproj
from shapely.geometry import LineString, mapping
from shapely.ops import transform, substring

from app.config.settings import get_settings
from app.schemas.features import (
    SegmentCoord,
    SegmentGeometry,
    SegmentFeatureVector,
)
from app.schemas.route import RouteGeometry

logger = logging.getLogger(__name__)

# ── CRS transformers (built once, reused across requests) ─────────────────────
_wgs84 = pyproj.CRS("EPSG:4326")


def _get_utm_crs(epsg: int) -> pyproj.CRS:
    return pyproj.CRS(f"EPSG:{epsg}")


def _build_transformers(utm_epsg: int):
    utm_crs = _get_utm_crs(utm_epsg)
    to_utm = pyproj.Transformer.from_crs(_wgs84, utm_crs, always_xy=True).transform
    to_wgs = pyproj.Transformer.from_crs(utm_crs, _wgs84, always_xy=True).transform
    return to_utm, to_wgs


# ── Internal segment dataclass ─────────────────────────────────────────────────

@dataclass
class _RawSegment:
    """Internal segment before Pydantic validation."""
    index: int
    geom_wgs84: LineString         # WGS-84 [lon, lat] for output
    geom_utm: LineString           # UTM for metric calculations
    start_distance_m: float
    end_distance_m: float
    length_m: float


# ── Core segmentation ──────────────────────────────────────────────────────────

def segment_route(
    route_geometry: RouteGeometry,
    route_id: str,
    segment_length_m: int | None = None,
    utm_epsg: int | None = None,
) -> List[SegmentFeatureVector]:
    """
    Segment a GeoJSON LineString into consecutive ~500m segments.

    Parameters
    ----------
    route_geometry : RouteGeometry
        Full route geometry from the TomTom routing response.
        Coordinates are in GeoJSON order: [longitude, latitude].
    route_id : str
        Stable identifier from the routing layer (e.g. "route_1").
    segment_length_m : int, optional
        Target segment length in metres. Defaults to settings value (500 m).
    utm_epsg : int, optional
        EPSG code for projected CRS. Defaults to settings value (32643 = UTM 43N).

    Returns
    -------
    List[SegmentFeatureVector]
        List of partially-populated SegmentFeatureVector objects.
        Only spatial/geometry fields are set here; feature fields are filled
        by subsequent extractors in feature_pipeline.py.
    """
    settings = get_settings()
    target_len = segment_length_m or settings.segment_length_m
    epsg = utm_epsg or settings.utm_epsg

    coords = route_geometry.coordinates  # [[lon, lat], ...]

    if len(coords) < 2:
        logger.warning("route %s has fewer than 2 coordinates — cannot segment.", route_id)
        return []

    to_utm, to_wgs = _build_transformers(epsg)

    # Build a Shapely LineString from GeoJSON [lon, lat] coordinates
    line_wgs84 = LineString(coords)

    # Project to UTM for metric length calculation
    line_utm = transform(to_utm, line_wgs84)
    total_length_m = line_utm.length

    if total_length_m < 1.0:
        logger.warning("route %s has near-zero length (%.2fm) — skipping segmentation.", route_id, total_length_m)
        return []

    logger.info(
        "Segmenting route %s: total=%.1fm, target_seg=%.0fm → ~%d segments",
        route_id,
        total_length_m,
        target_len,
        max(1, int(total_length_m / target_len)),
    )

    raw_segments: list[_RawSegment] = []
    current_start = 0.0
    seg_index = 0

    while current_start < total_length_m:
        current_end = min(current_start + target_len, total_length_m)

        # Extract sub-line along the projected UTM geometry
        seg_utm = substring(line_utm, current_start, current_end)

        # Guard: substring can return a Point if start==end
        if seg_utm.is_empty or seg_utm.geom_type != "LineString" or seg_utm.length < 0.1:
            current_start = current_end
            continue

        seg_length_m = seg_utm.length

        # Re-project segment back to WGS-84 for storage/output
        seg_wgs84 = transform(to_wgs, seg_utm)

        raw_segments.append(_RawSegment(
            index=seg_index,
            geom_wgs84=seg_wgs84,
            geom_utm=seg_utm,
            start_distance_m=current_start,
            end_distance_m=current_end,
            length_m=seg_length_m,
        ))

        seg_index += 1
        current_start = current_end

    logger.info("route %s → %d segments generated.", route_id, len(raw_segments))
    return [_build_feature_vector(seg, route_id) for seg in raw_segments]


def _build_feature_vector(seg: _RawSegment, route_id: str) -> SegmentFeatureVector:
    """Convert a _RawSegment into a SegmentFeatureVector with spatial fields populated."""
    coords_wgs = list(seg.geom_wgs84.coords)  # [(lon, lat), ...]

    start_lon, start_lat = coords_wgs[0]
    end_lon, end_lat = coords_wgs[-1]

    # Midpoint along the segment for point-based API queries (traffic, weather)
    mid_pt = seg.geom_wgs84.interpolate(0.5, normalized=True)

    segment_id = f"{route_id}_seg_{seg.index:03d}"

    # Convert Shapely geometry back to GeoJSON-compatible list of [lon, lat]
    geojson_coords = [[lon, lat] for lon, lat in coords_wgs]

    return SegmentFeatureVector(
        route_id=route_id,
        segment_id=segment_id,
        segment_index=seg.index,
        geometry=SegmentGeometry(type="LineString", coordinates=geojson_coords),
        start_coord=SegmentCoord(latitude=start_lat, longitude=start_lon),
        end_coord=SegmentCoord(latitude=end_lat, longitude=end_lon),
        midpoint_coord=SegmentCoord(latitude=mid_pt.y, longitude=mid_pt.x),
        segment_length_m=round(seg.length_m, 2),
        segment_length_km=round(seg.length_m / 1000, 4),
        start_distance_m=round(seg.start_distance_m, 2),
        end_distance_m=round(seg.end_distance_m, 2),
    )
