"""
Alert Repository

This module provides alert-specific database operations.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from supabase import Client

from src.database.core.database_manager import DatabaseManager
from src.database.models.trade_models import Alert

logger = logging.getLogger(__name__)

class AlertRepository:
    """Repository for alert-related database operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize the alert repository."""
        self.db_manager = db_manager
        self.client = db_manager.client
    
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
    
    async def get_alert_by_id(self, alert_id: int) -> Optional[Alert]:
        """Get an alert by ID."""
        try:
            result = await self.db_manager.select(
                "alerts",
                filters={"id": alert_id}
            )
            
            if result and result.get("data"):
                alert_dict = result["data"][0]
                return Alert(**alert_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get alert by ID {alert_id}: {e}")
            raise
    
    async def get_alert_by_discord_id(self, discord_id: str) -> Optional[Alert]:
        """Get an alert by Discord ID."""
        try:
            result = await self.db_manager.select(
                "alerts",
                filters={"discord_id": discord_id}
            )
            
            if result and result.get("data"):
                alert_dict = result["data"][0]
                return Alert(**alert_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get alert by Discord ID {discord_id}: {e}")
            raise
    
    async def get_alerts_by_trade(self, trade_discord_id: str) -> List[Alert]:
        """Get all alerts for a specific trade."""
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
    
    async def get_alerts_by_trader(self, trader: str, limit: Optional[int] = None) -> List[Alert]:
        """Get all alerts for a specific trader."""
        try:
            result = await self.db_manager.select(
                "alerts",
                filters={"trader": trader},
                order_by="created_at.desc",
                limit=limit
            )
            
            alerts = []
            if result and result.get("data"):
                for alert_dict in result["data"]:
                    alerts.append(Alert(**alert_dict))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get alerts for trader {trader}: {e}")
            raise
    
    async def get_alerts_by_status(self, status: str, limit: Optional[int] = None) -> List[Alert]:
        """Get alerts by status."""
        try:
            result = await self.db_manager.select(
                "alerts",
                filters={"status": status},
                order_by="created_at.desc",
                limit=limit
            )
            
            alerts = []
            if result and result.get("data"):
                for alert_dict in result["data"]:
                    alerts.append(Alert(**alert_dict))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get alerts by status {status}: {e}")
            raise
    
    async def get_recent_alerts(self, hours: int = 24, limit: Optional[int] = None) -> List[Alert]:
        """Get recent alerts within specified hours."""
        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_iso = cutoff.isoformat()
            
            result = await self.db_manager.select(
                "alerts",
                filters={"created_at": {"gte": cutoff_iso}},
                order_by="created_at.desc",
                limit=limit
            )
            
            alerts = []
            if result and result.get("data"):
                for alert_dict in result["data"]:
                    alerts.append(Alert(**alert_dict))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get recent alerts: {e}")
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
    
    async def update_alert_by_discord_id(self, discord_id: str, updates: Dict[str, Any]) -> Optional[Alert]:
        """Update an alert by Discord ID."""
        try:
            # Add updated_at timestamp
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            result = await self.db_manager.update(
                "alerts",
                updates,
                filters={"discord_id": discord_id}
            )
            
            if result and result.get("data"):
                alert_dict = result["data"][0]
                return Alert(**alert_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update alert by Discord ID {discord_id}: {e}")
            raise
    
    async def delete_alert(self, alert_id: int) -> bool:
        """Delete an alert record."""
        try:
            result = await self.db_manager.delete(
                "alerts",
                filters={"id": alert_id}
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to delete alert {alert_id}: {e}")
            raise
    
    async def get_alert_stats(self, trader: Optional[str] = None, 
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get alert statistics."""
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
            
            # Get all alerts for the period
            result = await self.db_manager.select(
                "alerts",
                filters=filters,
                limit=10000  # Large limit to get all alerts
            )
            
            alerts = []
            if result and result.get("data"):
                for alert_dict in result["data"]:
                    alerts.append(Alert(**alert_dict))
            
            # Calculate statistics
            stats = {
                "total_alerts": len(alerts),
                "successful_alerts": 0,
                "failed_alerts": 0,
                "pending_alerts": 0,
                "skipped_alerts": 0,
                "error_alerts": 0
            }
            
            for alert in alerts:
                if alert.status == "SUCCESS":
                    stats["successful_alerts"] += 1
                elif alert.status == "ERROR":
                    stats["error_alerts"] += 1
                elif alert.status == "PENDING":
                    stats["pending_alerts"] += 1
                elif alert.status == "SKIPPED":
                    stats["skipped_alerts"] += 1
                else:
                    stats["failed_alerts"] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get alert stats: {e}")
            raise
    
    async def get_duplicate_alerts(self, hours: int = 1) -> List[Alert]:
        """Get potential duplicate alerts within specified hours."""
        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_iso = cutoff.isoformat()
            
            # Get recent alerts
            recent_alerts = await self.get_recent_alerts(hours)
            
            # Group by trade and content to find duplicates
            alert_groups = {}
            for alert in recent_alerts:
                key = f"{alert.trade}_{alert.content}"
                if key not in alert_groups:
                    alert_groups[key] = []
                alert_groups[key].append(alert)
            
            # Return alerts that have duplicates
            duplicates = []
            for group in alert_groups.values():
                if len(group) > 1:
                    duplicates.extend(group[1:])  # Skip the first one, return duplicates
            
            return duplicates
            
        except Exception as e:
            logger.error(f"Failed to get duplicate alerts: {e}")
            raise
    
    async def cleanup_old_alerts(self, days: int = 30) -> int:
        """Clean up old alerts older than specified days."""
        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()
            
            # Get old alerts
            result = await self.db_manager.select(
                "alerts",
                filters={"created_at": {"lt": cutoff_iso}},
                columns=["id"]
            )
            
            if not result or not result.get("data"):
                return 0
            
            # Delete old alerts
            deleted_count = 0
            for alert_data in result["data"]:
                alert_id = alert_data["id"]
                if await self.delete_alert(alert_id):
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old alerts")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old alerts: {e}")
            raise
