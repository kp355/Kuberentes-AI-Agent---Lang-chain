from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import routers
from handlers.filter_handler import router as filter_router

#from handlers.agent_handler import router as agent_router

from handlers.recommendation_handler import router as recommendation_router



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Kubernetes Dashboard API",
        description="API for querying and filtering Kubernetes resources",
        version="1.0.0"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(filter_router, prefix="/api/v1/filter", tags=["filter"])

    #app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
    app.include_router(recommendation_router, prefix="/api/v1/recommendations", tags=["recommendations"])  


    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    return app

# Create the application instance
app = create_app()

# For development with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)