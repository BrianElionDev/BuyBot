"""
Data models for KuCoin WebSocket handlers.
Defines structures for KuCoin-specific WebSocket events.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

@dataclass
class KucoinExecutionReport:
    """Model for KuCoin order execution events."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    match_price: float
    match_size: float
    trade_time: int
    fee: float
    fee_currency: str
    raw_data: Dict[str, Any]

@dataclass
class KucoinOrderChange:
    """Model for KuCoin order lifecycle events."""
    order_id: str
    symbol: str
    change_type: str
    status: str
    filled_size: float
    old_size: float
    order_type: str
    side: str
    price: Optional[float] = None
    raw_data: Dict[str, Any] = None
