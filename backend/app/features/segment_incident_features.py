"""
backend/app/features/segment_incident_features.py
Module 7 — Per-Segment Live Incident Feature Extractor

Assigns TomTom live incidents to route segments and computes per-segment
incident feature counts.

Design decisions:
  - Reuses get_incidents() and haversine_distance() from tomtom_service.py.
    No duplicate API client, no duplicate HTTP call.
  - incidents_data_available=True means the API was called and responded
    successfully (even if no incidents were found).
  - incidents_data_available=False means the API failed — all incident
    fields are left as None, NOT zero, to distinguish "no incidents" from
    "data unavailable".
  - Incident categorisation follows the existing _ICON_CATEGORY_LABELS and
    compute_incident_features() logic from tomtom_service.py.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.schemas.features import SegmentFeatureVector
from app.schemas.incident import Incident
from app.services.tomtom_service import haversine_distance, _point_to_segment_distance
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def assign_incidents_to_segments(
    segments: List[SegmentFeatureVector],
    incidents: List[Incident],
    buffer_m: Optional[float] = None,
    data_available: bool = True,
) -> List[SegmentFeatureVector]:
    """
    Assign pre-fetched live incidents to route segments.

    The caller (feature_pipeline.py) is responsible for fetching incidents
    using the existing get_incidents() function. This function only performs
    the spatial assignment and feature aggregation.

    Parameters
    ----------
    segments : list[SegmentFeatureVector]
        Segments produced by route_segmentation.
    incidents : list[Incident]
        Pre-fetched incidents from TomTom for the route bbox.
        Pass an empty list if no incidents were found (data_available=True).
    buffer_m : float, optional
        Distance threshold in metres. Defaults to settings value.
    data_available : bool
        True if the API call succeeded (even with 0 incidents).
        False if the API call failed — all fields will remain None.

    Returns
    -------
    list[SegmentFeatureVector]
        Same list with incident fields updated.
    """
    from app.config.settings import get_settings
    settings = get_settings()
    threshold = buffer_m or settings.segment_incident_buffer_m

    if not data_available:
        # API failure — leave all incident fields as None
        for seg in segments:
            seg.incidents_data_available = False
        return segments

    for seg in segments:
        seg.incidents_data_available = True
        _assign_to_segment(seg, incidents, threshold)

    return segments


def _assign_to_segment(
    seg: SegmentFeatureVector,
    incidents: List[Incident],
    threshold_m: float,
) -> None:
    """Compute incident features for a single segment."""
    mid_lat = seg.midpoint_coord.latitude
    mid_lon = seg.midpoint_coord.longitude

    nearby: List[Incident] = []
    for inc in incidents:
        dist = haversine_distance(mid_lat, mid_lon, inc.latitude, inc.longitude)
        if dist <= threshold_m:
            nearby.append(inc)

    # Initialise all counts to 0 (API succeeded, just no incidents here)
    seg.incident_count = len(nearby)
    seg.accident_count = 0
    seg.roadwork_count = 0
    seg.road_closure_count = 0
    seg.lane_closure_count = 0
    seg.traffic_jam_incident_count = 0
    seg.dangerous_condition_count = 0
    seg.nearest_incident_distance_m = None

    if not nearby:
        return

    min_dist = float("inf")

    settings = get_settings()
    closure_threshold_m = settings.incident_road_closure_distance_threshold_meters

    for inc in nearby:
        t = inc.type.lower()
        cat = inc.icon_category or 0

        if "accident" in t or cat == 1:
            seg.accident_count += 1
        elif "road work" in t or "roadwork" in t or cat == 9:
            seg.roadwork_count += 1
        elif "road clos" in t or cat == 8:
            # Road closures must be strictly within corridor width (<= 25m)
            # to avoid false positives from parallel streets or cross-alleys
            inc_dist_to_seg = haversine_distance(mid_lat, mid_lon, inc.latitude, inc.longitude)
            if seg.geometry and seg.geometry.coordinates and len(seg.geometry.coordinates) >= 2:
                coords = seg.geometry.coordinates
                for i in range(len(coords) - 1):
                    ax, ay = coords[i]
                    bx, by = coords[i + 1]
                    d_line = _point_to_segment_distance(inc.longitude, inc.latitude, ax, ay, bx, by)
                    if d_line < inc_dist_to_seg:
                        inc_dist_to_seg = d_line
            if inc_dist_to_seg <= closure_threshold_m:
                seg.road_closure_count += 1
        elif "lane clos" in t or cat == 7:
            seg.lane_closure_count += 1
        elif "jam" in t or cat == 6:
            seg.traffic_jam_incident_count += 1
        elif "dangerous" in t or "flood" in t or cat in (3, 11):
            seg.dangerous_condition_count += 1

        # Track nearest incident distance using midpoint→incident haversine
        d = haversine_distance(
            mid_lat, mid_lon,
            inc.latitude, inc.longitude,
        )
        if d < min_dist:
            min_dist = d

    if min_dist < float("inf"):
        seg.nearest_incident_distance_m = round(min_dist, 1)
