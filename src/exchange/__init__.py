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

# KuCoin exchange implementation
from .kucoin import (
    KucoinExchange, KucoinOrder, KucoinPosition,
    KucoinBalance, KucoinTrade, KucoinIncome
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
from .kucoin import KucoinExchange as kucoin_exchange
from .fees import FixedFeeCalculator as fee_calculator

# Register exchanges with factory
from .core.exchange_factory import register_exchange
register_exchange("binance", BinanceExchange)
register_exchange("kucoin", KucoinExchange)

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

    # KuCoin
    'KucoinExchange',
    'KucoinOrder',
    'KucoinPosition',
    'KucoinBalance',
    'KucoinTrade',
    'KucoinIncome',

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
    'kucoin_exchange',
    'fee_calculator'
]
