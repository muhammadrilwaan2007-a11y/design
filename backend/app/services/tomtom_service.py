import asyncio
import logging
import math
import uuid
from typing import List, Optional, Tuple

import httpx

from app.config.settings import get_settings
from app.schemas.route import RouteGeometry
from app.schemas.traffic import TrafficSegment, TrafficSummary, TrafficRouteResponse
from app.schemas.incident import Incident, IncidentFeatures

logger = logging.getLogger(__name__)


# ── TomTom icon category → human readable fallback label ─────────────────────
# Used only when events[].description is not available.
_ICON_CATEGORY_LABELS = {
    0: "Unknown",
    1: "Accident",
    2: "Fog",
    3: "Dangerous Conditions",
    4: "Rain",
    5: "Ice",
    6: "Jam",
    7: "Lane Closed",
    8: "Road Closed",
    9: "Road Works",
    10: "Wind",
    11: "Flooding",
    14: "Broken Down Vehicle",
}

# Incident types considered "severe" for feature counting
_SEVERE_CATEGORIES = {1, 3, 8, 11}   # Accident, Dangerous, Road Closed, Flooding


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in meters."""
    R = 6371000  # Radius of earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def sample_route_geometry(geometry: RouteGeometry, interval_meters: float = 1000.0) -> List[tuple[float, float]]:
    """
    Sample points along a LineString geometry at approximately interval_meters.
    GeoJSON coordinates are [longitude, latitude].
    Returns a list of [latitude, longitude].
    """
    coords = geometry.coordinates
    if not coords:
        return []

    sampled_points = []
    
    # Always include the start point
    current_lon, current_lat = coords[0]
    sampled_points.append((current_lat, current_lon))
    
    accumulated_distance = 0.0

    for i in range(1, len(coords)):
        prev_lon, prev_lat = coords[i-1]
        curr_lon, curr_lat = coords[i]
        
        dist = haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
        accumulated_distance += dist

        if accumulated_distance >= interval_meters:
            sampled_points.append((curr_lat, curr_lon))
            accumulated_distance = 0.0

    # Ensure we include the end point if it's far enough from the last sampled point
    if len(coords) > 1:
        last_lon, last_lat = coords[-1]
        last_sampled_lat, last_sampled_lon = sampled_points[-1]
        if haversine_distance(last_sampled_lat, last_sampled_lon, last_lat, last_lon) > (interval_meters * 0.5):
            sampled_points.append((last_lat, last_lon))

    return sampled_points


async def fetch_traffic_for_point(client: httpx.AsyncClient, lat: float, lon: float, api_key: str) -> TrafficSegment:
    """Fetch and parse traffic data for a single point."""
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    params = {
        "point": f"{lat},{lon}",
        "key": api_key,
    }
    
    segment = TrafficSegment(latitude=lat, longitude=lon)
    
    try:
        response = await client.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        if "flowSegmentData" in data:
            flow = data["flowSegmentData"]
            
            segment.current_speed = flow.get("currentSpeed")
            segment.free_flow_speed = flow.get("freeFlowSpeed")
            segment.current_travel_time = flow.get("currentTravelTime")
            segment.free_flow_travel_time = flow.get("freeFlowTravelTime")
            segment.confidence = flow.get("confidence")
            segment.road_closure = flow.get("roadClosure", False)
            
            # Calculate metrics
            if segment.free_flow_speed and segment.free_flow_speed > 0 and segment.current_speed is not None:
                speed_ratio = segment.current_speed / segment.free_flow_speed
                segment.congestion_ratio = round(1.0 - speed_ratio, 3)
                segment.congestion_score = segment.congestion_ratio
                
            if segment.free_flow_travel_time and segment.current_travel_time is not None:
                segment.delay_seconds = segment.current_travel_time - segment.free_flow_travel_time
                if segment.free_flow_travel_time > 0:
                    segment.delay_ratio = round(segment.current_travel_time / segment.free_flow_travel_time, 3)

    except httpx.HTTPStatusError as e:
        logger.error(f"TomTom HTTP error for {lat},{lon}: {e}")
    except httpx.RequestError as e:
        logger.error(f"TomTom Request error for {lat},{lon}: {e}")
    except Exception as e:
        logger.error(f"Error processing TomTom response for {lat},{lon}: {e}")

    return segment


async def analyze_route_traffic(route_id: str, geometry: RouteGeometry) -> TrafficRouteResponse:
    """
    Analyze traffic for a full route by sampling its geometry and concurrently fetching
    traffic data from TomTom Flow API.
    """
    settings = get_settings()
    api_key = settings.tomtom_api_key
    
    if not api_key:
        logger.warning("TOMTOM_API_KEY is not set in settings.")
        return TrafficRouteResponse(route_id=route_id, segments=[], route_summary=TrafficSummary())

    sampled_points = sample_route_geometry(geometry, interval_meters=1000.0)
    
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_traffic_for_point(client, lat, lon, api_key)
            for lat, lon in sampled_points
        ]
        segments: List[TrafficSegment] = await asyncio.gather(*tasks, return_exceptions=False)
        
    # Calculate summary
    valid_congestion = [s.congestion_ratio for s in segments if s.congestion_ratio is not None]
    valid_delays = [s.delay_seconds for s in segments if s.delay_seconds is not None]
    
    summary = TrafficSummary()
    if valid_congestion:
        summary.average_congestion = round(sum(valid_congestion) / len(valid_congestion), 3)
        summary.maximum_congestion = max(valid_congestion)
    if valid_delays:
        summary.average_delay_seconds = int(sum(valid_delays) / len(valid_delays))
    
    summary.road_closure = any(s.road_closure for s in segments)
    
    return TrafficRouteResponse(
        route_id=route_id,
        segments=segments,
        route_summary=summary
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — LIVE INCIDENT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_combined_bbox(
    geometries: List[RouteGeometry],
    buffer_deg: float = 0.01,
) -> Tuple[float, float, float, float]:
    """
    Compute the combined bounding box of one or more route geometries.
    GeoJSON coords are [lon, lat].

    Returns (min_lon, min_lat, max_lon, max_lat) with a small geographic buffer
    applied on all sides.
    """
    all_lons: List[float] = []
    all_lats: List[float] = []
    for geom in geometries:
        for lon, lat in geom.coordinates:
            all_lons.append(lon)
            all_lats.append(lat)

    if not all_lons:
        raise ValueError("Cannot compute bbox from empty geometries.")

    return (
        min(all_lons) - buffer_deg,
        min(all_lats) - buffer_deg,
        max(all_lons) + buffer_deg,
        max(all_lats) + buffer_deg,
    )


def _point_to_segment_distance(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """
    Minimum Euclidean distance from point P=(px,py) to segment A=(ax,ay)–B=(bx,by).
    Coordinates are in degrees; result converted to metres via haversine.
    Works well for the short distances involved in urban routing.
    """
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        # Segment is a point
        return haversine_distance(py, px, ay, ax)

    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return haversine_distance(py, px, closest_y, closest_x)


def distance_point_to_route(lat: float, lon: float, geometry: RouteGeometry) -> float:
    """
    Return the minimum distance in metres from (lat, lon) to the nearest
    segment of the route polyline.
    GeoJSON coords are [lon, lat].
    """
    coords = geometry.coordinates
    if not coords:
        return float("inf")

    min_dist = float("inf")
    for i in range(len(coords) - 1):
        ax, ay = coords[i]       # lon, lat
        bx, by = coords[i + 1]  # lon, lat
        d = _point_to_segment_distance(lon, lat, ax, ay, bx, by)
        if d < min_dist:
            min_dist = d

    return min_dist


def _normalize_incident(raw: dict, idx: int) -> Optional[Incident]:
    """
    Normalise a single raw TomTom incident object into our Incident schema.

    TomTom v5 incidentDetails structure:
      {
        "type": "Feature",
        "geometry": { "type": "Point"|"LineString", "coordinates": [...] },
        "properties": {
          "iconCategory": 1,
          "magnitudeOfDelay": 3,
          "events": [{"description": "Accident", "code": 101}],
          "startTime": "...",
          "endTime": "...",
          "from": "...",
          "to": "...",
          "length": 120,
          "delay": 240,
          "roadNumbers": [...],
          "timeValidity": "present",
          "numberOfReports": 5,
          "lastReportTime": "..."
        }
      }
    """
    try:
        props = raw.get("properties", {})
        geometry = raw.get("geometry", {})

        # ── Extract coordinates ────────────────────────────────────────────────
        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type", "")
        if geom_type == "Point" and len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
        elif geom_type == "LineString" and coords:
            # Use midpoint of the LineString as the representative marker location
            mid = coords[len(coords) // 2]
            lon, lat = float(mid[0]), float(mid[1])
        else:
            return None  # Can't place on map

        # ── Incident type from events[].description ───────────────────────────
        events = props.get("events", [])
        icon_category = props.get("iconCategory")
        if events:
            primary_event = events[0]
            incident_type = primary_event.get("description") or _ICON_CATEGORY_LABELS.get(icon_category, "Unknown")
            description = "; ".join(
                e.get("description", "") for e in events if e.get("description")
            )
        else:
            incident_type = _ICON_CATEGORY_LABELS.get(icon_category, "Unknown")
            description = incident_type

        # ── Road name ─────────────────────────────────────────────────────────
        road_numbers = props.get("roadNumbers", [])
        road_name = ", ".join(road_numbers) if road_numbers else None

        # ── Stable ID ─────────────────────────────────────────────────────────
        incident_id = props.get("id") or f"incident_{idx}_{uuid.uuid4().hex[:8]}"

        return Incident(
            id=str(incident_id),
            type=incident_type,
            description=description,
            latitude=lat,
            longitude=lon,
            icon_category=icon_category,
            magnitude_of_delay=props.get("magnitudeOfDelay"),
            delay_seconds=props.get("delay"),
            road_name=road_name,
            from_location=props.get("from"),
            to_location=props.get("to"),
            length_meters=props.get("length"),
            start_time=props.get("startTime"),
            end_time=props.get("endTime"),
            time_validity=props.get("timeValidity"),
            number_of_reports=props.get("numberOfReports"),
            last_report_time=props.get("lastReportTime"),
        )
    except Exception as e:
        logger.warning(f"Failed to parse incident at index {idx}: {e}")
        return None


async def get_incidents(bbox: Tuple[float, float, float, float]) -> List[Incident]:
    """
    Fetch live incidents from TomTom Traffic Incidents API v5 for a bounding box.

    bbox: (min_lon, min_lat, max_lon, max_lat)

    Returns a list of normalized Incident objects.
    On any failure, returns an empty list (does not raise) so routes remain
    visible even if incident data is unavailable.
    """
    settings = get_settings()
    api_key = settings.tomtom_api_key

    if not api_key:
        logger.warning("TOMTOM_API_KEY is not set — skipping incident fetch.")
        return []

    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    # Request all properties we need in a single call
    fields = (
        "{incidents{type,geometry{type,coordinates},"
        "properties{iconCategory,magnitudeOfDelay,"
        "events{description,code},"
        "startTime,endTime,from,to,length,delay,"
        "roadNumbers,timeValidity,numberOfReports,lastReportTime}}}"
    )

    url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
    params = {
        "key": api_key,
        "bbox": bbox_str,
        "fields": fields,
        "language": "en-GB",
        "timeValidityFilter": "present",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=12.0)

        if response.status_code == 403:
            logger.error("TomTom Incidents API: invalid API key (403 Forbidden).")
            return []
        if response.status_code == 429:
            logger.warning("TomTom Incidents API: rate limit hit (429).")
            return []

        response.raise_for_status()
        data = response.json()

        raw_incidents = data.get("incidents", [])
        logger.info(f"Incident API: received {len(raw_incidents)} raw incidents for bbox {bbox_str}")

        normalized: List[Incident] = []
        for idx, raw in enumerate(raw_incidents):
            inc = _normalize_incident(raw, idx)
            if inc:
                normalized.append(inc)

        return normalized

    except httpx.TimeoutException:
        logger.error("TomTom Incidents API request timed out.")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"TomTom Incidents API HTTP error: {e}")
        return []
    except httpx.RequestError as e:
        logger.error(f"TomTom Incidents API request error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching incidents: {e}", exc_info=True)
        return []


def is_road_closure_incident(inc: Incident) -> bool:
    """Check if an incident represents an active road closure."""
    cat = inc.icon_category or 0
    t = (inc.type or "").lower()
    d = (inc.description or "").lower()
    return (
        cat == 8
        or "road clos" in t
        or "road closed" in t
        or t == "closed"
        or "road clos" in d
        or "road closed" in d
    )


def match_incidents_to_route(
    incidents: List[Incident],
    geometry: RouteGeometry,
    threshold_m: float = 150.0,
    road_closure_threshold_m: float = 25.0,
) -> List[Incident]:
    """
    For each incident, compute its distance to the route polyline.
    Mark is_route_relevant=True and record distance_to_route_m if within threshold.

    Two-tier spatial matching:
    - Road closures use a strict road-width threshold (e.g. 25m) so that closures on
      adjacent side streets / cross roads do not falsely block the main route corridor.
    - General incidents (accidents, jams, weather, road works) use threshold_m (e.g. 150m)
      to capture surrounding traffic conditions and bottlenecks.

    Returns new Incident instances (does not mutate originals).
    """
    matched: List[Incident] = []
    for inc in incidents:
        dist = distance_point_to_route(inc.latitude, inc.longitude, geometry)
        is_closure = is_road_closure_incident(inc)
        effective_threshold = road_closure_threshold_m if is_closure else threshold_m
        is_relevant = dist <= effective_threshold
        matched.append(inc.model_copy(update={
            "is_route_relevant": is_relevant,
            "distance_to_route_m": round(dist, 1),
        }))
    return matched


def compute_incident_features(relevant_incidents: List[Incident]) -> IncidentFeatures:
    """
    Aggregate relevant incidents into numerical ML features.
    Only incidents where is_route_relevant=True should be passed here.
    No scoring or weighting — raw measurements only.
    """
    features = IncidentFeatures()
    features.incident_count = len(relevant_incidents)

    for inc in relevant_incidents:
        t = inc.type.lower()
        cat = inc.icon_category or 0

        if "accident" in t or cat == 1:
            features.accident_count += 1
        elif "road work" in t or "roadwork" in t or cat == 9:
            features.roadwork_count += 1
        elif "road clos" in t or cat == 8:
            features.road_closure_count += 1
        elif "lane clos" in t or cat == 7:
            features.lane_closure_count += 1
        elif "jam" in t or cat == 6:
            features.traffic_jam_incident_count += 1
        elif "dangerous" in t or "flood" in t or cat in (3, 11):
            features.dangerous_condition_count += 1

        if cat in _SEVERE_CATEGORIES or (inc.magnitude_of_delay or 0) >= 3:
            features.severe_incident_count += 1

        if inc.delay_seconds:
            features.total_incident_delay_seconds += inc.delay_seconds

    distances = [
        inc.distance_to_route_m
        for inc in relevant_incidents
        if inc.distance_to_route_m is not None
    ]
    if distances:
        features.nearest_incident_distance_m = round(min(distances), 1)

    return features
