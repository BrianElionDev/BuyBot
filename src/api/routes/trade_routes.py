"""
Trade API Routes

This module contains API routes for trade management.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from src.api.models.request_models import TradeRequest, PositionUpdateRequest
from src.api.models.response_models import TradeResponse, APIResponse, PaginatedResponse
from src.api.models.api_models import FilterParams, SortParams, PaginationParams

# Import the Discord bot instance
from discord_bot.discord_bot import discord_bot

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/trades", summary="Get all trades")
async def get_trades(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    trader: Optional[str] = Query(None, description="Filter by trader"),
    status: Optional[str] = Query(None, description="Filter by status"),
    coin_symbol: Optional[str] = Query(None, description="Filter by coin symbol"),
    start_date: Optional[str] = Query(None, description="Start date filter"),
    end_date: Optional[str] = Query(None, description="End date filter")
):
    """
    Get a paginated list of trades with optional filtering.
    """
    try:
        # Build filter parameters
        filters = {}
        if trader:
            filters["trader"] = trader
        if status:
            filters["status"] = status
        if coin_symbol:
            filters["coin_symbol"] = coin_symbol
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date

        # Get trades from database
        trades = await discord_bot.db_manager.get_trades(
            page=page,
            size=size,
            filters=filters
        )

        return PaginatedResponse(
            items=trades["items"],
            pagination=PaginationParams(
                page=page,
                size=size,
                total=trades["total"]
            ),
            total_pages=trades["total_pages"]
        )

    except Exception as e:
        logger.error(f"Error getting trades: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades/{trade_id}", summary="Get trade by ID")
async def get_trade(trade_id: int):
    """
    Get a specific trade by its ID.
    """
    try:
        trade = await discord_bot.db_manager.get_trade_by_id(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        
        return TradeResponse(**trade)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trade {trade_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trades", summary="Create a new trade")
async def create_trade(trade_request: TradeRequest):
    """
    Create a new trade manually.
    """
    try:
        # Create trade using trading engine
        success, response = await discord_bot.trading_engine.process_signal(
            coin_symbol=trade_request.coin_symbol,
            signal_price=trade_request.price,
            position_type=trade_request.position_type,
            order_type=trade_request.order_type,
            stop_loss=trade_request.stop_loss,
            take_profits=trade_request.take_profits,
            entry_prices=[trade_request.price] if trade_request.price else None
        )

        if success:
            return APIResponse(
                status="success",
                message="Trade created successfully",
                data=response
            )
        else:
            raise HTTPException(status_code=400, detail=f"Failed to create trade: {response}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating trade: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/trades/{trade_id}", summary="Update trade")
async def update_trade(trade_id: int, update_request: PositionUpdateRequest):
    """
    Update an existing trade.
    """
    try:
        # Get the trade first
        trade = await discord_bot.db_manager.get_trade_by_id(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")

        # Perform the requested action
        if update_request.action == "close":
            success, response = await discord_bot.trading_engine.close_position_at_market(
                trade, reason="manual_close"
            )
        elif update_request.action == "update_stop_loss":
            success, response = await discord_bot.trading_engine.update_stop_loss(
                trade, update_request.price
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {update_request.action}")

        if success:
            return APIResponse(
                status="success",
                message=f"Trade {update_request.action} completed successfully",
                data=response
            )
        else:
            raise HTTPException(status_code=400, detail=f"Failed to {update_request.action}: {response}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating trade {trade_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/trades/{trade_id}", summary="Cancel trade")
async def cancel_trade(trade_id: int):
    """
    Cancel an existing trade.
    """
    try:
        # Get the trade first
        trade = await discord_bot.db_manager.get_trade_by_id(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")

        # Cancel the trade
        success, response = await discord_bot.trading_engine.cancel_order(trade)
        
        if success:
            return APIResponse(
                status="success",
                message="Trade cancelled successfully",
                data=response
            )
        else:
            raise HTTPException(status_code=400, detail=f"Failed to cancel trade: {response}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling trade {trade_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
