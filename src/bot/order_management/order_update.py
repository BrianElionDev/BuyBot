"""
Order update utilities for the trading bot.

This module contains functions for updating and modifying existing orders
including order modifications, status updates, and order tracking.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class OrderUpdater:
    """
    Core class for updating trading orders.
    """

    def __init__(self, binance_exchange):
        """
        Initialize the order updater.

        Args:
            binance_exchange: The Binance exchange instance
        """
        self.binance_exchange = binance_exchange

    async def update_order_status(self, trading_pair: str, order_id: str) -> Optional[Dict]:
        """
        Get the current status of an order.
        """
        try:
            logger.info(f"Getting status for order {order_id} on {trading_pair}")

            # Get order status from Binance
            order_status = await self.binance_exchange.get_futures_order_status(trading_pair, order_id)

            if order_status:
                logger.info(f"Order {order_id} status: {order_status.get('status', 'UNKNOWN')}")
                return order_status
            else:
                logger.warning(f"Could not retrieve status for order {order_id}")
                return None

        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}")
            return None

    async def modify_order(
        self,
        trading_pair: str,
        order_id: str,
        new_price: Optional[float] = None,
        new_quantity: Optional[float] = None
    ) -> Tuple[bool, Dict]:
        """
        Modify an existing order with new price and/or quantity.
        """
        try:
            logger.info(f"Modifying order {order_id} on {trading_pair}")

            # Get current order details
            current_order = await self.binance_exchange.get_futures_order_status(trading_pair, order_id)
            if not current_order:
                return False, {"error": f"Could not retrieve order {order_id}"}

            # Prepare modification parameters
            modify_params = {}
            if new_price is not None:
                modify_params['price'] = new_price
            if new_quantity is not None:
                modify_params['quantity'] = new_quantity

            if not modify_params:
                return False, {"error": "No modification parameters provided"}

            # Modify the order
            modified_order = await self.binance_exchange.modify_futures_order(
                trading_pair,
                order_id,
                **modify_params
            )

            if modified_order and 'orderId' in modified_order:
                logger.info(f"Successfully modified order {order_id}")
                return True, modified_order
            else:
                logger.error(f"Failed to modify order {order_id}: {modified_order}")
                return False, {"error": f"Failed to modify order: {modified_order}"}

        except Exception as e:
            logger.error(f"Error modifying order {order_id}: {e}")
            return False, {"error": f"Error modifying order: {str(e)}"}

    async def replace_order(
        self,
        trading_pair: str,
        old_order_id: str,
        new_side: str,
        new_quantity: float,
        new_price: Optional[float] = None,
        order_type: str = 'LIMIT'
    ) -> Tuple[bool, Dict]:
        """
        Replace an existing order with a new one.
        """
        try:
            logger.info(f"Replacing order {old_order_id} on {trading_pair}")

            # Cancel the old order first
            success, cancel_response = await self.binance_exchange.cancel_futures_order(trading_pair, old_order_id)
            if not success:
                logger.warning(f"Failed to cancel old order {old_order_id}: {cancel_response}")

            # Create the new order
            if order_type.upper() == 'MARKET':
                new_order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=new_side,
                    order_type_market='MARKET',
                    amount=new_quantity
                )
            else:
                if new_price is None:
                    return False, {"error": "Price is required for LIMIT orders"}

                new_order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=new_side,
                    order_type_market='LIMIT',
                    amount=new_quantity,
                    price=new_price
                )

            if new_order and 'orderId' in new_order:
                logger.info(f"Successfully replaced order {old_order_id} with {new_order['orderId']}")
                return True, new_order
            else:
                logger.error(f"Failed to create replacement order: {new_order}")
                return False, {"error": f"Failed to create replacement order: {new_order}"}

        except Exception as e:
            logger.error(f"Error replacing order {old_order_id}: {e}")
            return False, {"error": f"Error replacing order: {str(e)}"}

    async def get_order_history(self, trading_pair: str, limit: int = 100) -> Optional[list]:
        """
        Get order history for a trading pair.
        """
        try:
            logger.info(f"Getting order history for {trading_pair}")

            order_history = await self.binance_exchange.get_futures_order_history(trading_pair, limit=limit)

            if order_history:
                logger.info(f"Retrieved {len(order_history)} orders for {trading_pair}")
                return order_history
            else:
                logger.warning(f"No order history found for {trading_pair}")
                return []

        except Exception as e:
            logger.error(f"Error getting order history for {trading_pair}: {e}")
            return None

    async def get_open_orders(self, trading_pair: Optional[str] = None) -> Optional[list]:
        """
        Get all open orders, optionally filtered by trading pair.
        """
        try:
            if trading_pair:
                logger.info(f"Getting open orders for {trading_pair}")
            else:
                logger.info("Getting all open orders")

            open_orders = await self.binance_exchange.get_all_open_futures_orders()

            if open_orders:
                if trading_pair:
                    # Filter by trading pair
                    filtered_orders = [order for order in open_orders if order.get('symbol') == trading_pair]
                    logger.info(f"Retrieved {len(filtered_orders)} open orders for {trading_pair}")
                    return filtered_orders
                else:
                    logger.info(f"Retrieved {len(open_orders)} total open orders")
                    return open_orders
            else:
                logger.info("No open orders found")
                return []

        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return None

    async def validate_order_parameters(
        self,
        trading_pair: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = 'LIMIT'
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate order parameters before creation.
        """
        try:
            # Validate trading pair
            if not trading_pair or len(trading_pair) < 6:  # Minimum length for valid pair
                return False, "Invalid trading pair"

            # Validate side
            if side.upper() not in ['BUY', 'SELL']:
                return False, "Invalid order side. Must be 'BUY' or 'SELL'"

            # Validate quantity
            if quantity <= 0:
                return False, "Quantity must be greater than 0"

            # Validate price for LIMIT orders
            if order_type.upper() == 'LIMIT' and (price is None or price <= 0):
                return False, "Price is required and must be greater than 0 for LIMIT orders"

            # Validate order type
            if order_type.upper() not in ['MARKET', 'LIMIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                return False, "Invalid order type"

            return True, None

        except Exception as e:
            logger.error(f"Error validating order parameters: {e}")
            return False, f"Error in validation: {str(e)}"
