"""
API Routes Module

This module contains all API route handlers.
"""

from src.api.routes.discord_routes import router as discord_router
from src.api.routes.trade_routes import router as trade_router
from src.api.routes.analytics_routes import router as analytics_router
from src.api.routes.account_routes import router as account_router
from src.api.routes.health_routes import router as health_router

__all__ = [
    "discord_router",
    "trade_router",
    "analytics_router",
    "account_router",
    "health_router"
]
