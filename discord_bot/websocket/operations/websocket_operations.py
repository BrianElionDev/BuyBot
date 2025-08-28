"""
WebSocket Database Operations

Handles all WebSocket-related database operations for the Discord bot.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from supabase import Client

from ..models.websocket_models import WebSocketEvent, WebSocketEventType, WebSocketConnectionInfo

logger = logging.getLogger(__name__)


class WebSocketOperations:
    """Handles WebSocket-related database operations."""
    
    def __init__(self, supabase_client: Client):
        """Initialize with Supabase client."""
        self.supabase = supabase_client
    
    async def log_websocket_event(self, event: WebSocketEvent) -> bool:
        """Log a WebSocket event to the database."""
        try:
            event_data = event.to_dict()
            response = self.supabase.table("websocket_events").insert(event_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Logged WebSocket event: {event.event_type.value}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error logging WebSocket event: {e}")
            return False
    
    async def get_recent_websocket_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent WebSocket events."""
        try:
            response = self.supabase.table("websocket_events").select("*").order("timestamp", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting recent WebSocket events: {e}")
            return []
    
    async def get_websocket_events_by_type(self, event_type: WebSocketEventType, limit: int = 50) -> List[Dict[str, Any]]:
        """Get WebSocket events by type."""
        try:
            response = self.supabase.table("websocket_events").select("*").eq("event_type", event_type.value).order("timestamp", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting WebSocket events by type {event_type.value}: {e}")
            return []
    
    async def get_websocket_events_by_source(self, source: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get WebSocket events by source."""
        try:
            response = self.supabase.table("websocket_events").select("*").eq("source", source).order("timestamp", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting WebSocket events by source {source}: {e}")
            return []
    
    async def update_connection_status(self, connection_info: WebSocketConnectionInfo) -> bool:
        """Update WebSocket connection status."""
        try:
            status_data = connection_info.to_dict()
            status_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Try to update existing record, insert if not exists
            response = self.supabase.table("websocket_connection_status").upsert(status_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Updated WebSocket connection status: {connection_info.status.value}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating WebSocket connection status: {e}")
            return False
    
    async def get_connection_status(self) -> Optional[Dict[str, Any]]:
        """Get current WebSocket connection status."""
        try:
            response = self.supabase.table("websocket_connection_status").select("*").limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting WebSocket connection status: {e}")
            return None
    
    async def log_error_event(self, error_message: str, source: str = "websocket") -> bool:
        """Log a WebSocket error event."""
        try:
            error_event = WebSocketEvent(
                event_type=WebSocketEventType.ERROR,
                error_message=error_message,
                source=source
            )
            return await self.log_websocket_event(error_event)
        except Exception as e:
            logger.error(f"Error logging WebSocket error event: {e}")
            return False
    
    async def log_trade_event(self, event_type: WebSocketEventType, trade_data: Dict[str, Any]) -> bool:
        """Log a trade-related WebSocket event."""
        try:
            trade_event = WebSocketEvent(
                event_type=event_type,
                data=trade_data,
                source="trade_system"
            )
            return await self.log_websocket_event(trade_event)
        except Exception as e:
            logger.error(f"Error logging trade WebSocket event: {e}")
            return False
    
    async def log_alert_event(self, event_type: WebSocketEventType, alert_data: Dict[str, Any]) -> bool:
        """Log an alert-related WebSocket event."""
        try:
            alert_event = WebSocketEvent(
                event_type=event_type,
                data=alert_data,
                source="alert_system"
            )
            return await self.log_websocket_event(alert_event)
        except Exception as e:
            logger.error(f"Error logging alert WebSocket event: {e}")
            return False
    
    async def cleanup_old_events(self, days_old: int = 30) -> bool:
        """Clean up old WebSocket events."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            cutoff_str = cutoff_date.isoformat()
            
            response = self.supabase.table("websocket_events").delete().lt("timestamp", cutoff_str).execute()
            logger.info(f"Cleaned up WebSocket events older than {days_old} days")
            return True
        except Exception as e:
            logger.error(f"Error cleaning up old WebSocket events: {e}")
            return False
    
    async def get_event_statistics(self) -> Dict[str, Any]:
        """Get WebSocket event statistics."""
        try:
            # Get total events count
            total_response = self.supabase.table("websocket_events").select("*").execute()
            total_events = len(total_response.data) if total_response.data else 0
            
            # Get events by type
            stats = {"total_events": total_events, "events_by_type": {}}
            
            for event_type in WebSocketEventType:
                type_response = self.supabase.table("websocket_events").select("*").eq("event_type", event_type.value).execute()
                count = len(type_response.data) if type_response.data else 0
                stats["events_by_type"][event_type.value] = count
            
            return stats
        except Exception as e:
            logger.error(f"Error getting WebSocket event statistics: {e}")
            return {"total_events": 0, "events_by_type": {}}
