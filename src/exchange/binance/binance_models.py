"""
Binance Data Models

Data models for Binance exchange operations.
Following Clean Code principles with clear, focused models.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal


@dataclass
class BinanceOrder:
    """Data model for Binance order information."""

    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "NEW"
    executed_qty: float = 0.0
    avg_price: float = 0.0
    client_order_id: Optional[str] = None
    time: Optional[int] = None
    update_time: Optional[int] = None
    reduce_only: bool = False
    close_position: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'orderId': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'type': self.order_type,
            'origQty': self.quantity,
            'price': self.price,
            'stopPrice': self.stop_price,
            'status': self.status,
            'executedQty': self.executed_qty,
            'avgPrice': self.avg_price,
            'clientOrderId': self.client_order_id,
            'time': self.time,
            'updateTime': self.update_time,
            'reduceOnly': self.reduce_only,
            'closePosition': self.close_position
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinanceOrder':
        """Create from dictionary representation."""
        return cls(
            order_id=str(data.get('orderId', '')),
            symbol=data.get('symbol', ''),
            side=data.get('side', ''),
            order_type=data.get('type', ''),
            quantity=float(data.get('origQty', 0)),
            price=float(data.get('price', 0)) if data.get('price') else None,
            stop_price=float(data.get('stopPrice', 0)) if data.get('stopPrice') else None,
            status=data.get('status', 'NEW'),
            executed_qty=float(data.get('executedQty', 0)),
            avg_price=float(data.get('avgPrice', 0)),
            client_order_id=data.get('clientOrderId'),
            time=data.get('time'),
            update_time=data.get('updateTime'),
            reduce_only=data.get('reduceOnly', False),
            close_position=data.get('closePosition', False)
        )


@dataclass
class BinancePosition:
    """Data model for Binance position information."""

    symbol: str
    position_amt: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    liquidation_price: float
    leverage: int
    margin_type: str
    isolated_margin: float = 0.0
    is_auto_add_margin: bool = False
    position_side: str = "BOTH"
    notional: float = 0.0
    isolated_wallet: float = 0.0
    update_time: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'symbol': self.symbol,
            'positionAmt': self.position_amt,
            'entryPrice': self.entry_price,
            'markPrice': self.mark_price,
            'unRealizedProfit': self.unrealized_pnl,
            'liquidationPrice': self.liquidation_price,
            'leverage': self.leverage,
            'marginType': self.margin_type,
            'isolatedMargin': self.isolated_margin,
            'isAutoAddMargin': self.is_auto_add_margin,
            'positionSide': self.position_side,
            'notional': self.notional,
            'isolatedWallet': self.isolated_wallet,
            'updateTime': self.update_time
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinancePosition':
        """Create from dictionary representation."""
        return cls(
            symbol=data.get('symbol', ''),
            position_amt=float(data.get('positionAmt', 0)),
            entry_price=float(data.get('entryPrice', 0)),
            mark_price=float(data.get('markPrice', 0)),
            unrealized_pnl=float(data.get('unRealizedProfit', 0)),
            liquidation_price=float(data.get('liquidationPrice', 0)),
            leverage=int(data.get('leverage', 1)),
            margin_type=data.get('marginType', 'isolated'),
            isolated_margin=float(data.get('isolatedMargin', 0)),
            is_auto_add_margin=data.get('isAutoAddMargin', False),
            position_side=data.get('positionSide', 'BOTH'),
            notional=float(data.get('notional', 0)),
            isolated_wallet=float(data.get('isolatedWallet', 0)),
            update_time=data.get('updateTime')
        )


@dataclass
class BinanceBalance:
    """Data model for Binance balance information."""

    asset: str
    wallet_balance: float
    unrealized_pnl: float
    margin_balance: float
    maint_margin: float
    initial_margin: float
    position_initial_margin: float
    open_order_initial_margin: float
    max_withdraw_amount: float
    cross_wallet_balance: float
    cross_un_pnl: float
    available_balance: float
    margin_available: bool = True
    update_time: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'asset': self.asset,
            'walletBalance': self.wallet_balance,
            'unrealizedProfit': self.unrealized_pnl,
            'marginBalance': self.margin_balance,
            'maintMargin': self.maint_margin,
            'initialMargin': self.initial_margin,
            'positionInitialMargin': self.position_initial_margin,
            'openOrderInitialMargin': self.open_order_initial_margin,
            'maxWithdrawAmount': self.max_withdraw_amount,
            'crossWalletBalance': self.cross_wallet_balance,
            'crossUnPnl': self.cross_un_pnl,
            'availableBalance': self.available_balance,
            'marginAvailable': self.margin_available,
            'updateTime': self.update_time
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinanceBalance':
        """Create from dictionary representation."""
        return cls(
            asset=data.get('asset', ''),
            wallet_balance=float(data.get('walletBalance', 0)),
            unrealized_pnl=float(data.get('unrealizedProfit', 0)),
            margin_balance=float(data.get('marginBalance', 0)),
            maint_margin=float(data.get('maintMargin', 0)),
            initial_margin=float(data.get('initialMargin', 0)),
            position_initial_margin=float(data.get('positionInitialMargin', 0)),
            open_order_initial_margin=float(data.get('openOrderInitialMargin', 0)),
            max_withdraw_amount=float(data.get('maxWithdrawAmount', 0)),
            cross_wallet_balance=float(data.get('crossWalletBalance', 0)),
            cross_un_pnl=float(data.get('crossUnPnl', 0)),
            available_balance=float(data.get('availableBalance', 0)),
            margin_available=data.get('marginAvailable', True),
            update_time=data.get('updateTime')
        )


@dataclass
class BinanceTrade:
    """Data model for Binance trade information."""

    trade_id: str
    symbol: str
    order_id: str
    price: float
    quantity: float
    commission: float
    commission_asset: str
    time: int
    is_buyer: bool
    is_maker: bool
    is_best_match: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'id': self.trade_id,
            'symbol': self.symbol,
            'orderId': self.order_id,
            'price': self.price,
            'qty': self.quantity,
            'commission': self.commission,
            'commissionAsset': self.commission_asset,
            'time': self.time,
            'isBuyer': self.is_buyer,
            'isMaker': self.is_maker,
            'isBestMatch': self.is_best_match
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinanceTrade':
        """Create from dictionary representation."""
        return cls(
            trade_id=str(data.get('id', '')),
            symbol=data.get('symbol', ''),
            order_id=str(data.get('orderId', '')),
            price=float(data.get('price', 0)),
            quantity=float(data.get('qty', 0)),
            commission=float(data.get('commission', 0)),
            commission_asset=data.get('commissionAsset', ''),
            time=int(data.get('time', 0)),
            is_buyer=data.get('isBuyer', False),
            is_maker=data.get('isMaker', False),
            is_best_match=data.get('isBestMatch', False)
        )


@dataclass
class BinanceIncome:
    """Data model for Binance income information."""

    symbol: str
    income_type: str
    income: float
    asset: str
    time: int
    info: str
    trade_id: Optional[str] = None
    tran_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'symbol': self.symbol,
            'incomeType': self.income_type,
            'income': self.income,
            'asset': self.asset,
            'time': self.time,
            'info': self.info,
            'tradeId': self.trade_id,
            'tranId': self.tran_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinanceIncome':
        """Create from dictionary representation."""
        return cls(
            symbol=data.get('symbol', ''),
            income_type=data.get('incomeType', ''),
            income=float(data.get('income', 0)),
            asset=data.get('asset', ''),
            time=int(data.get('time', 0)),
            info=data.get('info', ''),
            trade_id=data.get('tradeId'),
            tran_id=data.get('tranId')
        )
