"""
API Response Models

This module contains Pydantic models for API response formatting.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from src.api.models.api_models import PaginationParams

class APIResponse(BaseModel):
    """Base API response model."""
    status: str = Field(..., description="Response status")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

class TradeResponse(BaseModel):
    """Model for trade responses."""
    trade_id: int = Field(..., description="Trade ID")
    status: str = Field(..., description="Trade status")
    coin_symbol: str = Field(..., description="Trading pair")
    position_type: str = Field(..., description="LONG or SHORT")
    entry_price: Optional[float] = Field(None, description="Entry price")
    position_size: Optional[float] = Field(None, description="Position size")
    pnl: Optional[float] = Field(None, description="Profit/Loss")
    created_at: datetime = Field(..., description="Trade creation time")

class PositionResponse(BaseModel):
    """Model for position responses."""
    symbol: str = Field(..., description="Trading pair")
    position_amt: float = Field(..., description="Position amount")
    entry_price: float = Field(..., description="Entry price")
    mark_price: float = Field(..., description="Mark price")
    unrealized_pnl: float = Field(..., description="Unrealized P&L")
    liquidation_price: float = Field(..., description="Liquidation price")

class OrderResponse(BaseModel):
    """Model for order responses."""
    order_id: str = Field(..., description="Order ID")
    symbol: str = Field(..., description="Trading pair")
    side: str = Field(..., description="BUY or SELL")
    order_type: str = Field(..., description="Order type")
    status: str = Field(..., description="Order status")
    price: Optional[float] = Field(None, description="Order price")
    quantity: float = Field(..., description="Order quantity")
    executed_qty: float = Field(..., description="Executed quantity")

class BalanceResponse(BaseModel):
    """Model for balance responses."""
    asset: str = Field(..., description="Asset name")
    free: float = Field(..., description="Free balance")
    locked: float = Field(..., description="Locked balance")
    total: float = Field(..., description="Total balance")

class AnalyticsResponse(BaseModel):
    """Model for analytics responses."""
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    win_rate: float = Field(..., description="Win rate percentage")
    total_pnl: float = Field(..., description="Total P&L")
    avg_trade_pnl: float = Field(..., description="Average trade P&L")
    max_drawdown: float = Field(..., description="Maximum drawdown")

class HealthResponse(BaseModel):
    """Model for health check responses."""
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    version: str = Field(..., description="API version")
    uptime: float = Field(..., description="Service uptime in seconds")
    database_status: str = Field(..., description="Database connection status")
    exchange_status: str = Field(..., description="Exchange connection status")

class ErrorResponse(BaseModel):
    """Model for error responses."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")

class PaginatedResponse(BaseModel):
    """Model for paginated responses."""
    items: List[Dict[str, Any]] = Field(..., description="List of items")
    pagination: PaginationParams = Field(..., description="Pagination information")
    total_pages: int = Field(..., description="Total number of pages")
