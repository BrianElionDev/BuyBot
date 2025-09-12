"""
KuCoin Data Models

KuCoin-specific data models for orders, positions, balances, and trades.
Following Clean Code principles with clear, focused data structures.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from decimal import Decimal
from enum import Enum


class KucoinOrderStatus(Enum):
    """KuCoin order status enumeration."""
    NEW = "new"
    ACTIVE = "active"
    DONE = "done"
    CANCELED = "canceled"


class KucoinOrderType(Enum):
    """KuCoin order type enumeration."""
    LIMIT = "limit"
    MARKET = "market"
    STOP_LIMIT = "stop_limit"
    STOP_MARKET = "stop_market"


class KucoinOrderSide(Enum):
    """KuCoin order side enumeration."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class KucoinOrder:
    """KuCoin order data model."""
    id: Optional[str] = None
    client_oid: Optional[str] = None
    symbol: str = ""
    side: str = ""
    order_type: str = ""
    size: Optional[float] = None
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    post_only: bool = False
    hidden: bool = False
    iceberg: bool = False
    visible_size: Optional[float] = None
    stp: Optional[str] = None
    status: str = KucoinOrderStatus.NEW.value
    filled_size: Optional[float] = None
    filled_funds: Optional[float] = None
    filled_fees: Optional[float] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    trade_id: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class KucoinPosition:
    """KuCoin position data model."""
    id: Optional[str] = None
    symbol: str = ""
    side: str = ""
    size: Optional[float] = None
    entry_price: Optional[float] = None
    mark_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percentage: Optional[float] = None
    margin: Optional[float] = None
    leverage: Optional[float] = None
    risk_limit: Optional[float] = None
    auto_deposit: bool = False
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class KucoinBalance:
    """KuCoin balance data model."""
    currency: str = ""
    balance: float = 0.0
    available: float = 0.0
    holds: float = 0.0
    type: str = "trade"
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class KucoinTrade:
    """KuCoin trade data model."""
    id: Optional[str] = None
    symbol: str = ""
    side: str = ""
    size: Optional[float] = None
    price: Optional[float] = None
    funds: Optional[float] = None
    fee: Optional[float] = None
    fee_currency: str = ""
    liquidity: str = ""
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    created_at: Optional[int] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class KucoinIncome:
    """KuCoin income data model."""
    id: Optional[str] = None
    symbol: str = ""
    income_type: str = ""
    income: Optional[float] = None
    asset: str = ""
    info: str = ""
    trade_id: Optional[str] = None
    created_at: Optional[int] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class KucoinAccountInfo:
    """KuCoin account information model."""
    account_id: Optional[str] = None
    account_type: str = "trade"
    balances: List[KucoinBalance] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class KucoinSymbolInfo:
    """KuCoin symbol information model."""
    symbol: str = ""
    name: str = ""
    base_currency: str = ""
    quote_currency: str = ""
    base_min_size: Optional[float] = None
    quote_min_size: Optional[float] = None
    base_max_size: Optional[float] = None
    quote_max_size: Optional[float] = None
    base_increment: Optional[float] = None
    quote_increment: Optional[float] = None
    price_increment: Optional[float] = None
    fee_currency: str = ""
    enable_trading: bool = True
    is_margin_enabled: bool = False
    raw_response: Optional[Dict[str, Any]] = None
