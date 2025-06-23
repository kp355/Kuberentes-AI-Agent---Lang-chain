from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

# Use relative import since we're in the same package
from models.model import DashboardFilter, FilterRequest, FilterResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/query", response_model=FilterResponse)
async def handle_filter(request: FilterRequest) -> FilterResponse:
    """
    Handle filter requests with natural language queries.
    
    Args:
        request: FilterRequest containing the natural language query
        
    Returns:
        FilterResponse with parsed filter parameters
    """
    try:
        # Parse the query into a DashboardFilter
        dashboard_filter = DashboardFilter.from_query(request.query)
        
        # Convert to FilterResponse
        return FilterResponse(
            resource_type=dashboard_filter.selected_resource,
            from_date=dashboard_filter.date_range.start,
            to_date=dashboard_filter.date_range.to
        )
        
    except Exception as e:
        logger.error(f"Error processing filter request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process filter request: {str(e)}"
        )
