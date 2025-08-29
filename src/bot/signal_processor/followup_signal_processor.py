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
        self.binance_exchange = trading_engine.binance_exchange
        self.db_manager = trading_engine.db_manager

    async def process_trade_update(self, trade_id: int, action: str, details: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Process updates for an existing trade, like taking profit, moving stop loss, or partial close.
        """
        active_trade = await self.db_manager.get_trade_by_id(trade_id)
        if not active_trade:
            logger.error(f"Could not find an active trade for ID {trade_id} to process update.")
            return False, {"error": "Active trade not found"}

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
        entry_price = active_trade.get('entry_price')
        if not coin_symbol or not position_type:
            logger.error(f"Missing coin_symbol or position_type for trade {trade_id}")
            return False, {"error": f"Missing coin_symbol or position_type for trade {trade_id}"}
        trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

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
            tp_order = await self.binance_exchange.create_futures_order(
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
            cancel_result = await self.trading_engine.cancel_tp_sl_orders(trading_pair)
            if not cancel_result:
                logger.warning(f"Failed to cancel TP/SL orders for {trading_pair} - proceeding with position close")

            # Create closing order
            close_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            close_order = await self.binance_exchange.create_futures_order(
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

            # Try to use position-based TP/SL first (appears in TP/SL column)
            try:
                if self.binance_exchange.client:
                    # Set position-based stop loss
                    response = await self.binance_exchange.client.futures_change_position_tpsl_mode(
                        symbol=trading_pair,
                        dualSidePosition='false',
                        stopLossPrice=f"{new_stop_price}"
                    )

                    if response and response.get('status') == 'OK':
                        logger.info(f"Successfully updated position-based stop loss to {new_stop_price} for {trading_pair}")

                        # Create mock response for consistency
                        import time
                        mock_response = {
                            'orderId': f"pos_sl_{trading_pair}_{int(time.time())}",
                            'symbol': trading_pair,
                            'status': 'NEW',
                            'type': 'STOP_MARKET',
                            'side': 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY',
                            'price': f"{new_stop_price}",
                            'origQty': str(position_size)
                        }
                        return True, mock_response
                    else:
                        logger.warning(f"Failed to set position-based stop loss: {response}")
                else:
                    logger.warning("Binance client not available for position-based TP/SL")
            except Exception as e:
                logger.warning(f"Error setting position-based stop loss: {e}")

            # Fall back to separate stop loss order (appears in Open Orders)
            logger.info(f"Falling back to separate stop loss order for {trading_pair}")

            # Cancel old SL order if exists
            if stop_loss_order_id:
                await self.binance_exchange.cancel_futures_order(trading_pair, stop_loss_order_id)

            new_sl_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            new_sl_order = await self.binance_exchange.create_futures_order(
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
            valid_actions = ['take_profit', 'stop_loss_hit', 'position_closed', 'stop_loss_update']
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
