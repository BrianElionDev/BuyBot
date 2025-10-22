"""
Followup signal processing utilities for the trading bot.

This module contains functions for processing followup trading signals
including trade updates, position modifications, and order management.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'


class FollowupSignalProcessor:
    """
    Core class for processing followup trading signals.
    """

    def __init__(self, trading_engine):
        """
        Initialize the followup signal processor.

        Args:
            trading_engine: The trading engine instance
        """
        self.trading_engine = trading_engine
        self.exchange = trading_engine.exchange
        self.db_manager = trading_engine.db_manager

    async def check_trade_status_on_binance(self, coin_symbol: str, exchange_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check the current status of a trade on Binance.

        Returns:
            Dictionary with position info, order status, etc.
        """
        try:
            symbol = f"{coin_symbol}USDT"
            result = {
                'has_position': False,
                'position_size': 0.0,
                'position_side': None,
                'unrealized_pnl': 0.0,
                'has_open_orders': False,
                'stop_orders': []
            }

            # Check positions
            positions = await self.exchange.get_positions(symbol=symbol)
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    result['has_position'] = True
                    result['position_size'] = abs(position_amt)
                    result['position_side'] = 'LONG' if position_amt > 0 else 'SHORT'
                    result['unrealized_pnl'] = float(pos.get('unRealizedProfit', 0))
                    break

            # Check open orders (especially stop losses)
            if exchange_order_id:
                try:
                    order_status = await self.exchange.get_order_status(symbol, exchange_order_id)
                    result['order_status'] = order_status
                except:
                    pass

            # Get all open orders for this symbol
            open_orders = await self.exchange.get_open_orders(symbol=symbol)
            result['has_open_orders'] = len(open_orders) > 0
            result['stop_orders'] = [order for order in open_orders if order.get('type') in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']]

            return result

        except Exception as e:
            logger.error(f"Error checking trade status on Binance for {coin_symbol}: {e}")
            return {'error': str(e)}

    async def validate_trade_for_followup(self, trade_id: int, action: str) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validate that a trade exists and has the necessary data for follow-up actions.

        Returns:
            (is_valid, trade_data, error_message)
        """
        # Get trade from database
        active_trade = await self.db_manager.get_trade_by_id(trade_id)
        if not active_trade:
            return False, {}, f"Trade {trade_id} not found in database"

        # Check if trade has basic required data
        coin_symbol = active_trade.get('coin_symbol')
        if not coin_symbol:
            return False, active_trade, f"Trade {trade_id} missing coin_symbol"

        # Check if trade was successfully executed (has exchange order)
        exchange_order_id = active_trade.get('exchange_order_id')
        binance_response = active_trade.get('binance_response', '')
        exchange_response = active_trade.get('exchange_response', '')
        kucoin_response = active_trade.get('kucoin_response', '')

        if not exchange_order_id:
            try:
                import json
                if binance_response:
                    if isinstance(binance_response, str):
                        response_data = json.loads(binance_response)
                    elif isinstance(binance_response, dict):
                        response_data = binance_response
                    else:
                        response_data = None
                    if isinstance(response_data, dict):
                        exchange_order_id = response_data.get('orderId') or response_data.get('order_id')
                        client_order_id = response_data.get('clientOrderId') or response_data.get('client_order_id')
                    else:
                        client_order_id = None
                else:
                    client_order_id = None

                if (not exchange_order_id) and exchange_response:
                    if isinstance(exchange_response, str):
                        er = json.loads(exchange_response)
                    elif isinstance(exchange_response, dict):
                        er = exchange_response
                    else:
                        er = None
                    if isinstance(er, dict):
                        exchange_order_id = er.get('orderId') or er.get('order_id')
                        client_order_id = client_order_id or er.get('clientOrderId') or er.get('client_order_id')

                if (not exchange_order_id) and kucoin_response:
                    if isinstance(kucoin_response, str):
                        kr = json.loads(kucoin_response)
                    elif isinstance(kucoin_response, dict):
                        kr = kucoin_response
                    else:
                        kr = None
                    if isinstance(kr, dict):
                        exchange_order_id = kr.get('orderId') or kr.get('order_id') or kr.get('id')
                        client_order_id = client_order_id or kr.get('clientOid')

                if (not exchange_order_id) and client_order_id and hasattr(self.exchange, 'get_order_by_client_id'):
                    try:
                        coin_symbol = active_trade.get('coin_symbol') or ''
                        symbol = f"{coin_symbol}USDT" if coin_symbol else None
                        order_info = await self.exchange.get_order_by_client_id(client_order_id, symbol)
                        if isinstance(order_info, dict):
                            exchange_order_id = order_info.get('orderId') or order_info.get('order_id')
                    except Exception:
                        pass
            except Exception:
                pass

        if not exchange_order_id:
            return False, active_trade, f"Trade {trade_id} has no exchange order ID - original trade likely failed"

        if str(active_trade.get('status', '')).upper() == 'CLOSED':
            return False, active_trade, f"Trade {trade_id} already closed"

        try:
            binance_status = await self.check_trade_status_on_binance(coin_symbol, exchange_order_id)

            position_requiring_actions = ['stop_loss_hit', 'take_profit_1', 'stops_to_be', 'tp1and_sl_to_be', 'position_closed']
            if action in position_requiring_actions:
                if 'error' in binance_status:
                    logger.warning(f"Could not get live position data from Binance for {coin_symbol}: {binance_status['error']}. Using stored position_size.")
                    position_size = float(active_trade.get('position_size') or 0.0)
                else:
                    position_size = binance_status.get('position_size', 0.0)
                    logger.info(f"Using live Binance position size: {position_size} for {coin_symbol}")

                if position_size <= 0:
                    return False, active_trade, f"Trade {trade_id} has zero position size - cannot execute {action}"

            if 'error' in binance_status:
                logger.warning(f"Could not validate trade {trade_id} against Binance: {binance_status['error']}")
                return True, active_trade, ""  # Allow action but log warning

            # For position-closing actions, we need an active position
            if action in ['stop_loss_hit', 'take_profit_1', 'position_closed']:
                if not binance_status['has_position']:
                    return False, active_trade, f"No active position found on Binance for {coin_symbol}USDT - cannot execute {action}"

                # Update the trade data with current position size from Binance
                active_trade['current_binance_position_size'] = binance_status['position_size']
                active_trade['current_binance_side'] = binance_status['position_side']

            # For stop loss updates, we need either a position or existing stop order
            if action in ['stops_to_be', 'tp1and_sl_to_be']:
                if not binance_status['has_position'] and len(binance_status['stop_orders']) == 0:
                    return False, active_trade, f"No active position or stop orders found for {coin_symbol}USDT - cannot update stops"

            # For order cancellations, check if there are orders to cancel
            if action in ['limit_order_cancelled']:
                if not binance_status['has_open_orders']:
                    logger.warning(f"No open orders found for {coin_symbol}USDT - order may already be cancelled")
                    # Don't fail this, just log warning as order might already be cancelled

            logger.info(f"Trade {trade_id} validation passed for action {action}. Binance status: Position={binance_status['has_position']}, Size={binance_status['position_size']}")
            return True, active_trade, ""

        except Exception as e:
            logger.warning(f"Could not validate trade {trade_id} against Binance: {e}")
            # If we can't validate against Binance, allow the action but log the warning
            return True, active_trade, ""

    async def process_trade_update(self, trade_id: int, action: str, details: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Process updates for an existing trade with position aggregation awareness.
        Handles followup alerts for merged positions correctly.
        """
        # Validate trade before processing
        is_valid, active_trade, error_msg = await self.validate_trade_for_followup(trade_id, action)
        if not is_valid:
            logger.error(f"Trade validation failed: {error_msg}")
            return False, {"error": error_msg}

        if not active_trade:
            logger.error(f"Could not find an active trade for ID {trade_id} to process update.")
            return False, {"error": "Active trade not found"}

        # POSITION AGGREGATION AWARENESS - Check if this trade is part of an aggregated position
        try:
            from src.bot.position_management import PositionManager

            position_manager = PositionManager(self.db_manager, self.exchange)
            coin_symbol = active_trade.get('coin_symbol')
            position_type = active_trade.get('signal_type', 'LONG')

            if coin_symbol:
                # Get all active positions to check for aggregation
                positions = await position_manager.get_active_positions()

                # Look for aggregated position containing this trade
                for position in positions.values():
                    if (position.symbol == coin_symbol and
                        position.side == position_type and
                        trade_id in position.trade_ids):

                        # This trade is part of an aggregated position
                        if trade_id != position.primary_trade_id:
                            # This is a secondary trade in an aggregated position
                            logger.info(f"Trade {trade_id} is part of aggregated position (primary: {position.primary_trade_id})")

                            # Redirect the update to the primary trade
                            primary_trade = await self.db_manager.get_trade_by_id(position.primary_trade_id)
                            if primary_trade:
                                logger.info(f"Redirecting update to primary trade {position.primary_trade_id}")
                                return await self._process_primary_trade_update(
                                    primary_trade, active_trade, action, details, position
                                )
                            else:
                                logger.error(f"Could not find primary trade {position.primary_trade_id}")
                                return False, {"error": "Primary trade not found for aggregated position"}
                        else:
                            # This is the primary trade - proceed normally but with aggregated position info
                            logger.info(f"Processing update for primary trade {trade_id} in aggregated position")
                            active_trade['aggregated_position'] = {
                                'total_size': position.size,
                                'trade_count': len(position.trade_ids),
                                'is_primary': True
                            }
                            break

        except Exception as e:
            logger.error(f"Error in position aggregation check: {e}")
            # Continue with normal processing if aggregation check fails
            logger.info("Continuing with normal trade update processing")

        # Parse position size and order info
        position_size = float(active_trade.get('position_size') or 0.0)
        from src.bot.utils.response_parser import ResponseParser
        binance_response = ResponseParser.parse_binance_response(active_trade.get('binance_response'))
        exchange_order_id = (active_trade.get('exchange_order_id') or (binance_response.get('orderId') if binance_response else None))
        stop_loss_order_id = (active_trade.get('stop_loss_order_id') or ((binance_response.get('stop_loss_order_details') or {}).get('orderId') if binance_response else None))
        from src.bot.utils.signal_parser import SignalParser
        parsed_signal = SignalParser.parse_parsed_signal(active_trade.get('parsed_signal'))
        coin_symbol = parsed_signal.get('coin_symbol') or active_trade.get('coin_symbol')
        position_type = parsed_signal.get('position_type') or active_trade.get('signal_type')
        entry_price = active_trade.get('entry_price') or 0.0
        if not coin_symbol or not position_type:
            logger.error(f"Missing coin_symbol or position_type for trade {trade_id}")
            return False, {"error": f"Missing coin_symbol or position_type for trade {trade_id}"}
        trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)

        # Check if position is open before acting
        is_open = await self.trading_engine.is_position_open(coin_symbol)
        if not is_open:
            logger.warning(f"Position for {coin_symbol} is already closed. No action taken.")
            return False, {"error": f"Position for {coin_symbol} is already closed."}

        # Process different action types
        if action.startswith('take_profit_'):
            return await self._process_take_profit_action(
                trade_id, action, details, coin_symbol, position_type, position_size, trading_pair
            )
        elif action in ['take_profit', 'stop_loss_hit', 'position_closed']:
            return await self._process_position_close(
                action, coin_symbol, position_type, position_size, trading_pair, details
            )
        elif action == 'stop_loss_update':
            return await self._process_stop_loss_update(
                details, coin_symbol, position_type, position_size, entry_price, trading_pair, stop_loss_order_id
            )
        elif action == 'limit_order_cancelled':
            return await self._process_limit_order_cancellation(
                coin_symbol, position_type, trading_pair, active_trade
            )
        else:
            logger.error(f"Unknown action: {action}")
            return False, {"error": f"Unknown action: {action}"}

    async def _process_take_profit_action(
        self,
        trade_id: int,
        action: str,
        details: Dict[str, Any],
        coin_symbol: str,
        position_type: str,
        position_size: float,
        trading_pair: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Process take profit actions for specific TP levels.
        """
        try:
            tp_idx = int(action.split('_')[-1])
            tp_price = details.get('tp_price')
            if not tp_price:
                logger.error(f"No TP price provided for TP{tp_idx}")
                return False, {"error": f"No TP price provided for TP{tp_idx}"}

            # Calculate amount to close
            close_pct = details.get('close_percentage', 100.0)
            amount_to_close = position_size * (close_pct / 100.0)
            logger.info(f"Placing TP{tp_idx} for {coin_symbol} at {tp_price} for {amount_to_close}")

            # Place a LIMIT order at tp_price for amount_to_close, reduceOnly
            tp_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            tp_order = await self.exchange.create_futures_order(
                pair=trading_pair,
                side=tp_side,
                order_type='LIMIT',
                amount=amount_to_close,
                price=tp_price,
                reduce_only=True
            )

            if tp_order and 'orderId' in tp_order:
                logger.info(f"TP{tp_idx} order placed: {tp_order['orderId']}")
                return True, tp_order
            else:
                logger.error(f"Failed to place TP{tp_idx} order: {tp_order}")
                return False, {"error": f"Failed to place TP{tp_idx} order", "response": tp_order}

        except Exception as e:
            logger.error(f"Error processing take profit action: {e}")
            return False, {"error": f"Error processing take profit: {str(e)}"}

    async def _process_position_close(
        self,
        action: str,
        coin_symbol: str,
        position_type: str,
        position_size: float,
        trading_pair: str,
        details: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Process position close actions.
        """
        try:
            logger.info(f"Closing position for {coin_symbol} at market. Reason: {action}")

            # Calculate amount to close
            close_pct = details.get('close_percentage', 100.0)
            amount_to_close = position_size * (close_pct / 100.0)

            # Cancel all TP/SL orders before closing position
            logger.info(f"Canceling all TP/SL orders for {trading_pair} before closing position")
            cancel_result = await self.trading_engine.cancel_tp_sl_orders(trading_pair, active_trade)
            if not cancel_result:
                logger.warning(f"Failed to cancel TP/SL orders for {trading_pair} - proceeding with position close")

            # Create closing order
            close_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            close_order = await self.exchange.create_futures_order(
                pair=trading_pair,
                side=close_side,
                order_type='MARKET',
                amount=amount_to_close,
                reduce_only=True
            )

            if close_order and 'orderId' in close_order:
                logger.info(f"Position closed: {close_order['orderId']}")
                return True, close_order
            else:
                logger.error(f"Failed to close position: {close_order}")
                return False, {"error": "Failed to close position", "response": close_order}

        except Exception as e:
            logger.error(f"Error processing position close: {e}")
            return False, {"error": f"Error closing position: {str(e)}"}

    async def _process_stop_loss_update(
        self,
        details: Dict[str, Any],
        coin_symbol: str,
        position_type: str,
        position_size: float,
        entry_price: float,
        trading_pair: str,
        stop_loss_order_id: Optional[str]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Process stop loss update actions.
        """
        try:
            new_stop_price = details.get('stop_price')
            if new_stop_price == 'BE':
                new_stop_price = entry_price
            if not isinstance(new_stop_price, (float, int)) or new_stop_price is None or new_stop_price <= 0:
                logger.error(f"Invalid new stop price for update: {new_stop_price}")
                return False, {"error": f"Invalid new stop price for update: {new_stop_price}"}

            logger.info(f"Updating stop loss for {coin_symbol} to {new_stop_price}")

            # Use separate stop loss order (appears in Open Orders)
            logger.info(f"Falling back to separate stop loss order for {trading_pair}")

            # Cancel old SL order if exists
            if stop_loss_order_id:
                await self.exchange.cancel_futures_order(trading_pair, stop_loss_order_id)

            new_sl_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            new_sl_order = await self.exchange.create_futures_order(
                pair=trading_pair,
                side=new_sl_side,
                order_type='STOP_MARKET',
                stop_price=new_stop_price,
                amount=position_size,
                reduce_only=True
            )

            if new_sl_order and 'orderId' in new_sl_order:
                logger.info(f"Stop loss updated: {new_sl_order['orderId']}")
                return True, new_sl_order
            else:
                logger.error(f"Failed to update stop loss: {new_sl_order}")
                return False, {"error": "Failed to update stop loss", "response": new_sl_order}

        except Exception as e:
            logger.error(f"Error processing stop loss update: {e}")
            return False, {"error": f"Error updating stop loss: {str(e)}"}

    async def _process_limit_order_cancellation(
        self,
        coin_symbol: str,
        position_type: str,
        trading_pair: str,
        active_trade: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Process limit order cancellation."""
        try:
            logger.info(f"Cancelling limit order for {coin_symbol}")

            # Cancel the main order
            exchange_order_id = active_trade.get('exchange_order_id')
            if exchange_order_id:
                success, response = await self.exchange.cancel_futures_order(trading_pair, exchange_order_id)
                if success:
                    logger.info(f"Successfully cancelled limit order {exchange_order_id}")
                    return True, response
                else:
                    logger.warning(f"Failed to cancel limit order {exchange_order_id}: {response}")
                    return False, {"error": f"Failed to cancel order: {response}"}
            else:
                logger.warning(f"No exchange order ID found for trade {active_trade.get('id')}")
                return False, {"error": "No exchange order ID found"}

        except Exception as e:
            logger.error(f"Error cancelling limit order: {e}")
            return False, {"error": f"Error cancelling order: {str(e)}"}

    async def validate_trade_update(
        self,
        trade_id: int,
        action: str,
        details: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate trade update parameters before processing.
        """
        try:
            # Check if trade exists
            active_trade = await self.db_manager.get_trade_by_id(trade_id)
            if not active_trade:
                return False, f"Trade with ID {trade_id} not found"

            # Validate action type
            valid_actions = [
                'take_profit', 'stop_loss_hit', 'position_closed', 'stop_loss_update',
                'limit_order_cancelled', 'break_even', 'stops_to_be'
            ]
            valid_actions.extend([f'take_profit_{i}' for i in range(1, 11)])  # TP1, TP2, etc.

            if action not in valid_actions:
                return False, f"Invalid action: {action}. Valid actions: {valid_actions}"

            # Validate details based on action
            if action.startswith('take_profit_'):
                if 'tp_price' not in details:
                    return False, f"Missing tp_price for action {action}"
                tp_price = details.get('tp_price')
                if not isinstance(tp_price, (float, int)) or tp_price <= 0:
                    return False, f"Invalid tp_price: {tp_price}"

            elif action == 'stop_loss_update':
                if 'stop_price' not in details:
                    return False, "Missing stop_price for stop_loss_update action"
                stop_price = details.get('stop_price')
                if stop_price != 'BE' and (not isinstance(stop_price, (float, int)) or stop_price <= 0):
                    return False, f"Invalid stop_price: {stop_price}"

            # Validate close_percentage if provided
            if 'close_percentage' in details:
                close_pct = details.get('close_percentage')
                if not isinstance(close_pct, (float, int)) or close_pct <= 0 or close_pct > 100:
                    return False, f"Invalid close_percentage: {close_pct}. Must be between 0 and 100"

            return True, None

        except Exception as e:
            logger.error(f"Error validating trade update: {e}")
            return False, f"Error in validation: {str(e)}"

    async def _process_primary_trade_update(
        self,
        primary_trade: Dict[str, Any],
        secondary_trade: Dict[str, Any],
        action: str,
        details: Dict[str, Any],
        position_info
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Process a followup alert for a secondary trade by redirecting it to the primary trade.

        Args:
            primary_trade: The primary trade in the aggregated position
            secondary_trade: The secondary trade that received the alert
            action: The action to perform
            details: Action details
            position_info: Information about the aggregated position

        Returns:
            Tuple of (success, result)
        """
        try:
            logger.info(f"Processing followup alert for secondary trade {secondary_trade['id']} via primary trade {primary_trade['id']}")

            # Update the action details to reflect the aggregated position
            updated_details = details.copy()
            updated_details['original_trade_id'] = secondary_trade['id']
            updated_details['aggregated_position'] = {
                'total_size': position_info.size,
                'trade_count': len(position_info.trade_ids),
                'is_aggregated': True
            }

            # Process the update using the primary trade
            # This ensures the update affects the correct Binance position
            result = await self.process_trade_update(
                primary_trade['id'],
                action,
                updated_details
            )

            if result[0]:  # Success
                # Log the successful redirection
                logger.info(f"Successfully processed followup alert for trade {secondary_trade['id']} via primary trade {primary_trade['id']}")

                # Add information about the redirection to the result
                if isinstance(result[1], dict):
                    result[1]['redirected_from_trade_id'] = secondary_trade['id']
                    result[1]['aggregated_position_updated'] = True

                try:
                    from src.services.status.status_normalizer import normalize_status
                    update_fields = {
                        'status': normalize_status('MERGED'),
                        'merged_into_trade_id': primary_trade['id']
                    }
                    await self.db_manager.update_existing_trade(secondary_trade['id'], update_fields)
                    logger.info(f"Marked secondary trade {secondary_trade['id']} as MERGED into {primary_trade['id']}")
                except Exception as e:
                    logger.warning(f"Failed to mark secondary trade {secondary_trade['id']} as MERGED: {e}")

                return result
            else:
                logger.error(f"Failed to process followup alert via primary trade: {result[1]}")
                return result

        except Exception as e:
            logger.error(f"Error processing primary trade update: {e}")
            return False, {"error": f"Error processing primary trade update: {str(e)}"}
