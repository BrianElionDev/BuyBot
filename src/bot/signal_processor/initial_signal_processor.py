"""
Initial signal processing utilities for the trading bot.

This module contains functions for processing initial trading signals
including signal validation, trade amount calculation, and initial order placement.
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timezone

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
        self.exchange = trading_engine.exchange
        self.price_service = trading_engine.price_service
        self.fee_calculator = trading_engine.fee_calculator
        self.db_manager = trading_engine.db_manager
        self.trade_cooldowns = trading_engine.trade_cooldowns
        self._symbol_locks: Dict[str, asyncio.Lock] = {}

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
        entry_prices: Optional[List[float]] = None,
        discord_id: Optional[str] = None,
        position_size_override: Optional[float] = None
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Processes a CEX (Binance) signal with position conflict detection.
        This is the main entry point for executing trades based on alerts.
        """
        logger.info(f"--- Processing CEX Signal for {coin_symbol} ---")

        try:
            trader_id = getattr(self.trading_engine, 'trader_id', '') or ''
            lock_key = f"{trader_id.lower()}::{coin_symbol.lower()}"
            if lock_key not in self._symbol_locks:
                self._symbol_locks[lock_key] = asyncio.Lock()
            lock = self._symbol_locks[lock_key]
        except Exception:
            lock = asyncio.Lock()

        async with lock:
            # Check cooldown
            cooldown_key = f"cex_{coin_symbol}"
            if time.time() - self.trade_cooldowns.get(cooldown_key, 0) < self.trading_engine.config.TRADE_COOLDOWN:
                reason = f"Trade cooldown active for {coin_symbol}"
                logger.info(reason)
                return False, reason

            # POSITION CONFLICT DETECTION - Check for existing positions
        try:
            from src.bot.position_management import PositionManager, SymbolCooldownManager

            # Initialize position management components
            position_manager = PositionManager(self.db_manager, self.exchange)
            cooldown_manager = SymbolCooldownManager()

            # Check for position conflicts
            conflict = await position_manager.check_position_conflict(
                coin_symbol, position_type, 999999  # Use temp ID for conflict check
            )

            if conflict:
                logger.info(f"Position conflict detected for {coin_symbol} {position_type}: {conflict.reason}")

                # Handle the conflict based on type
                if conflict.conflict_type == "same_side":
                    # Same side conflict - merge the trades
                    logger.info(f"Merging new trade into existing {position_type} position for {coin_symbol}")

                    # Calculate new position size
                    trade_amount = await self._calculate_trade_amount(
                        coin_symbol, signal_price, quantity_multiplier, True, position_size_override
                    )

                    # Get existing position info
                    existing_position = conflict.existing_position
                    new_total_size = existing_position.size + trade_amount
                    new_weighted_entry = (
                        (existing_position.size * existing_position.entry_price +
                         trade_amount * signal_price) / new_total_size
                    )

                    # Update the existing position (Trade 1)
                    await self._update_existing_position(
                        existing_position.primary_trade_id,
                        new_total_size,
                        new_weighted_entry,
                        signal_price,
                        trade_amount
                    )

                    # Mark Trade 2 as merged (update existing row using discord_id)
                    if discord_id:
                        await self._mark_trade_as_merged(
                            discord_id,  # Use the discord_id from the signal
                            existing_position.primary_trade_id,
                            new_total_size,
                            new_weighted_entry
                        )
                    else:
                        logger.warning("No discord_id provided, cannot mark trade as merged")

                    # Set position cooldown
                    cooldown_manager.set_position_cooldown(coin_symbol, 600)  # 10 minutes

                    return True, {
                        'action': 'merged',
                        'primary_trade_id': existing_position.primary_trade_id,
                        'new_position_size': new_total_size,
                        'new_entry_price': new_weighted_entry,
                        'message': f"Trade merged into existing {position_type} position for {coin_symbol}"
                    }

                elif conflict.conflict_type == "opposite_side":
                    # Opposite side conflict - reject the trade
                    logger.info(f"Rejecting trade due to opposite side conflict: {conflict.reason}")
                    cooldown_manager.set_position_cooldown(coin_symbol, 600)  # 10 minutes
                    return False, f"Trade rejected: {conflict.reason}"

            # No conflict - proceed with normal trade creation
            logger.info(f"No position conflict detected for {coin_symbol} {position_type}")

        except Exception as e:
            logger.error(f"Error in position conflict detection: {e}")
            logger.info("Continuing with normal trade creation due to conflict detection error")

        # --- Pair Validation and Auto-Switching ---
        is_futures = position_type.upper() in ['LONG', 'SHORT']
        trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)

        # CRITICAL: Validate symbol early (before trade calculation) to fail fast
        exchange_info = await self.exchange.get_exchange_info()
        if not exchange_info:
            logger.error(f"Could not retrieve exchange info for {trading_pair}")
            return False, f"Could not retrieve exchange info for {trading_pair}"

        # Check if symbol actually exists in exchange info
        symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == trading_pair), None)
        if not symbol_info:
            logger.error(f"Symbol {trading_pair} does not exist on exchange")
            return False, f"Symbol {trading_pair} does not exist on exchange"

        # Check if symbol is in TRADING status
        if symbol_info.get('status') != 'TRADING':
            logger.error(f"Symbol {trading_pair} is not in TRADING status: {symbol_info.get('status')}")
            return False, f"Symbol {trading_pair} is not in TRADING status"

        # Additional validation: Check if symbol is supported
        is_supported = await self.exchange.is_futures_symbol_supported(trading_pair)
        if not is_supported:
            logger.error(f"Symbol {trading_pair} not supported or not trading on Binance Futures.")
            return False, f"Symbol {trading_pair} not supported or not trading."

        # Get symbol filters early for validation
        filters = await self.exchange.get_futures_symbol_filters(trading_pair)
        if not filters:
            logger.error(f"Could not retrieve symbol filters for {trading_pair}. Cannot proceed with trade.")
            return False, f"Could not retrieve symbol filters for {trading_pair}"

        # Extract validation parameters
        lot_size_filter = filters.get('LOT_SIZE', {})
        min_qty = float(lot_size_filter.get('minQty', 0))
        max_qty = float(lot_size_filter.get('maxQty', float('inf')))
        min_notional_filter = filters.get('MIN_NOTIONAL', {}) if 'MIN_NOTIONAL' in filters else {}
        min_notional_val = min_notional_filter.get('minNotional', min_notional_filter.get('notional', 0))
        min_notional = float(min_notional_val or 0)

        logger.info(f"Processing trade for {trading_pair} ({'Futures' if is_futures else 'Spot'})")
        logger.info(f"Position Type: {position_type}")
        logger.info(f"Signal Price: ${signal_price:.8f}")
        logger.info(f"Order Type: {order_type}")
        if stop_loss:
            logger.info(f"Stop Loss: ${stop_loss}")
        if take_profits:
            logger.info(f"Take Profits: {', '.join([f'${tp:.8f}' for tp in take_profits])}")

        # Get current market price
        current_price = await self.exchange.get_futures_mark_price(f'{coin_symbol.upper()}USDT')
        if not current_price:
            reason = f"Failed to get price for {coin_symbol}"
            logger.error(reason)
            return False, reason

        # --- CRITICAL FIX: Pre-validate minimum quantity BEFORE calculating trade amount ---
        # This prevents wasting time calculating and then failing validation
        if is_futures and min_qty > 0 and min_notional > 0:
            try:
                # Get position_size from config (same logic as _calculate_trade_amount)
                usdt_amount = self.trading_engine.config.TRADE_AMOUNT
                try:
                    from src.services.trader_config_service import trader_config_service
                    trader_id = getattr(self.trading_engine, 'trader_id', None) or ''
                    exch_name = self.exchange.__class__.__name__.lower()
                    exchange_key = 'binance' if 'binance' in exch_name else ('kucoin' if 'kucoin' in exch_name else 'binance')

                    config = await trader_config_service.get_trader_config(trader_id)
                    if config and config.exchange.value == exchange_key:
                        usdt_amount = float(config.position_size)
                        logger.info(f"Using database position_size (final notional): ${usdt_amount} for trader {trader_id}")
                except Exception as e:
                    logger.warning(f"Failed to get position_size from TraderConfigService, using config default: {e}")

                # Calculate what the trade_amount would be
                estimated_trade_amount = usdt_amount / current_price

                # Apply quantity multiplier if enabled
                try:
                    enable_multiplier = bool(getattr(self.trading_engine.config, 'ENABLE_QUANTITY_MULTIPLIER', False))
                except Exception:
                    enable_multiplier = False
                if enable_multiplier and quantity_multiplier and quantity_multiplier > 1:
                    estimated_trade_amount *= quantity_multiplier

                # Check if estimated amount would be below minimums
                min_required_usdt = max(min_qty * current_price, min_notional)

                # AUTO-ADJUSTMENT: If below minimum, automatically adjust to minimum (with risk limits)
                if estimated_trade_amount < min_qty or estimated_trade_amount * current_price < min_notional:
                    # Calculate required minimum
                    required_qty = max(min_qty, min_notional / current_price)
                    required_usdt = required_qty * current_price

                    # Risk limit: Don't auto-adjust if it would exceed 5x the original position size
                    max_allowed_usdt = usdt_amount * 5.0

                    if required_usdt <= max_allowed_usdt:
                        logger.info(f"Auto-adjusting position size from ${usdt_amount:.2f} to ${required_usdt:.2f} to meet minimum requirements")
                        # Update the estimated trade amount
                        estimated_trade_amount = required_qty
                        # Update usdt_amount for subsequent calculations
                        usdt_amount = required_usdt
                        logger.info(f"Adjusted trade_amount to {estimated_trade_amount:.8f} (${required_usdt:.2f} notional)")
                    else:
                        # Exceeds risk limit, reject with clear message
                        error_msg = f"Position size ${usdt_amount:.2f} too small. Minimum required: ${min_required_usdt:.2f}, but auto-adjustment would exceed 2x limit (${max_allowed_usdt:.2f}). Please increase position size manually."
                        logger.warning(error_msg)
                        return False, {"error": error_msg, "retry_suggested": True, "suggested_size": min_required_usdt}

                logger.info(f"Pre-validation passed: estimated trade_amount {estimated_trade_amount:.8f} meets minimums (min_qty: {min_qty}, min_notional: ${min_notional:.2f})")
            except Exception as e:
                logger.warning(f"Pre-validation check failed, proceeding with normal flow: {e}")

        # --- Proximity Check for LIMIT Orders ---
        # Apply platform price-range logic: decide MARKET vs LIMIT and optimal limit price
        try:
            if entry_prices and isinstance(entry_prices, list) and len(entry_prices) > 0:
                upper_bound = max(entry_prices)
                lower_bound = min(entry_prices)
                pos_upper = position_type.upper() == "LONG"
                # Market execution if current within acceptable side bound, else place limit at optimal bound
                if position_type.upper() == "LONG":
                    if current_price <= upper_bound:
                        order_type = "MARKET"
                    else:
                        order_type = "LIMIT"
                        signal_price = upper_bound
                elif position_type.upper() == "SHORT":
                    if current_price >= lower_bound:
                        order_type = "MARKET"
                    else:
                        order_type = "LIMIT"
                        signal_price = lower_bound
            else:
                # Keep existing LIMIT sanity check if no range provided
                if order_type.upper() == "LIMIT":
                    threshold = 0.2
                    price_diff_pct = abs(signal_price - current_price) / current_price if current_price > 0 else 0
                    if current_price and price_diff_pct > threshold:
                        logger.warning(f"LIMIT order price {signal_price} is too far from market price {current_price} ({price_diff_pct*100:.2f}% > {threshold*100}%). Converting to MARKET order.")
                        order_type = "MARKET"
                        logger.info(f"Converted LIMIT order to MARKET order for {coin_symbol} due to price distance")
        except Exception as e:
            logger.warning(f"Price-range decision failed, keeping provided order_type {order_type}: {e}")

        # --- Order Book Liquidity Check ---
        order_book = None
        if hasattr(self.exchange, 'get_order_book'):
            order_book = await self.exchange.get_order_book(trading_pair)
        if not order_book or not order_book.get('bids') or not order_book.get('asks'):
            logger.warning(f"No order book depth for {trading_pair}. Skipping order.")
            return False, {"error": f"No order book depth for {trading_pair}, order skipped."}

        # --- Normalize Stop Loss to float (if provided) ---
        normalized_sl: Optional[float] = None
        try:
            if stop_loss is not None:
                stop_loss_str = str(stop_loss).strip().upper()
                if stop_loss_str in ['BE', 'BREAK_EVEN', 'BREAK-EVEN', 'BREAKEVEN']:
                    # Allow BE stop loss if entry_prices are available
                    if entry_prices and len(entry_prices) > 0:
                        normalized_sl = float(entry_prices[0])
                        logger.info(f"Using entry price {normalized_sl} as break-even stop loss")
                        stop_loss = normalized_sl
                    else:
                        logger.warning(f"Break-even stop loss requires entry price(s) to be specified")
                        return False, {"error": "Break-even stop loss requires entry price(s) to be specified"}

                if normalized_sl is None:
                    normalized_sl = self._normalize_stop_loss_value(stop_loss)
                    if normalized_sl is None or normalized_sl <= 0:
                        logger.warning(f"Parsed stop loss is invalid from value: {stop_loss}")
                    else:
                        stop_loss = normalized_sl
        except Exception as e:
            logger.warning(f"Failed to normalize stop loss '{stop_loss}': {e}")

        # --- Calculate Trade Amount ---
        # Use signal_price (limit price) for LIMIT orders, current_price for MARKET orders
        price_for_calculation = signal_price if order_type.upper() == 'LIMIT' else current_price
        trade_amount = await self._calculate_trade_amount(
            coin_symbol, price_for_calculation, quantity_multiplier, is_futures, position_size_override
        )
        if trade_amount <= 0:
            return False, "Calculated trade amount is zero or negative."

        # --- Validate Trade Amount ---
        # Use signal_price (limit price) for LIMIT orders, current_price for MARKET orders
        price_for_validation = signal_price if order_type.upper() == 'LIMIT' else current_price
        validation_result = await self._validate_trade_amount(
            trading_pair, trade_amount, price_for_validation, min_qty, max_qty, min_notional, is_futures
        )
        if not validation_result[0]:
            error_msg = validation_result[1]
            # If error is a dict with retry suggestions, return it as-is
            if isinstance(error_msg, dict):
                return False, error_msg
            # Otherwise, return as string
            return False, error_msg or "Validation failed"

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

        # If we reach here, non-futures flow is not implemented in this processor
        return False, "Spot trading flow not implemented in InitialSignalProcessor"

    async def _calculate_trade_amount(
        self,
        coin_symbol: str,
        current_price: float,
        quantity_multiplier: Optional[int],
        is_futures: bool,
        position_size_override: Optional[float] = None
    ) -> float:
        """
        Calculate the trade amount based on live database position_size and current price.

        Args:
            position_size_override: Optional override for position size (for retries with adjusted size)
        """
        try:
            # Use override if provided (for retries), otherwise get from database
            if position_size_override is not None:
                usdt_amount = float(position_size_override)
                logger.info(f"Using position_size override (final notional): ${usdt_amount}")
            else:
                # Get position_size from database - REQUIRED, no fallback
                try:
                    from src.services.trader_config_service import trader_config_service
                    trader_id = getattr(self.trading_engine, 'trader_id', None) or ''
                    if not trader_id:
                        logger.error("trader_id not set on trading engine, cannot retrieve position_size")
                        return 0.0

                    exch_name = self.exchange.__class__.__name__.lower()
                    exchange_key = 'binance' if 'binance' in exch_name else ('kucoin' if 'kucoin' in exch_name else 'binance')

                    config = await trader_config_service.get_trader_config(trader_id)
                    if not config:
                        logger.error(f"No trader config found for trader={trader_id} (normalized). Cannot proceed without position_size from trader_exchange_config table.")
                        return 0.0

                    if config.exchange.value != exchange_key:
                        logger.error(f"Trader config exchange mismatch: trader={trader_id} configured for {config.exchange.value}, but order is for {exchange_key}")
                        return 0.0

                    usdt_amount = float(config.position_size)
                    if usdt_amount <= 0:
                        logger.error(f"Invalid position_size from database: {usdt_amount} for trader {trader_id}")
                        return 0.0

                    logger.info(f"Using position_size from trader_exchange_config: ${usdt_amount} for trader {trader_id} on {exchange_key}")
                except Exception as e:
                    logger.error(f"Failed to get position_size from TraderConfigService: {e}", exc_info=True)
                    return 0.0

            # Calculate trade amount based on USDT value and current price
            # IMPORTANT: position_size is FINAL NOTIONAL (no leverage amplification here)
            trade_amount = usdt_amount / current_price
            logger.info(f"Calculated trade amount (no leverage amplification): {trade_amount} {coin_symbol} (${usdt_amount:.2f} / ${current_price:.8f})")

            # Optionally apply quantity multiplier only if explicitly enabled in config
            try:
                enable_multiplier = bool(getattr(self.trading_engine.config, 'ENABLE_QUANTITY_MULTIPLIER', False))
            except Exception:
                enable_multiplier = False
            if enable_multiplier and quantity_multiplier and quantity_multiplier > 1:
                trade_amount *= quantity_multiplier
                logger.info(f"Applied quantity multiplier {quantity_multiplier}: {trade_amount} {coin_symbol}")

            # Auto-bump to meet minimum requirements if needed
            if is_futures:
                try:
                    trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)
                    filters = await self.exchange.get_futures_symbol_filters(trading_pair)
                    if filters:
                        lot_size_filter = filters.get('LOT_SIZE', {})
                        min_qty = float(lot_size_filter.get('minQty', 0))
                        min_notional_filter = filters.get('MIN_NOTIONAL', {}) if 'MIN_NOTIONAL' in filters else {}
                        min_notional_val = min_notional_filter.get('minNotional', min_notional_filter.get('notional', 0))
                        min_notional = float(min_notional_val or 0)

                        # Check if trade_amount meets minimums
                        if min_qty > 0 and min_notional > 0:
                            if trade_amount < min_qty or trade_amount * current_price < min_notional:
                                # Calculate required minimum
                                required_qty = max(min_qty, min_notional / current_price)
                                required_usdt = required_qty * current_price

                                # Risk limit: Don't auto-adjust if it would exceed 5x the original position size
                                max_allowed_usdt = usdt_amount * 5.0

                                if required_usdt <= max_allowed_usdt:
                                    logger.info(f"Auto-adjusting trade amount from {trade_amount:.8f} to {required_qty:.8f} to meet minimum requirements (${required_usdt:.2f} notional)")
                                    trade_amount = required_qty
                                else:
                                    # Exceeds risk limit, return 0.0 to trigger validation error
                                    logger.warning(f"Auto-adjustment would exceed 5x limit (${required_usdt:.2f} > ${max_allowed_usdt:.2f}), returning 0.0")
                                    return 0.0
                except Exception as e:
                    logger.warning(f"Auto-bump check failed, proceeding with calculated amount: {e}")

            return float(trade_amount)

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
                    logger.warning(f"Order notional {notional_value:.2f} below minimum {min_notional:.2f} for {trading_pair}. Skipping order.")
                    # Calculate required minimum trade amount for retry suggestion
                    required_trade_amount = min_notional / current_price if current_price > 0 else min_qty
                    required_notional = required_trade_amount * current_price
                    return False, {
                        "error": f"Notional {notional_value:.2f} below minimum {min_notional:.2f} for {trading_pair}, order skipped.",
                        "retry_suggested": True,
                        "suggested_size": required_notional,
                        "code": -4164
                    }

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
            positions = await self.exchange.get_position_risk(symbol=trading_pair)
            current_position_size = 0.0
            actual_leverage = 1.0
            try:
                # Prefer TraderConfigService for consistent leverage resolution
                from src.services.trader_config_service import trader_config_service
                trader_id = getattr(self.trading_engine, 'trader_id', None) or ''
                exch_name = self.exchange.__class__.__name__.lower()
                exchange_key = 'binance' if 'binance' in exch_name else ('kucoin' if 'kucoin' in exch_name else 'binance')

                config = await trader_config_service.get_trader_config(trader_id)
                if config and config.exchange.value == exchange_key:
                    actual_leverage = float(config.leverage)
                else:
                    # Fallback to runtime_config if service not available/mismatch
                    from src.config.runtime_config import runtime_config as _rc
                    if _rc:
                        cfg = await _rc.get_trader_exchange_config(trader_id, exchange_key)
                        if isinstance(cfg, dict):
                            actual_leverage = float(cfg.get('leverage', 1.0))
                        else:
                            actual_leverage = 1.0
                    else:
                        logger.warning("No trader config available; defaulting leverage to 1x for validation")
            except Exception as e:
                logger.warning(f"Failed to get leverage for validation: {e}")

            for position in positions or []:
                if not isinstance(position, dict):
                    continue
                if position.get('symbol') == trading_pair:
                    current_position_size = abs(float(position.get('positionAmt', 0)))
                    # Get actual leverage from position (fallback to previously resolved value)
                    actual_leverage = float(position.get('leverage', actual_leverage))
                    break

            # Calculate new total position size
            new_total_size = current_position_size + trade_amount

            # Get account leverage info
            if hasattr(self.exchange, 'client') and self.exchange.client:
                account_info = await self.exchange.client.futures_account()
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

            leverage_value: Optional[float] = None
            if is_futures:
                try:
                    # Resolve leverage via TraderConfigService with robust normalization/variants
                    from src.services.trader_config_service import trader_config_service
                    trader_id = getattr(self.trading_engine, 'trader_id', None) or ''
                    exch_name = self.exchange.__class__.__name__.lower()
                    exchange_key = 'binance' if 'binance' in exch_name else ('kucoin' if 'kucoin' in exch_name else 'binance')

                    config = await trader_config_service.get_trader_config(trader_id)
                    if config and config.exchange.value == exchange_key:
                        leverage_value = float(config.leverage)
                        logger.info(f"Leverage from TraderConfigService for trader {trader_id} on {exchange_key}: {leverage_value}")
                    else:
                        # Fall back to runtime_config direct call only if necessary
                        from src.config.runtime_config import runtime_config as _rc
                        if _rc:
                            cfg = await _rc.get_trader_exchange_config(trader_id, exchange_key)
                            if isinstance(cfg, dict):
                                leverage_value = float(cfg.get('leverage', 1.0))
                            else:
                                leverage_value = 1.0
                            logger.info(f"Leverage from RuntimeConfig fallback for trader {trader_id} on {exchange_key}: {leverage_value}")
                        else:
                            logger.warning("No trader config available; defaulting leverage to 1x")
                            leverage_value = 1.0
                except Exception as e:
                    logger.error(f"Failed to resolve leverage from services: {e}")
                    leverage_value = 1.0

            # IMPORTANT: Do not modify trade_amount using leverage. Leverage is set on the
            # exchange for margin/risk but position_size already represents final notional.

            is_kucoin = 'kucoin' in self.exchange.__class__.__name__.lower()
            if is_futures and not is_kucoin:
                try:
                    if leverage_value and hasattr(self.exchange, 'set_futures_leverage'):
                        await self.exchange.set_futures_leverage(trading_pair, int(leverage_value))
                except Exception as e:
                    logger.warning(f"Failed to set leverage {leverage_value} for {trading_pair}: {e}")
            if order_type.upper() == 'MARKET':
                if is_kucoin:
                    order = await self.exchange.create_futures_order(
                        pair=trading_pair,
                        side=order_side,
                        order_type='MARKET',
                        amount=trade_amount,
                        leverage=leverage_value
                    )
                else:
                    order = await self.exchange.create_futures_order(
                        pair=trading_pair,
                        side=order_side,
                        order_type='MARKET',
                        amount=trade_amount
                    )
            else:  # LIMIT
                if is_kucoin:
                    order = await self.exchange.create_futures_order(
                        pair=trading_pair,
                        side=order_side,
                        order_type='LIMIT',
                        amount=trade_amount,
                        price=signal_price,
                        leverage=leverage_value
                    )
                else:
                    order = await self.exchange.create_futures_order(
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

            try:
                from src.services.notifications.trade_notification_service import trade_notification_service, TradeExecutionData
                from typing import cast

                order_dict = cast(dict, order)
                order_id = order_dict.get('orderId', 'Unknown')

                # For MARKET orders, use avgPrice if available (actual fill price), otherwise fallback to price or signal_price
                fill_price = None
                avg_price_val = order_dict.get('avgPrice')
                price_val = order_dict.get('price')
                try:
                    if isinstance(avg_price_val, (int, float, str)) and float(avg_price_val) > 0:
                        fill_price = float(avg_price_val)
                    elif isinstance(price_val, (int, float, str)) and float(price_val) > 0:
                        fill_price = float(price_val)
                except Exception:
                    fill_price = None
                if fill_price is None:
                    fill_price = signal_price

                # Use executedQty if available (actual filled quantity), otherwise origQty or trade_amount
                fill_quantity = None
                executed_qty_val = order_dict.get('executedQty')
                orig_qty_val = order_dict.get('origQty')
                try:
                    if isinstance(executed_qty_val, (int, float, str)) and float(executed_qty_val) > 0:
                        fill_quantity = float(executed_qty_val)
                    elif isinstance(orig_qty_val, (int, float, str)) and float(orig_qty_val) > 0:
                        fill_quantity = float(orig_qty_val)
                except Exception:
                    fill_quantity = None
                else:
                    fill_quantity = trade_amount

                # Determine exchange name from exchange object
                exchange_name = "Binance" if "Binance" in self.exchange.__class__.__name__ else "Kucoin"

                notification_data = TradeExecutionData(
                    symbol=trading_pair,
                    position_type=position_type,
                    entry_price=float(fill_price if fill_price is not None else signal_price),
                    quantity=float(fill_quantity if fill_quantity is not None else trade_amount),
                    order_id=str(order_id),
                    exchange=exchange_name,
                    timestamp=datetime.now(timezone.utc)
                )

                asyncio.create_task(trade_notification_service.notify_trade_execution_success(notification_data))

            except Exception as e:
                logger.error(f"Failed to send trade execution notification: {e}")

            # Create TP/SL orders: enforce platform defaults (5%) and apply overrides from signal
            tp_sl_orders = []
            stop_loss_order_id = None
            try:
                # Determine effective entry for default calculations
                effective_entry = float(fill_price if fill_price is not None else signal_price)
            except Exception:
                effective_entry = float(signal_price)

            # Compute defaults if not provided by the signal
            default_sl = None
            default_tp = None
            try:
                from src.bot.utils.price_calculator import PriceCalculator
                if stop_loss is None and effective_entry > 0:
                    default_sl = PriceCalculator.calculate_5_percent_stop_loss(effective_entry, position_type)
                if (not take_profits or len(take_profits) == 0) and effective_entry > 0:
                    default_tp = PriceCalculator.calculate_5_percent_take_profit(effective_entry, position_type)
            except Exception as e:
                logger.warning(f"Failed default TP/SL computation: {e}")

            # Apply platform rule:
            # - Always place an SL: use provided SL if present else default 5%
            # - TP: if signal TP provided, place it for 50% of position; else place default 5% for 100%
            final_sl = None
            if stop_loss is not None:
                try:
                    final_sl = float(stop_loss)
                except Exception:
                    final_sl = default_sl
            else:
                final_sl = default_sl

            final_tps: List[float] = []
            partial_tp_size = None
            if take_profits and len(take_profits) > 0:
                # Use only first TP from signal and make it 50% size
                try:
                    final_tps = [float(take_profits[0])]
                except Exception:
                    final_tps = []
                partial_tp_size = float(trade_amount) * 0.5
            elif default_tp is not None:
                final_tps = [float(default_tp)]
                partial_tp_size = None  # full size by default

            # Create orders via order creator (handles partial TP and full-size SL internally)
            if final_sl is not None or final_tps:
                # If partial TP size is set, temporarily pass that as position_size for TP creation,
                # and rely on internal logic to place SL for full size.
                tp_size_to_use = float(trade_amount if partial_tp_size is None else partial_tp_size)
                tp_sl_orders, stop_loss_order_id = await self.trading_engine._create_tp_sl_orders(
                    trading_pair, position_type, tp_size_to_use, final_tps, final_sl
                )

            # Update cooldown
            self.trade_cooldowns[f"cex_{coin_symbol}"] = time.time()

            logger.info(f"Trade execution completed successfully for {coin_symbol}")

            # Return complete order response with all exchange data
            response_data = {
                **order,  # Include ALL fields from exchange order response
                'order_id': order['orderId'],
                'tp_sl_orders': tp_sl_orders,
                'stop_loss_order_id': stop_loss_order_id,
                'status': 'OPEN'
            }

            # Final safety validation to prevent half-empty PENDING-like records
            try:
                essential_ok = (
                    bool(trading_pair) and
                    bool(response_data.get('order_id')) and
                    position_type.upper() in ('LONG', 'SHORT')
                )
                if not essential_ok:
                    logger.error(f"Essential fields missing for trade creation: {response_data}")
                    return False, "Essential fields missing; refusing to create incomplete trade"
            except Exception:
                pass

            return True, response_data

        except Exception as e:
            logger.error(f"Error executing trade: {e}", exc_info=True)
            return False, f"Error executing trade: {str(e)}"

    def _normalize_stop_loss_value(self, value: Union[float, str]) -> Optional[float]:
        """Parse stop loss that may include percentage e.g. '40190 (7.14%)' into float price."""
        try:
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip()
            # Extract first floating number encountered
            import re
            m = re.search(r"-?\d+(?:\.\d+)?", text)
            if not m:
                return None
            return float(m.group(0))
        except Exception:
            return None

    async def _update_existing_position(
        self,
        primary_trade_id: int,
        new_total_size: float,
        new_weighted_entry: float,
        signal_price: float,
        trade_amount: float
    ) -> bool:
        """
        Update an existing position with new trade data.

        Args:
            primary_trade_id: ID of the primary trade to update
            new_total_size: New total position size
            new_weighted_entry: New weighted average entry price
            signal_price: Price of the new signal
            trade_amount: Amount of the new trade

        Returns:
            True if successful, False otherwise
        """
        try:
            from datetime import datetime, timezone

            # Update the primary trade with merged data
            update_data = {
                'position_size': new_total_size,
                'entry_price': new_weighted_entry,
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'merged_trades_count': 1,  # Will be incremented by database operation
                'last_merge_at': datetime.now(timezone.utc).isoformat()
            }

            # Update the trade in database
            success = await self.db_manager.update_trade(primary_trade_id, update_data)

            if success:
                logger.info(f"Successfully updated position {primary_trade_id} with merged trade data")
                logger.info(f"New size: {new_total_size}, New entry: {new_weighted_entry}")
                return True
            else:
                logger.error(f"Failed to update position {primary_trade_id}")
                return False

        except Exception as e:
            logger.error(f"Error updating existing position: {e}")
            return False

    async def _mark_trade_as_merged(
        self,
        discord_id: str,
        primary_trade_id: int,
        new_total_size: float,
        new_weighted_entry: float
    ) -> bool:
        """
        Mark a trade as merged by updating its existing row using discord_id.

        Args:
            discord_id: Discord ID of the trade to mark as merged
            primary_trade_id: ID of the primary trade it was merged into
            new_total_size: New total position size after merge
            new_weighted_entry: New weighted average entry price after merge

        Returns:
            True if successful, False otherwise
        """
        try:
            from datetime import datetime, timezone

            # Find the trade by discord_id first
            trade = await self.db_manager.find_trade_by_discord_id(discord_id)
            if not trade:
                logger.error(f"Could not find trade with discord_id: {discord_id}")
                return False

            trade_id = trade['id']

            # Update the trade to mark it as merged
            merge_data = {
                'status': 'MERGED',
                'merged_into_trade_id': primary_trade_id,
                'merge_reason': 'Position aggregation - same symbol/side conflict',
                'merged_at': datetime.now(timezone.utc).isoformat(),
                'position_size': 0,  # Set to 0 since it's merged
                'entry_price': 0,    # Set to 0 since it's merged
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Update the existing trade row
            success = await self.db_manager.update_existing_trade(trade_id, merge_data)

            if success:
                logger.info(f"Successfully marked trade {trade_id} (discord_id: {discord_id}) as merged into {primary_trade_id}")
                logger.info(f"New aggregated position: {new_total_size} @ {new_weighted_entry}")
                return True
            else:
                logger.error(f"Failed to mark trade {trade_id} as merged")
                return False

        except Exception as e:
            logger.error(f"Error marking trade as merged: {e}")
            return False
