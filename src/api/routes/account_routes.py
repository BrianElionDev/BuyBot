"""
Account API Routes

This module contains API routes for account management.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from src.api.models.request_models import AccountStatusRequest
from src.api.models.response_models import PositionResponse, OrderResponse, BalanceResponse, APIResponse

# Import the Discord bot instance
from discord_bot.discord_bot import discord_bot

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/account/status", summary="Get account status")
async def get_account_status(
    include_positions: bool = Query(True, description="Include position data"),
    include_orders: bool = Query(True, description="Include order data"),
    include_balance: bool = Query(True, description="Include balance data")
):
    """
    Get comprehensive account status including positions, orders, and balance.
    """
    try:
        account_data = {}
        
        if include_positions:
            positions = await discord_bot.binance_exchange.get_futures_position_information()
            account_data["positions"] = positions
        
        if include_orders:
            orders = await discord_bot.binance_exchange.get_all_open_futures_orders()
            account_data["orders"] = orders
        
        if include_balance:
            balance = await discord_bot.binance_exchange.get_futures_account_balance()
            account_data["balance"] = balance

        return APIResponse(
            status="success",
            message="Account status retrieved successfully",
            data=account_data
        )

    except Exception as e:
        logger.error(f"Error getting account status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/account/positions", summary="Get account positions")
async def get_account_positions():
    """
    Get all open positions in the account.
    """
    try:
        positions = await discord_bot.binance_exchange.get_futures_position_information()
        
        # Filter out zero positions
        active_positions = [
            position for position in positions 
            if float(position.get('positionAmt', 0)) != 0
        ]

        return APIResponse(
            status="success",
            message="Positions retrieved successfully",
            data={"positions": active_positions}
        )

    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/account/orders", summary="Get open orders")
async def get_open_orders():
    """
    Get all open orders in the account.
    """
    try:
        orders = await discord_bot.binance_exchange.get_all_open_futures_orders()

        return APIResponse(
            status="success",
            message="Open orders retrieved successfully",
            data={"orders": orders}
        )

    except Exception as e:
        logger.error(f"Error getting open orders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/account/balance", summary="Get account balance")
async def get_account_balance():
    """
    Get account balance information.
    """
    try:
        balance = await discord_bot.binance_exchange.get_futures_account_balance()

        return APIResponse(
            status="success",
            message="Account balance retrieved successfully",
            data={"balance": balance}
        )

    except Exception as e:
        logger.error(f"Error getting account balance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/account/income", summary="Get income history")
async def get_income_history(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    start_time: Optional[str] = Query(None, description="Start time filter"),
    end_time: Optional[str] = Query(None, description="End time filter"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return")
):
    """
    Get income history for the account.
    """
    try:
        income = await discord_bot.binance_exchange.get_income_history(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return APIResponse(
            status="success",
            message="Income history retrieved successfully",
            data={"income": income}
        )

    except Exception as e:
        logger.error(f"Error getting income history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/account/trades", summary="Get trade history")
async def get_trade_history(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    start_time: Optional[str] = Query(None, description="Start time filter"),
    end_time: Optional[str] = Query(None, description="End time filter"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return")
):
    """
    Get trade history for the account.
    """
    try:
        trades = await discord_bot.binance_exchange.get_user_trades(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return APIResponse(
            status="success",
            message="Trade history retrieved successfully",
            data={"trades": trades}
        )

    except Exception as e:
        logger.error(f"Error getting trade history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/account/sync", summary="Sync account data")
async def sync_account_data():
    """
    Trigger manual sync of account data with the database.
    """
    try:
        # Trigger the sync process
        await discord_bot.sync_trade_statuses_with_binance(
            discord_bot, 
            discord_bot.supabase
        )

        return APIResponse(
            status="success",
            message="Account data sync completed successfully"
        )

    except Exception as e:
        logger.error(f"Error syncing account data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
