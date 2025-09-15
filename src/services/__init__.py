"""
Rubicon Trading Bot - External service integrations
"""

# Import from modularized services
from .notifications import (
    NotificationManager, TelegramService, MessageFormatter,
    TradeNotification, OrderFillNotification, PnLNotification,
    StopLossNotification, TakeProfitNotification, ErrorNotification,
    SystemStatusNotification, NotificationConfig
)

from .pricing import (
    PriceService, PriceCache, PriceValidator,
    PriceServiceConfig, PriceData, MarketData, PriceCacheEntry,
    PriceValidationResult, CoinData
)

from .analytics import (
    PnLCalculator, PerformanceAnalyzer,
    PnLData, PerformanceMetrics, TradeAnalysis, RiskMetrics,
    PortfolioSnapshot, MarketAnalysis, AnalyticsConfig
)

__all__ = [
    # New modular services
    'NotificationManager', 'TelegramService', 'MessageFormatter',
    'TradeNotification', 'OrderFillNotification', 'PnLNotification',
    'StopLossNotification', 'TakeProfitNotification', 'ErrorNotification',
    'SystemStatusNotification', 'NotificationConfig',
    
    'PriceService', 'PriceCache', 'PriceValidator',
    'PriceServiceConfig', 'PriceData', 'MarketData', 'PriceCacheEntry',
    'PriceValidationResult', 'CoinData',
    
    'PnLCalculator', 'PerformanceAnalyzer',
    'PnLData', 'PerformanceMetrics', 'TradeAnalysis', 'RiskMetrics',
    'PortfolioSnapshot', 'MarketAnalysis', 'AnalyticsConfig'
]
