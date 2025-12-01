"""Handler for AI agent queries using LangGraph."""
from fastapi import APIRouter, HTTPException, Query
from models.model import QueryRequest, QueryResponse
from core.langgraph_agent import get_agent
from utils.kubeconfig_loader import get_kubeconfig_path
import structlog
import time

logger = structlog.get_logger()
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    cluster_id: str = Query(None, description="Kubernetes cluster ID"),
    session_id: str = Query(None, description="Session ID for tracking")
):
    """Process a natural language query about Kubernetes using LangGraph agent."""
    logger.info("Received query", prompt=request.prompt, namespace=request.namespace, cluster_id=cluster_id, session_id=session_id)
    
    start_time = time.time()
    
    try:
        # Get kubeconfig
        kubeconfig_path = get_kubeconfig_path()
        
        # Get agent
        agent = get_agent(kubeconfig_path)
        
        # Process query - use request.prompt since that's what the model has
        result = await agent.query(
            query=request.prompt,  # ✅ Use request.prompt
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
        logger.error("Query processing failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/diagnose-pod")
async def diagnose_pod(
    pod_name: str = Query(...),
    namespace: str = Query(default="default"),
    cluster_id: str = Query(None)
):
    """Diagnose a specific pod failure."""
    logger.info("Diagnosing pod", pod=pod_name, namespace=namespace, cluster_id=cluster_id)
    
    try:
        from services.pod_diagnostics import get_pod_diagnostics_service
        
        kubeconfig_path = get_kubeconfig_path()
        service = get_pod_diagnostics_service(kubeconfig_path)
        
        result = await service.diagnose_pod(pod_name, namespace)
        
        logger.info("Pod diagnosis completed", pod=pod_name)
        return result
        
    except Exception as e:
        logger.error("Pod diagnosis failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")