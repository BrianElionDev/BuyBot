"""
Trade and Alert Data Models

Defines the data structures for trades and alerts in the Discord bot.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import json


@dataclass
class TradeModel:
    """Data model for trade records."""

    id: Optional[int] = None
    discord_id: Optional[str] = None
    trader: Optional[str] = None
    timestamp: Optional[datetime] = None
    content: Optional[str] = None
    parsed_signal: Optional[Dict[str, Any]] = None
    coin_symbol: Optional[str] = None
    signal_type: Optional[str] = None
    position_size: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    status: Optional[str] = None
    order_status: Optional[str] = None
    exchange_response: Optional[Dict[str, Any]] = None
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'id': self.id,
            'discord_id': self.discord_id,
            'trader': self.trader,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'content': self.content,
            'parsed_signal': json.dumps(self.parsed_signal) if self.parsed_signal else None,
            'coin_symbol': self.coin_symbol,
            'signal_type': self.signal_type,
            'position_size': self.position_size,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'pnl_usd': self.pnl_usd,
            'status': self.status,
            'order_status': self.order_status,
            'exchange_response': json.dumps(self.exchange_response) if self.exchange_response else None,
            'stop_loss_order_id': self.stop_loss_order_id,
            'take_profit_order_id': self.take_profit_order_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradeModel':
        """Create from dictionary representation."""
        # Parse timestamps
        timestamp = None
        if data.get('timestamp'):
            if isinstance(data['timestamp'], str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], datetime):
                timestamp = data['timestamp']

        created_at = None
        if data.get('created_at'):
            if isinstance(data['created_at'], str):
                created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            elif isinstance(data['created_at'], datetime):
                created_at = data['created_at']

        updated_at = None
        if data.get('updated_at'):
            if isinstance(data['updated_at'], str):
                updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
            elif isinstance(data['updated_at'], datetime):
                updated_at = data['updated_at']

        closed_at = None
        if data.get('closed_at'):
            if isinstance(data['closed_at'], str):
                closed_at = datetime.fromisoformat(data['closed_at'].replace('Z', '+00:00'))
            elif isinstance(data['closed_at'], datetime):
                closed_at = data['closed_at']

        # Parse JSON fields
        parsed_signal = None
        if data.get('parsed_signal'):
            if isinstance(data['parsed_signal'], str):
                parsed_signal = json.loads(data['parsed_signal'])
            else:
                parsed_signal = data['parsed_signal']

        exchange_response = None
        raw_resp = data.get('exchange_response') or data.get('binance_response') or data.get('kucoin_response')
        if raw_resp is not None:
            if isinstance(raw_resp, str):
                try:
                    exchange_response = json.loads(raw_resp)
                except Exception:
                    exchange_response = raw_resp
            else:
                exchange_response = raw_resp

        return cls(
            id=data.get('id'),
            discord_id=data.get('discord_id'),
            trader=data.get('trader'),
            timestamp=timestamp,
            content=data.get('content'),
            parsed_signal=parsed_signal,
            coin_symbol=data.get('coin_symbol'),
            signal_type=data.get('signal_type'),
            position_size=data.get('position_size'),
            entry_price=data.get('entry_price'),
            exit_price=data.get('exit_price'),
            pnl_usd=data.get('pnl_usd'),
            status=data.get('status'),
            order_status=data.get('order_status'),
            exchange_response=exchange_response,
            stop_loss_order_id=data.get('stop_loss_order_id'),
            take_profit_order_id=data.get('take_profit_order_id'),
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at
        )


@dataclass
class AlertModel:
    """Data model for alert records."""

    id: Optional[int] = None
    discord_id: Optional[str] = None
    trade: Optional[str] = None
    content: Optional[str] = None
    trader: Optional[str] = None
    timestamp: Optional[datetime] = None
    parsed_alert: Optional[Dict[str, Any]] = None
    exchange_response: Optional[Dict[str, Any]] = None
    exchange: Optional[str] = None
    status: Optional[str] = None
    alert_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'id': self.id,
            'discord_id': self.discord_id,
            'trade': self.trade,
            'content': self.content,
            'trader': self.trader,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'parsed_alert': json.dumps(self.parsed_alert) if self.parsed_alert else None,
            'exchange_response': json.dumps(self.exchange_response) if self.exchange_response else None,
            'exchange': self.exchange,
            'status': self.status,
            'alert_hash': self.alert_hash,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertModel':
        """Create from dictionary representation."""
        # Parse timestamps
        timestamp = None
        if data.get('timestamp'):
            if isinstance(data['timestamp'], str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], datetime):
                timestamp = data['timestamp']

        created_at = None
        if data.get('created_at'):
            if isinstance(data['created_at'], str):
                created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            elif isinstance(data['created_at'], datetime):
                created_at = data['created_at']

        updated_at = None
        if data.get('updated_at'):
            if isinstance(data['updated_at'], str):
                updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
            elif isinstance(data['updated_at'], datetime):
                updated_at = data['updated_at']

        # Parse JSON fields
        parsed_alert = None
        if data.get('parsed_alert'):
            if isinstance(data['parsed_alert'], str):
                parsed_alert = json.loads(data['parsed_alert'])
            else:
                parsed_alert = data['parsed_alert']

        exchange_response = None
        raw_resp = data.get('exchange_response') or data.get('binance_response') or data.get('kucoin_response')
        if raw_resp is not None:
            if isinstance(raw_resp, str):
                try:
                    exchange_response = json.loads(raw_resp)
                except Exception:
                    exchange_response = raw_resp
            else:
                exchange_response = raw_resp

        return cls(
            id=data.get('id'),
            discord_id=data.get('discord_id'),
            trade=data.get('trade'),
            content=data.get('content'),
            trader=data.get('trader'),
            timestamp=timestamp,
            parsed_alert=parsed_alert,
            exchange_response=exchange_response,
            exchange=data.get('exchange'),
            status=data.get('status'),
            alert_hash=data.get('alert_hash'),
            created_at=created_at,
            updated_at=updated_at
        )
