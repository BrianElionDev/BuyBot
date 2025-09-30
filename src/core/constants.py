"""
Centralized constants for the Rubicon Trading Bot.

This module contains all application-wide constants to ensure consistency
across the codebase and eliminate magic numbers/strings. Constants are
organized by category for easy maintenance and discovery.

Categories:
- Order Types: Standard order types for trading operations
- Futures Order Types: Specialized order types for futures trading
- Position Types: Position direction constants
- Trade Status: Trade lifecycle status values
- Order Status: Order execution status values
- Default Values: Application default configuration values
- Timeouts and Intervals: Timing-related constants
- Confidence Thresholds: Matching algorithm thresholds
- Error Messages: Standardized error message templates

Usage:
    from src.core.constants import ORDER_TYPE_MARKET, POSITION_TYPE_LONG

    if order_type == ORDER_TYPE_MARKET:
        # Handle market order
        pass
"""

# Order Types
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'

# Futures Order Types
FUTURE_ORDER_TYPE_MARKET = 'MARKET'
FUTURE_ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET = 'TAKE_PROFIT_MARKET'

# Position Types
POSITION_TYPE_LONG = 'LONG'
POSITION_TYPE_SHORT = 'SHORT'
POSITION_TYPE_BOTH = 'BOTH'

# Trade Status
TRADE_STATUS_PENDING = 'PENDING'
TRADE_STATUS_OPEN = 'OPEN'
TRADE_STATUS_CLOSED = 'CLOSED'
TRADE_STATUS_CANCELLED = 'CANCELLED'
TRADE_STATUS_FAILED = 'FAILED'
TRADE_STATUS_PARTIALLY_CLOSED = 'PARTIALLY_CLOSED'

# Order Status
ORDER_STATUS_NEW = 'NEW'
ORDER_STATUS_PARTIALLY_FILLED = 'PARTIALLY_FILLED'
ORDER_STATUS_FILLED = 'FILLED'
ORDER_STATUS_CANCELED = 'CANCELED'
ORDER_STATUS_REJECTED = 'REJECTED'
ORDER_STATUS_EXPIRED = 'EXPIRED'

# Default Values
DEFAULT_CLOSE_PERCENTAGE = 100.0
DEFAULT_RISK_PERCENTAGE = 2.0
DEFAULT_TP_PERCENTAGE = 5.0
DEFAULT_SL_PERCENTAGE = 2.0

# Timeouts and Intervals
DEFAULT_SYNC_INTERVAL_HOURS = 24
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRY_ATTEMPTS = 3

# Confidence Thresholds
MIN_MATCH_CONFIDENCE = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.8

# Error Messages
ERROR_INVALID_TRADE_DATA = "Invalid trade data provided"
ERROR_POSITION_NOT_FOUND = "Position not found"
ERROR_INSUFFICIENT_BALANCE = "Insufficient balance"
ERROR_ORDER_FAILED = "Order execution failed"
ERROR_EXCHANGE_ERROR = "Exchange API error"
ERROR_DATABASE_ERROR = "Database operation failed"
