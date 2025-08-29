"""
Data models for WebSocket synchronization.
Defines structures for database synchronization and data consistency.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

@dataclass
class SyncEvent:
    """Model for synchronization events."""
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime
    source: str
    target: str
    status: str

@dataclass
class DatabaseSyncState:
    """Model for database synchronization state."""
    last_sync_time: datetime
    sync_status: str
    pending_events: int
    failed_events: int
    successful_events: int

@dataclass
class TradeSyncData:
    """Model for trade synchronization data."""
    trade_id: str
    order_id: str
    symbol: str
    status: str
    executed_qty: float
    avg_price: float
    realized_pnl: float
    sync_timestamp: datetime

@dataclass
class PositionSyncData:
    """Model for position synchronization data."""
    symbol: str
    position_amt: float
    entry_price: float
    mark_price: float
    un_realized_pnl: float
    sync_timestamp: datetime

@dataclass
class BalanceSyncData:
    """Model for balance synchronization data."""
    asset: str
    balance: float
    available_balance: float
    sync_timestamp: datetime
