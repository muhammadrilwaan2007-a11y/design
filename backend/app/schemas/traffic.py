from typing import Optional
from pydantic import BaseModel

from app.schemas.route import RouteGeometry


class TrafficSegment(BaseModel):
    """Traffic metrics for a specific point along a route."""
    latitude: float
    longitude: float
    
    current_speed: Optional[int] = None
    free_flow_speed: Optional[int] = None
    
    congestion_ratio: Optional[float] = None
    congestion_score: Optional[float] = None
    
    current_travel_time: Optional[int] = None
    free_flow_travel_time: Optional[int] = None
    
    delay_seconds: Optional[int] = None
    delay_ratio: Optional[float] = None
    
    confidence: Optional[float] = None
    road_closure: Optional[bool] = None


class TrafficSummary(BaseModel):
    """Aggregated traffic metrics for an entire route."""
    average_congestion: Optional[float] = None
    average_delay_seconds: Optional[int] = None
    maximum_congestion: Optional[float] = None
    road_closure: bool = False


class TrafficRouteRequest(BaseModel):
    """Request payload to analyze traffic for a candidate route."""
    route_id: str
    geometry: RouteGeometry


class TrafficRouteResponse(BaseModel):
    """Traffic analysis response for a candidate route."""
    route_id: str
    segments: list[TrafficSegment]
    route_summary: TrafficSummary
