"""
Active Futures Repository

This module provides active futures-specific database operations.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from supabase import Client

from src.database.core.database_manager import DatabaseManager
from src.database.models.trade_models import ActiveFutures, ActiveFuturesFilter

logger = logging.getLogger(__name__)

class ActiveFuturesRepository:
    """Repository for active futures-related database operations."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize the active futures repository."""
        self.db_manager = db_manager
        self.client = db_manager.client

    async def get_active_futures_by_trader(self, trader: str) -> List[ActiveFutures]:
        """Get active futures for a specific trader."""
        try:
            result = await self.db_manager.select(
                "active_futures",
                filters={"trader": trader},
                order_by="created_at",
                order_direction="desc"
            )

            if result and result.get("data"):
                return [ActiveFutures(**item) for item in result["data"]]

            return []

        except Exception as e:
            logger.error(f"Failed to get active futures by trader {trader}: {e}")
            raise

    async def get_futures_by_status(self, status: str) -> List[ActiveFutures]:
        """Get futures by status."""
        try:
            result = await self.db_manager.select(
                "active_futures",
                filters={"status": status},
                order_by="created_at",
                order_direction="desc"
            )

            if result and result.get("data"):
                return [ActiveFutures(**item) for item in result["data"]]

            return []

        except Exception as e:
            logger.error(f"Failed to get futures by status {status}: {e}")
            raise

    async def get_futures_by_traders_and_status(self, traders: List[str], status: str) -> List[ActiveFutures]:
        """Get futures by multiple traders and status."""
        try:
            client = self.db_manager.client
            if client is None:
                # Ensure client is initialized
                await self.db_manager.initialize()
                client = self.db_manager.client
            query = client.table("active_futures").select("*")

            if traders:
                # Normalize traders list to plain strings without quotes/whitespace
                clean_traders = [str(t).strip().strip('"').strip("'") for t in traders if str(t).strip().strip('"').strip("'")]
                if clean_traders:
                    query = query.in_("trader", clean_traders)
                else:
                    return []

            if status:
                query = query.eq("status", status)

            query = query.order("created_at", desc=True)
            result = query.execute()

            if result.data:
                return [ActiveFutures(**item) for item in result.data]

            return []

        except Exception as e:
            logger.error(f"Failed to get futures by traders {traders} and status {status}: {e}")
            raise

    async def get_futures_changes_since(self, timestamp: str) -> List[ActiveFutures]:
        """Get futures changes since a specific timestamp."""
        try:
            result = await self.db_manager.select(
                "active_futures",
                filters={"created_at": f"gte.{timestamp}"},
                order_by="created_at",
                order_direction="desc"
            )

            if result and result.get("data"):
                return [ActiveFutures(**item) for item in result["data"]]

            return []

        except Exception as e:
            logger.error(f"Failed to get futures changes since {timestamp}: {e}")
            raise

    async def update_futures_status(self, futures_id: int, status: str, stopped_at: Optional[str] = None) -> bool:
        """Update futures status."""
        try:
            update_data = {"status": status}
            if stopped_at:
                update_data["stopped_at"] = stopped_at

            result = await self.db_manager.update(
                "active_futures",
                futures_id,
                update_data
            )

            return result is not None

        except Exception as e:
            logger.error(f"Failed to update futures status for ID {futures_id}: {e}")
            raise

    async def get_futures_by_filter(self, filter_obj: ActiveFuturesFilter) -> List[ActiveFutures]:
        """Get futures using filter object."""
        try:
            filters = {}

            if filter_obj.trader:
                filters["trader"] = filter_obj.trader
            if filter_obj.status:
                filters["status"] = filter_obj.status
            if filter_obj.start_date:
                filters["created_at"] = f"gte.{filter_obj.start_date}"
            if filter_obj.end_date:
                filters["created_at"] = f"lte.{filter_obj.end_date}"

            result = await self.db_manager.select(
                "active_futures",
                filters=filters,
                order_by="created_at",
                order_direction="desc"
            )

            if result and result.get("data"):
                return [ActiveFutures(**item) for item in result["data"]]

            return []

        except Exception as e:
            logger.error(f"Failed to get futures by filter: {e}")
            raise

    async def get_recent_closed_futures(self, hours: int = 24) -> List[ActiveFutures]:
        """Get recently closed futures within specified hours."""
        try:
            cutoff_time = datetime.now(timezone.utc)
            cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - hours)
            cutoff_str = cutoff_time.isoformat()

            result = await self.db_manager.select(
                "active_futures",
                filters={
                    "status": "CLOSED",
                    "stopped_at": f"gte.{cutoff_str}"
                },
                order_by="stopped_at",
                order_direction="desc"
            )

            if result and result.get("data"):
                return [ActiveFutures(**item) for item in result["data"]]

            return []

        except Exception as e:
            logger.error(f"Failed to get recent closed futures: {e}")
            raise
