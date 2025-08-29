"""
Analytics Repository

This module provides analytics-specific database operations.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from supabase import Client

from src.database.core.database_manager import DatabaseManager
from src.database.models.analytics_models import (
    AnalyticsRecord, AnalyticsFilter, AnalyticsUpdate, ReportConfig, ReportData
)

logger = logging.getLogger(__name__)

class AnalyticsRepository:
    """Repository for analytics-related database operations."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize the analytics repository."""
        self.db_manager = db_manager
        self.client = db_manager.client

    async def create_analytics_record(self, record_data: Dict[str, Any]) -> Optional[AnalyticsRecord]:
        """Create a new analytics record."""
        try:
            # Add timestamps
            now = datetime.now(timezone.utc).isoformat()
            record_data.update({
                "created_at": now,
                "updated_at": now
            })

            result = await self.db_manager.insert("analytics_records", record_data)

            if result and result.get("data"):
                record_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return AnalyticsRecord(**record_dict)

            return None

        except Exception as e:
            logger.error(f"Failed to create analytics record: {e}")
            raise

    async def get_analytics_record_by_id(self, record_id: int) -> Optional[AnalyticsRecord]:
        """Get an analytics record by ID."""
        try:
            result = await self.db_manager.select(
                "analytics_records",
                filters={"id": record_id}
            )

            if result and result.get("data"):
                record_dict = result["data"][0]
                return AnalyticsRecord(**record_dict)

            return None

        except Exception as e:
            logger.error(f"Failed to get analytics record by ID {record_id}: {e}")
            raise

    async def get_analytics_records_by_filter(self, analytics_filter: AnalyticsFilter,
                                           limit: Optional[int] = None,
                                           offset: Optional[int] = None) -> List[AnalyticsRecord]:
        """Get analytics records by filter criteria."""
        try:
            filters = {}

            if analytics_filter.trader:
                filters["trader"] = analytics_filter.trader
            if analytics_filter.analytics_type:
                filters["analytics_type"] = analytics_filter.analytics_type
            if analytics_filter.metric_type:
                filters["metric_type"] = analytics_filter.metric_type
            if analytics_filter.period_start:
                filters["period_start"] = {"gte": analytics_filter.period_start}
            if analytics_filter.period_end:
                filters["period_end"] = {"lte": analytics_filter.period_end}
            if analytics_filter.min_value is not None:
                filters["value"] = {"gte": analytics_filter.min_value}
            if analytics_filter.max_value is not None:
                if "value" in filters:
                    filters["value"]["lte"] = analytics_filter.max_value
                else:
                    filters["value"] = {"lte": analytics_filter.max_value}

            result = await self.db_manager.select(
                "analytics_records",
                filters=filters,
                order_by="period_start.desc",
                limit=limit
            )

            records = []
            if result and result.get("data"):
                for record_dict in result["data"]:
                    records.append(AnalyticsRecord(**record_dict))

            return records

        except Exception as e:
            logger.error(f"Failed to get analytics records by filter: {e}")
            raise

    async def update_analytics_record(self, record_id: int, updates: AnalyticsUpdate) -> Optional[AnalyticsRecord]:
        """Update an analytics record."""
        try:
            # Convert AnalyticsUpdate to dict, excluding None values
            update_data = {}
            for field, value in updates.__dict__.items():
                if value is not None:
                    update_data[field] = value

            # Add updated_at timestamp
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            result = await self.db_manager.update(
                "analytics_records",
                update_data,
                filters={"id": record_id}
            )

            if result and result.get("data"):
                record_dict = result["data"][0]
                return AnalyticsRecord(**record_dict)

            return None

        except Exception as e:
            logger.error(f"Failed to update analytics record {record_id}: {e}")
            raise

    async def delete_analytics_record(self, record_id: int) -> bool:
        """Delete an analytics record."""
        try:
            result = await self.db_manager.delete(
                "analytics_records",
                filters={"id": record_id}
            )

            return result is not None

        except Exception as e:
            logger.error(f"Failed to delete analytics record {record_id}: {e}")
            raise

    async def get_performance_metrics(self, trader: str,
                                    start_date: str,
                                    end_date: str) -> Dict[str, Any]:
        """Get performance metrics for a trader in a date range."""
        try:
            # Get analytics records for the period
            records = await self.get_analytics_records_by_filter(
                AnalyticsFilter(
                    trader=trader,
                    period_start=start_date,
                    period_end=end_date
                )
            )

            # Calculate performance metrics
            metrics = {
                "total_pnl": 0.0,
                "total_volume": 0.0,
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_trade_pnl": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0
            }

            pnl_records = [r for r in records if r.metric_type == "PNL"]
            volume_records = [r for r in records if r.metric_type == "VOLUME"]
            trade_count_records = [r for r in records if r.metric_type == "TRADE_COUNT"]

            # Calculate total PnL
            for record in pnl_records:
                metrics["total_pnl"] += record.value

            # Calculate total volume
            for record in volume_records:
                metrics["total_volume"] += record.value

            # Calculate total trades
            for record in trade_count_records:
                metrics["total_trades"] += int(record.value)

            # Calculate average trade PnL
            if metrics["total_trades"] > 0:
                metrics["avg_trade_pnl"] = metrics["total_pnl"] / metrics["total_trades"]

            # TODO: Implement more complex calculations like Sharpe ratio, max drawdown
            # This would require more sophisticated analysis of the data

            return metrics

        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            raise

    async def get_daily_returns(self, trader: str,
                              start_date: str,
                              end_date: str) -> List[Dict[str, Any]]:
        """Get daily returns for a trader."""
        try:
            # Get daily PnL records
            records = await self.get_analytics_records_by_filter(
                AnalyticsFilter(
                    trader=trader,
                    analytics_type="DAILY",
                    metric_type="PNL",
                    period_start=start_date,
                    period_end=end_date
                )
            )

            daily_returns = []
            for record in records:
                daily_returns.append({
                    "date": record.period_start,
                    "pnl": record.value,
                    "metadata": record.metadata
                })

            return daily_returns

        except Exception as e:
            logger.error(f"Failed to get daily returns: {e}")
            raise

    async def get_equity_curve(self, trader: str,
                             start_date: str,
                             end_date: str) -> List[Dict[str, Any]]:
        """Get equity curve data for a trader."""
        try:
            # Get daily PnL records
            daily_returns = await self.get_daily_returns(trader, start_date, end_date)

            # Calculate cumulative equity
            equity_curve = []
            cumulative_pnl = 0.0

            for daily_return in daily_returns:
                cumulative_pnl += daily_return["pnl"]
                equity_curve.append({
                    "date": daily_return["date"],
                    "equity": cumulative_pnl,
                    "daily_pnl": daily_return["pnl"]
                })

            return equity_curve

        except Exception as e:
            logger.error(f"Failed to get equity curve: {e}")
            raise

    async def get_drawdown_curve(self, trader: str,
                               start_date: str,
                               end_date: str) -> List[Dict[str, Any]]:
        """Get drawdown curve data for a trader."""
        try:
            # Get equity curve
            equity_curve = await self.get_equity_curve(trader, start_date, end_date)

            # Calculate drawdown
            drawdown_curve = []
            peak_equity = 0.0

            for point in equity_curve:
                if point["equity"] > peak_equity:
                    peak_equity = point["equity"]

                drawdown = (peak_equity - point["equity"]) / peak_equity if peak_equity > 0 else 0.0

                drawdown_curve.append({
                    "date": point["date"],
                    "drawdown": drawdown,
                    "equity": point["equity"],
                    "peak_equity": peak_equity
                })

            return drawdown_curve

        except Exception as e:
            logger.error(f"Failed to get drawdown curve: {e}")
            raise

    async def generate_report(self, config: ReportConfig) -> ReportData:
        """Generate a comprehensive analytics report."""
        try:
            from datetime import datetime, timedelta

            # Calculate date range based on period
            end_date = datetime.now(timezone.utc)
            if config.period == "7d":
                start_date = end_date - timedelta(days=7)
            elif config.period == "30d":
                start_date = end_date - timedelta(days=30)
            elif config.period == "90d":
                start_date = end_date - timedelta(days=90)
            elif config.period == "1y":
                start_date = end_date - timedelta(days=365)
            else:
                start_date = end_date - timedelta(days=30)  # Default to 30 days

            start_date_str = start_date.isoformat()
            end_date_str = end_date.isoformat()

            # Get performance metrics
            performance_metrics = await self.get_performance_metrics(
                config.trader, start_date_str, end_date_str
            )

            # Get analytics records
            analytics_records = await self.get_analytics_records_by_filter(
                AnalyticsFilter(
                    trader=config.trader,
                    period_start=start_date_str,
                    period_end=end_date_str
                )
            )

            # Create report data
            report_data = ReportData(
                config=config,
                analytics_records=analytics_records,
                generated_at=datetime.now(timezone.utc)
            )

            # Add performance metrics to summary
            from src.database.models.analytics_models import PerformanceMetrics
            report_data.summary.performance = PerformanceMetrics(
                total_pnl=performance_metrics["total_pnl"],
                total_volume=performance_metrics["total_volume"],
                total_trades=performance_metrics["total_trades"],
                win_rate=performance_metrics["win_rate"],
                avg_trade_pnl=performance_metrics["avg_trade_pnl"],
                max_drawdown=performance_metrics["max_drawdown"],
                sharpe_ratio=performance_metrics["sharpe_ratio"]
            )

            return report_data

        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise

    async def cleanup_old_records(self, days: int = 90) -> int:
        """Clean up old analytics records."""
        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Get old records
            result = await self.db_manager.select(
                "analytics_records",
                filters={"created_at": {"lt": cutoff_iso}},
                columns=["id"]
            )

            if not result or not result.get("data"):
                return 0

            # Delete old records
            deleted_count = 0
            for record_data in result["data"]:
                record_id = record_data["id"]
                if await self.delete_analytics_record(record_id):
                    deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} old analytics records")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old analytics records: {e}")
            raise
