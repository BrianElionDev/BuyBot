"""
Trade Database Models

This module contains data models for trade-related database operations.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

class TradeStatus(Enum):
    """Trade status enumeration."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"

class OrderStatus(Enum):
    """Order status enumeration."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class PositionType(Enum):
    """Position type enumeration."""
    LONG = "LONG"
    SHORT = "SHORT"

@dataclass
class Trade:
    """Trade data model."""
    id: Optional[int] = None
    discord_id: str = ""
    trader: str = ""
    timestamp: str = ""
    content: str = ""
    status: str = TradeStatus.PENDING.value
    order_status: Optional[str] = None
    coin_symbol: Optional[str] = None
    signal_type: Optional[str] = None
    position_size: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    net_pnl: Optional[float] = None
    binance_exit_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    parsed_signal: Optional[str] = None
    binance_response: Optional[str] = None
    sync_order_response: Optional[str] = None
    exchange_order_id: Optional[str] = None
    stop_loss_order_id: Optional[str] = None
    last_order_sync: Optional[str] = None
    last_pnl_sync: Optional[str] = None
    sync_error_count: int = 0
    sync_issues: List[str] = field(default_factory=list)
    manual_verification_needed: bool = False
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None

@dataclass
class Alert:
    """Alert data model."""
    id: Optional[int] = None
    timestamp: str = ""
    discord_id: str = ""
    trade: str = ""
    content: str = ""
    trader: str = ""
    status: str = "PENDING"
    parsed_alert: Optional[str] = None
    binance_response: Optional[str] = None
    kucoin_response: Optional[str] = None
    exchange: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class TradeFilter:
    """Trade filter model for queries."""
    trader: Optional[str] = None
    status: Optional[str] = None
    coin_symbol: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    discord_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    manual_verification_needed: Optional[bool] = None

@dataclass
class TradeUpdate:
    """Trade update model."""
    status: Optional[str] = None
    order_status: Optional[str] = None
    position_size: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    net_pnl: Optional[float] = None
    binance_exit_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    binance_response: Optional[str] = None
    sync_order_response: Optional[str] = None
    exchange_order_id: Optional[str] = None
    stop_loss_order_id: Optional[str] = None
    last_order_sync: Optional[str] = None
    last_pnl_sync: Optional[str] = None
    sync_error_count: Optional[int] = None
    sync_issues: Optional[List[str]] = None
    manual_verification_needed: Optional[bool] = None
    error_message: Optional[str] = None
    closed_at: Optional[str] = None

@dataclass
class TradeStats:
    """Trade statistics model."""
    total_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    pending_trades: int = 0
    failed_trades: int = 0
    total_pnl: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    max_drawdown: float = 0.0

@dataclass
class ActiveFutures:
    """Active futures data model."""
    id: Optional[int] = None
    created_at: Optional[str] = None
    trader: str = ""
    title: str = ""
    content: str = ""
    status: str = "ACTIVE"
    stopped_at: Optional[str] = None

@dataclass
class ActiveFuturesFilter:
    """Active futures filter model for queries."""
    trader: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@dataclass
class TradeSummary:
    """Trade summary model."""
    period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stats: TradeStats = field(default_factory=TradeStats)
    trades: List[Trade] = field(default_factory=list)
    alerts: List[Alert] = field(default_factory=list)
