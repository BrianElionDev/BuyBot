"""
KuCoin user data handler for processing order execution and lifecycle events.
Handles order matches, fills, cancellations, and status changes.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from .kucoin_handler_models import KucoinExecutionReport, KucoinOrderChange
from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter

logger = logging.getLogger(__name__)

class KucoinUserDataHandler:
    """
    Handles KuCoin user data events from WebSocket streams.
    """

    def __init__(self):
        """Initialize user data handler."""
        self.execution_history: list[KucoinExecutionReport] = []
        self.order_change_history: list[KucoinOrderChange] = []

    async def handle_execution_report(self, event_data: Dict[str, Any]) -> Optional[KucoinExecutionReport]:
        """
        Handle order execution events (order.match).

        Args:
            event_data: Raw execution event data from WebSocket

        Returns:
            Optional[KucoinExecutionReport]: Processed execution report
        """
        try:
            data = event_data.get('data', {})
            if not data:
                logger.warning("[KC-Handler] No data in execution event")
                return None

            order_id = str(data.get('orderId', ''))
            symbol = data.get('symbol', '')
            side = data.get('side', '').lower()
            order_type = data.get('orderType', '')
            match_price = float(data.get('matchPrice', 0))
            match_size = float(data.get('matchSize', 0))
            trade_time = int(data.get('tradeTime', 0))
            fee = float(data.get('fee', 0))
            fee_currency = data.get('feeCurrency', 'USDT')

            execution_report = KucoinExecutionReport(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                match_price=match_price,
                match_size=match_size,
                trade_time=trade_time,
                fee=fee,
                fee_currency=fee_currency,
                raw_data=data
            )

            self.execution_history.append(execution_report)

            if len(self.execution_history) > 1000:
                self.execution_history = self.execution_history[-1000:]

            logger.info(f"[KC-Handler] Execution: {symbol} {order_id} - {side} {match_size} @ {match_price}")

            return execution_report

        except Exception as e:
            logger.error(f"[KC-Handler] Error processing execution report: {e}")
            return None

    async def handle_order_change(self, event_data: Dict[str, Any]) -> Optional[KucoinOrderChange]:
        """
        Handle order lifecycle events (order.change).

        Args:
            event_data: Raw order change event data from WebSocket

        Returns:
            Optional[KucoinOrderChange]: Processed order change
        """
        try:
            data = event_data.get('data', {})
            if not data:
                logger.warning("[KC-Handler] No data in order change event")
                return None

            order_id = str(data.get('orderId', ''))
            symbol = data.get('symbol', '')
            change_type = data.get('type', '').lower()
            status = data.get('status', '').lower()
            filled_size = float(data.get('filledSize', 0))
            old_size = float(data.get('oldSize', 0))
            order_type = data.get('orderType', '')
            side = data.get('side', '').lower()
            price = data.get('price')
            if price:
                price = float(price)

            order_change = KucoinOrderChange(
                order_id=order_id,
                symbol=symbol,
                change_type=change_type,
                status=status,
                filled_size=filled_size,
                old_size=old_size,
                order_type=order_type,
                side=side,
                price=price,
                raw_data=data
            )

            self.order_change_history.append(order_change)

            if len(self.order_change_history) > 1000:
                self.order_change_history = self.order_change_history[-1000:]

            logger.info(f"[KC-Handler] Order Change: {symbol} {order_id} - {change_type} ({status})")

            return order_change

        except Exception as e:
            logger.error(f"[KC-Handler] Error processing order change: {e}")
            return None

    def convert_symbol_to_bot_format(self, kucoin_symbol: str) -> str:
        """
        Convert KuCoin symbol to bot format (XBTUSDTM -> BTCUSDT).

        Args:
            kucoin_symbol: KuCoin symbol format

        Returns:
            Bot symbol format
        """
        try:
            return symbol_converter.convert_kucoin_to_bot(kucoin_symbol)
        except Exception as e:
            logger.error(f"[KC-Handler] Error converting symbol {kucoin_symbol}: {e}")
            return kucoin_symbol

    def map_kucoin_status_to_internal(self, kucoin_status: str) -> tuple[str, str]:
        """
        Map KuCoin order status to internal order_status and position status.

        Args:
            kucoin_status: KuCoin status (filled, canceled, open, match)

        Returns:
            Tuple of (order_status, position_status)
        """
        status_lower = kucoin_status.lower()

        if status_lower == 'filled':
            return ('FILLED', 'CLOSED')
        elif status_lower == 'canceled':
            return ('CANCELED', 'FAILED')
        elif status_lower == 'open':
            return ('NEW', 'PENDING')
        elif status_lower == 'match':
            return ('PARTIALLY_FILLED', 'ACTIVE')
        else:
            return ('UNKNOWN', 'PENDING')

    def get_execution_history(self, symbol: Optional[str] = None, limit: int = 100) -> list[KucoinExecutionReport]:
        """
        Get execution history.

        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of records to return

        Returns:
            List of execution reports
        """
        history = self.execution_history

        if symbol:
            history = [report for report in history if report.symbol == symbol]

        return history[-limit:]

    def get_order_change_history(self, symbol: Optional[str] = None, limit: int = 100) -> list[KucoinOrderChange]:
        """
        Get order change history.

        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of records to return

        Returns:
            List of order changes
        """
        history = self.order_change_history

        if symbol:
            history = [change for change in history if change.symbol == symbol]

        return history[-limit:]

    def get_latest_execution_report(self, order_id: str) -> Optional[KucoinExecutionReport]:
        """
        Get the latest execution report for a specific order.

        Args:
            order_id: Order ID

        Returns:
            Optional[KucoinExecutionReport]: Latest execution report or None
        """
        for report in reversed(self.execution_history):
            if report.order_id == order_id:
                return report
        return None

    def clear_history(self, history_type: Optional[str] = None):
        """
        Clear history data.

        Args:
            history_type: Type of history to clear ('execution', 'orderChange', or None for all)
        """
        if history_type == 'execution' or history_type is None:
            self.execution_history.clear()
        if history_type == 'orderChange' or history_type is None:
            self.order_change_history.clear()

        logger.info(f"[KC-Handler] Cleared {history_type or 'all'} history")
