"""
WebSocket Utilities

Helper functions and utilities for WebSocket operations.
"""

import logging
import asyncio
import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from ..models.websocket_models import WebSocketEvent, WebSocketEventType, WebSocketConnectionInfo, WebSocketStatus

logger = logging.getLogger(__name__)


class WebSocketUtils:
    """Utility functions for WebSocket operations."""
    
    @staticmethod
    def create_websocket_event(event_type: WebSocketEventType, data: Optional[Dict[str, Any]] = None, 
                              error_message: Optional[str] = None, source: Optional[str] = None) -> WebSocketEvent:
        """Create a WebSocket event."""
        return WebSocketEvent(
            event_type=event_type,
            data=data,
            error_message=error_message,
            source=source
        )
    
    @staticmethod
    def create_connection_info(status: WebSocketStatus = WebSocketStatus.DISCONNECTED) -> WebSocketConnectionInfo:
        """Create a WebSocket connection info object."""
        return WebSocketConnectionInfo(status=status)
    
    @staticmethod
    def format_websocket_message(event: WebSocketEvent) -> str:
        """Format a WebSocket event as a JSON message."""
        try:
            return json.dumps(event.to_dict())
        except Exception as e:
            logger.error(f"Error formatting WebSocket message: {e}")
            return json.dumps({
                'event_type': 'error',
                'error_message': f'Failed to format message: {str(e)}',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
    
    @staticmethod
    def parse_websocket_message(message: str) -> Optional[WebSocketEvent]:
        """Parse a WebSocket message into an event."""
        try:
            data = json.loads(message)
            return WebSocketEvent.from_dict(data)
        except Exception as e:
            logger.error(f"Error parsing WebSocket message: {e}")
            return None
    
    @staticmethod
    def validate_websocket_url(url: str) -> bool:
        """Validate a WebSocket URL."""
        try:
            if not url.startswith(('ws://', 'wss://')):
                return False
            
            # Basic URL validation
            if len(url) < 10:  # Minimum length for a valid WebSocket URL
                return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def calculate_reconnect_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        """Calculate exponential backoff delay for reconnection."""
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)
    
    @staticmethod
    async def wait_with_timeout(coro, timeout: float) -> Any:
        """Wait for a coroutine with timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Operation timed out after {timeout} seconds")
            return None
        except Exception as e:
            logger.error(f"Error in timed operation: {e}")
            return None
    
    @staticmethod
    def is_websocket_connected(websocket) -> bool:
        """Check if a WebSocket connection is open."""
        try:
            return websocket.open
        except Exception:
            return False
    
    @staticmethod
    def get_connection_status_summary(connection_info: WebSocketConnectionInfo) -> Dict[str, Any]:
        """Get a summary of connection status."""
        return {
            'status': connection_info.status.value,
            'connected_at': connection_info.connected_at.isoformat() if connection_info.connected_at else None,
            'reconnect_attempts': connection_info.reconnect_attempts,
            'error_count': connection_info.error_count,
            'last_error': connection_info.last_error,
            'uptime': None  # Calculate if needed
        }
    
    @staticmethod
    def create_heartbeat_message() -> str:
        """Create a heartbeat message."""
        return json.dumps({
            'type': 'heartbeat',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    @staticmethod
    def is_heartbeat_message(message: str) -> bool:
        """Check if a message is a heartbeat message."""
        try:
            data = json.loads(message)
            return data.get('type') == 'heartbeat'
        except Exception:
            return False
    
    @staticmethod
    def create_error_event(error_message: str, source: str = "websocket") -> WebSocketEvent:
        """Create an error event."""
        return WebSocketEvent(
            event_type=WebSocketEventType.ERROR,
            error_message=error_message,
            source=source
        )
    
    @staticmethod
    def log_websocket_error(error: Exception, context: str = "websocket") -> None:
        """Log a WebSocket error with context."""
        if isinstance(error, ConnectionClosed):
            logger.warning(f"WebSocket connection closed in {context}: {error}")
        elif isinstance(error, WebSocketException):
            logger.error(f"WebSocket exception in {context}: {error}")
        else:
            logger.error(f"Unexpected error in {context}: {error}")
    
    @staticmethod
    def should_reconnect(error: Exception, max_attempts: int, current_attempts: int) -> bool:
        """Determine if we should attempt to reconnect."""
        if current_attempts >= max_attempts:
            return False
        
        # Don't reconnect for certain types of errors
        if isinstance(error, ConnectionClosed) and error.code == 1000:  # Normal closure
            return False
        
        return True
    
    @staticmethod
    def format_connection_stats(connection_info: WebSocketConnectionInfo) -> str:
        """Format connection statistics as a string."""
        stats = []
        stats.append(f"Status: {connection_info.status.value}")
        
        if connection_info.connected_at:
            stats.append(f"Connected: {connection_info.connected_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if connection_info.last_heartbeat:
            stats.append(f"Last Heartbeat: {connection_info.last_heartbeat.strftime('%Y-%m-%d %H:%M:%S')}")
        
        stats.append(f"Reconnect Attempts: {connection_info.reconnect_attempts}")
        stats.append(f"Error Count: {connection_info.error_count}")
        
        if connection_info.last_error:
            stats.append(f"Last Error: {connection_info.last_error}")
        
        return " | ".join(stats)
