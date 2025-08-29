"""
Trade Repository

This module provides trade-specific database operations.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from supabase import Client

from src.database.core.database_manager import DatabaseManager
from src.database.models.trade_models import (
    Trade, Alert, TradeFilter, TradeUpdate, TradeStats, TradeSummary
)

logger = logging.getLogger(__name__)

class TradeRepository:
    """Repository for trade-related database operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize the trade repository."""
        self.db_manager = db_manager
        self.client = db_manager.client
    
    async def create_trade(self, trade_data: Dict[str, Any]) -> Optional[Trade]:
        """Create a new trade record."""
        try:
            # Add timestamps
            now = datetime.now(timezone.utc).isoformat()
            trade_data.update({
                "created_at": now,
                "updated_at": now
            })
            
            result = await self.db_manager.insert("trades", trade_data)
            
            if result and result.get("data"):
                trade_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return Trade(**trade_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create trade: {e}")
            raise
    
    async def get_trade_by_id(self, trade_id: int) -> Optional[Trade]:
        """Get a trade by ID."""
        try:
            result = await self.db_manager.select(
                "trades",
                filters={"id": trade_id}
            )
            
            if result and result.get("data"):
                trade_dict = result["data"][0]
                return Trade(**trade_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get trade by ID {trade_id}: {e}")
            raise
    
    async def get_trade_by_discord_id(self, discord_id: str) -> Optional[Trade]:
        """Get a trade by Discord ID."""
        try:
            result = await self.db_manager.select(
                "trades",
                filters={"discord_id": discord_id}
            )
            
            if result and result.get("data"):
                trade_dict = result["data"][0]
                return Trade(**trade_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get trade by Discord ID {discord_id}: {e}")
            raise
    
    async def get_trades_by_filter(self, trade_filter: TradeFilter, 
                                 limit: Optional[int] = None,
                                 offset: Optional[int] = None) -> List[Trade]:
        """Get trades by filter criteria."""
        try:
            filters = {}
            
            if trade_filter.trader:
                filters["trader"] = trade_filter.trader
            if trade_filter.status:
                filters["status"] = trade_filter.status
            if trade_filter.coin_symbol:
                filters["coin_symbol"] = trade_filter.coin_symbol
            if trade_filter.discord_id:
                filters["discord_id"] = trade_filter.discord_id
            if trade_filter.exchange_order_id:
                filters["exchange_order_id"] = trade_filter.exchange_order_id
            if trade_filter.manual_verification_needed is not None:
                filters["manual_verification_needed"] = trade_filter.manual_verification_needed
            
            # Handle date range filters
            if trade_filter.start_date or trade_filter.end_date:
                if trade_filter.start_date:
                    filters["created_at"] = {"gte": trade_filter.start_date}
                if trade_filter.end_date:
                    if "created_at" in filters:
                        filters["created_at"]["lte"] = trade_filter.end_date
                    else:
                        filters["created_at"] = {"lte": trade_filter.end_date}
            
            result = await self.db_manager.select(
                "trades",
                filters=filters,
                order_by="created_at.desc",
                limit=limit
            )
            
            trades = []
            if result and result.get("data"):
                for trade_dict in result["data"]:
                    trades.append(Trade(**trade_dict))
            
            return trades
            
        except Exception as e:
            logger.error(f"Failed to get trades by filter: {e}")
            raise
    
    async def update_trade(self, trade_id: int, updates: TradeUpdate) -> Optional[Trade]:
        """Update a trade record."""
        try:
            # Convert TradeUpdate to dict, excluding None values
            update_data = {}
            for field, value in updates.__dict__.items():
                if value is not None:
                    update_data[field] = value
            
            # Add updated_at timestamp
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            result = await self.db_manager.update(
                "trades",
                update_data,
                filters={"id": trade_id}
            )
            
            if result and result.get("data"):
                trade_dict = result["data"][0]
                return Trade(**trade_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update trade {trade_id}: {e}")
            raise
    
    async def delete_trade(self, trade_id: int) -> bool:
        """Delete a trade record."""
        try:
            result = await self.db_manager.delete(
                "trades",
                filters={"id": trade_id}
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to delete trade {trade_id}: {e}")
            raise
    
    async def get_trade_stats(self, trader: Optional[str] = None, 
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> TradeStats:
        """Get trade statistics."""
        try:
            filters = {}
            if trader:
                filters["trader"] = trader
            if start_date or end_date:
                if start_date:
                    filters["created_at"] = {"gte": start_date}
                if end_date:
                    if "created_at" in filters:
                        filters["created_at"]["lte"] = end_date
                    else:
                        filters["created_at"] = {"lte": end_date}
            
            # Get all trades for the period
            trades = await self.get_trades_by_filter(
                TradeFilter(trader=trader),
                limit=10000  # Large limit to get all trades
            )
            
            # Calculate statistics
            stats = TradeStats()
            stats.total_trades = len(trades)
            
            total_pnl = 0.0
            winning_trades = 0
            losing_trades = 0
            
            for trade in trades:
                if trade.status == "OPEN":
                    stats.open_trades += 1
                elif trade.status == "CLOSED":
                    stats.closed_trades += 1
                elif trade.status == "PENDING":
                    stats.pending_trades += 1
                elif trade.status == "FAILED":
                    stats.failed_trades += 1
                
                if trade.pnl_usd:
                    total_pnl += trade.pnl_usd
                    if trade.pnl_usd > 0:
                        winning_trades += 1
                    elif trade.pnl_usd < 0:
                        losing_trades += 1
            
            stats.total_pnl = total_pnl
            stats.winning_trades = winning_trades
            stats.losing_trades = losing_trades
            
            if stats.total_trades > 0:
                stats.win_rate = (winning_trades / stats.total_trades) * 100
                stats.avg_trade_pnl = total_pnl / stats.total_trades
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get trade stats: {e}")
            raise
    
    async def create_alert(self, alert_data: Dict[str, Any]) -> Optional[Alert]:
        """Create a new alert record."""
        try:
            # Add timestamps
            now = datetime.now(timezone.utc).isoformat()
            alert_data.update({
                "created_at": now,
                "updated_at": now
            })
            
            result = await self.db_manager.insert("alerts", alert_data)
            
            if result and result.get("data"):
                alert_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return Alert(**alert_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            raise
    
    async def get_alerts_by_trade(self, trade_discord_id: str) -> List[Alert]:
        """Get alerts for a specific trade."""
        try:
            result = await self.db_manager.select(
                "alerts",
                filters={"trade": trade_discord_id},
                order_by="created_at.asc"
            )
            
            alerts = []
            if result and result.get("data"):
                for alert_dict in result["data"]:
                    alerts.append(Alert(**alert_dict))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get alerts for trade {trade_discord_id}: {e}")
            raise
    
    async def update_alert(self, alert_id: int, updates: Dict[str, Any]) -> Optional[Alert]:
        """Update an alert record."""
        try:
            # Add updated_at timestamp
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            result = await self.db_manager.update(
                "alerts",
                updates,
                filters={"id": alert_id}
            )
            
            if result and result.get("data"):
                alert_dict = result["data"][0]
                return Alert(**alert_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update alert {alert_id}: {e}")
            raise
    
    async def get_trades_needing_sync(self, hours: int = 24) -> List[Trade]:
        """Get trades that need synchronization."""
        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_iso = cutoff.isoformat()
            
            # Get trades that haven't been synced recently or have sync issues
            result = await self.db_manager.select(
                "trades",
                filters={
                    "or": [
                        {"last_order_sync": {"lt": cutoff_iso}},
                        {"last_pnl_sync": {"lt": cutoff_iso}},
                        {"sync_error_count": {"gt": 0}},
                        {"manual_verification_needed": True}
                    ]
                },
                order_by="created_at.desc"
            )
            
            trades = []
            if result and result.get("data"):
                for trade_dict in result["data"]:
                    trades.append(Trade(**trade_dict))
            
            return trades
            
        except Exception as e:
            logger.error(f"Failed to get trades needing sync: {e}")
            raise
    
    async def get_open_trades(self, trader: Optional[str] = None) -> List[Trade]:
        """Get all open trades."""
        try:
            filters = {"status": "OPEN"}
            if trader:
                filters["trader"] = trader
            
            result = await self.db_manager.select(
                "trades",
                filters=filters,
                order_by="created_at.desc"
            )
            
            trades = []
            if result and result.get("data"):
                for trade_dict in result["data"]:
                    trades.append(Trade(**trade_dict))
            
            return trades
            
        except Exception as e:
            logger.error(f"Failed to get open trades: {e}")
            raise
