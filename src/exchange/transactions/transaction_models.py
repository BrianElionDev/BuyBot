"""
Transaction Data Models

Data models for transaction management.
Following Clean Code principles with clear, focused models.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class TransactionType(Enum):
    """Transaction types."""
    ORDER = "ORDER"
    POSITION = "POSITION"
    BALANCE = "BALANCE"
    FEE = "FEE"
    FUNDING = "FUNDING"


class OrderStatus(Enum):
    """Order status values."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class PositionStatus(Enum):
    """Position status values."""
    NONE = "NONE"
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"


@dataclass
class Transaction:
    """Data model for transaction information."""

    transaction_id: str
    transaction_type: TransactionType
    symbol: str
    amount: float
    price: float
    timestamp: datetime
    status: str
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    fee: float = 0.0
    fee_asset: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'transaction_id': self.transaction_id,
            'transaction_type': self.transaction_type.value,
            'symbol': self.symbol,
            'amount': self.amount,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'exchange_order_id': self.exchange_order_id,
            'client_order_id': self.client_order_id,
            'fee': self.fee,
            'fee_asset': self.fee_asset,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create from dictionary representation."""
        timestamp = datetime.fromisoformat(data['timestamp']) if isinstance(data['timestamp'], str) else data['timestamp']

        return cls(
            transaction_id=data['transaction_id'],
            transaction_type=TransactionType(data['transaction_type']),
            symbol=data['symbol'],
            amount=float(data['amount']),
            price=float(data['price']),
            timestamp=timestamp,
            status=data['status'],
            exchange_order_id=data.get('exchange_order_id'),
            client_order_id=data.get('client_order_id'),
            fee=float(data.get('fee', 0)),
            fee_asset=data.get('fee_asset', ''),
            metadata=data.get('metadata', {})
        )


@dataclass
class Order:
    """Data model for order information."""

    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    status: OrderStatus
    price: Optional[float] = None
    stop_price: Optional[float] = None
    executed_quantity: float = 0.0
    average_price: float = 0.0
    client_order_id: Optional[str] = None
    time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    reduce_only: bool = False
    close_position: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': self.quantity,
            'price': self.price,
            'stop_price': self.stop_price,
            'status': self.status.value,
            'executed_quantity': self.executed_quantity,
            'average_price': self.average_price,
            'client_order_id': self.client_order_id,
            'time': self.time.isoformat() if self.time else None,
            'update_time': self.update_time.isoformat() if self.update_time else None,
            'reduce_only': self.reduce_only,
            'close_position': self.close_position
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """Create from dictionary representation."""
        time = None
        if data.get('time'):
            time = datetime.fromisoformat(data['time']) if isinstance(data['time'], str) else data['time']

        update_time = None
        if data.get('update_time'):
            update_time = datetime.fromisoformat(data['update_time']) if isinstance(data['update_time'], str) else data['update_time']

        return cls(
            order_id=data['order_id'],
            symbol=data['symbol'],
            side=data['side'],
            order_type=data['order_type'],
            quantity=float(data['quantity']),
            price=float(data['price']) if data.get('price') else None,
            stop_price=float(data['stop_price']) if data.get('stop_price') else None,
            status=OrderStatus(data['status']),
            executed_quantity=float(data.get('executed_quantity', 0)),
            average_price=float(data.get('average_price', 0)),
            client_order_id=data.get('client_order_id'),
            time=time,
            update_time=update_time,
            reduce_only=data.get('reduce_only', False),
            close_position=data.get('close_position', False)
        )


@dataclass
class Position:
    """Data model for position information."""

    symbol: str
    position_amount: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    liquidation_price: float
    leverage: int
    margin_type: str
    status: PositionStatus
    isolated_margin: float = 0.0
    is_auto_add_margin: bool = False
    position_side: str = "BOTH"
    notional: float = 0.0
    isolated_wallet: float = 0.0
    update_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'symbol': self.symbol,
            'position_amount': self.position_amount,
            'entry_price': self.entry_price,
            'mark_price': self.mark_price,
            'unrealized_pnl': self.unrealized_pnl,
            'liquidation_price': self.liquidation_price,
            'leverage': self.leverage,
            'margin_type': self.margin_type,
            'status': self.status.value,
            'isolated_margin': self.isolated_margin,
            'is_auto_add_margin': self.is_auto_add_margin,
            'position_side': self.position_side,
            'notional': self.notional,
            'isolated_wallet': self.isolated_wallet,
            'update_time': self.update_time.isoformat() if self.update_time else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create from dictionary representation."""
        update_time = None
        if data.get('update_time'):
            update_time = datetime.fromisoformat(data['update_time']) if isinstance(data['update_time'], str) else data['update_time']

        return cls(
            symbol=data['symbol'],
            position_amount=float(data['position_amount']),
            entry_price=float(data['entry_price']),
            mark_price=float(data['mark_price']),
            unrealized_pnl=float(data['unrealized_pnl']),
            liquidation_price=float(data['liquidation_price']),
            leverage=int(data['leverage']),
            margin_type=data['margin_type'],
            status=PositionStatus(data['status']),
            isolated_margin=float(data.get('isolated_margin', 0)),
            is_auto_add_margin=data.get('is_auto_add_margin', False),
            position_side=data.get('position_side', 'BOTH'),
            notional=float(data.get('notional', 0)),
            isolated_wallet=float(data.get('isolated_wallet', 0)),
            update_time=update_time
        )
