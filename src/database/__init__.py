"""
Database Layer

This module provides a comprehensive database abstraction layer for the trading bot.
"""

# Core components
from src.database.core.database_config import DatabaseConfig, database_config
from src.database.core.connection_manager import DatabaseConnectionManager, connection_manager, get_db_connection
from src.database.core.database_manager import DatabaseManager

# Models
from src.database.models.trade_models import (
    Trade, Alert, TradeFilter, TradeUpdate, TradeStats, TradeSummary,
    TradeStatus, OrderStatus, PositionType, ActiveFutures, ActiveFuturesFilter
)
from src.database.models.user_models import (
    User, UserProfile, UserSession, UserActivity, UserFilter, UserUpdate, UserStats, UserSummary,
    UserRole, UserStatus
)
from src.database.models.analytics_models import (
    AnalyticsRecord, AnalyticsFilter, AnalyticsUpdate, ReportConfig, ReportData,
    PerformanceMetrics, RiskMetrics, TradingMetrics, AnalyticsSummary,
    AnalyticsType, MetricType
)

# Repositories
from src.database.repositories.trade_repository import TradeRepository
from src.database.repositories.user_repository import UserRepository
from src.database.repositories.alert_repository import AlertRepository
from src.database.repositories.analytics_repository import AnalyticsRepository
from src.database.repositories.active_futures_repository import ActiveFuturesRepository

__all__ = [
    # Core
    "DatabaseConfig",
    "database_config",
    "DatabaseConnectionManager",
    "connection_manager",
    "get_db_connection",
    "DatabaseManager",

    # Models
    "Trade",
    "Alert",
    "TradeFilter",
    "TradeUpdate",
    "TradeStats",
    "TradeSummary",
    "TradeStatus",
    "OrderStatus",
    "PositionType",
    "ActiveFutures",
    "ActiveFuturesFilter",
    "User",
    "UserProfile",
    "UserSession",
    "UserActivity",
    "UserFilter",
    "UserUpdate",
    "UserStats",
    "UserSummary",
    "UserRole",
    "UserStatus",
    "AnalyticsRecord",
    "AnalyticsFilter",
    "AnalyticsUpdate",
    "ReportConfig",
    "ReportData",
    "PerformanceMetrics",
    "RiskMetrics",
    "TradingMetrics",
    "AnalyticsSummary",
    "AnalyticsType",
    "MetricType",

    # Repositories
    "TradeRepository",
    "UserRepository",
    "AlertRepository",
    "AnalyticsRepository",
    "ActiveFuturesRepository"
]
