"""
Order cancellation utilities for the trading bot.

This module contains functions for cancelling various types of orders
including TP/SL orders, individual orders, and bulk cancellations.
"""

import logging
import json
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class OrderCanceller:
    """
    Core class for cancelling trading orders.
    """

    def __init__(self, exchange):
        """
        Initialize the order canceller.

        Args:
            exchange: The exchange instance (Binance, KuCoin, etc.)
        """
        self.exchange = exchange

    async def cancel_tp_sl_orders(self, trading_pair: str, active_trade: Dict) -> bool:
        """
        Cancel TP/SL orders for a specific symbol using stored order IDs.
        """
        try:
            cancelled_count = 0

            if active_trade is None:
                active_trade = {}

            # If we have an active trade with stored order IDs, use those
            if active_trade:
                # Cancel stop loss order if we have its ID
                stop_loss_order_id = active_trade.get('stop_loss_order_id')
                if stop_loss_order_id:
                    try:
                        logger.info(f"Cancelling stop loss order {stop_loss_order_id} for {trading_pair}")
                        success, _ = await self.exchange.cancel_futures_order(trading_pair, stop_loss_order_id)
                        if success:
                            cancelled_count += 1
                            logger.info(f"Successfully cancelled stop loss order {stop_loss_order_id}")
                        else:
                            logger.warning(f"Failed to cancel stop loss order {stop_loss_order_id} - may not exist")
                    except Exception as e:
                        logger.warning(f"Error cancelling stop loss order {stop_loss_order_id}: {e}")

                # Cancel take profit orders if we have their IDs
                binance_response = active_trade.get('binance_response')
                if isinstance(binance_response, str):
                    try:
                        binance_response = json.loads(binance_response)
                    except Exception:
                        binance_response = {}

                tp_sl_orders = [] if binance_response is None else binance_response.get('tp_sl_orders', [])
                for tp_sl_order in tp_sl_orders:
                    if isinstance(tp_sl_order, dict) and 'orderId' in tp_sl_order:
                        order_id = tp_sl_order['orderId']
                        order_type = tp_sl_order.get('order_type', 'UNKNOWN')
                        try:
                            logger.info(f"Cancelling {order_type} order {order_id} for {trading_pair}")
                            success, _ = await self.exchange.cancel_futures_order(trading_pair, order_id)
                            if success:
                                cancelled_count += 1
                                logger.info(f"Successfully cancelled {order_type} order {order_id}")
                            else:
                                logger.warning(f"Failed to cancel {order_type} order {order_id} - may not exist")
                        except Exception as e:
                            logger.warning(f"Error cancelling {order_type} order {order_id}: {e}")

            # Fallback: if no active_trade provided or no stored order IDs, try to find and cancel TP/SL orders
            if cancelled_count == 0:
                logger.info(f"No stored order IDs found, attempting to find and cancel TP/SL orders for {trading_pair}")
                open_orders = await self.exchange.get_all_open_futures_orders()

                for order in open_orders:
                    if (order['symbol'] == trading_pair and
                        order['type'] in ['STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT'] and
                        order.get('reduceOnly', False)):
                        try:
                            logger.info(f"Cancelling TP/SL order {order['orderId']} ({order['type']}) for {trading_pair}")
                            success, _ = await self.exchange.cancel_futures_order(trading_pair, order['orderId'])
                            if success:
                                cancelled_count += 1
                                logger.info(f"Successfully cancelled TP/SL order {order['orderId']}")
                            else:
                                logger.warning(f"Failed to cancel TP/SL order {order['orderId']}")
                        except Exception as e:
                            logger.error(f"Error cancelling TP/SL order {order['orderId']}: {e}")

            logger.info(f"Successfully cancelled {cancelled_count} TP/SL orders for {trading_pair}")
            return cancelled_count > 0

        except Exception as e:
            logger.error(f"Error canceling TP/SL orders for {trading_pair}: {e}")
            return False

    async def cancel_order(self, active_trade: Dict) -> Tuple[bool, Dict]:
        """
        Cancels an open order associated with a trade.
        """
        try:
            from src.bot.utils.signal_parser import SignalParser

            parsed_signal = SignalParser.parse_parsed_signal(active_trade.get("parsed_signal"))
            coin_symbol = parsed_signal.get("coin_symbol")
            order_id = active_trade.get("exchange_order_id")

            if not coin_symbol or not order_id:
                return False, {"error": f"Missing coin_symbol or order_id for trade {active_trade.get('id')}"}

            logger.info(f"Attempting to cancel order {order_id} for {coin_symbol}")

            trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)
            success, response = await self.exchange.cancel_futures_order(trading_pair, order_id)

            if success:
                logger.info(f"Successfully cancelled order {order_id} for {coin_symbol}")
                return True, response
            else:
                logger.error(f"Failed to cancel order {order_id} for {coin_symbol}. Reason: {response}")
                return False, response

        except Exception as e:
            logger.error(f"Error cancelling order for {active_trade.get('coin_symbol', 'unknown')}: {e}")
            return False, {"error": f"Error cancelling order: {str(e)}"}

    async def cancel_all_orders_for_symbol(self, trading_pair: str) -> bool:
        """
        Cancel all open orders for a specific trading pair.
        """
        try:
            logger.info(f"Cancelling all orders for {trading_pair}")

            open_orders = await self.exchange.get_all_open_futures_orders()
            cancelled_count = 0

            for order in open_orders:
                if order['symbol'] == trading_pair:
                    try:
                        order_id = order['orderId']
                        order_type = order['type']
                        logger.info(f"Cancelling {order_type} order {order_id} for {trading_pair}")

                        success, _ = await self.exchange.cancel_futures_order(trading_pair, order_id)
                        if success:
                            cancelled_count += 1
                            logger.info(f"Successfully cancelled {order_type} order {order_id}")
                        else:
                            logger.warning(f"Failed to cancel {order_type} order {order_id}")
                    except Exception as e:
                        logger.error(f"Error cancelling order {order.get('orderId', 'unknown')}: {e}")

            logger.info(f"Successfully cancelled {cancelled_count} orders for {trading_pair}")
            return cancelled_count > 0

        except Exception as e:
            logger.error(f"Error cancelling all orders for {trading_pair}: {e}")
            return False

    async def cancel_orders_by_type(self, trading_pair: str, order_types: list) -> bool:
        """
        Cancel orders of specific types for a trading pair.
        """
        try:
            logger.info(f"Cancelling {order_types} orders for {trading_pair}")

            open_orders = await self.exchange.get_all_open_futures_orders()
            cancelled_count = 0

            for order in open_orders:
                if (order['symbol'] == trading_pair and
                    order['type'] in order_types):
                    try:
                        order_id = order['orderId']
                        order_type = order['type']
                        logger.info(f"Cancelling {order_type} order {order_id} for {trading_pair}")

                        success, _ = await self.exchange.cancel_futures_order(trading_pair, order_id)
                        if success:
                            cancelled_count += 1
                            logger.info(f"Successfully cancelled {order_type} order {order_id}")
                        else:
                            logger.warning(f"Failed to cancel {order_type} order {order_id}")
                    except Exception as e:
                        logger.error(f"Error cancelling order {order.get('orderId', 'unknown')}: {e}")

            logger.info(f"Successfully cancelled {cancelled_count} {order_types} orders for {trading_pair}")
            return cancelled_count > 0

        except Exception as e:
            logger.error(f"Error cancelling {order_types} orders for {trading_pair}: {e}")
            return False

    async def cancel_order_by_id(self, trading_pair: str, order_id: str) -> Tuple[bool, Dict]:
        """
        Cancel a specific order by its ID.
        """
        try:
            logger.info(f"Cancelling order {order_id} for {trading_pair}")

            success, response = await self.exchange.cancel_futures_order(trading_pair, order_id)

            if success:
                logger.info(f"Successfully cancelled order {order_id} for {trading_pair}")
                return True, response
            else:
                logger.error(f"Failed to cancel order {order_id} for {trading_pair}. Reason: {response}")
                return False, response

        except Exception as e:
            logger.error(f"Error cancelling order {order_id} for {trading_pair}: {e}")
            return False, {"error": f"Error cancelling order: {str(e)}"}
