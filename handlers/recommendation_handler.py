"""Handler for AI recommendations and resource optimization."""
from fastapi import APIRouter, HTTPException
from models.model import RecommendationResponse
from services.resource_optimizer import get_resource_optimizer
from utils.kubeconfig_loader import get_kubeconfig_path
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.get("/recommendations/{namespace}", response_model=RecommendationResponse)
async def get_recommendations(namespace: str = "default"):
    """Get AI-powered resource optimization recommendations."""
    logger.info("Getting recommendations", namespace=namespace)
    
    try:
        kubeconfig_path = get_kubeconfig_path()
        optimizer = get_resource_optimizer(kubeconfig_path)
        
        result = await optimizer.get_recommendations(namespace)
        
        logger.info("Recommendations generated", count=len(result.recommendations))
        return result
        
    except Exception as e:
        logger.error("Recommendation generation failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")
