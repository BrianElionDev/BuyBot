"""
API Request Models

This module contains Pydantic models for API request validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class InitialDiscordSignal(BaseModel):
    """Model for initial Discord trade signals."""
    timestamp: str = Field(..., description="Timestamp of the signal")
    content: str = Field(..., description="Raw signal content")
    discord_id: str = Field(..., description="Discord message ID")
    trader: str = Field(..., description="Trader identifier")
    structured: Optional[str] = Field(None, description="Structured signal data")

class DiscordUpdateSignal(BaseModel):
    """Model for Discord trade update signals."""
    timestamp: str = Field(..., description="Timestamp of the update")
    content: str = Field(..., description="Raw update content")
    trade: str = Field(..., description="Reference to original trade signal_id")
    discord_id: str = Field(..., description="Discord message ID")
    trader: Optional[str] = Field(None, description="Trader identifier")
    structured: Optional[str] = Field(None, description="Structured update data")

class TradeRequest(BaseModel):
    """Model for trade requests."""
    coin_symbol: str = Field(..., description="Trading pair symbol")
    position_type: str = Field(..., description="LONG or SHORT")
    order_type: str = Field(..., description="MARKET, LIMIT, etc.")
    amount: float = Field(..., description="Position size")
    price: Optional[float] = Field(None, description="Entry price")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profits: Optional[List[float]] = Field(None, description="Take profit prices")

class PositionUpdateRequest(BaseModel):
    """Model for position update requests."""
    trade_id: int = Field(..., description="Trade ID to update")
    action: str = Field(..., description="Action to perform")
    price: Optional[float] = Field(None, description="Price for the action")
    amount: Optional[float] = Field(None, description="Amount for the action")

class AnalyticsRequest(BaseModel):
    """Model for analytics requests."""
    start_date: str = Field(..., description="Start date for analysis")
    end_date: str = Field(..., description="End date for analysis")
    trader: Optional[str] = Field(None, description="Trader filter")
    coin_symbol: Optional[str] = Field(None, description="Coin symbol filter")

class AccountStatusRequest(BaseModel):
    """Model for account status requests."""
    include_positions: bool = Field(True, description="Include position data")
    include_orders: bool = Field(True, description="Include order data")
    include_balance: bool = Field(True, description="Include balance data")
