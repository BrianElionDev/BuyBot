"""
Analytics Database Models

This module contains data models for analytics-related database operations.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

class AnalyticsType(Enum):
    """Analytics type enumeration."""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"

class MetricType(Enum):
    """Metric type enumeration."""
    PNL = "PNL"
    VOLUME = "VOLUME"
    TRADE_COUNT = "TRADE_COUNT"
    WIN_RATE = "WIN_RATE"
    DRAWDOWN = "DRAWDOWN"
    SHARPE_RATIO = "SHARPE_RATIO"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"

@dataclass
class AnalyticsRecord:
    """Analytics record data model."""
    id: Optional[int] = None
    trader: str = ""
    analytics_type: str = AnalyticsType.DAILY.value
    metric_type: str = MetricType.PNL.value
    period_start: str = ""
    period_end: str = ""
    value: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class PerformanceMetrics:
    """Performance metrics data model."""
    total_pnl: float = 0.0
    total_volume: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    recovery_factor: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0

@dataclass
class RiskMetrics:
    """Risk metrics data model."""
    var_95: float = 0.0  # Value at Risk (95%)
    var_99: float = 0.0  # Value at Risk (99%)
    cvar_95: float = 0.0  # Conditional Value at Risk (95%)
    cvar_99: float = 0.0  # Conditional Value at Risk (99%)
    volatility: float = 0.0
    beta: float = 0.0
    correlation: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    avg_trade_duration: float = 0.0

@dataclass
class TradingMetrics:
    """Trading metrics data model."""
    total_positions: int = 0
    open_positions: int = 0
    closed_positions: int = 0
    avg_position_size: float = 0.0
    avg_holding_time: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trades_per_day: float = 0.0
    most_traded_symbol: str = ""
    most_profitable_symbol: str = ""

@dataclass
class AnalyticsSummary:
    """Analytics summary data model."""
    period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trader: str = ""
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    risk: RiskMetrics = field(default_factory=RiskMetrics)
    trading: TradingMetrics = field(default_factory=TradingMetrics)
    daily_returns: List[float] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    drawdown_curve: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class AnalyticsFilter:
    """Analytics filter model for queries."""
    trader: Optional[str] = None
    analytics_type: Optional[str] = None
    metric_type: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None

@dataclass
class AnalyticsUpdate:
    """Analytics update model."""
    value: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ReportConfig:
    """Report configuration model."""
    report_type: str = "performance"
    period: str = "30d"
    trader: Optional[str] = None
    include_charts: bool = True
    include_metrics: bool = True
    include_trades: bool = False
    format: str = "json"
    timezone: str = "UTC"

@dataclass
class ReportData:
    """Report data model."""
    config: ReportConfig = field(default_factory=ReportConfig)
    summary: AnalyticsSummary = field(default_factory=AnalyticsSummary)
    analytics_records: List[AnalyticsRecord] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0"
