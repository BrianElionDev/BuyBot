"""
Exchange Module

This module contains all exchange-related functionality.
"""

# Core exchange components
from .core import ExchangeBase, ExchangeFactory, ExchangeConfig

# Binance exchange implementation
from .binance import (
    BinanceExchange, BinanceOrder, BinancePosition,
    BinanceBalance, BinanceTrade, BinanceIncome
)

# Transaction management
from .transactions import (
    Transaction, Order, Position, TransactionType,
    OrderStatus, PositionStatus
)

# Fee management
from .fees import FixedFeeCalculator

# Legacy imports for backward compatibility
from .binance import BinanceExchange as binance_exchange
from .fees import FixedFeeCalculator as fee_calculator

__all__ = [
    # Core
    'ExchangeBase',
    'ExchangeFactory',
    'ExchangeConfig',

    # Binance
    'BinanceExchange',
    'BinanceOrder',
    'BinancePosition',
    'BinanceBalance',
    'BinanceTrade',
    'BinanceIncome',

    # Transactions
    'Transaction',
    'Order',
    'Position',
    'TransactionType',
    'OrderStatus',
    'PositionStatus',

    # Fees
    'FixedFeeCalculator',

    # Legacy
    'binance_exchange',
    'fee_calculator'
]
