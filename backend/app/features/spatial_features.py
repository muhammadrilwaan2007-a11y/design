"""
backend/app/features/spatial_features.py
Module 7 — Road & Spatial Feature Extractor

Derives road and geometry-based features for each route segment purely
from the existing route geometry. No additional API calls are required.

Features computed:
  - turn_count       : Number of bearing changes exceeding the threshold
  - turn_density     : turns per km of segment length

Features NOT available from current data sources (returned as null):
  - road_class       : Would require OSM or TomTom Road Network API
  - speed_limit_kmh  : Would require HERE or TomTom Speed Limit API

Design: bearing change > settings.turn_bearing_threshold_deg (default 15°)
is counted as a turn. This threshold is configurable so it can be tuned
without code changes.
"""

from __future__ import annotations

import logging
import math
from typing import List

from app.config.settings import get_settings
from app.schemas.features import SegmentFeatureVector

logger = logging.getLogger(__name__)


def _bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Compute the initial bearing (0–360°) from point A to point B.
    Input: WGS-84 lon/lat in decimal degrees.
    """
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    diff_lon = math.radians(lon2 - lon1)

    x = math.sin(diff_lon) * math.cos(lat2_r)
    y = (
        math.cos(lat1_r) * math.sin(lat2_r)
        - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(diff_lon)
    )
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360) % 360


def _bearing_change(b1: float, b2: float) -> float:
    """Return the absolute angular difference between two bearings (0–180°)."""
    diff = abs(b1 - b2) % 360
    return min(diff, 360 - diff)


def compute_segment_spatial_features(
    segments: List[SegmentFeatureVector],
    turn_threshold_deg: float | None = None,
) -> List[SegmentFeatureVector]:
    """
    Compute road/spatial features for each segment from geometry alone.

    Parameters
    ----------
    segments : list[SegmentFeatureVector]
        Segments from route_segmentation.
    turn_threshold_deg : float, optional
        Minimum bearing change to count as a turn.
        Defaults to settings.turn_bearing_threshold_deg (15°).

    Returns
    -------
    list[SegmentFeatureVector]
        Same list with spatial fields updated.
    """
    settings = get_settings()
    threshold = turn_threshold_deg or settings.turn_bearing_threshold_deg

    for seg in segments:
        try:
            _compute_for_segment(seg, threshold)
        except Exception as exc:
            logger.warning(
                "Failed to compute spatial features for segment %s: %s",
                seg.segment_id, exc,
            )

    return segments


def _compute_for_segment(seg: SegmentFeatureVector, threshold: float) -> None:
    """Compute and set spatial features on a single segment."""
    if seg.geometry is None or len(seg.geometry.coordinates) < 2:
        seg.turn_count = 0
        seg.turn_density = 0.0
        return

    coords = seg.geometry.coordinates  # [[lon, lat], ...]
    turn_count = 0

    if len(coords) >= 3:
        # Compute bearing for each consecutive pair of coordinate segments
        bearings = []
        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i]
            lon2, lat2 = coords[i + 1]
            # Only compute bearing if points are distinct
            if (lon1, lat1) != (lon2, lat2):
                bearings.append(_bearing(lon1, lat1, lon2, lat2))

        # Count transitions where bearing changes more than threshold
        for i in range(len(bearings) - 1):
            if _bearing_change(bearings[i], bearings[i + 1]) >= threshold:
                turn_count += 1

    km = max(seg.segment_length_km, 0.001)
    seg.turn_count = turn_count
    seg.turn_density = round(turn_count / km, 2)

    # road_class and speed_limit_kmh are not available from current sources.
    # They are already None in the schema — no action needed.
