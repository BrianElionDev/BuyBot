"""
Database synchronization for KuCoin WebSocket events.
Handles real-time synchronization between WebSocket events and database.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.websocket.sync.sync_models import TradeSyncData
from src.core.response_normalizer import normalize_exchange_response
from src.core.status_manager import StatusManager
from ..handlers.kucoin_user_data_handler import KucoinUserDataHandler

logger = logging.getLogger(__name__)

class KucoinDatabaseSync:
    """
    Handles real-time database synchronization with KuCoin WebSocket events.
    """

    def __init__(self, db_manager):
        """
        Initialize database sync.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.order_id_cache = {}
        self.processed_notifications = set()
        self.handler = KucoinUserDataHandler()

    async def handle_execution_report(self, data: Dict[str, Any]) -> Optional[TradeSyncData]:
        """
        Handle order execution events from WebSocket.
        Links KuCoin orders to database trades and updates status.

        Args:
            data: Execution report data from WebSocket

        Returns:
            Optional[TradeSyncData]: Sync data if successful
        """
        try:
            event_data = data.get('data', {}) if 'data' in data else data
            execution_report = await self.handler.handle_execution_report({'data': event_data})

            if not execution_report:
                return None

            order_id = execution_report.order_id
            symbol = execution_report.symbol
            match_price = execution_report.match_price
            match_size = execution_report.match_size

            logger.info(f"[KC-Sync] Execution: {symbol} {order_id} - Qty: {match_size} - Price: {match_price}")

            trade = await self._find_trade_by_order_id(str(order_id)) if order_id else None
            if not trade:
                logger.warning(f"[KC-Sync] Trade not found for order ID: {order_id}")
                return None

            trade_id = trade['id']
            logger.info(f"[KC-Sync] Found trade {trade_id} for order {order_id}")

            await self._update_trade_from_execution(
                trade_id, trade, execution_report, match_size, match_price
            )

            sync_data = TradeSyncData(
                trade_id=str(trade_id),
                order_id=str(order_id),
                symbol=self.handler.convert_symbol_to_bot_format(symbol),
                status='FILLED',
                executed_qty=match_size,
                avg_price=match_price,
                realized_pnl=0.0,
                sync_timestamp=datetime.now(timezone.utc)
            )

            return sync_data

        except Exception as e:
            logger.error(f"[KC-Sync] Error handling execution report: {e}")
            return None

    async def handle_order_change(self, data: Dict[str, Any]) -> Optional[TradeSyncData]:
        """
        Handle order lifecycle events from WebSocket.

        Args:
            data: Order change data from WebSocket

        Returns:
            Optional[TradeSyncData]: Sync data if successful
        """
        try:
            event_data = data.get('data', {}) if 'data' in data else data
            order_change = await self.handler.handle_order_change({'data': event_data})

            if not order_change:
                return None

            order_id = order_change.order_id
            symbol = order_change.symbol
            change_type = order_change.change_type
            status = order_change.status
            filled_size = order_change.filled_size

            logger.info(f"[KC-Sync] Order Change: {symbol} {order_id} - {change_type} ({status})")

            trade = await self._find_trade_by_order_id(str(order_id)) if order_id else None
            if not trade:
                logger.warning(f"[KC-Sync] Trade not found for order ID: {order_id}")
                return None

            trade_id = trade['id']

            order_status, position_status = self.handler.map_kucoin_status_to_internal(status)

            if change_type == 'canceled' or status == 'canceled':
                await self._update_trade_on_cancellation(trade_id, trade, order_change)
            elif change_type == 'filled' or status == 'filled':
                await self._update_trade_on_fill(trade_id, trade, order_change, filled_size)
            else:
                await self._update_trade_status(trade_id, trade, order_change, order_status, position_status)

            sync_data = TradeSyncData(
                trade_id=str(trade_id),
                order_id=str(order_id),
                symbol=self.handler.convert_symbol_to_bot_format(symbol),
                status=position_status,
                executed_qty=filled_size,
                avg_price=order_change.price or 0.0,
                realized_pnl=0.0,
                sync_timestamp=datetime.now(timezone.utc)
            )

            return sync_data

        except Exception as e:
            logger.error(f"[KC-Sync] Error handling order change: {e}")
            return None

    async def _find_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Find trade in database by KuCoin order ID.

        Args:
            order_id: KuCoin order ID

        Returns:
            Optional[Dict]: Trade data or None if not found
        """
        try:
            trade = await self.db_manager.find_trade_by_order_id(order_id)

            if trade:
                self.order_id_cache[order_id] = trade['id']

                if not trade.get('exchange_order_id'):
                    await self._update_trade_order_id(trade['id'], order_id)

                logger.info(f"[KC-Sync] Found trade {trade['id']} for order {order_id}")
                return trade
            else:
                logger.warning(f"[KC-Sync] Trade not found for order ID: {order_id}")
                return None

        except Exception as e:
            logger.error(f"[KC-Sync] Error finding trade by order ID {order_id}: {e}")
            return None

    async def _update_trade_from_execution(self, trade_id: int, trade: Dict[str, Any],
                                          execution_report, executed_qty: float, avg_price: float):
        """Update trade from execution report."""
        try:
            signal_type = str(trade.get('signal_type') or '').upper()
            side = execution_report.side.lower()
            is_exit_order = False

            if signal_type == 'LONG' and side == 'sell':
                is_exit_order = True
            elif signal_type == 'SHORT' and side == 'buy':
                is_exit_order = True

            updates: Dict[str, Any] = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(execution_report.raw_data),
                'exchange_response': json.dumps(execution_report.raw_data),
                'order_status': 'FILLED',
                'position_size': executed_qty
            }

            price_verified = bool(trade.get('price_verified')) if trade else False

            if is_exit_order:
                updates['status'] = 'CLOSED'
                if avg_price > 0 and not price_verified:
                    updates['exit_price'] = avg_price
                    updates['price_source'] = 'ws_execution'
                updates['closed_at'] = datetime.now(timezone.utc).isoformat()
            else:
                updates['status'] = 'ACTIVE'
                if avg_price > 0 and not price_verified:
                    updates['entry_price'] = avg_price
                    updates['price_source'] = 'ws_execution'

            if not trade.get('exchange_order_id'):
                updates['exchange_order_id'] = execution_report.order_id

            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"[KC-Sync] Updated trade {trade_id} from execution")

        except Exception as e:
            logger.error(f"[KC-Sync] Error updating trade from execution: {e}")

    async def _update_trade_on_fill(self, trade_id: int, trade: Dict[str, Any],
                                   order_change, filled_size: float):
        """Update trade when order is filled."""
        try:
            signal_type = str(trade.get('signal_type') or '').upper()
            side = order_change.side.lower()
            is_exit_order = False

            if signal_type == 'LONG' and side == 'sell':
                is_exit_order = True
            elif signal_type == 'SHORT' and side == 'buy':
                is_exit_order = True

            updates: Dict[str, Any] = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(order_change.raw_data),
                'exchange_response': json.dumps(order_change.raw_data),
                'order_status': 'FILLED',
                'position_size': filled_size
            }

            price_verified = bool(trade.get('price_verified')) if trade else False

            if order_change.price and order_change.price > 0:
                if is_exit_order:
                    updates['status'] = 'CLOSED'
                    if not price_verified:
                        updates['exit_price'] = order_change.price
                        updates['price_source'] = 'ws_execution'
                    updates['closed_at'] = datetime.now(timezone.utc).isoformat()
                else:
                    updates['status'] = 'ACTIVE'
                    if not price_verified:
                        updates['entry_price'] = order_change.price
                        updates['price_source'] = 'ws_execution'
            else:
                if is_exit_order:
                    updates['status'] = 'CLOSED'
                    updates['closed_at'] = datetime.now(timezone.utc).isoformat()
                else:
                    updates['status'] = 'ACTIVE'

            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"[KC-Sync] Updated trade {trade_id} on fill")

        except Exception as e:
            logger.error(f"[KC-Sync] Error updating trade on fill: {e}")

    async def _update_trade_on_cancellation(self, trade_id: int, trade: Dict[str, Any],
                                           order_change):
        """Update trade when order is canceled and send notification."""
        try:
            updates: Dict[str, Any] = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(order_change.raw_data),
                'exchange_response': json.dumps(order_change.raw_data),
                'order_status': 'CANCELED',
                'status': 'FAILED'
            }

            if not trade.get('position_size'):
                updates['position_size'] = 0.0
            if trade.get('pnl_usd') is None:
                updates['pnl_usd'] = 0.0

            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"[KC-Sync] Updated trade {trade_id} on cancellation")

                local_symbol = trade.get('coin_symbol') or self.handler.convert_symbol_to_bot_format(order_change.symbol)
                if isinstance(local_symbol, str) and local_symbol.upper().startswith('XBT'):
                    local_symbol = local_symbol.upper().replace('XBT', 'BTC', 1)

                order_id = str(trade.get('exchange_order_id') or order_change.order_id)
                notification_key = f"{order_id}_CANCELED_{local_symbol}"

                if notification_key not in self.processed_notifications:
                    from src.services.notifications.notification_manager import NotificationManager
                    from src.services.notifications.alert_deduplicator import alert_deduplicator

                    if alert_deduplicator.should_send_alert(
                        trade_id=str(trade_id),
                        error_type="ORDER_CANCELED",
                        symbol=local_symbol,
                        exchange='kucoin'
                    ):
                        notifier = NotificationManager()
                        error_msg = f"Order CANCELED for {local_symbol}"

                        context: Dict[str, Any] = {
                            "exchange": "kucoin",
                            "symbol": local_symbol,
                            "order_id": order_id,
                            "order_type": order_change.order_type,
                            "requested_price": order_change.price or 0,
                            "filled_qty": order_change.filled_size,
                        }

                        await notifier.send_error_notification(
                            error_type="ORDER_CANCELED",
                            error_message=error_msg,
                            context=context
                        )
                        logger.info(f"[KC-Sync] Sent cancellation notification for {notification_key}")

                    self.processed_notifications.add(notification_key)
                    if len(self.processed_notifications) > 1000:
                        old_entries = list(self.processed_notifications)[:200]
                        self.processed_notifications = self.processed_notifications - set(old_entries)

        except Exception as e:
            logger.error(f"[KC-Sync] Error updating trade on cancellation: {e}")

    async def _update_trade_status(self, trade_id: int, trade: Dict[str, Any],
                                  order_change, order_status: str, position_status: str):
        """Update trade status from order change."""
        try:
            updates: Dict[str, Any] = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(order_change.raw_data),
                'exchange_response': json.dumps(order_change.raw_data),
                'order_status': order_status,
                'status': position_status
            }

            if order_change.filled_size > 0:
                updates['position_size'] = order_change.filled_size

            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"[KC-Sync] Updated trade {trade_id} status to {position_status}")

        except Exception as e:
            logger.error(f"[KC-Sync] Error updating trade status: {e}")

    async def _update_trade_order_id(self, trade_id: int, order_id: str):
        """Update trade with exchange order ID."""
        try:
            updates = {
                'exchange_order_id': order_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"[KC-Sync] Updated trade {trade_id} with order ID {order_id}")

        except Exception as e:
            logger.error(f"[KC-Sync] Error updating trade order ID: {e}")

    def clear_cache(self):
        """Clear order ID cache."""
        self.order_id_cache.clear()
        logger.info("[KC-Sync] Cleared order ID cache")
