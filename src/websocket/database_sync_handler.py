"""
Database synchronization handler for WebSocket events.
Links Binance orders to database trades and keeps them synchronized in real-time.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from decimal import Decimal
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from discord_bot.utils.timestamp_manager import WebSocketTimestampHandler, TimestampManager

logger = logging.getLogger(__name__)

class DatabaseSyncHandler:
    """
    Handles real-time database synchronization with Binance WebSocket events.

    Key Features:
    - Links Binance orderId to database exchange_order_id
    - Updates trade status when orders fill
    - Calculates and updates PnL in real-time
    - Handles partial fills and position updates
    """

    def __init__(self, db_manager):
        """
        Initialize database sync handler.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        
        # Initialize timestamp management
        if hasattr(db_manager, 'supabase'):
            self.timestamp_manager = TimestampManager(db_manager.supabase)
            self.websocket_timestamp_handler = WebSocketTimestampHandler(self.timestamp_manager)
        else:
            self.timestamp_manager = None
            self.websocket_timestamp_handler = None
        self.order_id_cache = {}  # Cache for orderId -> trade_id mapping

    async def handle_execution_report(self, data: Dict[str, Any]):
        """
        Handle execution report events from Binance WebSocket.
        This is the main event for order status changes.
        """
        try:
            # Extract key data from execution report
            order_id = data.get('i')  # Binance order ID
            symbol = data.get('s')    # Symbol (e.g., 'BTCUSDT')
            status = data.get('X')    # Order status (NEW, FILLED, PARTIALLY_FILLED, etc.)
            executed_qty = float(data.get('z', 0))  # Cumulative filled quantity
            avg_price = float(data.get('ap', 0))    # Average fill price
            realized_pnl = float(data.get('Y', 0))  # Realized PnL from Binance
            side = data.get('S')      # Side (BUY/SELL)

            logger.info(f"Execution Report: {symbol} {order_id} - {status} - Qty: {executed_qty} - Price: {avg_price}")
            # Find the corresponding trade in database
            trade = await self._find_trade_by_order_id(str(order_id)) if order_id is not None else None
            if not trade:
                logger.warning(f"Trade not found for order ID: {order_id}")
                return

            trade_id = trade['id']
            logger.info(f"Found trade {trade_id} for order {order_id}")
            # Update trade based on order status
            if status is not None:
                await self._update_trade_status(trade_id, trade, data, status, executed_qty, avg_price, realized_pnl)
            else:
                logger.warning(f"Skipping trade update - status is None for order {order_id}")

        except Exception as e:
            logger.error(f"Error handling execution report: {e}")

    async def handle_account_position(self, data: Dict[str, Any]):
        """
        Handle account position updates.
        Updates unrealized PnL and position information.
        """
        try:
            logger.info("Account position update received")

            # Get all open trades and update their unrealized PnL
            open_trades = await self._get_open_trades()

            for trade in open_trades:
                symbol = trade.get('coin_symbol', '') + 'USDT'

                # Find position data for this symbol
                position_data = self._find_position_data(data, symbol)
                if position_data:
                    await self._update_position_data(trade['id'], position_data)

        except Exception as e:
            logger.error(f"Error handling account position: {e}")

    async def handle_ticker(self, data: Dict[str, Any]):
        """
        Handle market ticker updates for unrealized PnL calculation.
        """
        try:
            symbol = data.get('s')  # e.g., 'BTCUSDT'
            current_price = float(data.get('c', 0))  # Current price

            if current_price > 0:
                # Find open trades for this symbol
                open_trades = await self._get_open_trades_by_symbol(symbol) if symbol is not None else []

                for trade in open_trades:
                    await self._update_unrealized_pnl(trade['id'], trade, current_price)

        except Exception as e:
            logger.error(f"Error handling ticker: {e}")

    async def _find_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Find trade in database by Binance order ID.
        Uses exchange_order_id field for matching.
        """
        try:
            # First check cache
            if order_id in self.order_id_cache:
                trade_id = self.order_id_cache[order_id]
                response = self.db_manager.supabase.from_("trades").select("*").eq("id", trade_id).execute()
                if response.data:
                    return response.data[0]

            # Get 7-day cutoff for performance
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            cutoff_iso = cutoff.isoformat()

            # Search by exchange_order_id (limited to 7 days)
            response = self.db_manager.supabase.from_("trades").select("*").eq("exchange_order_id", order_id).gte("created_at", cutoff_iso).execute()

            if response.data:
                trade = response.data[0]
                # Cache the mapping
                self.order_id_cache[order_id] = trade['id']
                return trade

            # If not found by exchange_order_id, try parsing sync_order_response (limited to 7 days)
            response = self.db_manager.supabase.from_("trades").select("*").gte("created_at", cutoff_iso).execute()
            for trade in response.data:
                sync_order_response = trade.get('sync_order_response', '')
                if sync_order_response and order_id in sync_order_response:
                    # Found it! Update the exchange_order_id
                    await self._update_trade_order_id(trade['id'], order_id)
                    self.order_id_cache[order_id] = trade['id']
                    return trade

            return None

        except Exception as e:
            logger.error(f"Error finding trade by order ID {order_id}: {e}")
            return None

    async def _update_trade_status(self, trade_id: int, trade: Dict[str, Any],
                                 execution_data: Dict[str, Any], status: str,
                                 executed_qty: float, avg_price: float, realized_pnl: float):
        """
        Update trade status based on order execution.
        """
        try:
            updates = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'sync_order_response': json.dumps(execution_data)
            }

            # Import status constants
            from discord_bot.status_constants import map_binance_order_status, determine_position_status_from_order

            # Update order status
            order_status = map_binance_order_status(status)
            updates['order_status'] = order_status

            # CRITICAL: Determine position status based on order status, executed quantity, and order type
            is_exit_order = execution_data.get('reduceOnly', False) or execution_data.get('closePosition', False)
            position_status = determine_position_status_from_order(order_status, executed_qty, is_exit_order)
            updates['status'] = position_status  # status column now holds position status

            # Add additional data based on order status
            if status == 'FILLED':
                if executed_qty > 0:
                    # CRITICAL: Update exit price and PnL for filled orders
                    updates.update({
                        'exit_price': str(avg_price),
                        'binance_exit_price': str(avg_price),
                        'pnl_usd': str(realized_pnl),
                        'realized_pnl': str(realized_pnl),
                        'position_size': str(executed_qty)
                    })
            elif status == 'PARTIALLY_FILLED':
                if executed_qty > 0:
                    # CRITICAL: Update position size for partial fills
                    updates.update({
                        'position_size': str(executed_qty)
                    })

                    # CRITICAL: Determine if this is an entry or exit order
                    # Entry orders: reduceOnly=False or not present, closePosition=False or not present
                    # Exit orders: reduceOnly=True or closePosition=True
                    is_exit_order = execution_data.get('reduceOnly', False) or execution_data.get('closePosition', False)
                    
                    if is_exit_order:
                        # This is an exit order - update binance_exit_price and set closed_at
                        updates['binance_exit_price'] = str(avg_price)
                        logger.info(f"Updated binance_exit_price to execution price: {avg_price} (exit order)")
                        
                        # Set closed_at timestamp using WebSocket timestamp manager
                        if self.websocket_timestamp_handler:
                            fill_time = execution_data.get('T')  # Transaction time
                            await self.websocket_timestamp_handler.handle_order_execution(execution_data)
                    else:
                        # This is an entry order - update binance_entry_price and set created_at
                        # CRITICAL: Only set binance_entry_price if there's actual execution (executed_qty > 0)
                        current_binance_entry_price = trade.get('binance_entry_price')
                        if executed_qty > 0 and (not current_binance_entry_price or float(current_binance_entry_price) == 0):
                            if avg_price > 0:
                                updates['binance_entry_price'] = str(avg_price)
                        
                        # Set created_at timestamp using WebSocket timestamp manager
                        if self.websocket_timestamp_handler:
                            execution_time = execution_data.get('T')  # Transaction time
                            await self.websocket_timestamp_handler.handle_order_execution(execution_data)
                            
                        logger.info(f"Updated missing binance_entry_price to execution price: {avg_price} (entry order)")

                    logger.info(f"Trade {trade_id} FILLED at {avg_price} - PnL: {realized_pnl}")

            elif status == 'PARTIALLY_FILLED':
                # CRITICAL: Update position size for partial fills
                updates.update({
                    'position_size': str(executed_qty)
                })

                # CRITICAL: Determine if this is an entry or exit order
                is_exit_order = execution_data.get('reduceOnly', False) or execution_data.get('closePosition', False)
                
                if is_exit_order:
                    # This is an exit order - update binance_exit_price
                    updates['binance_exit_price'] = str(avg_price)
                    logger.info(f"Updated binance_exit_price to execution price: {avg_price} (exit order - partial)")
                else:
                    # This is an entry order - update binance_entry_price if missing
                    # CRITICAL: Only set binance_entry_price if there's actual execution (executed_qty > 0)
                    current_binance_entry_price = trade.get('binance_entry_price')
                    if executed_qty > 0 and (not current_binance_entry_price or float(current_binance_entry_price) == 0):
                        if avg_price > 0:
                            updates['binance_entry_price'] = str(avg_price)
                            logger.info(f"Updated missing binance_entry_price to execution price: {avg_price} (entry order - partial)")

                logger.info(f"Trade {trade_id} PARTIALLY_FILLED at {avg_price}")

            elif status == 'NEW':
                # CRITICAL: Update position size for new orders
                if executed_qty > 0:
                    updates['position_size'] = str(executed_qty)
                logger.info(f"Trade {trade_id} order unfilled")

            elif status in ['CANCELED', 'EXPIRED', 'REJECTED']:
                logger.warning(f"Trade {trade_id} {status} - {execution_data}")
            else:
                logger.warning(f"Skipping trade update - status is {status} for order {trade_id}")

            # CRITICAL: Validate that all required fields are populated
            self._validate_critical_fields(trade_id, updates, trade)

            # Update the database
            await self.db_manager.update_existing_trade(trade_id, updates)

        except Exception as e:
            logger.error(f"Error updating trade status for {trade_id}: {e}")

    def _validate_critical_fields(self, trade_id: int, updates: Dict[str, Any], original_trade: Dict[str, Any]):
        """
        CRITICAL: Validate that all required fields are populated to prevent fraud.
        """
        try:
            critical_fields = {
                'position_size': 'Position size is required for accurate PnL calculation',
                'entry_price': 'Entry price is required for accurate PnL calculation',
                'binance_entry_price': 'Binance entry price is required for accurate PnL calculation',
                'binance_exit_price': 'Binance exit price is required for accurate PnL calculation',
                'pnl_usd': 'PnL is required for accurate financial reporting'
            }

            missing_fields = []
            validation_issues = []

            # Check current trade data and updates
            for field, description in critical_fields.items():
                current_value = original_trade.get(field)
                updated_value = updates.get(field)

                # Use updated value if available, otherwise use current value
                final_value = updated_value if updated_value is not None else current_value

                if not final_value or (isinstance(final_value, (int, float)) and final_value == 0):
                    missing_fields.append(field)
                    validation_issues.append(f"Missing {field}: {description}")

            if missing_fields:
                logger.error(f"CRITICAL: Trade {trade_id} missing required fields: {missing_fields}")
                logger.error(f"Validation issues: {validation_issues}")

                # Mark for manual verification
                updates['sync_issues'] = validation_issues
                updates['manual_verification_needed'] = True
                updates['sync_error_count'] = (original_trade.get('sync_error_count', 0) or 0) + 1

                # Log critical warning
                logger.critical(f"FRAUD RISK: Trade {trade_id} has missing critical fields that could lead to inaccurate financial reporting")
            else:
                logger.info(f"✅ Trade {trade_id} has all critical fields populated")

        except Exception as e:
            logger.error(f"Error validating critical fields for trade {trade_id}: {e}")

    async def _update_trade_order_id(self, trade_id: int, order_id: str):
        """
        Update trade with the correct exchange_order_id.
        """
        try:
            updates = {
                'exchange_order_id': order_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            await self.db_manager.update_existing_trade(trade_id, updates)
            logger.info(f"Updated trade {trade_id} with order ID {order_id}")
        except Exception as e:
            logger.error(f"Error updating trade order ID: {e}")

    async def _get_open_trades(self) -> List[Dict[str, Any]]:
        """
        Get all open trades from database (limited to 7 days for performance).
        """
        try:
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            cutoff_iso = cutoff.isoformat()

            response = self.db_manager.supabase.from_("trades").select("*").eq("status", "OPEN").gte("created_at", cutoff_iso).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []

    async def _get_open_trades_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Get open trades for a specific symbol (limited to 7 days for performance).
        """
        try:
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            cutoff_iso = cutoff.isoformat()

            # Remove 'USDT' suffix for database lookup
            coin_symbol = symbol.replace('USDT', '')
            response = self.db_manager.supabase.from_("trades").select("*").eq("status", "OPEN").eq("coin_symbol", coin_symbol).gte("created_at", cutoff_iso).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting open trades for {symbol}: {e}")
            return []

    async def _update_unrealized_pnl(self, trade_id: int, trade: Dict[str, Any], current_price: float):
        """
        Update unrealized PnL for an open trade.
        """
        try:
            entry_price = float(trade.get('entry_price', 0))
            position_size = float(trade.get('position_size', 0))
            position_type = trade.get('signal_type', 'LONG')

            if entry_price > 0 and position_size > 0:
                unrealized_pnl = self._calculate_unrealized_pnl(entry_price, current_price, position_size, position_type)

                updates = {
                    'unrealized_pnl': unrealized_pnl
                }

                await self.db_manager.update_existing_trade(trade_id, updates)

        except Exception as e:
            logger.error(f"Error updating unrealized PnL for trade {trade_id}: {e}")

    def _calculate_unrealized_pnl(self, entry_price: float, current_price: float, position_size: float, position_type: str) -> float:
        """
        Calculate unrealized PnL.
        """
        try:
            if position_type.upper() == 'LONG':
                return (current_price - entry_price) * position_size
            else:  # SHORT
                return (entry_price - current_price) * position_size
        except Exception as e:
            logger.error(f"Error calculating unrealized PnL: {e}")
            return 0.0

    def _find_position_data(self, account_data: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """
        Find position data for a specific symbol in account position update.
        """
        try:
            # This would need to be implemented based on the actual structure
            # of the outboundAccountPosition event
            return None
        except Exception as e:
            logger.error(f"Error finding position data: {e}")
            return None

    async def _update_position_data(self, trade_id: int, position_data: Dict[str, Any]):
        """
        Update trade with position data.
        """
        try:
            updates = {}

            # Add position-specific updates here
            # This would depend on the structure of position_data

            await self.db_manager.update_existing_trade(trade_id, updates)

        except Exception as e:
            logger.error(f"Error updating position data for trade {trade_id}: {e}")

    def get_order_id_mapping_stats(self) -> Dict[str, Any]:
        """
        Get statistics about order ID mappings.
        """
        return {
            'cached_mappings': len(self.order_id_cache),
            'cache_keys': list(self.order_id_cache.keys())
        }