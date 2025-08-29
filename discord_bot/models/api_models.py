"""
API Models for Discord Bot

Pydantic models for API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class InitialDiscordSignal(BaseModel):
    discord_id: str
    trader: str
    timestamp: str
    content: str
    structured: str

class DiscordUpdateSignal(BaseModel):
    timestamp: str
    content: str
    trade: str = Field(..., description="Reference to original trade signal_id")
    discord_id: str
    trader: Optional[str] = None

class Trade(BaseModel):
    id: Optional[int] = None
    coin_symbol: str
    signal_type: str
    position_type: str
    quantity: float
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    status: str = "PENDING"
    client_order_id: Optional[str] = None
    binance_order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_pnl_sync: Optional[datetime] = None
