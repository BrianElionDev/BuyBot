"""
Analytics API Routes

This module contains API routes for analytics and performance data.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from src.api.models.request_models import AnalyticsRequest
from src.api.models.response_models import AnalyticsResponse, APIResponse
from src.api.models.api_models import FilterParams

# Import the Discord bot instance
from discord_bot.discord_bot import discord_bot

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/analytics/performance", summary="Get performance analytics")
async def get_performance_analytics(
    start_date: Optional[str] = Query(None, description="Start date for analysis"),
    end_date: Optional[str] = Query(None, description="End date for analysis"),
    trader: Optional[str] = Query(None, description="Filter by trader"),
    coin_symbol: Optional[str] = Query(None, description="Filter by coin symbol")
):
    """
    Get performance analytics for trades.
    """
    try:
        # Build filter parameters
        filters = {}
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        if trader:
            filters["trader"] = trader
        if coin_symbol:
            filters["coin_symbol"] = coin_symbol

        # Get analytics from database
        analytics = await discord_bot.db_manager.get_performance_analytics(filters)

        return AnalyticsResponse(**analytics)

    except Exception as e:
        logger.error(f"Error getting performance analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/pnl", summary="Get PnL analytics")
async def get_pnl_analytics(
    start_date: Optional[str] = Query(None, description="Start date for analysis"),
    end_date: Optional[str] = Query(None, description="End date for analysis"),
    trader: Optional[str] = Query(None, description="Filter by trader"),
    coin_symbol: Optional[str] = Query(None, description="Filter by coin symbol")
):
    """
    Get PnL analytics for trades.
    """
    try:
        # Build filter parameters
        filters = {}
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        if trader:
            filters["trader"] = trader
        if coin_symbol:
            filters["coin_symbol"] = coin_symbol

        # Get PnL analytics from database
        pnl_data = await discord_bot.db_manager.get_pnl_analytics(filters)

        return APIResponse(
            status="success",
            message="PnL analytics retrieved successfully",
            data=pnl_data
        )

    except Exception as e:
        logger.error(f"Error getting PnL analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/win-rate", summary="Get win rate analytics")
async def get_win_rate_analytics(
    start_date: Optional[str] = Query(None, description="Start date for analysis"),
    end_date: Optional[str] = Query(None, description="End date for analysis"),
    trader: Optional[str] = Query(None, description="Filter by trader"),
    coin_symbol: Optional[str] = Query(None, description="Filter by coin symbol")
):
    """
    Get win rate analytics for trades.
    """
    try:
        # Build filter parameters
        filters = {}
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        if trader:
            filters["trader"] = trader
        if coin_symbol:
            filters["coin_symbol"] = coin_symbol

        # Get win rate analytics from database
        win_rate_data = await discord_bot.db_manager.get_win_rate_analytics(filters)

        return APIResponse(
            status="success",
            message="Win rate analytics retrieved successfully",
            data=win_rate_data
        )

    except Exception as e:
        logger.error(f"Error getting win rate analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/drawdown", summary="Get drawdown analytics")
async def get_drawdown_analytics(
    start_date: Optional[str] = Query(None, description="Start date for analysis"),
    end_date: Optional[str] = Query(None, description="End date for analysis"),
    trader: Optional[str] = Query(None, description="Filter by trader")
):
    """
    Get drawdown analytics for trades.
    """
    try:
        # Build filter parameters
        filters = {}
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        if trader:
            filters["trader"] = trader

        # Get drawdown analytics from database
        drawdown_data = await discord_bot.db_manager.get_drawdown_analytics(filters)

        return APIResponse(
            status="success",
            message="Drawdown analytics retrieved successfully",
            data=drawdown_data
        )

    except Exception as e:
        logger.error(f"Error getting drawdown analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/trader-performance", summary="Get trader performance comparison")
async def get_trader_performance(
    start_date: Optional[str] = Query(None, description="Start date for analysis"),
    end_date: Optional[str] = Query(None, description="End date for analysis")
):
    """
    Get performance comparison across different traders.
    """
    try:
        # Build filter parameters
        filters = {}
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date

        # Get trader performance from database
        trader_performance = await discord_bot.db_manager.get_trader_performance(filters)

        return APIResponse(
            status="success",
            message="Trader performance retrieved successfully",
            data=trader_performance
        )

    except Exception as e:
        logger.error(f"Error getting trader performance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
