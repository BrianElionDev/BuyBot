from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

@dataclass
class PnLData:
    """Data model for profit and loss calculations"""
    symbol: str
    position_type: str
    entry_price: float
    current_price: float
    quantity: float
    unrealized_pnl: float
    realized_pnl: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    fees_paid: float = 0.0
    total_cost: float = 0.0
    total_value: float = 0.0


@dataclass
class PerformanceMetrics:
    """Data model for performance metrics"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    average_win: float
    average_loss: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    period_start: datetime = datetime.now(timezone.utc)
    period_end: datetime = datetime.now(timezone.utc)


@dataclass
class TradeAnalysis:
    """Data model for individual trade analysis"""
    trade_id: str
    symbol: str
    position_type: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percentage: float
    duration: Optional[float] = None  # in seconds
    entry_time: datetime = datetime.now(timezone.utc)
    exit_time: datetime = datetime.now(timezone.utc)
    fees: float = 0.0
    slippage: Optional[float] = None
    market_conditions: Optional[str] = None
    strategy_used: Optional[str] = None


@dataclass
class RiskMetrics:
    """Data model for risk metrics"""
    value_at_risk: float
    conditional_value_at_risk: float
    volatility: float
    beta: Optional[float] = None
    correlation: Optional[float] = None
    max_position_size: float = 0.0
    current_exposure: float = 0.0
    leverage_used: float = 0.0
    margin_utilization: float = 0.0
    risk_per_trade: float = 0.0


@dataclass
class PortfolioSnapshot:
    """Data model for portfolio snapshot"""
    timestamp: datetime
    total_value: float
    total_pnl: float
    total_pnl_percentage: float
    cash_balance: float
    margin_balance: float
    unrealized_pnl: float
    realized_pnl: float
    open_positions: int
    closed_positions: int
    asset_allocation: Dict[str, float]
    risk_metrics: RiskMetrics


@dataclass
class MarketAnalysis:
    """Data model for market analysis"""
    symbol: str
    timestamp: datetime
    price: float
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    price_change_24h: Optional[float] = None
    price_change_percentage_24h: Optional[float] = None
    volatility: Optional[float] = None
    trend: Optional[str] = None  # 'bullish', 'bearish', 'neutral'
    support_levels: List[float] = []
    resistance_levels: List[float] = []
    technical_indicators: Dict[str, Any] = {}


@dataclass
class AnalyticsConfig:
    """Configuration for analytics service"""
    calculation_period: int = 30  # days
    risk_free_rate: float = 0.02  # 2% annual
    confidence_level: float = 0.95  # 95% VaR
    max_lookback_period: int = 365  # days
    enable_real_time: bool = True
    cache_results: bool = True
    cache_ttl: int = 300  # seconds
