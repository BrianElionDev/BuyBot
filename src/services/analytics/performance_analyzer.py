import logging
from typing import List, Optional, Dict, Tuple, Any
from datetime import datetime, timedelta
import statistics
from .analytics_models import (
    PerformanceMetrics, TradeAnalysis, RiskMetrics, AnalyticsConfig
)

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analyzes trading performance and generates metrics"""

    def __init__(self, config: Optional[AnalyticsConfig] = None):
        """Initialize the performance analyzer"""
        self.config = config or AnalyticsConfig()

    def calculate_performance_metrics(
        self,
        trades: List[TradeAnalysis],
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics from trade data

        Args:
            trades: List of trade analysis objects
            period_start: Start of analysis period
            period_end: End of analysis period

        Returns:
            PerformanceMetrics with calculated values
        """
        if not trades:
            return self._create_empty_metrics(period_start, period_end)

        # Filter trades by period if specified
        if period_start or period_end:
            trades = self._filter_trades_by_period(trades, period_start, period_end)

        if not trades:
            return self._create_empty_metrics(period_start, period_end)

        # Calculate basic metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]

        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0

        # Calculate PnL metrics
        total_pnl = sum(t.pnl for t in trades)
        average_win = statistics.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        average_loss = statistics.mean([t.pnl for t in losing_trades]) if losing_trades else 0

        # Calculate profit factor
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        # Calculate drawdown
        max_drawdown = self._calculate_max_drawdown(trades)

        # Calculate risk-adjusted metrics
        sharpe_ratio = self._calculate_sharpe_ratio(trades)
        sortino_ratio = self._calculate_sortino_ratio(trades)
        calmar_ratio = self._calculate_calmar_ratio(trades, max_drawdown)

        # Determine period
        if not period_start:
            period_start = min(t.entry_time for t in trades)
        if not period_end:
            period_end = max(t.exit_time for t in trades) if trades else datetime.now()

        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            total_pnl=total_pnl,
            average_win=average_win,
            average_loss=average_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            period_start=period_start,
            period_end=period_end
        )

    def calculate_risk_metrics(
        self,
        trades: List[TradeAnalysis],
        portfolio_value: float,
        current_exposure: float,
        leverage_used: float = 1.0
    ) -> RiskMetrics:
        """
        Calculate risk metrics for the portfolio

        Args:
            trades: List of trade analysis objects
            portfolio_value: Total portfolio value
            current_exposure: Current market exposure
            leverage_used: Current leverage

        Returns:
            RiskMetrics with calculated values
        """
        if not trades:
            return self._create_empty_risk_metrics(portfolio_value, current_exposure, leverage_used)

        # Calculate volatility from trade returns
        returns = [t.pnl_percentage / 100 for t in trades if t.pnl_percentage != 0]
        volatility = statistics.stdev(returns) if len(returns) > 1 else 0

        # Calculate VaR and CVaR
        pnl_values = [t.pnl for t in trades]
        value_at_risk, conditional_var = self._calculate_var_cvar(pnl_values)

        # Calculate position sizing metrics
        max_position_size = max(t.quantity * t.entry_price for t in trades) if trades else 0
        risk_per_trade = portfolio_value * 0.02  # 2% risk per trade

        # Calculate margin utilization
        margin_utilization = (current_exposure / portfolio_value) * 100 if portfolio_value > 0 else 0

        return RiskMetrics(
            value_at_risk=value_at_risk,
            conditional_value_at_risk=conditional_var,
            volatility=volatility,
            max_position_size=max_position_size,
            current_exposure=current_exposure,
            leverage_used=leverage_used,
            margin_utilization=margin_utilization,
            risk_per_trade=risk_per_trade
        )

    def analyze_trade_patterns(self, trades: List[TradeAnalysis]) -> Dict[str, Any]:
        """
        Analyze patterns in trading behavior

        Args:
            trades: List of trade analysis objects

        Returns:
            Dictionary with pattern analysis
        """
        if not trades:
            return {}

        patterns = {}

        # Time-based patterns
        patterns['hourly_distribution'] = self._analyze_hourly_distribution(trades)
        patterns['daily_distribution'] = self._analyze_daily_distribution(trades)
        patterns['monthly_distribution'] = self._analyze_monthly_distribution(trades)

        # Symbol-based patterns
        patterns['symbol_performance'] = self._analyze_symbol_performance(trades)

        # Position type patterns
        patterns['position_type_performance'] = self._analyze_position_type_performance(trades)

        # Duration patterns
        patterns['duration_analysis'] = self._analyze_trade_duration(trades)

        # Slippage analysis
        patterns['slippage_analysis'] = self._analyze_slippage(trades)

        return patterns

    def generate_performance_report(
        self,
        trades: List[TradeAnalysis],
        portfolio_value: float,
        current_exposure: float,
        leverage_used: float = 1.0
    ) -> Dict[str, Any]:
        """
        Generate comprehensive performance report

        Args:
            trades: List of trade analysis objects
            portfolio_value: Total portfolio value
            current_exposure: Current market exposure
            leverage_used: Current leverage

        Returns:
            Dictionary with complete performance report
        """
        # Calculate all metrics
        performance_metrics = self.calculate_performance_metrics(trades)
        risk_metrics = self.calculate_risk_metrics(trades, portfolio_value, current_exposure, leverage_used)
        trade_patterns = self.analyze_trade_patterns(trades)

        # Generate recommendations
        recommendations = self._generate_recommendations(performance_metrics, risk_metrics)

        return {
            'performance_metrics': performance_metrics,
            'risk_metrics': risk_metrics,
            'trade_patterns': trade_patterns,
            'recommendations': recommendations,
            'report_generated': datetime.now(),
            'analysis_period': {
                'start': performance_metrics.period_start,
                'end': performance_metrics.period_end,
                'duration_days': (performance_metrics.period_end - performance_metrics.period_start).days
            }
        }

    def _filter_trades_by_period(
        self,
        trades: List[TradeAnalysis],
        period_start: Optional[datetime],
        period_end: Optional[datetime]
    ) -> List[TradeAnalysis]:
        """Filter trades by time period"""
        filtered_trades = trades

        if period_start:
            filtered_trades = [t for t in filtered_trades if t.entry_time >= period_start]

        if period_end:
            filtered_trades = [t for t in filtered_trades if t.exit_time <= period_end]

        return filtered_trades

    def _calculate_max_drawdown(self, trades: List[TradeAnalysis]) -> float:
        """Calculate maximum drawdown from trade sequence"""
        if not trades:
            return 0.0

        # Sort trades by entry time
        sorted_trades = sorted(trades, key=lambda x: x.entry_time)

        peak = 0.0
        max_dd = 0.0
        running_pnl = 0.0

        for trade in sorted_trades:
            running_pnl += trade.pnl
            if running_pnl > peak:
                peak = running_pnl

            drawdown = peak - running_pnl
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    def _calculate_sharpe_ratio(self, trades: List[TradeAnalysis]) -> Optional[float]:
        """Calculate Sharpe ratio"""
        if len(trades) < 2:
            return None

        returns = [t.pnl_percentage / 100 for t in trades if t.pnl_percentage != 0]
        if len(returns) < 2:
            return None

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)

        if std_return == 0:
            return None

        # Annualized Sharpe ratio (assuming daily returns)
        sharpe = (mean_return / std_return) * (252 ** 0.5)
        return sharpe

    def _calculate_sortino_ratio(self, trades: List[TradeAnalysis]) -> Optional[float]:
        """Calculate Sortino ratio"""
        if len(trades) < 2:
            return None

        returns = [t.pnl_percentage / 100 for t in trades if t.pnl_percentage != 0]
        if len(returns) < 2:
            return None

        mean_return = statistics.mean(returns)
        negative_returns = [r for r in returns if r < 0]

        if not negative_returns:
            return None

        downside_deviation = statistics.stdev(negative_returns)

        if downside_deviation == 0:
            return None

        # Annualized Sortino ratio
        sortino = (mean_return / downside_deviation) * (252 ** 0.5)
        return sortino

    def _calculate_calmar_ratio(self, trades: List[TradeAnalysis], max_drawdown: float) -> Optional[float]:
        """Calculate Calmar ratio"""
        if max_drawdown == 0:
            return None

        # Calculate annualized return
        if not trades:
            return None

        total_return = sum(t.pnl_percentage for t in trades)
        if len(trades) < 2:
            return None

        duration_days = (trades[-1].exit_time - trades[0].entry_time).days
        if duration_days == 0:
            return None

        annualized_return = (total_return / duration_days) * 365

        calmar = annualized_return / max_drawdown if max_drawdown > 0 else None
        return calmar

    def _calculate_var_cvar(self, pnl_values: List[float]) -> Tuple[float, float]:
        """Calculate Value at Risk and Conditional VaR"""
        if not pnl_values:
            return 0.0, 0.0

        sorted_pnl = sorted(pnl_values)
        var_index = int(len(sorted_pnl) * (1 - self.config.confidence_level))
        var_index = max(0, min(var_index, len(sorted_pnl) - 1))

        var = sorted_pnl[var_index]

        # CVaR is the average of values below VaR
        tail_values = [pnl for pnl in pnl_values if pnl <= var]
        cvar = statistics.mean(tail_values) if tail_values else var

        return var, cvar

    def _create_empty_metrics(self, period_start: Optional[datetime], period_end: Optional[datetime]) -> PerformanceMetrics:
        """Create empty performance metrics"""
        now = datetime.now()
        start = period_start or now
        end = period_end or now

        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_pnl=0.0,
            average_win=0.0,
            average_loss=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            sharpe_ratio=None,
            sortino_ratio=None,
            calmar_ratio=None,
            period_start=start,
            period_end=end
        )

    def _create_empty_risk_metrics(
        self,
        portfolio_value: float,
        current_exposure: float,
        leverage_used: float
    ) -> RiskMetrics:
        """Create empty risk metrics"""
        return RiskMetrics(
            value_at_risk=0.0,
            conditional_value_at_risk=0.0,
            volatility=0.0,
            max_position_size=0.0,
            current_exposure=current_exposure,
            leverage_used=leverage_used,
            margin_utilization=0.0,
            risk_per_trade=0.0
        )

    def _analyze_hourly_distribution(self, trades: List[TradeAnalysis]) -> Dict[int, Dict[str, Any]]:
        """Analyze trade distribution by hour"""
        hourly_data = {}

        for trade in trades:
            hour = trade.entry_time.hour
            if hour not in hourly_data:
                hourly_data[hour] = {'count': 0, 'total_pnl': 0.0, 'pnl_values': []}

            hourly_data[hour]['count'] += 1
            hourly_data[hour]['total_pnl'] += trade.pnl
            hourly_data[hour]['pnl_values'].append(trade.pnl)

        # Calculate averages
        for hour in hourly_data:
            count = hourly_data[hour]['count']
            hourly_data[hour]['avg_pnl'] = hourly_data[hour]['total_pnl'] / count if count > 0 else 0
            hourly_data[hour]['win_rate'] = (
                len([p for p in hourly_data[hour]['pnl_values'] if p > 0]) / count * 100
            ) if count > 0 else 0

        return hourly_data

    def _analyze_daily_distribution(self, trades: List[TradeAnalysis]) -> Dict[str, Dict[str, Any]]:
        """Analyze trade distribution by day of week"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily_data = {day: {'count': 0, 'total_pnl': 0.0, 'pnl_values': []} for day in days}

        for trade in trades:
            day = trade.entry_time.strftime('%A')
            if day in daily_data:
                daily_data[day]['count'] += 1
                daily_data[day]['total_pnl'] += trade.pnl
                daily_data[day]['pnl_values'].append(trade.pnl)

        # Calculate averages
        for day in daily_data:
            count = daily_data[day]['count']
            daily_data[day]['avg_pnl'] = daily_data[day]['total_pnl'] / count if count > 0 else 0
            daily_data[day]['win_rate'] = (
                len([p for p in daily_data[day]['pnl_values'] if p > 0]) / count * 100
            ) if count > 0 else 0

        return daily_data

    def _analyze_monthly_distribution(self, trades: List[TradeAnalysis]) -> Dict[int, Dict[str, Any]]:
        """Analyze trade distribution by month"""
        monthly_data = {}

        for trade in trades:
            month = trade.entry_time.month
            if month not in monthly_data:
                monthly_data[month] = {'count': 0, 'total_pnl': 0.0, 'pnl_values': []}

            monthly_data[month]['count'] += 1
            monthly_data[month]['total_pnl'] += trade.pnl
            monthly_data[month]['pnl_values'].append(trade.pnl)

        # Calculate averages
        for month in monthly_data:
            count = monthly_data[month]['count']
            monthly_data[month]['avg_pnl'] = monthly_data[month]['total_pnl'] / count if count > 0 else 0
            monthly_data[month]['win_rate'] = (
                len([p for p in monthly_data[month]['pnl_values'] if p > 0]) / count * 100
            ) if count > 0 else 0

        return monthly_data

    def _analyze_symbol_performance(self, trades: List[TradeAnalysis]) -> Dict[str, Dict[str, Any]]:
        """Analyze performance by trading symbol"""
        symbol_data = {}

        for trade in trades:
            if trade.symbol not in symbol_data:
                symbol_data[trade.symbol] = {'count': 0, 'total_pnl': 0.0, 'pnl_values': []}

            symbol_data[trade.symbol]['count'] += 1
            symbol_data[trade.symbol]['total_pnl'] += trade.pnl
            symbol_data[trade.symbol]['pnl_values'].append(trade.pnl)

        # Calculate averages
        for symbol in symbol_data:
            count = symbol_data[symbol]['count']
            symbol_data[symbol]['avg_pnl'] = symbol_data[symbol]['total_pnl'] / count if count > 0 else 0
            symbol_data[symbol]['win_rate'] = (
                len([p for p in symbol_data[symbol]['pnl_values'] if p > 0]) / count * 100
            ) if count > 0 else 0

        return symbol_data

    def _analyze_position_type_performance(self, trades: List[TradeAnalysis]) -> Dict[str, Dict[str, Any]]:
        """Analyze performance by position type"""
        position_data = {'LONG': {'count': 0, 'total_pnl': 0.0, 'pnl_values': []},
                        'SHORT': {'count': 0, 'total_pnl': 0.0, 'pnl_values': []}}

        for trade in trades:
            position_type = trade.position_type.upper()
            if position_type in position_data:
                position_data[position_type]['count'] += 1
                position_data[position_type]['total_pnl'] += trade.pnl
                position_data[position_type]['pnl_values'].append(trade.pnl)

        # Calculate averages
        for position_type in position_data:
            count = position_data[position_type]['count']
            position_data[position_type]['avg_pnl'] = position_data[position_type]['total_pnl'] / count if count > 0 else 0
            position_data[position_type]['win_rate'] = (
                len([p for p in position_data[position_type]['pnl_values'] if p > 0]) / count * 100
            ) if count > 0 else 0

        return position_data

    def _analyze_trade_duration(self, trades: List[TradeAnalysis]) -> Dict[str, Any]:
        """Analyze trade duration patterns"""
        durations = []

        for trade in trades:
            if trade.duration:
                durations.append(trade.duration)

        if not durations:
            return {'avg_duration': 0, 'min_duration': 0, 'max_duration': 0}

        return {
            'avg_duration': statistics.mean(durations),
            'min_duration': min(durations),
            'max_duration': max(durations),
            'median_duration': statistics.median(durations)
        }

    def _analyze_slippage(self, trades: List[TradeAnalysis]) -> Dict[str, Any]:
        """Analyze slippage patterns"""
        slippages = [t.slippage for t in trades if t.slippage is not None]

        if not slippages:
            return {'avg_slippage': 0, 'min_slippage': 0, 'max_slippage': 0}

        return {
            'avg_slippage': statistics.mean(slippages),
            'min_slippage': min(slippages),
            'max_slippage': max(slippages),
            'median_slippage': statistics.median(slippages)
        }

    def _generate_recommendations(
        self,
        performance_metrics: PerformanceMetrics,
        risk_metrics: RiskMetrics
    ) -> List[str]:
        """Generate trading recommendations based on metrics"""
        recommendations = []

        # Performance-based recommendations
        if performance_metrics.win_rate < 40:
            recommendations.append("Consider improving entry/exit timing - win rate is below 40%")

        if performance_metrics.profit_factor < 1.0:
            recommendations.append("Focus on reducing losses - profit factor is below 1.0")

        if performance_metrics.max_drawdown > 20:
            recommendations.append("Implement stricter risk management - max drawdown exceeds 20%")

        # Risk-based recommendations
        if risk_metrics.margin_utilization > 80:
            recommendations.append("Reduce leverage - margin utilization is above 80%")

        if risk_metrics.volatility > 0.5:
            recommendations.append("Consider diversifying portfolio to reduce volatility")

        if not recommendations:
            recommendations.append("Performance metrics look good - continue current strategy")

        return recommendations
