"""Handler for natural language filter queries."""
from fastapi import APIRouter, HTTPException
from models.model import FilterResponse
from services.query_parser import get_query_parser
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.post("/parse-filter", response_model=FilterResponse)
async def parse_filter_query(query: str):
    """Parse natural language query into structured filters."""
    logger.info("Parsing filter query", query=query)
    
    try:
        parser = get_query_parser()
        result = await parser.parse_filter_query(query)
        
        logger.info("Filter parsed successfully", filter_count=len(result.filters))
        return result
        
    except Exception as e:
        logger.error("Filter parsing failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Filter parsing failed: {str(e)}")
