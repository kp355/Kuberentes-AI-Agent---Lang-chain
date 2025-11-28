"""Handler for AI agent queries using LangGraph."""
from fastapi import APIRouter, HTTPException
from models.model import QueryRequest, QueryResponse
from core.langgraph_agent import get_agent
from utils.kubeconfig_loader import get_kubeconfig_path
import structlog
import time

logger = structlog.get_logger()
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process a natural language query about Kubernetes using LangGraph agent."""
    logger.info("Received query", query=request.query, namespace=request.namespace)
    
    start_time = time.time()
    
    try:
        # Get kubeconfig
        kubeconfig_path = get_kubeconfig_path()
        
        # Get agent
        agent = get_agent(kubeconfig_path)
        
        # Process query
        result = await agent.query(
            query=request.query,
            namespace=request.namespace or "default",
            context=request.context or {}
        )
        
        execution_time = time.time() - start_time
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("response"))
        
        response = QueryResponse(
            response=result["response"],
            analysis=result.get("analysis"),
            suggestions=result.get("suggestions", []),
            confidence=0.9,
            execution_time=execution_time
        )
        
        logger.info("Query processed successfully", execution_time=execution_time)
        return response
        
    except Exception as e:
        logger.error("Query processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/diagnose-pod")
async def diagnose_pod(pod_name: str, namespace: str = "default"):
    """Diagnose a specific pod failure."""
    logger.info("Diagnosing pod", pod=pod_name, namespace=namespace)
    
    try:
        from services.pod_diagnostics import get_pod_diagnostics_service
        
        kubeconfig_path = get_kubeconfig_path()
        service = get_pod_diagnostics_service(kubeconfig_path)
        
        result = await service.diagnose_pod(pod_name, namespace)
        
        logger.info("Pod diagnosis completed", pod=pod_name)
        return result
        
    except Exception as e:
        logger.error("Pod diagnosis failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")
