"""
Initial signal processing utilities for the trading bot.

This module contains functions for processing initial trading signals
including signal validation, trade amount calculation, and initial order placement.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple, Union

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'


class InitialSignalProcessor:
    """
    Core class for processing initial trading signals.
    """

    def __init__(self, trading_engine):
        """
        Initialize the initial signal processor.

        Args:
            trading_engine: The trading engine instance
        """
        self.trading_engine = trading_engine
        self.binance_exchange = trading_engine.binance_exchange
        self.price_service = trading_engine.price_service
        self.fee_calculator = trading_engine.fee_calculator
        self.db_manager = trading_engine.db_manager
        self.trade_cooldowns = trading_engine.trade_cooldowns

    async def process_signal(
        self,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        order_type: str = "MARKET",
        stop_loss: Optional[Union[float, str]] = None,
        take_profits: Optional[List[float]] = None,
        dca_range: Optional[List[float]] = None,
        client_order_id: Optional[str] = None,
        price_threshold_override: Optional[float] = None,
        quantity_multiplier: Optional[int] = None,
        entry_prices: Optional[List[float]] = None
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Processes a CEX (Binance) signal.
        This is the main entry point for executing trades based on alerts.
        """
        logger.info(f"--- Processing CEX Signal for {coin_symbol} ---")

        # Check cooldown
        cooldown_key = f"cex_{coin_symbol}"
        if time.time() - self.trade_cooldowns.get(cooldown_key, 0) < self.trading_engine.config.TRADE_COOLDOWN:
            reason = f"Trade cooldown active for {coin_symbol}"
            logger.info(reason)
            return False, reason

        # --- Pair Validation and Auto-Switching ---
        is_futures = position_type.upper() in ['LONG', 'SHORT']
        trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

        # Enhanced symbol validation
        is_supported = await self.binance_exchange.is_futures_symbol_supported(trading_pair)
        if not is_supported:
            logger.error(f"Symbol {trading_pair} not supported or not trading on Binance Futures.")
            return False, f"Symbol {trading_pair} not supported or not trading."

        # Get symbol filters early for validation
        filters = await self.binance_exchange.get_futures_symbol_filters(trading_pair)
        if not filters:
            logger.error(f"Could not retrieve symbol filters for {trading_pair}. Cannot proceed with trade.")
            return False, f"Could not retrieve symbol filters for {trading_pair}"

        # Check if symbol is in TRADING status
        exchange_info = await self.binance_exchange.get_exchange_info()
        if exchange_info:
            symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == trading_pair), None)
            if symbol_info and symbol_info.get('status') != 'TRADING':
                logger.error(f"Symbol {trading_pair} is not in TRADING status: {symbol_info.get('status')}")
                return False, f"Symbol {trading_pair} is not in TRADING status"

        # Extract validation parameters
        lot_size_filter = filters.get('LOT_SIZE', {})
        min_qty = float(lot_size_filter.get('minQty', 0))
        max_qty = float(lot_size_filter.get('maxQty', float('inf')))
        min_notional = float(filters.get('MIN_NOTIONAL', {}).get('notional', 0)) if 'MIN_NOTIONAL' in filters else 0

        logger.info(f"Processing trade for {trading_pair} ({'Futures' if is_futures else 'Spot'})")
        logger.info(f"Position Type: {position_type}")
        logger.info(f"Signal Price: ${signal_price:.8f}")
        logger.info(f"Order Type: {order_type}")
        if stop_loss:
            logger.info(f"Stop Loss: ${stop_loss}")
        if take_profits:
            logger.info(f"Take Profits: {', '.join([f'${tp:.8f}' for tp in take_profits])}")

        # Get current market price
        current_price = await self.binance_exchange.get_futures_mark_price(f'{coin_symbol.upper()}USDT')
        if not current_price:
            reason = f"Failed to get price for {coin_symbol}"
            logger.error(reason)
            return False, reason

        # --- Proximity Check for LIMIT Orders ---
        if order_type.upper() == "LIMIT":
            market_price = await self.price_service.get_coin_price(coin_symbol)
            threshold = 0.1  # 10%
            if market_price and abs(signal_price - market_price) / market_price > threshold:
                logger.warning(f"LIMIT order price {signal_price} is too far from market price {market_price} (>{threshold*100}%). Skipping order.")
                return False, {"error": f"Limit price {signal_price} too far from market price {market_price}, order skipped."}

        # --- Order Book Liquidity Check ---
        order_book = None
        if hasattr(self.binance_exchange, 'get_order_book'):
            order_book = await self.binance_exchange.get_order_book(trading_pair)
        if not order_book or not order_book.get('bids') or not order_book.get('asks'):
            logger.warning(f"No order book depth for {trading_pair}. Skipping order.")
            return False, {"error": f"No order book depth for {trading_pair}, order skipped."}

        # --- Calculate Trade Amount ---
        trade_amount = await self._calculate_trade_amount(
            coin_symbol, current_price, quantity_multiplier, is_futures
        )
        if trade_amount <= 0:
            return False, "Calculated trade amount is zero or negative."

        # --- Validate Trade Amount ---
        validation_result = await self._validate_trade_amount(
            trading_pair, trade_amount, current_price, min_qty, max_qty, min_notional, is_futures
        )
        if not validation_result[0]:
            return False, validation_result[1] or "Validation failed"

        # --- Position/Leverage Validation ---
        if is_futures:
            position_validation = await self._validate_position_limits(
                trading_pair, trade_amount, current_price
            )
            if not position_validation[0]:
                return False, position_validation[1] or "Position validation failed"

        # --- Execute Trade ---
        return await self._execute_trade(
            trading_pair, coin_symbol, signal_price, position_type, order_type,
            trade_amount, stop_loss, take_profits, entry_prices, is_futures
        )

    async def _calculate_trade_amount(
        self,
        coin_symbol: str,
        current_price: float,
        quantity_multiplier: Optional[int],
        is_futures: bool
    ) -> float:
        """
        Calculate the trade amount based on USDT value and current price.
        """
        try:
            # Calculate trade amount based on USDT value and current price
            usdt_amount = self.trading_engine.config.TRADE_AMOUNT
            trade_amount = usdt_amount / current_price
            logger.info(f"Calculated trade amount: {trade_amount} {coin_symbol} (${usdt_amount:.2f} / ${current_price:.8f})")

            # Apply quantity multiplier if specified (for memecoins)
            if quantity_multiplier and quantity_multiplier > 1:
                trade_amount *= quantity_multiplier
                logger.info(f"Applied quantity multiplier {quantity_multiplier}: {trade_amount} {coin_symbol}")

            # Get symbol filters for precision formatting
            quantities = await self.binance_exchange.calculate_min_max_market_order_quantity(f"{coin_symbol}USDT")
            minQuantity = float(quantities[0])  # First element is min_qty
            maxQuantity = float(quantities[1])  # Second element is max_qty
            print(f"Min Quantity: {minQuantity}, Max Quantity: {maxQuantity}")
            trade_amount = max(minQuantity, min(maxQuantity, trade_amount))
            print(f"Adjusted trade amount: {trade_amount}")

            return trade_amount

        except Exception as e:
            logger.error(f"Failed to calculate trade amount: {e}", exc_info=True)
            return 0.0

    async def _validate_trade_amount(
        self,
        trading_pair: str,
        trade_amount: float,
        current_price: float,
        min_qty: float,
        max_qty: float,
        min_notional: float,
        is_futures: bool
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate the trade amount against exchange limits.
        """
        try:
            if is_futures:
                # Check quantity bounds with detailed logging
                if trade_amount < min_qty:
                    logger.warning(f"Order quantity {trade_amount} below minimum {min_qty} for {trading_pair}. Skipping order.")
                    return False, f"Quantity {trade_amount} below minimum {min_qty} for {trading_pair}, order skipped."

                if trade_amount > max_qty:
                    logger.warning(f"Order quantity {trade_amount} above maximum {max_qty} for {trading_pair}. Skipping order.")
                    return False, f"Quantity {trade_amount} above maximum {max_qty} for {trading_pair}, order skipped."

                # Check notional value
                notional_value = trade_amount * current_price
                if notional_value < min_notional:
                    logger.warning(f"Order notional {notional_value} below minimum {min_notional} for {trading_pair}. Skipping order.")
                    return False, f"Notional {notional_value} below minimum {min_notional} for {trading_pair}, order skipped."

                logger.info(f"Quantity validation passed for {trading_pair}: {trade_amount} (min: {min_qty}, max: {max_qty}, notional: {notional_value:.2f})")
            else:
                logger.warning(f"Could not get symbol filters for {trading_pair}. Proceeding with order.")

            return True, None

        except Exception as e:
            logger.error(f"Error validating trade amount: {e}")
            return False, f"Error in validation: {str(e)}"

    async def _validate_position_limits(
        self,
        trading_pair: str,
        trade_amount: float,
        current_price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate position limits for futures trading.
        """
        try:
            # Get current positions for this symbol
            positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
            current_position_size = 0.0
            actual_leverage = self.trading_engine.config.DEFAULT_LEVERAGE

            for position in positions:
                if position.get('symbol') == trading_pair:
                    current_position_size = abs(float(position.get('positionAmt', 0)))
                    # Get actual leverage from position
                    actual_leverage = float(position.get('leverage', self.trading_engine.config.DEFAULT_LEVERAGE))
                    break

            # Calculate new total position size
            new_total_size = current_position_size + trade_amount

            # Get account leverage info
            if self.binance_exchange.client:
                account_info = await self.binance_exchange.client.futures_account()
                max_leverage = float(account_info.get('maxLeverage', 125)) if account_info else 125

                # Estimate max position size based on leverage and balance
                total_balance = float(account_info.get('totalWalletBalance', 0)) if account_info else 0
                max_position_value = total_balance * max_leverage
                max_position_size = max_position_value / current_price

                if new_total_size > max_position_size:
                    logger.warning(f"Order would exceed max position size for {trading_pair}. Current: {current_position_size}, New: {new_total_size}, Max: {max_position_size}. Skipping order.")
                    return False, f"Would exceed max position size for {trading_pair}, order skipped."

                logger.info(f"Position validation passed for {trading_pair}. Current: {current_position_size}, New: {new_total_size}, Max: {max_position_size}")

            return True, None

        except Exception as e:
            logger.error(f"Error validating position limits: {e}")
            return False, f"Error in position validation: {str(e)}"

    async def _execute_trade(
        self,
        trading_pair: str,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        order_type: str,
        trade_amount: float,
        stop_loss: Optional[Union[float, str]],
        take_profits: Optional[List[float]],
        entry_prices: Optional[List[float]],
        is_futures: bool
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Execute the actual trade with order placement and TP/SL setup.
        """
        try:
            # Determine order side
            if position_type.upper() == 'LONG':
                order_side = SIDE_BUY
            elif position_type.upper() == 'SHORT':
                order_side = SIDE_SELL
            else:
                return False, f"Invalid position type: {position_type}"

            # Create the main order
            if order_type.upper() == 'MARKET':
                order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=order_side,
                    order_type='MARKET',
                    amount=trade_amount
                )
            else:  # LIMIT
                order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=order_side,
                    order_type='LIMIT',
                    amount=trade_amount,
                    price=signal_price
                )

            if not order or 'orderId' not in order:
                logger.error(f"Failed to create order for {trading_pair}: {order}")
                return False, f"Failed to create order: {order}"

            logger.info(f"Successfully created {order_type} order: {order['orderId']} for {trading_pair}")

            # Create TP/SL orders if specified
            tp_sl_orders = []
            stop_loss_order_id = None
            if stop_loss or take_profits:
                tp_sl_orders, stop_loss_order_id = await self.trading_engine._create_tp_sl_orders(
                    trading_pair, position_type, trade_amount, take_profits, stop_loss
                )

            # Update cooldown
            self.trade_cooldowns[f"cex_{coin_symbol}"] = time.time()

            logger.info(f"Trade execution completed successfully for {coin_symbol}")
            return True, {
                'order_id': order['orderId'],
                'tp_sl_orders': tp_sl_orders,
                'stop_loss_order_id': stop_loss_order_id,
                'status': 'OPEN'
            }

        except Exception as e:
            logger.error(f"Error executing trade: {e}", exc_info=True)
            return False, f"Error executing trade: {str(e)}"
