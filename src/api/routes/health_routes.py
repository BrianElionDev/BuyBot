"""
Health Check API Routes

This module contains API routes for health monitoring and system status.
"""

from fastapi import APIRouter, HTTPException
import logging
import time
from datetime import datetime
from typing import Dict, Any

from src.api.models.response_models import HealthResponse, APIResponse

# Import the Discord bot instance
from discord_bot.discord_bot import discord_bot

logger = logging.getLogger(__name__)
router = APIRouter()

# Track startup time for uptime calculation
STARTUP_TIME = time.time()

@router.get("/health", summary="Health check")
async def health_check():
    """
    Basic health check endpoint.
    """
    try:
        uptime = time.time() - STARTUP_TIME
        
        # Check database connection
        try:
            # Simple database check
            await discord_bot.db_manager.supabase.table("trades").select("id").limit(1).execute()
            database_status = "healthy"
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            database_status = "unhealthy"
        
        # Check exchange connection
        try:
            # Simple exchange check
            await discord_bot.binance_exchange.get_futures_exchange_info()
            exchange_status = "healthy"
        except Exception as e:
            logger.error(f"Exchange health check failed: {str(e)}")
            exchange_status = "unhealthy"
        
        # Determine overall status
        overall_status = "healthy" if database_status == "healthy" and exchange_status == "healthy" else "degraded"
        
        return HealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            version="1.0.0",
            uptime=uptime,
            database_status=database_status,
            exchange_status=exchange_status
        )

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health/detailed", summary="Detailed health check")
async def detailed_health_check():
    """
    Detailed health check with component status.
    """
    try:
        uptime = time.time() - STARTUP_TIME
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow(),
            "version": "1.0.0",
            "uptime": uptime,
            "components": {}
        }
        
        # Check database
        try:
            await discord_bot.db_manager.supabase.table("trades").select("id").limit(1).execute()
            health_data["components"]["database"] = {
                "status": "healthy",
                "message": "Database connection successful"
            }
        except Exception as e:
            health_data["components"]["database"] = {
                "status": "unhealthy",
                "message": f"Database connection failed: {str(e)}"
            }
            health_data["status"] = "degraded"
        
        # Check exchange
        try:
            await discord_bot.binance_exchange.get_futures_exchange_info()
            health_data["components"]["exchange"] = {
                "status": "healthy",
                "message": "Exchange connection successful"
            }
        except Exception as e:
            health_data["components"]["exchange"] = {
                "status": "unhealthy",
                "message": f"Exchange connection failed: {str(e)}"
            }
            health_data["status"] = "degraded"
        
        # Check WebSocket
        try:
            websocket_status = discord_bot.get_websocket_status()
            health_data["components"]["websocket"] = {
                "status": "healthy" if websocket_status.get("running") else "unhealthy",
                "message": f"WebSocket status: {websocket_status.get('error', 'running')}"
            }
            if not websocket_status.get("running"):
                health_data["status"] = "degraded"
        except Exception as e:
            health_data["components"]["websocket"] = {
                "status": "unhealthy",
                "message": f"WebSocket check failed: {str(e)}"
            }
            health_data["status"] = "degraded"
        
        # Check price service
        try:
            # Simple price check
            await discord_bot.price_service.get_price("BTC")
            health_data["components"]["price_service"] = {
                "status": "healthy",
                "message": "Price service working"
            }
        except Exception as e:
            health_data["components"]["price_service"] = {
                "status": "unhealthy",
                "message": f"Price service failed: {str(e)}"
            }
            health_data["status"] = "degraded"

        return APIResponse(
            status="success",
            message="Detailed health check completed",
            data=health_data
        )

    except Exception as e:
        logger.error(f"Detailed health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health/ready", summary="Readiness check")
async def readiness_check():
    """
    Readiness check for Kubernetes/container orchestration.
    """
    try:
        # Check if all critical components are ready
        ready = True
        issues = []
        
        # Check database
        try:
            await discord_bot.db_manager.supabase.table("trades").select("id").limit(1).execute()
        except Exception as e:
            ready = False
            issues.append(f"Database not ready: {str(e)}")
        
        # Check exchange
        try:
            await discord_bot.binance_exchange.get_futures_exchange_info()
        except Exception as e:
            ready = False
            issues.append(f"Exchange not ready: {str(e)}")
        
        if ready:
            return APIResponse(
                status="success",
                message="Service is ready",
                data={"ready": True}
            )
        else:
            return APIResponse(
                status="error",
                message="Service is not ready",
                data={"ready": False, "issues": issues}
            )

    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health/live", summary="Liveness check")
async def liveness_check():
    """
    Liveness check for Kubernetes/container orchestration.
    """
    try:
        # Simple check to ensure the service is responding
        return APIResponse(
            status="success",
            message="Service is alive",
            data={"alive": True, "timestamp": datetime.utcnow()}
        )

    except Exception as e:
        logger.error(f"Liveness check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
