"""
Enhanced Trade Creator

Integrates position management and conflict detection into trade creation
to prevent database inconsistencies and orphaned orders.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Union

from .position_manager import PositionManager, PositionConflictAction
from .symbol_cooldown import SymbolCooldownManager

logger = logging.getLogger(__name__)


class EnhancedTradeCreator:
    """
    Enhanced trade creator that handles position conflicts and aggregation.

    This class ensures that new trades are properly integrated with existing
    positions and prevents the creation of orphaned orders.
    """

    def __init__(self, db_manager, exchange, trading_engine):
        self.db_manager = db_manager
        self.exchange = exchange
        self.trading_engine = trading_engine

        # Initialize position management components
        self.position_manager = PositionManager(db_manager, exchange)
        self.cooldown_manager = SymbolCooldownManager(
            default_cooldown=300,  # 5 minutes
            position_cooldown=600  # 10 minutes
        )

        # Configuration
        self.auto_merge_enabled = True
        self.auto_reject_conflicts = True
        self.max_position_trades = 5  # Maximum trades per position

    async def create_trade_with_conflict_detection(
        self,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        order_type: str = "MARKET",
        stop_loss: Optional[float] = None,
        take_profits: Optional[List[float]] = None,
        dca_range: Optional[List[float]] = None,
        client_order_id: Optional[str] = None,
        price_threshold_override: Optional[float] = None,
        quantity_multiplier: Optional[int] = None,
        entry_prices: Optional[List[float]] = None,
        trader: str = None,
        discord_id: str = None
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Create a trade with position conflict detection and resolution.

        This is the main entry point that replaces the standard trade creation
        with enhanced position management.
        """
        try:
            logger.info(f"Creating enhanced trade for {coin_symbol} {position_type}")

            # Step 1: Check cooldowns
            is_on_cooldown, cooldown_reason = self.cooldown_manager.is_on_cooldown(
                coin_symbol, trader
            )
            if is_on_cooldown:
                logger.info(f"Trade rejected due to cooldown: {cooldown_reason}")
                return False, f"Cooldown active: {cooldown_reason}"

            # Step 2: Check for position conflicts
            # First, we need to create a temporary trade record to get an ID
            temp_trade_data = {
                'discord_id': discord_id or f"temp_{int(datetime.now().timestamp())}",
                'trader': trader or 'system',
                'content': f"Temporary trade for conflict detection",
                'status': 'PENDING',
                'coin_symbol': coin_symbol,
                'signal_type': position_type,
                'position_size': 0,  # Will be updated after conflict resolution
                'entry_price': signal_price,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Create temporary trade record
            temp_trade = await self.db_manager.save_signal_to_db(temp_trade_data)
            if not temp_trade:
                return False, "Failed to create temporary trade record"

            temp_trade_id = temp_trade['id']

            try:
                # Check for conflicts
                conflict = await self.position_manager.check_position_conflict(
                    coin_symbol, position_type, temp_trade_id
                )

                if conflict:
                    logger.info(f"Position conflict detected: {conflict.reason}")

                    # Handle the conflict
                    conflict_result = await self._handle_trade_conflict(
                        conflict, temp_trade_data, coin_symbol, signal_price,
                        position_type, order_type, stop_loss, take_profits,
                        dca_range, client_order_id, price_threshold_override,
                        quantity_multiplier, entry_prices, trader
                    )

                    return conflict_result
                else:
                    # No conflict, proceed with normal trade creation
                    logger.info(f"No position conflict for {coin_symbol}, proceeding with trade creation")

                    # Update the temporary trade with actual trade data
                    trade_data = {
                        'position_size': self._calculate_position_size(
                            coin_symbol, signal_price, quantity_multiplier
                        ),
                        'entry_price': signal_price,
                        'status': 'PENDING',
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }

                    await self.db_manager.update_trade(temp_trade_id, trade_data)

                    # Execute the trade
                    result = await self._execute_trade(
                        temp_trade_id, coin_symbol, signal_price, position_type,
                        order_type, stop_loss, take_profits, dca_range,
                        client_order_id, price_threshold_override,
                        quantity_multiplier, entry_prices
                    )

                    if result[0]:  # Success
                        # Set cooldown
                        self.cooldown_manager.set_cooldown(coin_symbol, trader)
                        logger.info(f"Successfully created trade {temp_trade_id} for {coin_symbol}")

                    return result

            except Exception as e:
                # Clean up temporary trade on error
                await self.db_manager.update_trade(temp_trade_id, {
                    'status': 'FAILED',
                    'sync_issues': [f"Error during conflict detection: {str(e)}"],
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                raise e

        except Exception as e:
            logger.error(f"Error in enhanced trade creation: {e}")
            return False, f"Error in trade creation: {str(e)}"

    async def _handle_trade_conflict(
        self, conflict, temp_trade_data, coin_symbol, signal_price,
        position_type, order_type, stop_loss, take_profits, dca_range,
        client_order_id, price_threshold_override, quantity_multiplier,
        entry_prices, trader
    ) -> Tuple[bool, Union[Dict, str]]:
        """Handle a detected trade conflict."""
        try:
            # Determine the best action based on conflict type and configuration
            action = self._determine_conflict_action(conflict)

            if action == PositionConflictAction.MERGE and self.auto_merge_enabled:
                logger.info(f"Merging trade into existing position for {coin_symbol}")

                # Prepare merge data
                merge_data = {
                    'position_size': self._calculate_position_size(
                        coin_symbol, signal_price, quantity_multiplier
                    ),
                    'entry_price': signal_price,
                    'status': 'PENDING',
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

                # Handle the merge
                result = await self.position_manager.handle_position_conflict(
                    conflict, merge_data
                )

                if result['success']:
                    # Set position cooldown (longer than regular cooldown)
                    self.cooldown_manager.set_position_cooldown(coin_symbol)

                    return True, {
                        'action': 'merged',
                        'primary_trade_id': result['primary_trade_id'],
                        'new_position_size': result['new_position_size'],
                        'new_entry_price': result['new_entry_price'],
                        'message': f"Trade merged into existing position"
                    }
                else:
                    return False, f"Failed to merge trade: {result.get('error', 'Unknown error')}"

            elif action == PositionConflictAction.REJECT or self.auto_reject_conflicts:
                logger.info(f"Rejecting trade due to position conflict for {coin_symbol}")

                # Set position cooldown
                self.cooldown_manager.set_position_cooldown(coin_symbol)

                # Handle the rejection
                result = await self.position_manager.handle_position_conflict(
                    conflict, temp_trade_data
                )

                return False, f"Trade rejected: {conflict.reason}"

            else:
                # For other actions, let the position manager handle it
                result = await self.position_manager.handle_position_conflict(
                    conflict, temp_trade_data
                )

                if result['success']:
                    return True, result
                else:
                    return False, result.get('error', 'Unknown error')

        except Exception as e:
            logger.error(f"Error handling trade conflict: {e}")
            return False, f"Error handling conflict: {str(e)}"

    def _determine_conflict_action(self, conflict) -> PositionConflictAction:
        """Determine the best action for a conflict based on configuration and conflict type."""
        if conflict.conflict_type == "same_side":
            # Same side conflicts can usually be merged
            if self.auto_merge_enabled:
                return PositionConflictAction.MERGE
            else:
                return PositionConflictAction.REJECT

        elif conflict.conflict_type == "opposite_side":
            # Opposite side conflicts should be rejected
            return PositionConflictAction.REJECT

        else:
            # Default to rejection for unknown conflict types
            return PositionConflictAction.REJECT

    async def _execute_trade(
        self, trade_id, coin_symbol, signal_price, position_type,
        order_type, stop_loss, take_profits, dca_range, client_order_id,
        price_threshold_override, quantity_multiplier, entry_prices
    ) -> Tuple[bool, Union[Dict, str]]:
        """Execute the actual trade using the trading engine."""
        try:
            # Use the existing trading engine to execute the trade
            result = await self.trading_engine.process_signal(
                coin_symbol=coin_symbol,
                signal_price=signal_price,
                position_type=position_type,
                order_type=order_type,
                stop_loss=stop_loss,
                take_profits=take_profits,
                dca_range=dca_range,
                client_order_id=client_order_id,
                price_threshold_override=price_threshold_override,
                quantity_multiplier=quantity_multiplier,
                entry_prices=entry_prices
            )

            # Update the trade record with the result
            if result[0]:  # Success
                update_data = {
                    'status': 'OPEN',
                    'binance_response': str(result[1]) if isinstance(result[1], dict) else '',
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
            else:
                update_data = {
                    'status': 'FAILED',
                    'sync_issues': [str(result[1])],
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

            await self.db_manager.update_trade(trade_id, update_data)

            return result

        except Exception as e:
            logger.error(f"Error executing trade: {e}")

            # Update trade with error
            await self.db_manager.update_trade(trade_id, {
                'status': 'FAILED',
                'sync_issues': [f"Execution error: {str(e)}"],
                'updated_at': datetime.now(timezone.utc).isoformat()
            })

            return False, f"Error executing trade: {str(e)}"

    def _calculate_position_size(self, coin_symbol: str, signal_price: float,
                               quantity_multiplier: Optional[int] = None) -> float:
        """Calculate position size for the trade."""
        try:
            # Use the trading engine's position size calculation
            if hasattr(self.trading_engine, 'calculate_position_size'):
                return self.trading_engine.calculate_position_size(
                    coin_symbol, signal_price, quantity_multiplier
                )
            else:
                # Fallback calculation
                base_size = 100.0  # Default base size
                if quantity_multiplier:
                    return base_size * quantity_multiplier
                return base_size
        except Exception as e:
            logger.warning(f"Error calculating position size: {e}")
            return 100.0  # Default fallback

    async def get_position_status(self, symbol: str) -> Dict[str, Any]:
        """Get detailed position status for a symbol."""
        try:
            positions = await self.position_manager.get_active_positions()

            # Look for positions matching the symbol
            matching_positions = []
            for position in positions.values():
                if position.symbol == symbol:
                    matching_positions.append(position)

            if not matching_positions:
                return {
                    'symbol': symbol,
                    'has_position': False,
                    'positions': []
                }

            return {
                'symbol': symbol,
                'has_position': True,
                'positions': [
                    {
                        'side': pos.side,
                        'size': pos.size,
                        'entry_price': pos.entry_price,
                        'mark_price': pos.mark_price,
                        'unrealized_pnl': pos.unrealized_pnl,
                        'trade_count': len(pos.trade_ids),
                        'primary_trade_id': pos.primary_trade_id
                    }
                    for pos in matching_positions
                ]
            }

        except Exception as e:
            logger.error(f"Error getting position status: {e}")
            return {'error': str(e)}

    async def cleanup_orphaned_orders_enhanced(self) -> Dict[str, Any]:
        """Enhanced orphaned orders cleanup that considers position aggregation."""
        try:
            # Get all active positions
            positions = await self.position_manager.get_active_positions()

            # Get all open orders
            orders = await self.exchange.get_all_open_futures_orders()

            # Create symbol lookup for positions
            position_symbols = set()
            for position in positions.values():
                position_symbols.add(position.symbol)

            # Find orphaned orders
            orphaned_orders = []
            for order in orders:
                symbol = order.get('symbol')
                order_type = order.get('type', '').upper()

                # Check if this is a SL/TP order
                is_sl_tp = (
                    order_type in ['STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT'] or
                    order.get('reduceOnly', False) or
                    order.get('stopPrice') is not None
                )

                # Check if symbol has no position
                has_position = symbol in position_symbols

                if is_sl_tp and not has_position:
                    orphaned_orders.append(order)

            # Close orphaned orders
            closed_count = 0
            failed_count = 0

            for order in orphaned_orders:
                try:
                    symbol = order.get('symbol')
                    order_id = order.get('orderId')

                    success, result = await self.exchange.cancel_futures_order(symbol, order_id)

                    if success:
                        closed_count += 1
                        logger.info(f"Closed orphaned order: {symbol} {order_id}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to close orphaned order: {symbol} {order_id}: {result}")

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error closing orphaned order: {e}")

            return {
                'success': True,
                'orphaned_orders_found': len(orphaned_orders),
                'orders_closed': closed_count,
                'orders_failed': failed_count
            }

        except Exception as e:
            logger.error(f"Error in enhanced orphaned orders cleanup: {e}")
            return {
                'success': False,
                'error': str(e)
            }
