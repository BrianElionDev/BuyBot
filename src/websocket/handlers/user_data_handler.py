"""
User data handler for processing user account-related WebSocket events.
Handles execution reports, balance updates, and account position changes.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .handler_models import ExecutionReport, BalanceUpdate, AccountPosition

logger = logging.getLogger(__name__)

class UserDataHandler:
    """
    Handles user data events from WebSocket streams.
    """

    def __init__(self):
        """Initialize user data handler."""
        self.execution_history: List[ExecutionReport] = []
        self.balance_updates: List[BalanceUpdate] = []
        self.account_positions: List[AccountPosition] = []

    async def handle_execution_report(self, event_data: Dict[str, Any]) -> Optional[ExecutionReport]:
        """
        Handle execution report events.

        Args:
            event_data: Raw execution report data

        Returns:
            Optional[ExecutionReport]: Processed execution report
        """
        try:
            # Handle both direct execution reports and ORDER_TRADE_UPDATE events
            if 'o' in event_data:
                order_data = event_data['o']
                logger.info(f"Processing ORDER_TRADE_UPDATE event: {order_data}")
            else:
                order_data = event_data
                logger.info(f"Processing direct execution report: {order_data}")

            order_id = order_data.get('i')  # Binance order ID
            symbol = order_data.get('s')    # Symbol
            status = order_data.get('X')    # Order status
            executed_qty = float(order_data.get('z', 0))  # Cumulative filled quantity
            avg_price = float(order_data.get('ap', 0))    # Average fill price
            realized_pnl = float(order_data.get('Y', 0))  # Realized PnL
            side = order_data.get('S')      # Side (BUY/SELL)
            order_type = order_data.get('o')  # Order type
            time = datetime.fromtimestamp(order_data.get('T', 0) / 1000)
            update_time = datetime.fromtimestamp(order_data.get('T', 0) / 1000)

            execution_report = ExecutionReport(
                order_id=str(order_id),
                symbol=symbol if symbol is not None else "",
                status=status if status is not None else "",
                executed_qty=executed_qty,
                avg_price=avg_price,
                realized_pnl=realized_pnl,
                side=side if side is not None else "",
                order_type=order_type if order_type is not None else "",
                time=time,
                update_time=update_time
            )

            # Store in history
            self.execution_history.append(execution_report)

            # Keep only last 1000 execution reports
            if len(self.execution_history) > 1000:
                self.execution_history = self.execution_history[-1000:]

            logger.info(f"Execution Report: {symbol} {order_id} - {status} - Qty: {executed_qty} - Price: {avg_price}")

            if status == 'FILLED' and executed_qty > 0:
                try:
                    import asyncio
                    from src.services.notifications.trade_notification_service import (
                        trade_notification_service, OrderFillData, StopLossData, TakeProfitData
                    )

                    position_type = 'LONG' if side == 'BUY' else 'SHORT'

                    order_type = order_data.get('o', '').upper()

                    if order_type == 'STOP_MARKET':
                        realized_pnl = realized_pnl if realized_pnl != 0 else 0.0

                        stop_loss_data = StopLossData(
                            symbol=symbol,
                            position_type=position_type,
                            entry_price=0.0,
                            stop_loss_price=avg_price,
                            quantity=executed_qty,
                            realized_pnl=realized_pnl,
                            timestamp=time
                        )

                        asyncio.create_task(trade_notification_service.notify_stop_loss_triggered(stop_loss_data))

                    elif order_type == 'TAKE_PROFIT_MARKET':
                        realized_pnl = realized_pnl if realized_pnl != 0 else 0.0

                        take_profit_data = TakeProfitData(
                            symbol=symbol,
                            position_type=position_type,
                            entry_price=0.0,
                            take_profit_price=avg_price,
                            quantity=executed_qty,
                            realized_pnl=realized_pnl,
                            timestamp=time
                        )

                        asyncio.create_task(trade_notification_service.notify_take_profit_triggered(take_profit_data))

                    else:
                        notification_data = OrderFillData(
                            symbol=symbol,
                            position_type=position_type,
                            fill_price=avg_price,
                            fill_quantity=executed_qty,
                            order_id=str(order_id),
                            timestamp=time
                        )

                        asyncio.create_task(trade_notification_service.notify_order_fill(notification_data))

                except Exception as e:
                    logger.error(f"Failed to send order fill notification: {e}")

            return execution_report

        except Exception as e:
            logger.error(f"Error processing execution report: {e}")
            return None

    async def handle_balance_update(self, event_data: Dict[str, Any]) -> Optional[BalanceUpdate]:
        """
        Handle balance update events.

        Args:
            event_data: Raw balance update data

        Returns:
            Optional[BalanceUpdate]: Processed balance update
        """
        try:
            asset = event_data.get('a')  # Asset
            balance_delta = float(event_data.get('d', 0))  # Balance delta
            event_time = datetime.fromtimestamp(event_data.get('E', 0) / 1000)
            clear_time = datetime.fromtimestamp(event_data.get('T', 0) / 1000)

            balance_update = BalanceUpdate(
                asset=asset if asset is not None else "",
                balance_delta=balance_delta,
                event_time=event_time,
                clear_time=clear_time
            )

            # Store in history
            self.balance_updates.append(balance_update)

            # Keep only last 1000 balance updates
            if len(self.balance_updates) > 1000:
                self.balance_updates = self.balance_updates[-1000:]

            logger.info(f"Balance Update: {asset} - Delta: {balance_delta}")
            return balance_update

        except Exception as e:
            logger.error(f"Error processing balance update: {e}")
            return None

    async def handle_account_position(self, event_data: Dict[str, Any]) -> Optional[AccountPosition]:
        """
        Handle account position events.

        Args:
            event_data: Raw account position data

        Returns:
            Optional[AccountPosition]: Processed account position
        """
        try:
            positions = event_data.get('P', [])  # Positions
            event_time = datetime.fromtimestamp(event_data.get('E', 0) / 1000)

            account_position = AccountPosition(
                positions=positions,
                event_time=event_time
            )

            # Store in history
            self.account_positions.append(account_position)

            # Keep only last 1000 position updates
            if len(self.account_positions) > 1000:
                self.account_positions = self.account_positions[-1000:]

            logger.info(f"Account Position Update: {len(positions)} positions")
            return account_position

        except Exception as e:
            logger.error(f"Error processing account position: {e}")
            return None

    def get_execution_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[ExecutionReport]:
        """
        Get execution history.

        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of records to return

        Returns:
            List[ExecutionReport]: Execution history
        """
        history = self.execution_history

        if symbol:
            history = [report for report in history if report.symbol == symbol]

        return history[-limit:]

    def get_balance_updates(self, asset: Optional[str] = None, limit: int = 100) -> List[BalanceUpdate]:
        """
        Get balance update history.

        Args:
            asset: Filter by asset (optional)
            limit: Maximum number of records to return

        Returns:
            List[BalanceUpdate]: Balance update history
        """
        updates = self.balance_updates

        if asset:
            updates = [update for update in updates if update.asset == asset]

        return updates[-limit:]

    def get_account_positions(self, limit: int = 100) -> List[AccountPosition]:
        """
        Get account position history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List[AccountPosition]: Account position history
        """
        return self.account_positions[-limit:]

    def get_latest_execution_report(self, order_id: str) -> Optional[ExecutionReport]:
        """
        Get the latest execution report for a specific order.

        Args:
            order_id: Order ID

        Returns:
            Optional[ExecutionReport]: Latest execution report or None
        """
        for report in reversed(self.execution_history):
            if report.order_id == order_id:
                return report
        return None

    def clear_history(self, history_type: Optional[str] = None):
        """
        Clear history data.

        Args:
            history_type: Type of history to clear ('execution', 'balance', 'position', or None for all)
        """
        if history_type == 'execution' or history_type is None:
            self.execution_history.clear()
        if history_type == 'balance' or history_type is None:
            self.balance_updates.clear()
        if history_type == 'position' or history_type is None:
            self.account_positions.clear()

        logger.info(f"Cleared {history_type or 'all'} history")
