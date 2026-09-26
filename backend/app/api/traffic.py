import logging
from fastapi import APIRouter, HTTPException

from app.schemas.traffic import TrafficRouteRequest, TrafficRouteResponse
from app.services.tomtom_service import analyze_route_traffic

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/traffic",
    tags=["traffic"],
)

@router.post("/analyze", response_model=TrafficRouteResponse)
async def analyze_traffic(request: TrafficRouteRequest):
    """
    Analyze real-time traffic for a given candidate route geometry.
    """
    try:
        if not request.geometry.coordinates:
            raise ValueError("Route geometry is empty.")
            
        logger.info(f"Traffic analysis requested for route: {request.route_id}")
        
        response = await analyze_route_traffic(request.route_id, request.geometry)
        return response
        
    except ValueError as e:
        logger.warning(f"Invalid traffic request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing traffic for route {request.route_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while analyzing traffic.")
