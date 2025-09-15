"""
API Server Module

This module contains the main FastAPI application server.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from src.api.core.api_config import api_config
from src.api.core.api_middleware import setup_middleware
from src.api.routes import discord_routes, trade_routes, analytics_routes, account_routes, health_routes

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Create FastAPI app
    app = FastAPI(
        title=api_config.title,
        version=api_config.version,
        description=api_config.description,
        debug=api_config.debug
    )
    
    # Setup middleware
    setup_middleware(app, api_config)
    
    # Include routers
    app.include_router(
        discord_routes.router,
        prefix="/api/v1",
        tags=["discord"]
    )
    
    app.include_router(
        trade_routes.router,
        prefix="/api/v1",
        tags=["trades"]
    )
    
    app.include_router(
        analytics_routes.router,
        prefix="/api/v1",
        tags=["analytics"]
    )
    
    app.include_router(
        account_routes.router,
        prefix="/api/v1",
        tags=["account"]
    )
    
    app.include_router(
        health_routes.router,
        prefix="/api/v1",
        tags=["health"]
    )
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": f"{api_config.title} is running",
            "version": api_config.version,
            "status": "healthy"
        }
    
    # Startup event
    @app.on_event("startup")
    async def startup_event():
        """Handle application startup."""
        logger.info(f"Starting {api_config.title} v{api_config.version}")
        logger.info(f"Debug mode: {api_config.debug}")
        logger.info(f"Server will run on {api_config.host}:{api_config.port}")
    
    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        """Handle application shutdown."""
        logger.info(f"Shutting down {api_config.title}")
    
    return app

# Create the app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.core.api_server:app",
        host=api_config.host,
        port=api_config.port,
        reload=api_config.debug
    )
