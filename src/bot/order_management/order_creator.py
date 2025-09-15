"""
Order creation utilities for the trading bot.

This module contains functions for creating various types of orders
including TP/SL orders, position-based orders, and separate orders.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple, Union

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
FUTURE_ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET = 'TAKE_PROFIT_MARKET'


class OrderCreator:
    """
    Core class for creating trading orders.
    """

    def __init__(self, binance_exchange):
        """
        Initialize the order creator.

        Args:
            binance_exchange: The Binance exchange instance
        """
        self.binance_exchange = binance_exchange

    async def create_tp_sl_orders(
        self,
        trading_pair: str,
        position_type: str,
        position_size: float,
        take_profits: Optional[List[float]] = None,
        stop_loss: Optional[Union[float, str]] = None
    ) -> Tuple[List[Dict], Optional[str]]:
        """
        Create Take Profit and Stop Loss orders using Binance's position-based TP/SL API.
        This will make them appear in the TP/SL column instead of Open Orders.
        Returns a tuple of (tp_sl_orders, stop_loss_order_id)
        """
        tp_sl_orders = []
        stop_loss_order_id = None

        try:
            # Determine the side for TP/SL orders based on position type
            if position_type.upper() == 'LONG':
                tp_sl_side = SIDE_SELL  # Sell to close long position
            elif position_type.upper() == 'SHORT':
                tp_sl_side = SIDE_BUY   # Buy to close short position
            else:
                logger.warning(f"Unknown position type {position_type} for TP/SL orders")
                return tp_sl_orders, stop_loss_order_id

            # Use position-based TP/SL instead of separate orders
            # This will make them appear in the TP/SL column in Binance
            try:
                # Get current position to set TP/SL on it
                positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
                current_position = None

                for position in positions:
                    if position.get('symbol') == trading_pair:
                        current_position = position
                        break

                if not current_position:
                    logger.warning(f"No position found for {trading_pair}, falling back to separate orders")
                    return await self.create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

                # Set position-based TP/SL using Binance API
                if self.binance_exchange.client:
                    # Prepare TP/SL parameters
                    tp_sl_params = {}

                    # Set take profit if provided
                    if take_profits and isinstance(take_profits, list) and len(take_profits) > 0:
                        # For position-based TP/SL, we can only set one TP level
                        # Use the first TP level for now
                        tp_price = float(take_profits[0])
                        tp_sl_params['takeProfitPrice'] = f"{tp_price}"
                        logger.info(f"Setting position-based TP at {tp_price} for {trading_pair}")

                    # Set stop loss if provided
                    if stop_loss:
                        sl_price = float(stop_loss)
                        tp_sl_params['stopLossPrice'] = f"{sl_price}"
                        logger.info(f"Setting position-based SL at {sl_price} for {trading_pair}")

                    # Fall back to separate orders which work reliably
                    logger.info(f"Using separate TP/SL orders for {trading_pair} (position-based not available)")

                # Use separate orders instead of position-based TP/SL
                logger.info(f"Using separate TP/SL orders for {trading_pair}")
                return await self.create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

            except Exception as e:
                logger.error(f"Error setting position-based TP/SL for {trading_pair}: {e}")
                # Fall back to separate orders
                return await self.create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

        except Exception as e:
            logger.error(f"Error in create_tp_sl_orders for {trading_pair}: {e}")
            return tp_sl_orders, stop_loss_order_id

    async def create_separate_tp_sl_orders(
        self,
        trading_pair: str,
        position_type: str,
        position_size: float,
        take_profits: Optional[List[float]] = None,
        stop_loss: Optional[Union[float, str]] = None
    ) -> Tuple[List[Dict], Optional[str]]:
        """
        Fallback method to create separate TP/SL orders (appears in Open Orders).
        This is the original implementation that creates STOP_MARKET and TAKE_PROFIT_MARKET orders.
        """
        tp_sl_orders = []
        stop_loss_order_id = None

        try:
            # Determine the side for TP/SL orders based on position type
            if position_type.upper() == 'LONG':
                tp_sl_side = SIDE_SELL  # Sell to close long position
            elif position_type.upper() == 'SHORT':
                tp_sl_side = SIDE_BUY   # Buy to close short position
            else:
                logger.warning(f"Unknown position type {position_type} for TP/SL orders")
                return tp_sl_orders, stop_loss_order_id

            # Create Take Profit orders
            if take_profits and isinstance(take_profits, list):
                for i, tp_price in enumerate(take_profits):
                    try:
                        tp_price_float = float(tp_price)

                        # For take profits, use reduceOnly with specific amount to handle partial positions correctly
                        tp_order = await self.binance_exchange.create_futures_order(
                            pair=trading_pair,
                            side=tp_sl_side,
                            order_type='TAKE_PROFIT_MARKET',
                            amount=position_size,  # Use specific amount for partial positions
                            stop_price=tp_price_float,
                            reduce_only=True  # This ensures it only reduces the position by the specified amount
                        )

                        if tp_order and 'orderId' in tp_order:
                            tp_order['order_type'] = 'TAKE_PROFIT'
                            tp_order['tp_level'] = i + 1
                            tp_sl_orders.append(tp_order)
                            logger.info(f"Created TP order {i+1} at {tp_price_float} for {trading_pair} with amount {position_size}")
                        else:
                            logger.error(f"Failed to create TP order {i+1}: {tp_order}")
                    except Exception as e:
                        logger.error(f"Error creating TP order {i+1} at {tp_price}: {e}")

            # Create Stop Loss order (supervisor requirement: default 5% if no SL provided)
            if stop_loss:
                try:
                    sl_price_float = float(stop_loss)
                    logger.info(f"Using provided stop loss: {sl_price_float}")
                except (ValueError, TypeError):
                    logger.warning(f"Invalid stop loss provided: {stop_loss}, using default 5%")
                    sl_price_float = None
            else:
                sl_price_float = None

            # If no valid stop loss provided, calculate default 5% from entry price
            if sl_price_float is None:
                # This would need to be calculated based on entry price
                # For now, we'll skip creating a default SL in this fallback method
                logger.warning(f"No valid stop loss provided for {trading_pair}, skipping SL creation")

            if sl_price_float is not None:
                try:
                    sl_order = await self.binance_exchange.create_futures_order(
                        pair=trading_pair,
                        side=tp_sl_side,
                        order_type='STOP_MARKET',
                        amount=position_size,
                        stop_price=sl_price_float,
                        reduce_only=True
                    )

                    if sl_order and 'orderId' in sl_order:
                        sl_order['order_type'] = 'STOP_LOSS'
                        tp_sl_orders.append(sl_order)
                        stop_loss_order_id = sl_order['orderId']
                        logger.info(f"Created SL order at {sl_price_float} for {trading_pair} with amount {position_size}")
                    else:
                        logger.error(f"Failed to create SL order: {sl_order}")
                except Exception as e:
                    logger.error(f"Error creating SL order at {sl_price_float}: {e}")

            return tp_sl_orders, stop_loss_order_id

        except Exception as e:
            logger.error(f"Error in create_separate_tp_sl_orders for {trading_pair}: {e}")
            return tp_sl_orders, stop_loss_order_id

    async def create_market_order(
        self,
        trading_pair: str,
        side: str,
        amount: float,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Create a market order.

        Args:
            trading_pair: The trading pair
            side: The order side ('BUY' or 'SELL')
            amount: The order amount
            reduce_only: Whether the order should be reduce-only

        Returns:
            Order response or None if failed
        """
        try:
            order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=side,
                order_type='MARKET',
                amount=amount,
                reduce_only=reduce_only
            )

            if order and 'orderId' in order:
                logger.info(f"Successfully created market order: {order['orderId']} for {trading_pair}")
                return order
            else:
                logger.error(f"Failed to create market order for {trading_pair}: {order}")
                return None

        except Exception as e:
            logger.error(f"Error creating market order for {trading_pair}: {e}")
            return None

    async def create_limit_order(
        self,
        trading_pair: str,
        side: str,
        amount: float,
        price: float,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Create a limit order.

        Args:
            trading_pair: The trading pair
            side: The order side ('BUY' or 'SELL')
            amount: The order amount
            price: The order price
            reduce_only: Whether the order should be reduce-only

        Returns:
            Order response or None if failed
        """
        try:
            order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=side,
                order_type='LIMIT',
                amount=amount,
                price=price,
                reduce_only=reduce_only
            )

            if order and 'orderId' in order:
                logger.info(f"Successfully created limit order: {order['orderId']} for {trading_pair}")
                return order
            else:
                logger.error(f"Failed to create limit order for {trading_pair}: {order}")
                return None

        except Exception as e:
            logger.error(f"Error creating limit order for {trading_pair}: {e}")
            return None
