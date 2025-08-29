"""
Take profit management utilities for the trading bot.

This module contains functions for managing take profit orders including
creation, cancellation, auditing, and verification of take profit orders.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET = 'TAKE_PROFIT_MARKET'


class TakeProfitManager:
    """
    Core class for managing take profit orders.
    """

    def __init__(self, binance_exchange):
        """
        Initialize the take profit manager.

        Args:
            binance_exchange: The Binance exchange instance
        """
        self.binance_exchange = binance_exchange

    async def ensure_take_profit_for_position(
        self,
        coin_symbol: str,
        position_type: str,
        position_size: float,
        entry_price: float,
        external_tp: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Ensure a take profit is in place for a position.

        Args:
            coin_symbol: The trading symbol
            position_type: The position type ('LONG' or 'SHORT')
            position_size: The position size
            entry_price: The entry price
            external_tp: External take profit price from signal (if provided)

        Returns:
            Tuple of (success, take_profit_order_id)
        """
        try:
            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

            # Determine take profit price and quantity
            if external_tp is not None and external_tp > 0:
                # Use external TP from signal (50% of position)
                logger.info(f"Using external take profit from signal: {external_tp}")
                tp_price = external_tp
                tp_quantity = position_size * 0.5  # 50% of position
            else:
                # Use default 5% TP from entry price (100% of position)
                from src.bot.utils.price_calculator import PriceCalculator
                tp_price = PriceCalculator.calculate_5_percent_take_profit(entry_price, position_type)
                if not tp_price:
                    logger.error(f"Failed to calculate default 5% take profit for {coin_symbol}")
                    return False, None
                tp_quantity = position_size  # 100% of position
                logger.info(f"Using default 5% take profit: {tp_price}")

            # Cancel any existing take profit orders for this symbol
            await self._cancel_existing_take_profit_orders(trading_pair)

            # Create new take profit order
            tp_side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY

            tp_order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=tp_side,
                order_type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                amount=tp_quantity,
                stop_price=tp_price,
                reduce_only=True
            )

            if tp_order and 'orderId' in tp_order:
                take_profit_order_id = str(tp_order['orderId'])
                logger.info(f"Successfully created take profit order: {take_profit_order_id} at {tp_price}")
                return True, take_profit_order_id
            else:
                logger.error(f"Failed to create take profit order: {tp_order}")
                return False, None

        except Exception as e:
            logger.error(f"Error ensuring take profit for {coin_symbol}: {e}")
            return False, None

    async def _cancel_existing_take_profit_orders(self, trading_pair: str) -> bool:
        """
        Cancel existing take profit orders for a trading pair.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get open orders for the symbol
            open_orders = await self.binance_exchange.get_all_open_futures_orders()

            if not open_orders:
                logger.info(f"No open orders found for {trading_pair}")
                return True

            # Cancel take profit orders
            cancelled_count = 0
            for order in open_orders:
                if order.get('type') == 'TAKE_PROFIT_MARKET':
                    order_id = order.get('orderId')
                    if order_id:
                        cancel_result = await self.binance_exchange.cancel_futures_order(trading_pair, order_id)
                        if cancel_result:
                            logger.info(f"Cancelled existing take profit order: {order_id}")
                            cancelled_count += 1
                        else:
                            logger.warning(f"Failed to cancel take profit order: {order_id}")

            logger.info(f"Cancelled {cancelled_count} existing take profit orders for {trading_pair}")
            return True

        except Exception as e:
            logger.error(f"Error cancelling existing take profit orders for {trading_pair}: {e}")
            return False

    async def audit_open_positions_for_take_profit(self) -> Dict[str, Any]:
        """
        Audit all open positions to ensure they have take profit orders.

        Returns:
            Dictionary with audit results
        """
        try:
            logger.info("Starting take profit audit for all open positions...")

            # Get all open positions
            positions = await self.binance_exchange.get_position_risk()

            audit_results = {
                'total_positions': 0,
                'positions_with_tp': 0,
                'positions_without_tp': 0,
                'tp_orders_created': 0,
                'errors': []
            }

            for position in positions:
                symbol = position.get('symbol')
                position_amt = float(position.get('positionAmt', 0))

                # Skip positions with zero size
                if position_amt == 0:
                    continue

                audit_results['total_positions'] += 1

                # Determine position type
                position_type = 'LONG' if position_amt > 0 else 'SHORT'
                entry_price = float(position.get('entryPrice', 0))

                if not entry_price:
                    audit_results['errors'].append(f"No entry price for {symbol}")
                    continue

                # Check if position has take profit orders
                has_tp = await self._check_position_has_take_profit(symbol)

                if has_tp:
                    audit_results['positions_with_tp'] += 1
                    logger.info(f"Position {symbol} already has take profit order")
                else:
                    audit_results['positions_without_tp'] += 1
                    logger.warning(f"Position {symbol} missing take profit order - creating default 5% TP")

                    # Create default 5% take profit
                    success, tp_order_id = await self.ensure_take_profit_for_position(
                        coin_symbol=symbol.replace('USDT', ''),
                        position_type=position_type,
                        position_size=abs(position_amt),
                        entry_price=entry_price
                    )

                    if success:
                        audit_results['tp_orders_created'] += 1
                        logger.info(f"Created take profit order for {symbol}: {tp_order_id}")
                    else:
                        audit_results['errors'].append(f"Failed to create take profit for {symbol}")

            logger.info(f"Take profit audit completed: {audit_results}")
            return audit_results

        except Exception as e:
            logger.error(f"Error during take profit audit: {e}")
            return {'error': str(e)}

    async def _check_position_has_take_profit(self, trading_pair: str) -> bool:
        """
        Check if a position has active take profit orders.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if position has take profit orders, False otherwise
        """
        try:
            open_orders = await self.binance_exchange.get_all_open_futures_orders()

            if not open_orders:
                return False

            # Check for take profit orders
            for order in open_orders:
                if (order.get('symbol') == trading_pair and
                    order.get('type') == 'TAKE_PROFIT_MARKET'):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking take profit orders for {trading_pair}: {e}")
            return False

    async def update_take_profit(
        self,
        active_trade: Dict,
        new_tp_price: float
    ) -> Tuple[bool, Dict]:
        """
        Update the take profit for an active position.

        Args:
            active_trade: The active trade dictionary
            new_tp_price: The new take profit price

        Returns:
            Tuple of (success, response_data)
        """
        try:
            from src.bot.utils.signal_parser import SignalParser

            parsed_signal = SignalParser.parse_parsed_signal(active_trade.get('parsed_signal'))
            coin_symbol = parsed_signal.get('coin_symbol')
            position_type = parsed_signal.get('position_type', 'LONG')
            position_size = float(active_trade.get('position_size') or 0.0)

            if not coin_symbol or position_size <= 0:
                return False, {"error": "Invalid trade data for take profit update"}

            # Ensure take profit with new price
            success, tp_order_id = await self.ensure_take_profit_for_position(
                coin_symbol=coin_symbol,
                position_type=position_type,
                position_size=position_size,
                entry_price=active_trade.get('entry_price', 0),
                external_tp=new_tp_price
            )

            if success:
                logger.info(f"Successfully updated take profit for {coin_symbol} to {new_tp_price}")
                return True, {"take_profit_order_id": tp_order_id}
            else:
                logger.error(f"Failed to update take profit for {coin_symbol}")
                return False, {"error": "Failed to update take profit"}

        except Exception as e:
            logger.error(f"Error updating take profit: {e}")
            return False, {"error": f"Error updating take profit: {str(e)}"}
