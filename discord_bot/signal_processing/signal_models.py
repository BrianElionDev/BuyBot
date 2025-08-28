"""
Discord Signal Data Models

This module contains data models and structures for Discord trading signals.
"""

from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ParsedSignal:
    """Data model for parsed trading signals."""
    coin_symbol: str
    position_type: str  # 'LONG' or 'SHORT'
    entry_prices: List[float]
    stop_loss: Optional[Union[float, str]] = None
    take_profits: Optional[List[float]] = None
    order_type: str = 'LIMIT'  # 'LIMIT', 'MARKET', 'SPOT'
    risk_level: Optional[str] = None
    quantity_multiplier: Optional[int] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'coin_symbol': self.coin_symbol,
            'position_type': self.position_type,
            'entry_prices': self.entry_prices,
            'stop_loss': self.stop_loss,
            'take_profits': self.take_profits,
            'order_type': self.order_type,
            'risk_level': self.risk_level,
            'quantity_multiplier': self.quantity_multiplier,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParsedSignal':
        """Create from dictionary representation."""
        timestamp = None
        if data.get('timestamp'):
            if isinstance(data['timestamp'], str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], datetime):
                timestamp = data['timestamp']

        return cls(
            coin_symbol=data['coin_symbol'],
            position_type=data['position_type'],
            entry_prices=data['entry_prices'],
            stop_loss=data.get('stop_loss'),
            take_profits=data.get('take_profits'),
            order_type=data.get('order_type', 'LIMIT'),
            risk_level=data.get('risk_level'),
            quantity_multiplier=data.get('quantity_multiplier'),
            timestamp=timestamp
        )


@dataclass
class AlertAction:
    """Data model for alert actions."""
    action_type: str
    coin_symbol: Optional[str] = None
    content: Optional[str] = None
    action_description: Optional[str] = None
    binance_action: Optional[str] = None
    position_status: Optional[str] = None
    reason: Optional[str] = None
    leverage: Optional[int] = None
    trailing_percentage: Optional[float] = None
    stop_loss_price: Optional[float] = None
    entry_price: Optional[float] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'action_type': self.action_type,
            'coin_symbol': self.coin_symbol,
            'content': self.content,
            'action_description': self.action_description,
            'binance_action': self.binance_action,
            'position_status': self.position_status,
            'reason': self.reason,
            'leverage': self.leverage,
            'trailing_percentage': self.trailing_percentage,
            'stop_loss_price': self.stop_loss_price,
            'entry_price': self.entry_price,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertAction':
        """Create from dictionary representation."""
        timestamp = None
        if data.get('timestamp'):
            if isinstance(data['timestamp'], str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], datetime):
                timestamp = data['timestamp']

        return cls(
            action_type=data['action_type'],
            coin_symbol=data.get('coin_symbol'),
            content=data.get('content'),
            action_description=data.get('action_description'),
            binance_action=data.get('binance_action'),
            position_status=data.get('position_status'),
            reason=data.get('reason'),
            leverage=data.get('leverage'),
            trailing_percentage=data.get('trailing_percentage'),
            stop_loss_price=data.get('stop_loss_price'),
            entry_price=data.get('entry_price'),
            timestamp=timestamp
        )


@dataclass
class SignalValidationResult:
    """Data model for signal validation results."""
    is_valid: bool
    error_message: Optional[str] = None
    warnings: List[str] = None
    parsed_signal: Optional[ParsedSignal] = None

    def __post_init__(self):
        """Initialize warnings list if not provided."""
        if self.warnings is None:
            self.warnings = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'is_valid': self.is_valid,
            'error_message': self.error_message,
            'warnings': self.warnings,
            'parsed_signal': self.parsed_signal.to_dict() if self.parsed_signal else None
        }


@dataclass
class SignalProcessingResult:
    """Data model for signal processing results."""
    success: bool
    parsed_signal: Optional[ParsedSignal] = None
    alert_action: Optional[AlertAction] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'success': self.success,
            'parsed_signal': self.parsed_signal.to_dict() if self.parsed_signal else None,
            'alert_action': self.alert_action.to_dict() if self.alert_action else None,
            'error_message': self.error_message,
            'processing_time': self.processing_time,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


# Constants for signal processing
SUPPORTED_ORDER_TYPES = ['LIMIT', 'MARKET', 'SPOT']
SUPPORTED_POSITION_TYPES = ['LONG', 'SHORT']
SUPPORTED_ACTION_TYPES = [
    'liquidation', 'partial_fill', 'tp1_and_sl_to_be', 'stop_loss_hit',
    'leverage_update', 'trailing_stop_loss', 'position_size_adjustment',
    'stop_loss_update', 'stops_to_be', 'stops_to_price', 'dca_to_entry',
    'unknown'
]
