"""FastAPI main application with LangChain + LangGraph integration."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from handlers import agent_handler, filter_handler, recommendation_handler
from models.model import HealthResponse
from models.config import config
import structlog
from datetime import datetime

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="Kubernetes AI Troubleshooter",
    description="LangChain + LangGraph powered Kubernetes troubleshooting assistant",
    version="2.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agent_handler.router, prefix="/api/agent", tags=["agent"])
app.include_router(filter_handler.router, prefix="/api/filter", tags=["filter"])
app.include_router(recommendation_handler.router, prefix="/api/recommendations", tags=["recommendations"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Kubernetes AI Troubleshooter",
        "version": "2.0.0",
        "framework": "LangChain + LangGraph",
        "status": "operational"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        # Check LLM availability
        from models.ai import get_llm
        llm = get_llm()
        llm_status = "healthy" if llm else "unavailable"
        
        # Check Kubernetes connectivity
        try:
            from utils.kubeconfig_loader import get_kubeconfig_path
            kubeconfig_path = get_kubeconfig_path()
            k8s_status = "healthy"
        except Exception:
            k8s_status = "unavailable"
        
        return HealthResponse(
            status="healthy",
            version="2.0.0",
            timestamp=datetime.now(),
            components={
                "llm": llm_status,
                "kubernetes": k8s_status,
                "langgraph": "healthy"
            }
        )
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return HealthResponse(
            status="unhealthy",
            version="2.0.0",
            timestamp=datetime.now(),
            components={"error": str(e)}
        )


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Starting Kubernetes AI Troubleshooter", version="2.0.0")
    logger.info("Framework: LangChain + LangGraph")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Shutting down Kubernetes AI Troubleshooter")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
