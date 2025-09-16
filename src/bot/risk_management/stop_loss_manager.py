"""
Stop loss management utilities for the trading bot.

This module contains functions for managing stop loss orders including
creation, cancellation, auditing, and verification of stop loss orders.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
FUTURE_ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'


class StopLossManager:
    """
    Core class for managing stop loss orders.
    """

    def __init__(self, exchange):
        """
        Initialize the stop loss manager.

        Args:
            exchange: The exchange instance (Binance, KuCoin, etc.)
        """
        self.exchange = exchange

    def _get_trading_pair(self, coin_symbol: str) -> str:
        """
        Get trading pair format based on exchange type.

        Args:
            coin_symbol: The coin symbol (e.g., 'BTC')

        Returns:
            Trading pair in exchange format
        """
        # Check if exchange has a method to get trading pair format
        if hasattr(self.exchange, 'get_futures_trading_pair'):
            return self.exchange.get_futures_trading_pair(coin_symbol)
        elif hasattr(self.exchange, 'get_trading_pair'):
            return self.exchange.get_trading_pair(coin_symbol)
        else:
            # Default format for most exchanges
            return f"{coin_symbol.upper()}USDT"

    async def ensure_stop_loss_for_position(
        self,
        coin_symbol: str,
        position_type: str,
        position_size: float,
        entry_price: float,
        external_sl: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Ensure a stop loss is in place for a position (supervisor requirement).

        Args:
            coin_symbol: The trading symbol
            position_type: The position type ('LONG' or 'SHORT')
            position_size: The position size
            entry_price: The entry price
            external_sl: External stop loss price from signal (if provided)

        Returns:
            Tuple of (success, stop_loss_order_id)
        """
        try:
            trading_pair = self._get_trading_pair(coin_symbol)

            # Determine stop loss price
            if external_sl is not None and external_sl > 0:
                # Use external SL from signal (supervisor requirement: cancel ours and replace with signal SL)
                logger.info(f"Using external stop loss from signal: {external_sl}")
                sl_price = external_sl
            else:
                # Use default 5% SL from entry price (supervisor requirement)
                from src.bot.utils.price_calculator import PriceCalculator
                sl_price = PriceCalculator.calculate_5_percent_stop_loss(entry_price, position_type)
                if not sl_price:
                    logger.error(f"Failed to calculate default 5% stop loss for {coin_symbol}")
                    return False, None
                logger.info(f"Using default 5% stop loss: {sl_price}")

            # Cancel any existing stop loss orders for this symbol
            await self._cancel_existing_stop_loss_orders(trading_pair)

            # Create new stop loss order
            sl_side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY

            sl_order = await self.exchange.create_futures_order(
                pair=trading_pair,
                side=sl_side,
                order_type=FUTURE_ORDER_TYPE_STOP_MARKET,
                amount=position_size,
                stop_price=sl_price,
                reduce_only=True
            )

            if sl_order and 'orderId' in sl_order:
                stop_loss_order_id = str(sl_order['orderId'])
                logger.info(f"Successfully created stop loss order: {stop_loss_order_id} at {sl_price}")
                return True, stop_loss_order_id
            else:
                logger.error(f"Failed to create stop loss order: {sl_order}")
                return False, None

        except Exception as e:
            logger.error(f"Error ensuring stop loss for {coin_symbol}: {e}")
            return False, None

    async def _cancel_existing_stop_loss_orders(self, trading_pair: str) -> bool:
        """
        Cancel existing stop loss orders for a trading pair.

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

            # Cancel stop loss orders
            cancelled_count = 0
            for order in open_orders:
                if order.get('type') == 'STOP_MARKET':
                    order_id = order.get('orderId')
                    if order_id:
                        cancel_result = await self.binance_exchange.cancel_futures_order(trading_pair, order_id)
                        if cancel_result:
                            logger.info(f"Cancelled existing stop loss order: {order_id}")
                            cancelled_count += 1
                        else:
                            logger.warning(f"Failed to cancel stop loss order: {order_id}")

            logger.info(f"Cancelled {cancelled_count} existing stop loss orders for {trading_pair}")
            return True

        except Exception as e:
            logger.error(f"Error cancelling existing stop loss orders for {trading_pair}: {e}")
            return False

    async def audit_open_positions_for_stop_loss(self) -> Dict[str, Any]:
        """
        Audit all open positions to ensure they have stop loss orders (supervisor requirement).

        Returns:
            Dictionary with audit results
        """
        try:
            logger.info("Starting stop loss audit for all open positions...")

            # Get all open positions
            positions = await self.binance_exchange.get_position_risk()

            audit_results = {
                'total_positions': 0,
                'positions_with_sl': 0,
                'positions_without_sl': 0,
                'sl_orders_created': 0,
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

                # Check if position has stop loss orders
                has_sl = await self._check_position_has_stop_loss(symbol)

                if has_sl:
                    audit_results['positions_with_sl'] += 1
                    logger.info(f"Position {symbol} already has stop loss order")
                else:
                    audit_results['positions_without_sl'] += 1
                    logger.warning(f"Position {symbol} missing stop loss order - creating default 5% SL")

                    # Create default 5% stop loss
                    success, sl_order_id = await self.ensure_stop_loss_for_position(
                        coin_symbol=symbol.replace('USDT', ''),
                        position_type=position_type,
                        position_size=abs(position_amt),
                        entry_price=entry_price
                    )

                    if success:
                        audit_results['sl_orders_created'] += 1
                        logger.info(f"Created stop loss order for {symbol}: {sl_order_id}")
                    else:
                        audit_results['errors'].append(f"Failed to create stop loss for {symbol}")

            logger.info(f"Stop loss audit completed: {audit_results}")
            return audit_results

        except Exception as e:
            logger.error(f"Error during stop loss audit: {e}")
            return {'error': str(e)}

    async def _check_position_has_stop_loss(self, trading_pair: str) -> bool:
        """
        Check if a position has active stop loss orders.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if position has stop loss orders, False otherwise
        """
        try:
            open_orders = await self.binance_exchange.get_all_open_futures_orders()

            if not open_orders:
                return False

            # Check for stop loss orders
            for order in open_orders:
                if (order.get('symbol') == trading_pair and
                    order.get('type') == 'STOP_MARKET'):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking stop loss orders for {trading_pair}: {e}")
            return False

    async def update_stop_loss(
        self,
        active_trade: Dict,
        new_sl_price: float
    ) -> Tuple[bool, Dict]:
        """
        Update the stop loss for an active position.

        Args:
            active_trade: The active trade dictionary
            new_sl_price: The new stop loss price

        Returns:
            Tuple of (success, response_data)
        """
        try:
            from src.bot.utils.signal_parser import SignalParser
            import time

            parsed_signal = SignalParser.parse_parsed_signal(active_trade.get('parsed_signal'))
            coin_symbol = parsed_signal.get('coin_symbol')
            position_type = parsed_signal.get('position_type', 'LONG')
            position_size = float(active_trade.get('position_size') or 0.0)

            if not coin_symbol or position_size <= 0:
                return False, {"error": "Invalid trade data for stop loss update"}

            # Ensure stop loss with new price
            success, sl_order_id = await self.ensure_stop_loss_for_position(
                coin_symbol=coin_symbol,
                position_type=position_type,
                position_size=position_size,
                entry_price=active_trade.get('entry_price', 0),
                external_sl=new_sl_price
            )

            if success:
                logger.info(f"Successfully updated stop loss for {coin_symbol} to {new_sl_price}")
                return True, {"stop_loss_order_id": sl_order_id}
            else:
                logger.error(f"Failed to update stop loss for {coin_symbol}")
                return False, {"error": "Failed to update stop loss"}

        except Exception as e:
            logger.error(f"Error updating stop loss: {e}")
            return False, {"error": f"Error updating stop loss: {str(e)}"}
