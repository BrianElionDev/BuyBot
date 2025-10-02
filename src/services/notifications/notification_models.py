from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class TradeNotification:
    """Data model for trade execution notifications"""
    coin_symbol: str
    position_type: str
    entry_price: float
    quantity: float
    order_id: str
    status: str
    exchange: str
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class OrderFillNotification:
    """Data model for order fill notifications"""
    coin_symbol: str
    position_type: str
    fill_price: float
    fill_quantity: float
    order_id: str
    exchange: str
    commission: Optional[float] = None
    timestamp: Optional[datetime] = None


@dataclass
class PnLNotification:
    """Data model for PnL update notifications"""
    coin_symbol: str
    position_type: str
    entry_price: float
    current_price: float
    quantity: float
    unrealized_pnl: float
    exchange: str
    realized_pnl: Optional[float] = None
    timestamp: Optional[datetime] = None


@dataclass
class StopLossNotification:
    """Data model for stop-loss notifications"""
    coin_symbol: str
    position_type: str
    entry_price: float
    sl_price: float
    quantity: float
    realized_pnl: float
    exchange: str
    timestamp: Optional[datetime] = None


@dataclass
class TakeProfitNotification:
    """Data model for take-profit notifications"""
    coin_symbol: str
    position_type: str
    entry_price: float
    tp_price: float
    quantity: float
    realized_pnl: float
    exchange: str
    timestamp: Optional[datetime] = None


@dataclass
class ErrorNotification:
    """Data model for error notifications"""
    error_type: str
    error_message: str
    context: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


@dataclass
class SystemStatusNotification:
    """Data model for system status notifications"""
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


@dataclass
class NotificationConfig:
    """Configuration for notification service"""
    bot_token: str
    chat_id: str
    enabled: bool = True
    parse_mode: str = "HTML"
