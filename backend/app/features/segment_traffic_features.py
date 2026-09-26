"""
backend/app/features/segment_traffic_features.py
Module 7 — Per-Segment Traffic Feature Extractor

Fetches TomTom Traffic Flow data for each segment midpoint and maps it
to the segment feature vector.

Design decisions:
  - Reuses fetch_traffic_for_point() from tomtom_service.py (the existing
    async function). No new API client or HTTP logic is introduced here.
  - Traffic data is fetched concurrently for all segments (asyncio.gather).
  - congestion_ratio = current_speed / free_flow_speed.
    This matches the existing TrafficSegment.congestion_ratio calculation.
  - traffic_data_available=True if TomTom responded (even with partial data).
  - traffic_data_available=False if the API call raised an exception.
  - Traffic congestion is NOT interpreted as a safety signal here. Raw values
    only. Module 8 XGBoost will learn the relationship from training data.

Units:
  - current_speed_kmh  → km/h  (TomTom FlowSegmentData currentSpeed is km/h)
  - free_flow_speed_kmh → km/h
  - congestion_ratio   → 0.0–1.0+ (dimensionless)
  - travel_time_s      → seconds  (currentTravelTime)
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

import httpx

from app.config.settings import get_settings
from app.schemas.features import SegmentFeatureVector
from app.services.tomtom_service import fetch_traffic_for_point

logger = logging.getLogger(__name__)


async def compute_segment_traffic_features(
    segments: List[SegmentFeatureVector],
) -> List[SegmentFeatureVector]:
    """
    Fetch traffic data for each segment midpoint concurrently and populate
    traffic fields on each SegmentFeatureVector.

    Parameters
    ----------
    segments : list[SegmentFeatureVector]
        Segments from route_segmentation.

    Returns
    -------
    list[SegmentFeatureVector]
        Same list with traffic fields populated.
    """
    if not segments:
        return segments

    settings = get_settings()
    api_key = settings.tomtom_api_key

    if not api_key:
        logger.warning("TOMTOM_API_KEY not set — traffic features unavailable.")
        for seg in segments:
            seg.traffic_data_available = False
        return segments

    sem = asyncio.Semaphore(6)

    async def _fetch_with_sem(seg, c):
        async with sem:
            await _fetch_for_segment(seg, c, api_key)

    async with httpx.AsyncClient(timeout=8.0) as client:
        tasks = [
            _fetch_with_sem(seg, client)
            for seg in segments
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return segments


async def _fetch_for_segment(
    seg: SegmentFeatureVector,
    client: httpx.AsyncClient,
    api_key: str,
) -> None:
    """Fetch and map traffic data for a single segment."""
    lat = seg.midpoint_coord.latitude
    lon = seg.midpoint_coord.longitude

    try:
        traffic_seg = await fetch_traffic_for_point(client, lat, lon, api_key)

        if traffic_seg.current_speed is not None or traffic_seg.free_flow_speed is not None:
            seg.traffic_data_available = True

        # current_speed and free_flow_speed from TomTom are already in km/h
        seg.current_speed_kmh = (
            float(traffic_seg.current_speed)
            if traffic_seg.current_speed is not None else None
        )
        seg.free_flow_speed_kmh = (
            float(traffic_seg.free_flow_speed)
            if traffic_seg.free_flow_speed is not None else None
        )
        seg.travel_time_s = (
            float(traffic_seg.current_travel_time)
            if traffic_seg.current_travel_time is not None else None
        )

        # congestion_ratio already computed by fetch_traffic_for_point as:
        # 1 - (current_speed / free_flow_speed)
        # We want: current_speed / free_flow_speed (so 1.0 = free flow, 0.0 = standstill)
        # Reverse it here for a more intuitive ML feature.
        if (
            traffic_seg.free_flow_speed is not None
            and traffic_seg.free_flow_speed > 0
            and traffic_seg.current_speed is not None
        ):
            seg.congestion_ratio = round(
                traffic_seg.current_speed / traffic_seg.free_flow_speed, 3
            )
            seg.traffic_data_available = True
        else:
            seg.congestion_ratio = None

    except Exception as exc:
        logger.warning(
            "Traffic fetch failed for segment %s at (%.4f, %.4f): %s",
            seg.segment_id, lat, lon, exc,
        )
        seg.traffic_data_available = False
        # All traffic fields remain None — not zero
