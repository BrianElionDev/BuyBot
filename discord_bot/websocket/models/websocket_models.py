"""
WebSocket Data Models

Defines the data structures for WebSocket events and status in the Discord bot.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum


class WebSocketEventType(Enum):
    """Types of WebSocket events."""
    TRADE_CREATED = "trade_created"
    TRADE_UPDATED = "trade_updated"
    ALERT_CREATED = "alert_created"
    ALERT_UPDATED = "alert_updated"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    ERROR = "error"
    CONNECTION_STATUS = "connection_status"


class WebSocketStatus(Enum):
    """WebSocket connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class WebSocketEvent:
    """Data model for WebSocket events."""
    
    event_type: WebSocketEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    source: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'error_message': self.error_message,
            'source': self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebSocketEvent':
        """Create from dictionary representation."""
        # Parse timestamp
        timestamp = datetime.now(timezone.utc)
        if data.get('timestamp'):
            if isinstance(data['timestamp'], str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], datetime):
                timestamp = data['timestamp']
        
        # Parse event type
        event_type = WebSocketEventType.ERROR
        if data.get('event_type'):
            try:
                event_type = WebSocketEventType(data['event_type'])
            except ValueError:
                event_type = WebSocketEventType.ERROR
        
        return cls(
            event_type=event_type,
            timestamp=timestamp,
            data=data.get('data'),
            error_message=data.get('error_message'),
            source=data.get('source')
        )


@dataclass
class WebSocketConnectionInfo:
    """Information about WebSocket connection."""
    
    status: WebSocketStatus = WebSocketStatus.DISCONNECTED
    connected_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 1.0
    error_count: int = 0
    last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'status': self.status.value,
            'connected_at': self.connected_at.isoformat() if self.connected_at else None,
            'disconnected_at': self.disconnected_at.isoformat() if self.disconnected_at else None,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'reconnect_attempts': self.reconnect_attempts,
            'max_reconnect_attempts': self.max_reconnect_attempts,
            'reconnect_delay': self.reconnect_delay,
            'error_count': self.error_count,
            'last_error': self.last_error
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebSocketConnectionInfo':
        """Create from dictionary representation."""
        # Parse timestamps
        connected_at = None
        if data.get('connected_at'):
            if isinstance(data['connected_at'], str):
                connected_at = datetime.fromisoformat(data['connected_at'].replace('Z', '+00:00'))
            elif isinstance(data['connected_at'], datetime):
                connected_at = data['connected_at']
        
        disconnected_at = None
        if data.get('disconnected_at'):
            if isinstance(data['disconnected_at'], str):
                disconnected_at = datetime.fromisoformat(data['disconnected_at'].replace('Z', '+00:00'))
            elif isinstance(data['disconnected_at'], datetime):
                disconnected_at = data['disconnected_at']
        
        last_heartbeat = None
        if data.get('last_heartbeat'):
            if isinstance(data['last_heartbeat'], str):
                last_heartbeat = datetime.fromisoformat(data['last_heartbeat'].replace('Z', '+00:00'))
            elif isinstance(data['last_heartbeat'], datetime):
                last_heartbeat = data['last_heartbeat']
        
        # Parse status
        status = WebSocketStatus.DISCONNECTED
        if data.get('status'):
            try:
                status = WebSocketStatus(data['status'])
            except ValueError:
                status = WebSocketStatus.DISCONNECTED
        
        return cls(
            status=status,
            connected_at=connected_at,
            disconnected_at=disconnected_at,
            last_heartbeat=last_heartbeat,
            reconnect_attempts=data.get('reconnect_attempts', 0),
            max_reconnect_attempts=data.get('max_reconnect_attempts', 5),
            reconnect_delay=data.get('reconnect_delay', 1.0),
            error_count=data.get('error_count', 0),
            last_error=data.get('last_error')
        )
