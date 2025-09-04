"""
Alert Database Operations

Handles all alert-related database operations for the Discord bot.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from supabase import Client

from ..models.trade_models import AlertModel

logger = logging.getLogger(__name__)


class AlertOperations:
    """Handles alert-related database operations."""

    def __init__(self, supabase_client: Client):
        """Initialize with Supabase client."""
        self.supabase = supabase_client

    async def save_alert_to_database(self, alert_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Save a new alert to the database."""
        try:
            response = self.supabase.table("alerts").insert(alert_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Saved alert to database: {response.data[0]['id']}")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error saving alert to database: {e}")
            return None

    async def update_existing_alert(self, alert_id: int, updates: Dict[str, Any]) -> bool:
        """Update an existing alert record."""
        try:
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()
            response = self.supabase.table("alerts").update(updates).eq("id", alert_id).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Updated alert {alert_id} successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating alert {alert_id}: {e}")
            return False

    async def update_alert_by_discord_id_or_trade(self, discord_id: str, trade: Optional[str], updates: Dict[str, Any]) -> bool:
        """Update alert by Discord ID or trade reference."""
        try:
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()

            # Try to find by discord_id first
            response = self.supabase.table("alerts").select("id").eq("discord_id", discord_id).limit(1).execute()
            if response.data and len(response.data) > 0:
                alert_id = response.data[0]['id']
                return await self.update_existing_alert(alert_id, updates)

            # If not found by discord_id and trade is provided, try by trade
            if trade:
                response = self.supabase.table("alerts").select("id").eq("trade", trade).limit(1).execute()
                if response.data and len(response.data) > 0:
                    alert_id = response.data[0]['id']
                    return await self.update_existing_alert(alert_id, updates)

            # If not found, create a new alert
            alert_data = {
                "discord_id": discord_id,
                "trade": trade,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **updates
            }
            return await self.save_alert_to_database(alert_data) is not None

        except Exception as e:
            logger.error(f"Error updating alert by discord_id {discord_id} or trade {trade}: {e}")
            return False

    async def get_alert_by_id(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """Get an alert by ID."""
        try:
            response = self.supabase.table("alerts").select("*").eq("id", alert_id).limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting alert {alert_id}: {e}")
            return None

    async def get_alert_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get an alert by Discord ID."""
        try:
            response = self.supabase.table("alerts").select("*").eq("discord_id", discord_id).limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting alert by discord_id {discord_id}: {e}")
            return None

    async def get_alerts_by_trade(self, trade: str) -> List[Dict[str, Any]]:
        """Get all alerts for a specific trade."""
        try:
            response = self.supabase.table("alerts").select("*").eq("trade", trade).order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting alerts for trade {trade}: {e}")
            return []

    async def get_alerts_by_trader(self, trader: str) -> List[Dict[str, Any]]:
        """Get all alerts by a specific trader."""
        try:
            response = self.supabase.table("alerts").select("*").eq("trader", trader).order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting alerts for trader {trader}: {e}")
            return []

    async def get_alerts_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all alerts with a specific status."""
        try:
            response = self.supabase.table("alerts").select("*").eq("status", status).order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting alerts with status {status}: {e}")
            return []

    async def delete_alert(self, alert_id: int) -> bool:
        """Delete an alert record."""
        try:
            response = self.supabase.table("alerts").delete().eq("id", alert_id).execute()
            if response.data:
                logger.info(f"Deleted alert {alert_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting alert {alert_id}: {e}")
            return False

    async def update_alert_status(self, alert_id: int, status: str) -> bool:
        """Update alert status."""
        try:
            updates = {
                'status': status,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            return await self.update_existing_alert(alert_id, updates)
        except Exception as e:
            logger.error(f"Error updating alert {alert_id} status to {status}: {e}")
            return False

    async def check_duplicate_alert(self, alert_hash: str) -> bool:
        """Check if an alert hash already exists."""
        try:
            try:
                response = self.supabase.table("alerts").select("id").eq("alert_hash", alert_hash).execute()
                if response.data and len(response.data) > 0:
                    return True
            except Exception as e:
                logger.debug(f"alert_hash column not available, using fallback duplicate detection: {e}")

                # In a production environment, you might want to implement content-based duplicate detection
                return False

            return False

        except Exception as e:
            logger.warning(f"Error checking duplicate alert hash {alert_hash}: {e}")
            return False

    async def store_alert_hash(self, alert_hash: str) -> bool:
        """Store an alert hash to prevent duplicates."""
        try:
            alert_data = {
                "alert_hash": alert_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            return await self.save_alert_to_database(alert_data) is not None
        except Exception as e:
            logger.error(f"Error storing alert hash {alert_hash}: {e}")
            return False
