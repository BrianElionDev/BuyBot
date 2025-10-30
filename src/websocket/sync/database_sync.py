"""
Database synchronization for WebSocket events.
Handles real-time synchronization between WebSocket events and database.
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from decimal import Decimal

from .sync_models import SyncEvent, DatabaseSyncState, TradeSyncData, PositionSyncData, BalanceSyncData
from src.core.response_normalizer import normalize_exchange_response

logger = logging.getLogger(__name__)

class DatabaseSync:
    """
    Handles real-time database synchronization with WebSocket events.
    """

    def __init__(self, db_manager):
        """
        Initialize database sync.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.order_id_cache = {}  # Cache for orderId -> trade_id mapping
        # Track processed notifications to prevent duplicates (max 1000 entries)
        self.processed_notifications = set()
        self.sync_state = DatabaseSyncState(
            last_sync_time=datetime.now(timezone.utc),
            sync_status='idle',
            pending_events=0,
            failed_events=0,
            successful_events=0
        )

    async def handle_execution_report(self, data: Dict[str, Any]) -> Optional[TradeSyncData]:
        """
        Handle execution report events from WebSocket.
        Links Binance orders to database trades and updates status.

        Args:
            data: Execution report data

        Returns:
            Optional[TradeSyncData]: Sync data if successful
        """
        try:
            # Handle both direct execution reports and ORDER_TRADE_UPDATE events
            if 'o' in data:
                order_data = data['o']
                logger.info(f"Processing ORDER_TRADE_UPDATE event: {order_data}")
            else:
                order_data = data
                logger.info(f"Processing direct execution report: {order_data}")

            order_id = order_data.get('i')  # Binance order ID
            symbol = order_data.get('s')    # Symbol
            status = order_data.get('X')    # Order status
            executed_qty = float(order_data.get('z', 0))  # Cumulative filled quantity
            avg_price = float(order_data.get('ap', 0))    # Average fill price
            realized_pnl = float(order_data.get('Y', 0))  # Realized PnL

            logger.info(f"Execution Report: {symbol} {order_id} - {status} - Qty: {executed_qty} - Price: {avg_price}")

            # Find the corresponding trade in database
            trade = await self._find_trade_by_order_id(str(order_id)) if order_id is not None else None
            if not trade:
                logger.warning(f"Trade not found for order ID: {order_id}")
                return None

            trade_id = trade['id']
            logger.info(f"Found trade {trade_id} for order {order_id}")

            # Update trade based on order status
            if status is not None:
                await self._update_trade_status(trade_id, trade, order_data, status, executed_qty, avg_price, realized_pnl)

                # Create sync data
                sync_data = TradeSyncData(
                    trade_id=str(trade_id),
                    order_id=str(order_id),
                    symbol=str(symbol or ''),
                    status=status,
                    executed_qty=executed_qty,
                    avg_price=avg_price,
                    realized_pnl=realized_pnl,
                    sync_timestamp=datetime.now(timezone.utc)
                )

                self._update_sync_state('success')
                return sync_data

        except Exception as e:
            logger.error(f"Error handling execution report: {e}")
            self._update_sync_state('failed')
            return None

    async def handle_account_position(self, data: Dict[str, Any]) -> Optional[List[PositionSyncData]]:
        """
        Handle account position updates.

        Args:
            data: Account position data

        Returns:
            Optional[List[PositionSyncData]]: Position sync data
        """
        try:
            logger.info("Account position update received")
            positions = data.get('P', [])
            sync_data_list = []

            for position in positions:
                symbol = position.get('s')  # Symbol
                position_amt = float(position.get('pa', 0))  # Position amount
                entry_price = float(position.get('ep', 0))  # Entry price
                mark_price = float(position.get('mp', 0))  # Mark price
                un_realized_pnl = float(position.get('up', 0))  # Unrealized PnL

                sync_data = PositionSyncData(
                    symbol=symbol,
                    position_amt=position_amt,
                    entry_price=entry_price,
                    mark_price=mark_price,
                    un_realized_pnl=un_realized_pnl,
                    sync_timestamp=datetime.now(timezone.utc)
                )
                sync_data_list.append(sync_data)

            self._update_sync_state('success')
            return sync_data_list

        except Exception as e:
            logger.error(f"Error handling account position: {e}")
            self._update_sync_state('failed')
            return None

    async def handle_balance_update(self, data: Dict[str, Any]) -> Optional[BalanceSyncData]:
        """
        Handle balance update events.

        Args:
            data: Balance update data

        Returns:
            Optional[BalanceSyncData]: Balance sync data
        """
        try:
            asset = str(data.get('a') or '')  # Asset (ensure string)
            balance_delta = float(data.get('d', 0))  # Balance delta

            sync_data = BalanceSyncData(
                asset=asset,
                balance=balance_delta,
                available_balance=balance_delta,
                sync_timestamp=datetime.now(timezone.utc)
            )

            logger.info(f"Balance Update: {asset} - Delta: {balance_delta}")
            self._update_sync_state('success')
            return sync_data

        except Exception as e:
            logger.error(f"Error handling balance update: {e}")
            self._update_sync_state('failed')
            return None

    async def _find_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Find trade in database by Binance order ID.

        Args:
            order_id: Binance order ID

        Returns:
            Optional[Dict]: Trade data or None if not found
        """
        try:
            trade = await self.db_manager.find_trade_by_order_id(order_id)

            if trade:
                self.order_id_cache[order_id] = trade['id']

                if not trade.get('exchange_order_id'):
                    await self._update_trade_order_id(trade['id'], order_id)

                logger.info(f"Found trade {trade['id']} for order {order_id}")
                return trade
            else:
                logger.warning(f"Trade not found for order ID: {order_id}")
                return None

        except Exception as e:
            logger.error(f"Error finding trade by order ID {order_id}: {e}")
            return None

    async def _update_trade_status(self, trade_id: int, trade: Dict[str, Any],
                                 execution_data: Dict[str, Any], status: str,
                                 executed_qty: float, avg_price: float, realized_pnl: float):
        """
        Update trade status based on order execution.

        Args:
            trade_id: Trade ID
            trade: Trade data
            execution_data: Execution data
            status: Order status
            executed_qty: Executed quantity
            avg_price: Average price
            realized_pnl: Realized PnL
        """
        try:
            updates: Dict[str, Any] = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(execution_data),
                # Persist last seen execution data in unified exchange_response for UI/notifications
                'exchange_response': json.dumps(execution_data)
            }

            # Use unified status mapping
            from src.core.status_manager import StatusManager
            order_status, position_status = StatusManager.map_exchange_to_internal(status, executed_qty)
            updates['status'] = position_status
            updates['order_status'] = order_status

            # Determine entry vs exit in an exchange-agnostic way
            side_raw = execution_data.get('S')  # BUY/SELL for Binance; may be missing on others
            signal_type = str(trade.get('signal_type') or '').upper()
            reduce_only = bool(execution_data.get('R')) if 'R' in execution_data else False
            close_position_flag = bool(execution_data.get('cp')) if 'cp' in execution_data else False

            is_exit_order = False
            try:
                if reduce_only or close_position_flag:
                    is_exit_order = True
                elif side_raw and signal_type:
                    side = str(side_raw).upper()
                    if signal_type == 'LONG' and side == 'SELL':
                        is_exit_order = True
                    elif signal_type == 'SHORT' and side == 'BUY':
                        is_exit_order = True
            except Exception:
                is_exit_order = False

            # Update quantities and prices using canonical columns
            if executed_qty > 0:
                updates['position_size'] = executed_qty
                if status == 'FILLED':
                    if is_exit_order:
                        updates['status'] = 'CLOSED'
                        if avg_price and avg_price > 0:
                            updates['exit_price'] = avg_price
                        if realized_pnl is not None:
                            updates['pnl_usd'] = realized_pnl
                    else:
                        updates['status'] = 'ACTIVE'
                        updates['entry_price'] = avg_price

            # Ensure terminal-cancel defaults for unfilled orders to avoid nulls
            if status in ['CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED'] and executed_qty == 0:
                # Only backfill defaults if currently missing in DB
                try:
                    if not trade.get('position_size'):
                        updates['position_size'] = 0.0
                except Exception:
                    updates['position_size'] = 0.0
                if trade.get('pnl_usd') is None:
                    updates['pnl_usd'] = 0.0
                # Exit price for never-opened orders should be explicit zero for UI consistency
                if trade.get('exit_price') is None:
                    updates['exit_price'] = 0.0

            # Update PnL if available
            if realized_pnl != 0:
                updates['realized_pnl'] = realized_pnl

            if updates.get('status') == 'CLOSED':
                if avg_price and avg_price > 0:
                    updates['exit_price'] = avg_price
                if realized_pnl is not None:
                    updates['pnl_usd'] = realized_pnl

            # Update database
            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"Updated trade {trade_id} status to {updates.get('status')} order_status {updates.get('order_status')}")
                # Notify via Telegram for error states only (success notifications handled by initial signal processor)
                try:
                    if status in ['CANCELED', 'REJECTED', 'EXPIRED']:
                        # Get local symbol first, normalize KuCoin XBT->BTC for DB context
                        local_symbol = trade.get('coin_symbol') or str(execution_data.get('s') or '')
                        try:
                            if isinstance(local_symbol, str) and local_symbol.upper().startswith('XBT'):
                                local_symbol = local_symbol.upper().replace('XBT', 'BTC', 1)
                        except Exception:
                            pass
                        # Create a unique key for this notification to prevent duplicates
                        order_id = str(trade.get('exchange_order_id') or execution_data.get('i') or '')
                        notification_key = f"{order_id}_{status}_{local_symbol}"

                        # Determine exchange from trade (fallback 'binance')
                        exchange_name = str(trade.get('exchange') or 'binance')

                        # Prepare enriched context
                        normalized = normalize_exchange_response(exchange_name, execution_data)
                        # Prefer requested data for non-filled terminal states
                        requested_price = execution_data.get('p') or execution_data.get('sp') or normalized.get('price') or normalized.get('stopPrice') or 0
                        requested_qty = execution_data.get('q') or normalized.get('origQty') or 0

                        # Extract helpful raw WS fields if present
                        context: Dict[str, Any] = {
                            "exchange": exchange_name,
                            "symbol": local_symbol or normalized.get('symbol') or '',
                            "order_id": order_id,
                            "client_order_id": execution_data.get('c') or normalized.get('clientOrderId') or '',
                            "order_type": execution_data.get('o') or normalized.get('type') or '',
                            "time_in_force": execution_data.get('f') or '',
                            "requested_price": float(requested_price) if requested_price else 0,
                            "requested_qty": float(requested_qty) if requested_qty else 0,
                            "avg_price": float(execution_data.get('ap') or normalized.get('avgPrice') or 0),
                            "filled_qty": float(execution_data.get('z') or normalized.get('executedQty') or 0),
                            "stop_price": float(execution_data.get('sp') or normalized.get('stopPrice') or 0),
                            "expire_reason": execution_data.get('V') or '',
                            "reduce_only": bool(execution_data.get('R')) if 'R' in execution_data else False,
                            "working_type": execution_data.get('wt') or '',
                            "price_protection": execution_data.get('pm') or '',
                            "error_code": execution_data.get('er') or '',
                        }

                        # Enrich with DB trade context when available
                        if trade:
                            if trade.get('entry_price') is not None:
                                context['entry_price'] = float(trade.get('entry_price') or 0)
                            if trade.get('exit_price') is not None:
                                context['exit_price'] = float(trade.get('exit_price') or 0)
                            if trade.get('position_size') is not None:
                                context['position_size'] = float(trade.get('position_size') or 0)
                            if trade.get('pnl_usd') is not None:
                                context['pnl_usd'] = float(trade.get('pnl_usd') or 0)
                            if trade.get('signal_type') is not None:
                                context['position_type'] = str(trade.get('signal_type'))

                        # Check if we've already sent this notification
                        if notification_key not in self.processed_notifications:
                            from src.services.notifications.notification_manager import NotificationManager
                            from src.services.notifications.alert_deduplicator import alert_deduplicator

                            # Check for duplicates using the centralized deduplicator
                            if alert_deduplicator.should_send_alert(
                                trade_id=str(trade_id),
                                error_type=f"ORDER_{status}",
                                symbol=local_symbol,
                                exchange=exchange_name
                            ):
                                notifier = NotificationManager()
                                await notifier.send_error_notification(
                                    error_type=f"ORDER_{status}",
                                    error_message=f"Order {status} for {local_symbol}",
                                    context=context
                                )
                                logger.info(f"Sent error notification for {notification_key}")
                            else:
                                logger.info(f"Skipping duplicate error notification for {notification_key}")

                            # Mark this notification as processed
                            self.processed_notifications.add(notification_key)
                            # Clean up old entries to prevent memory growth (keep last 1000)
                            if len(self.processed_notifications) > 1000:
                                old_entries = list(self.processed_notifications)[:200]
                                self.processed_notifications = self.processed_notifications - set(old_entries)
                        else:
                            logger.info(f"Skipping duplicate notification for {notification_key}")
                except Exception as e:
                    logger.error(f"Failed to send websocket execution notification: {e}")
            else:
                logger.warning(f"Failed to update trade {trade_id}")

        except Exception as e:
            logger.error(f"Error updating trade status for {trade_id}: {e}")

    async def _update_trade_order_id(self, trade_id: int, order_id: str):
        """
        Update trade with exchange order ID.

        Args:
            trade_id: Trade ID
            order_id: Exchange order ID
        """
        try:
            updates = {
                'exchange_order_id': order_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"Updated trade {trade_id} with order ID {order_id}")
            else:
                logger.warning(f"Failed to update trade {trade_id} with order ID")

        except Exception as e:
            logger.error(f"Error updating trade order ID for {trade_id}: {e}")

    def _update_sync_state(self, status: str):
        """
        Update synchronization state.

        Args:
            status: Sync status ('success', 'failed', 'pending')
        """
        self.sync_state.last_sync_time = datetime.now(timezone.utc)
        self.sync_state.sync_status = status

        if status == 'success':
            self.sync_state.successful_events += 1
        elif status == 'failed':
            self.sync_state.failed_events += 1
        elif status == 'pending':
            self.sync_state.pending_events += 1

    def get_sync_state(self) -> DatabaseSyncState:
        """
        Get current synchronization state.

        Returns:
            DatabaseSyncState: Current sync state
        """
        return self.sync_state

    def clear_cache(self):
        """Clear order ID cache."""
        self.order_id_cache.clear()
        logger.info("Cleared order ID cache")
