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
                    symbol=symbol,
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
            asset = data.get('a')  # Asset
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
            updates = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(execution_data),
                # Persist last seen execution data in unified exchange_response for UI/notifications
                'exchange_response': json.dumps(execution_data)
            }

            # Map Binance status to internal status and order_status enums
            # Use canonical values defined in src/core/constants.py
            binance_to_internal = {
                'NEW': ('PENDING', 'NEW'),
                'PARTIALLY_FILLED': ('OPEN', 'PARTIALLY_FILLED'),
                'FILLED': ('CLOSED', 'FILLED'),
                'CANCELED': ('CANCELLED', 'CANCELED'),
                'REJECTED': ('FAILED', 'REJECTED'),
                'EXPIRED': ('CANCELLED', 'EXPIRED')
            }

            status_pair = binance_to_internal.get(status, ('OPEN', status if isinstance(status, str) else 'UNKNOWN'))
            updates['status'] = status_pair[0]
            updates['order_status'] = status_pair[1]

            # Update quantities and prices using canonical columns
            if executed_qty > 0:
                updates['position_size'] = executed_qty
                updates['entry_price'] = avg_price

            # Update PnL if available
            if realized_pnl != 0:
                updates['realized_pnl'] = realized_pnl

            # Update database
            response = self.db_manager.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            if response.data:
                logger.info(f"Updated trade {trade_id} status to {updates.get('status')} order_status {updates.get('order_status')}")
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
