"""
WebSocket module for real-time data streaming and synchronization.
Provides modular WebSocket management, event handling, and database synchronization.
"""

# Core WebSocket components
from .core.websocket_manager import WebSocketManager
from .core.connection_manager import ConnectionManager
from .core.event_dispatcher import EventDispatcher, WebSocketEvent
from .core.websocket_config import WebSocketConfig

# Event handlers
from .handlers.market_data_handler import MarketDataHandler
from .handlers.user_data_handler import UserDataHandler
from .handlers.error_handler import ErrorHandler
from .handlers.handler_models import (
    ExecutionReport, BalanceUpdate, AccountPosition,
    MarketData, ErrorEvent
)

# Database synchronization
from .sync.sync_manager import SyncManager
from .sync.database_sync import DatabaseSync
from .sync.sync_models import (
    SyncEvent, DatabaseSyncState, TradeSyncData,
    PositionSyncData, BalanceSyncData
)

__all__ = [
    # Core components
    'WebSocketManager',
    'ConnectionManager',
    'EventDispatcher',
    'WebSocketEvent',
    'WebSocketConfig',

    # Handlers
    'MarketDataHandler',
    'UserDataHandler',
    'ErrorHandler',

    # Handler models
    'ExecutionReport',
    'BalanceUpdate',
    'AccountPosition',
    'MarketData',
    'ErrorEvent',

    # Sync components
    'SyncManager',
    'DatabaseSync',

    # Sync models
    'SyncEvent',
    'DatabaseSyncState',
    'TradeSyncData',
    'PositionSyncData',
    'BalanceSyncData'
]