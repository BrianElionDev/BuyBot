"""
Data models for WebSocket handlers.
Defines structures for different types of WebSocket events and data.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

@dataclass
class ExecutionReport:
    """Model for execution report events."""
    order_id: str
    symbol: str
    status: str
    executed_qty: float
    avg_price: float
    realized_pnl: float
    side: str
    order_type: str
    time: datetime
    update_time: datetime

@dataclass
class BalanceUpdate:
    """Model for balance update events."""
    asset: str
    balance_delta: float
    event_time: datetime
    clear_time: datetime

@dataclass
class AccountPosition:
    """Model for account position events."""
    positions: List[Dict[str, Any]]
    event_time: datetime

@dataclass
class MarketData:
    """Model for market data events."""
    symbol: str
    price: float
    quantity: float
    trade_time: datetime
    event_type: str

@dataclass
class ErrorEvent:
    """Model for error events."""
    code: int
    message: str
    event_time: datetime
