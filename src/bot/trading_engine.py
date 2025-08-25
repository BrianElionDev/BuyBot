import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

# Import DatabaseManager type for type hints only
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_bot.database import DatabaseManager
from src.exchange.binance_exchange import BinanceExchange
from src.services.price_service import PriceService
from src.exchange.fee_calculator import FixedFeeCalculator, BinanceFuturesFeeCalculator

from config import settings as config
import json

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'
FUTURE_ORDER_TYPE_MARKET = 'MARKET'
FUTURE_ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'

class TradingEngine:
    """
    The core logic for processing signals and executing trades.
    """
    def __init__(self, price_service: PriceService, binance_exchange: BinanceExchange, db_manager: 'DatabaseManager'):
        self.price_service = price_service
        self.binance_exchange = binance_exchange
        self.db_manager = db_manager
        self.trade_cooldowns = {}
        # Choose fee calculator based on configuration
        if config.USE_FIXED_FEE_CALCULATOR:
            self.fee_calculator = FixedFeeCalculator(fee_rate=config.FIXED_FEE_RATE)
            logger.info(f"Using FixedFeeCalculator with {config.FIXED_FEE_RATE * 100}% fee cap")
        else:
            self.fee_calculator = BinanceFuturesFeeCalculator()
            logger.info("Using BinanceFuturesFeeCalculator with complex fee formulas")
        logger.info("TradingEngine initialized.")

    def _parse_parsed_signal(self, parsed_signal_data) -> Dict[str, Any]:
        """Parse the parsed_signal JSON string into a dictionary."""
        if isinstance(parsed_signal_data, dict):
            return parsed_signal_data
        elif isinstance(parsed_signal_data, str):
            try:
                return json.loads(parsed_signal_data)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse parsed_signal JSON: {parsed_signal_data}")
                return {}
        else:
            logger.warning(f"Unexpected parsed_signal type: {type(parsed_signal_data)}")
            return {}

    def _safe_parse_binance_response(self, binance_response) -> Dict:
        """Safely parse binance_response field which is stored as text but may contain JSON."""
        if isinstance(binance_response, dict):
            return binance_response
        elif isinstance(binance_response, str):
            # Handle empty or invalid strings
            if not binance_response or binance_response.strip() == '':
                return {}

            # Try to parse as JSON
            try:
                return json.loads(binance_response.strip())
            except (json.JSONDecodeError, ValueError):
                # If it's not valid JSON, treat it as a plain text error message
                return {"error": binance_response.strip()}
        else:
            return {}

    def _handle_price_range_logic(
        self,
        entry_prices: Optional[List[float]],
        order_type: str,
        position_type: str,
        current_price: float
    ) -> Tuple[Optional[float], str]:
        """
        Handle price range logic for different order types.

        Args:
            entry_prices: List of entry prices (can be a range)
            order_type: MARKET or LIMIT
            position_type: LONG or SHORT
            current_price: Current market price

        Returns:
            Tuple of (effective_price, decision_reason)
        """
        if not entry_prices or len(entry_prices) == 0:
            return current_price, "No entry prices provided, using current market price"

        # Single price (no range)
        if len(entry_prices) == 1:
            return entry_prices[0], "Single entry price provided"

        # Price range detected
        if len(entry_prices) == 2:
            lower_bound = min(entry_prices)
            upper_bound = max(entry_prices)

            if order_type.upper() == "MARKET":
                # Market orders should only execute if current price is within the specified range
                if position_type.upper() == "LONG":
                    # For long positions, only execute if current price is at or below the upper bound
                    if current_price <= upper_bound:
                        return current_price, f"Market order - executing at current price ${current_price:.8f} (within range ${lower_bound:.8f}-${upper_bound:.8f})"
                    else:
                        return None, f"Market order REJECTED - current price ${current_price:.8f} above range ${lower_bound:.8f}-${upper_bound:.8f}"
                elif position_type.upper() == "SHORT":
                    # For short positions, only execute if current price is at or above the lower bound
                    if current_price >= lower_bound:
                        return current_price, f"Market order - executing at current price ${current_price:.8f} (within range ${lower_bound:.8f}-${upper_bound:.8f})"
                    else:
                        return None, f"Market order REJECTED - current price ${current_price:.8f} below range ${lower_bound:.8f}-${upper_bound:.8f}"
                else:
                    # Unknown position type - execute at current price
                    return current_price, f"Market order - executing at current price ${current_price:.8f} (unknown position type)"

            elif order_type.upper() == "LIMIT":
                if position_type.upper() == "LONG":
                    # For long positions, place limit at upper bound (best buy price)
                    effective_price = upper_bound
                    reason = f"Long limit order - placing at upper bound ${upper_bound:.8f} (range: ${lower_bound:.8f}-${upper_bound:.8f})"

                    # Optional: Only place if current price is above the range (waiting for price to drop)
                    if current_price > upper_bound:
                        reason += f" - Current price ${current_price:.8f} above range, waiting for entry"
                    elif current_price < lower_bound:
                        reason += f" - Current price ${current_price:.8f} below range, order may fill immediately"
                    else:
                        reason += f" - Current price ${current_price:.8f} within range"

                elif position_type.upper() == "SHORT":
                    # For short positions, place limit at lower bound (best sell price)
                    effective_price = lower_bound
                    reason = f"Short limit order - placing at lower bound ${lower_bound:.8f} (range: ${lower_bound:.8f}-${upper_bound:.8f})"

                    # Optional: Only place if current price is below the range (waiting for price to rise)
                    if current_price < lower_bound:
                        reason += f" - Current price ${current_price:.8f} below range, waiting for entry"
                    elif current_price > upper_bound:
                        reason += f" - Current price ${current_price:.8f} above range, order may fill immediately"
                    else:
                        reason += f" - Current price ${current_price:.8f} within range"
                else:
                    # Default to first price for unknown position types
                    effective_price = entry_prices[0]
                    reason = f"Unknown position type '{position_type}' - using first price ${effective_price:.8f}"

                return effective_price, reason
            else:
                # Unknown order type
                return entry_prices[0], f"Unknown order type '{order_type}' - using first price ${entry_prices[0]:.8f}"

        # More than 2 prices (complex range or multiple entry points)
        if len(entry_prices) > 2:
            if order_type.upper() == "MARKET":
                return current_price, f"Market order with multiple prices - executing at current price ${current_price:.8f}"
            else:
                # For limit orders, use the most favorable price based on position type
                if position_type.upper() == "LONG":
                    effective_price = min(entry_prices)  # Best buy price
                    reason = f"Long limit order with multiple prices - using lowest price ${effective_price:.8f}"
                elif position_type.upper() == "SHORT":
                    effective_price = max(entry_prices)  # Best sell price
                    reason = f"Short limit order with multiple prices - using highest price ${effective_price:.8f}"
                else:
                    effective_price = entry_prices[0]
                    reason = f"Unknown position type with multiple prices - using first price ${effective_price:.8f}"

                return effective_price, reason

        # Fallback
        return current_price, "Fallback to current market price"

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
        if time.time() - self.trade_cooldowns.get(cooldown_key, 0) < config.TRADE_COOLDOWN:
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

        # --- Get order book for liquidity check (add method if needed) ---
        order_book = None
        if hasattr(self.binance_exchange, 'get_order_book'):
            order_book = await self.binance_exchange.get_order_book(trading_pair)
        # If not implemented, skip this check

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
        trade_amount = 0.0
        try:
            # Calculate trade amount based on USDT value and current price
            usdt_amount = config.TRADE_AMOUNT
            trade_amount = usdt_amount / current_price
            logger.info(f"Calculated trade amount: {trade_amount} {coin_symbol} (${usdt_amount:.2f} / ${current_price:.8f})")

            # Apply quantity multiplier if specified (for memecoins)
            if quantity_multiplier and quantity_multiplier > 1:
                trade_amount *= quantity_multiplier
                logger.info(f"Applied quantity multiplier {quantity_multiplier}: {trade_amount} {coin_symbol}")

            # --- Fee Calculation and Adjustment ---
            if is_futures:
                # Calculate fees for the trade using fixed fee cap
                fee_analysis = self.fee_calculator.calculate_comprehensive_fees(
                    margin=usdt_amount,
                    leverage=config.DEFAULT_LEVERAGE,  # Use leverage from settings
                    entry_price=current_price
                )

                # Log fee information
                logger.info(f"Fee Analysis for {trading_pair}:")
                logger.info(f"  Single Trade Fee: ${fee_analysis['single_trade_fee']} USDT")
                logger.info(f"  Total Fees (Entry + Exit): ${fee_analysis['total_fees']} USDT")
                logger.info(f"  Breakeven Price: ${fee_analysis['breakeven_price']}")
                logger.info(f"  Fee % of Margin: {fee_analysis['fee_percentage_of_margin']:.4f}%")

                # Store fee information for later use
                fee_info = {
                    'single_trade_fee': float(fee_analysis['single_trade_fee']),
                    'total_fees': float(fee_analysis['total_fees']),
                    'breakeven_price': float(fee_analysis['breakeven_price']),
                    'fee_percentage_of_margin': float(fee_analysis['fee_percentage_of_margin']),
                    'fee_type': fee_analysis['fee_type'],
                    'effective_fee_rate': float(fee_analysis['effective_fee_rate'])
                }
            else:
                fee_info = None

            # Get symbol filters for precision formatting
            # Commented out for now as it's handled elsewhere
            # symbol_filters = await self.binance_exchange.get_futures_symbol_filters(trading_pair)
        except Exception as e:
            reason = f"Failed to calculate trade amount: {e}"
            logger.error(reason, exc_info=True)
            return False, reason

        if trade_amount <= 0:
            return False, "Calculated trade amount is zero or negative."
          #----Calculate trade quantity ----
        quantities = await self.binance_exchange.calculate_min_max_market_order_quantity(f"{coin_symbol}USDT")
        minQuantity = float(quantities['min_quantity'])
        maxQuantity = float(quantities['max_quantity'])
        print(f"Min Quantity: {minQuantity}, Max Quantity: {maxQuantity}")
        trade_amount = max(minQuantity, min(maxQuantity, trade_amount))
        print(f"Adjusted trade amount: {trade_amount}")
        # --- Enhanced Quantity/Notional Validation ---
        if is_futures:
            # Check quantity bounds with detailed logging
            if trade_amount < minQuantity:
                logger.warning(f"Order quantity {trade_amount} below minimum {min_qty} for {trading_pair}. Skipping order.")
                return False, {"error": f"Quantity {trade_amount} below minimum {min_qty} for {trading_pair}, order skipped."}

            if trade_amount > maxQuantity:
                logger.warning(f"Order quantity {trade_amount} above maximum {max_qty} for {trading_pair}. Skipping order.")
                return False, {"error": f"Quantity {trade_amount} above maximum {max_qty} for {trading_pair}, order skipped."}

            # Check notional value
            notional_value = trade_amount * current_price
            if notional_value < min_notional:
                logger.warning(f"Order notional {notional_value} below minimum {min_notional} for {trading_pair}. Skipping order.")
                return False, {"error": f"Notional {notional_value} below minimum {min_notional} for {trading_pair}, order skipped."}

            logger.info(f"Quantity validation passed for {trading_pair}: {trade_amount} (min: {min_qty}, max: {max_qty}, notional: {notional_value:.2f})")
        else:
            logger.warning(f"Could not get symbol filters for {trading_pair}. Proceeding with order.")

        # --- Position/Leverage Validation ---
        if is_futures:
            try:
                # Get current positions for this symbol
                positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
                current_position_size = 0.0
                actual_leverage = config.DEFAULT_LEVERAGE  # Use leverage from settings

                for position in positions:
                    if position.get('symbol') == trading_pair:
                        current_position_size = abs(float(position.get('positionAmt', 0)))
                        # Get actual leverage from position
                        actual_leverage = float(position.get('leverage', config.DEFAULT_LEVERAGE))
                        break

                # Calculate new total position size
                new_total_size = current_position_size + trade_amount

                # Get account leverage info
                if self.binance_exchange.client:
                    account_info = await self.binance_exchange.client.futures_account()
                    max_leverage = float(account_info.get('maxLeverage', 125)) if account_info else 125  # Default to 125x

                    # Estimate max position size based on leverage and balance
                    total_balance = float(account_info.get('totalWalletBalance', 0)) if account_info else 0
                    max_position_value = total_balance * max_leverage
                    max_position_size = max_position_value / current_price

                    if new_total_size > max_position_size:
                        logger.warning(f"Order would exceed max position size for {trading_pair}. Current: {current_position_size}, New: {new_total_size}, Max: {max_position_size}. Skipping order.")
                        return False, {"error": f"Would exceed max position size for {trading_pair}, order skipped."}

                    logger.info(f"Position validation passed for {trading_pair}. Current: {current_position_size}, New: {new_total_size}, Max: {max_position_size}")

                    # Update fee calculation with actual leverage
                    if fee_info:
                        updated_fee_analysis = self.fee_calculator.calculate_comprehensive_fees(
                            margin=usdt_amount,
                            leverage=actual_leverage,
                            entry_price=current_price
                        )

                        # Update fee info with actual leverage
                        fee_info.update({
                            'single_trade_fee': float(updated_fee_analysis['single_trade_fee']),
                            'total_fees': float(updated_fee_analysis['total_fees']),
                            'breakeven_price': float(updated_fee_analysis['breakeven_price']),
                            'fee_percentage_of_margin': float(updated_fee_analysis['fee_percentage_of_margin']),
                            'actual_leverage': actual_leverage
                        })

                        logger.info(f"Updated fee analysis with actual leverage {actual_leverage}:")
                        logger.info(f"  Single Trade Fee: ${fee_info['single_trade_fee']} USDT")
                        logger.info(f"  Total Fees: ${fee_info['total_fees']} USDT")
                        logger.info(f"  Breakeven Price: ${fee_info['breakeven_price']}")
                else:
                    logger.warning("Binance client not available for position validation. Proceeding with order.")

            except Exception as e:
                logger.warning(f"Position validation failed for {trading_pair}: {e}. Proceeding with order.")
                # Continue with order if validation fails (don't block trading)

        # --- End Calculate Trade Amount ---

        # --- Place order and handle partial fills/cancels ---
        order_result = {}
        try:
            if is_futures:
                entry_side = SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL

                # Final validation before placing order
                logger.info(f"Placing {order_type} order for {trading_pair}: {entry_side} {trade_amount} @ ${signal_price:.8f}")

                # For MARKET orders, ensure we have a valid quantity
                if order_type.upper() == 'MARKET':
                    # Double-check quantity is within bounds
                    if trade_amount < min_qty:
                        logger.error(f"Final validation failed: quantity {trade_amount} below minimum {min_qty}")
                        return False, {"error": f"Quantity {trade_amount} below minimum {min_qty}"}

                    if trade_amount > max_qty:
                        logger.error(f"Final validation failed: quantity {trade_amount} above maximum {max_qty}")
                        return False, {"error": f"Quantity {trade_amount} above maximum {max_qty}"}

                # Handle price range logic
                if entry_prices is None:
                    entry_prices = [signal_price]  # Fallback to signal_price if no entry_prices provided

                effective_price, reason = self._handle_price_range_logic(
                    entry_prices=entry_prices,
                    order_type=order_type,
                    position_type=position_type,
                    current_price=current_price
                )
                logger.info(f"Effective price for {trading_pair}: {effective_price} ({reason})")

                # Check if price range validation rejected the order
                if effective_price is None:
                    logger.warning(f"Order rejected due to price range validation: {reason}")
                    return False, {"error": reason}

                order_result = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=entry_side,
                    order_type_market=order_type,
                    amount=trade_amount,
                    price=effective_price if order_type == 'LIMIT' else None,
                    client_order_id=client_order_id
                )

                # Check if order was created successfully
                if 'orderId' in order_result:
                    logger.info(f"Order created successfully: {order_result['orderId']}")

                    # Add fee information to order result
                    if fee_info:
                        order_result['fee_analysis'] = fee_info
                        logger.info(f"Fee analysis added to order result: {fee_info}")

                    # Create TP/SL orders as separate orders after position opening
                    # Convert origQty to float since it comes as string from Binance API
                    position_size = float(order_result.get('origQty', trade_amount))
                    tp_sl_orders, stop_loss_order_id = await self._create_tp_sl_orders(
                        trading_pair=trading_pair,
                        position_type=position_type,
                        position_size=position_size,
                        take_profits=take_profits,
                        stop_loss=stop_loss
                    )

                    # Add TP/SL order details to the main order result
                    if tp_sl_orders:
                        order_result['tp_sl_orders'] = tp_sl_orders
                        logger.info(f"Created {len(tp_sl_orders)} TP/SL orders for {trading_pair}")

                    # Store stop loss order ID for database update
                    if stop_loss_order_id:
                        order_result['stop_loss_order_id'] = stop_loss_order_id
                        logger.info(f"Stop loss order ID stored: {stop_loss_order_id}")

                    elif order_type.upper() == 'LIMIT':
                        # For LIMIT orders, store TP/SL parameters for later creation after fill
                        logger.info(f"LIMIT order placed - TP/SL orders will be created after order is filled")
                        order_result['pending_tp_sl'] = {
                            'trading_pair': trading_pair,
                            'position_type': position_type,
                            'position_size': order_result.get('origQty', trade_amount),
                            'take_profits': take_profits,
                            'stop_loss': stop_loss
                        }
                        logger.info(f"Stored TP/SL parameters for post-fill creation")

                    # Return success - order status will be checked separately in Discord bot
                    return True, order_result
                elif 'error' in order_result:
                    logger.error(f"Order creation failed: {order_result['error']}")
                    return False, order_result
                else:
                    logger.warning(f"Unexpected order result: {order_result}")
                    return False, {"error": "Unexpected order result"}
            else:
                # Spot trading logic (if needed)
                order_result = await self.binance_exchange.create_order(
                    pair=trading_pair,
                    side=SIDE_BUY,
                    order_type_market=ORDER_TYPE_MARKET,
                    amount=trade_amount
                )

                if 'orderId' in order_result:
                    logger.info(f"Spot order created successfully: {order_result['orderId']}")
                    return True, order_result
                else:
                    logger.error(f"Spot order creation failed: {order_result}")
                    return False, order_result

        except Exception as e:
            logger.error(f"Order placement failed for {trading_pair}: {e}", exc_info=True)
            return False, {"error": f"Order placement failed: {str(e)}"}

        # --- End of order placement logic ---
        # Note: Order status checking is now handled separately in the Discord bot
        # to prevent API permission issues from affecting order creation

        # The order placement logic above should have already returned True/False
        # If we reach here, something went wrong
        logger.error(f"Unexpected execution flow for {trading_pair} - order placement should have returned")
        return False, {"error": "Unexpected execution flow"}

    async def calculate_position_breakeven_price(
        self,
        trading_pair: str,
        entry_price: float,
        position_type: str,
        order_type: str = "MARKET",
        use_bnb: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate breakeven price for a position including all fees.

        Args:
            trading_pair: Trading pair (e.g., 'BTCUSDT')
            entry_price: Entry price of the position
            position_type: 'LONG' or 'SHORT'
            order_type: 'MARKET' or 'LIMIT'
            use_bnb: Whether to apply BNB discount

        Returns:
            Dictionary with breakeven analysis
        """
        try:
            # Get current position information
            positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
            actual_leverage = config.DEFAULT_LEVERAGE
            position_size = 0.0

            for position in positions:
                if position.get('symbol') == trading_pair:
                    position_size = abs(float(position.get('positionAmt', 0)))
                    actual_leverage = float(position.get('leverage', config.DEFAULT_LEVERAGE))
                    break

            if position_size == 0:
                return {
                    'error': f'No position found for {trading_pair}',
                    'breakeven_price': None,
                    'fee_analysis': None
                }

            # Calculate notional value
            notional_value = position_size * entry_price

            # Calculate breakeven price using fixed fee cap
            breakeven_analysis = self.fee_calculator.calculate_comprehensive_fees(
                margin=notional_value / actual_leverage,  # Convert notional to margin
                leverage=actual_leverage,
                entry_price=entry_price
            )

            return {
                'trading_pair': trading_pair,
                'entry_price': entry_price,
                'position_size': position_size,
                'actual_leverage': actual_leverage,
                'notional_value': notional_value,
                'breakeven_price': float(breakeven_analysis['breakeven_price']),
                'fee_analysis': {
                    'single_trade_fee': float(breakeven_analysis['single_trade_fee']),
                    'total_fees': float(breakeven_analysis['total_fees']),
                    'fee_percentage_of_margin': float(breakeven_analysis['fee_percentage_of_margin']),
                    'fee_type': breakeven_analysis['fee_type'],
                    'effective_fee_rate': float(breakeven_analysis['effective_fee_rate'])
                }
            }

        except Exception as e:
            logger.error(f"Error calculating breakeven price for {trading_pair}: {e}")
            return {
                'error': f'Failed to calculate breakeven price: {str(e)}',
                'breakeven_price': None,
                'fee_analysis': None
            }

    async def _create_tp_sl_orders(self, trading_pair: str, position_type: str, position_size: float,
                                 take_profits: Optional[List[float]] = None, stop_loss: Optional[Union[float, str]] = None) -> Tuple[List[Dict], Optional[str]]:
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
                    return await self._create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

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

                    # Only proceed if we have TP or SL to set
                    if tp_sl_params:
                        # Set TP/SL on the position
                        response = await self.binance_exchange.client.futures_change_position_tpsl_mode(
                            symbol=trading_pair,
                            dualSidePosition='false'  # Single position mode
                        )

                        if response and response.get('status') == 'OK':
                            # Now set the TP/SL prices
                            tp_sl_response = await self.binance_exchange.client.futures_change_position_tpsl_mode(
                                symbol=trading_pair,
                                dualSidePosition='false',
                                **tp_sl_params
                            )

                            if tp_sl_response and tp_sl_response.get('status') == 'OK':
                                logger.info(f"Successfully set position-based TP/SL for {trading_pair}")

                                # Create mock order responses for consistency
                                if 'takeProfitPrice' in tp_sl_params:
                                    tp_order = {
                                        'orderId': f"pos_tp_{trading_pair}_{int(time.time())}",
                                        'symbol': trading_pair,
                                        'status': 'NEW',
                                        'type': 'TAKE_PROFIT_MARKET',
                                        'side': tp_sl_side,
                                        'price': tp_sl_params['takeProfitPrice'],
                                        'origQty': str(position_size),
                                        'order_type': 'TAKE_PROFIT',
                                        'tp_level': 1
                                    }
                                    tp_sl_orders.append(tp_order)

                                if 'stopLossPrice' in tp_sl_params:
                                    sl_order = {
                                        'orderId': f"pos_sl_{trading_pair}_{int(time.time())}",
                                        'symbol': trading_pair,
                                        'status': 'NEW',
                                        'type': 'STOP_MARKET',
                                        'side': tp_sl_side,
                                        'price': tp_sl_params['stopLossPrice'],
                                        'origQty': str(position_size),
                                        'order_type': 'STOP_LOSS'
                                    }
                                    tp_sl_orders.append(sl_order)
                                    stop_loss_order_id = sl_order['orderId']

                                return tp_sl_orders, stop_loss_order_id
                            else:
                                logger.warning(f"Failed to set position-based TP/SL: {tp_sl_response}")
                        else:
                            logger.warning(f"Failed to enable TP/SL mode: {response}")

                # Fall back to separate orders if position-based TP/SL fails
                logger.info(f"Falling back to separate TP/SL orders for {trading_pair}")
                return await self._create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

            except Exception as e:
                logger.error(f"Error setting position-based TP/SL for {trading_pair}: {e}")
                # Fall back to separate orders
                return await self._create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

        except Exception as e:
            logger.error(f"Error in _create_tp_sl_orders for {trading_pair}: {e}")
            return tp_sl_orders, stop_loss_order_id

    async def _create_separate_tp_sl_orders(self, trading_pair: str, position_type: str, position_size: float,
                                          take_profits: Optional[List[float]] = None, stop_loss: Optional[Union[float, str]] = None) -> Tuple[List[Dict], Optional[str]]:
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
                            order_type_market='TAKE_PROFIT_MARKET',
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

            # Create Stop Loss order
            if stop_loss:
                try:
                    sl_price_float = float(stop_loss)

                    # For stop loss, use reduceOnly with specific amount to handle partial positions correctly
                    sl_order = await self.binance_exchange.create_futures_order(
                        pair=trading_pair,
                        side=tp_sl_side,
                        order_type_market='STOP_MARKET',
                        amount=position_size,  # Use specific amount for partial positions
                        stop_price=sl_price_float,
                        reduce_only=True  # This ensures it only reduces the position by the specified amount
                    )

                    if sl_order and 'orderId' in sl_order:
                        sl_order['order_type'] = 'STOP_LOSS'
                        tp_sl_orders.append(sl_order)
                        stop_loss_order_id = str(sl_order['orderId'])
                        logger.info(f"Created SL order at {sl_price_float} for {trading_pair} with amount {position_size} and order ID: {stop_loss_order_id}")
                    else:
                        logger.error(f"Failed to create SL order: {sl_order}")
                except Exception as e:
                    logger.error(f"Error creating SL order at {stop_loss}: {e}")

            return tp_sl_orders, stop_loss_order_id

        except Exception as e:
            logger.error(f"Error in _create_separate_tp_sl_orders for {trading_pair}: {e}")
            return tp_sl_orders, stop_loss_order_id

    async def update_tp_sl_orders(self, trading_pair: str, position_type: str,
                                new_take_profits: Optional[List[float]] = None,
                                new_stop_loss: Optional[float] = None) -> Tuple[bool, List[Dict]]:
        """
        Update TP/SL orders by canceling existing ones and creating new ones.
        This follows Binance Futures API requirements where TP/SL orders cannot be updated directly.
        """
        try:
            # 1. Cancel existing TP/SL orders for the symbol
            logger.info(f"Canceling existing TP/SL orders for {trading_pair}")
            cancel_result = await self.binance_exchange.cancel_all_futures_orders(trading_pair)

            if not cancel_result:
                logger.warning(f"Failed to cancel existing orders for {trading_pair}")

            # 2. Get current position size
            positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
            position_size = 0.0

            for position in positions:
                if position.get('symbol') == trading_pair:
                    position_size = abs(float(position.get('positionAmt', 0)))
                    break

            if position_size == 0:
                logger.warning(f"No open position found for {trading_pair}")
                return False, []

            # 3. Create new TP/SL orders
            new_orders, new_stop_loss_order_id = await self._create_tp_sl_orders(
                trading_pair=trading_pair,
                position_type=position_type,
                position_size=position_size,
                take_profits=new_take_profits,
                stop_loss=new_stop_loss
            )

            if new_orders:
                logger.info(f"Successfully updated TP/SL orders for {trading_pair}: {len(new_orders)} orders")
                result = {'orders': new_orders}
                if new_stop_loss_order_id:
                    result['stop_loss_order_id'] = new_stop_loss_order_id
                return True, result
            else:
                logger.warning(f"No new TP/SL orders created for {trading_pair}")
                return False, []

        except Exception as e:
            logger.error(f"Error updating TP/SL orders for {trading_pair}: {e}")
            return False, []

    async def cancel_tp_sl_orders(self, trading_pair: str, active_trade: Dict = None) -> bool:
        """
        Cancel TP/SL orders for a specific symbol using stored order IDs.
        """
        try:
            cancelled_count = 0

            # If we have an active trade with stored order IDs, use those
            if active_trade:
                # Cancel stop loss order if we have its ID
                stop_loss_order_id = active_trade.get('stop_loss_order_id')
                if stop_loss_order_id:
                    try:
                        logger.info(f"Cancelling stop loss order {stop_loss_order_id} for {trading_pair}")
                        success, _ = await self.binance_exchange.cancel_futures_order(trading_pair, stop_loss_order_id)
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
                    import json
                    try:
                        binance_response = json.loads(binance_response)
                    except Exception:
                        binance_response = {}

                tp_sl_orders = binance_response.get('tp_sl_orders', [])
                for tp_sl_order in tp_sl_orders:
                    if isinstance(tp_sl_order, dict) and 'orderId' in tp_sl_order:
                        order_id = tp_sl_order['orderId']
                        order_type = tp_sl_order.get('order_type', 'UNKNOWN')
                        try:
                            logger.info(f"Cancelling {order_type} order {order_id} for {trading_pair}")
                            success, _ = await self.binance_exchange.cancel_futures_order(trading_pair, order_id)
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
                open_orders = await self.binance_exchange.get_all_open_futures_orders()

                for order in open_orders:
                    if (order['symbol'] == trading_pair and
                        order['type'] in ['STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT'] and
                        order.get('reduceOnly', False)):
                        try:
                            logger.info(f"Cancelling TP/SL order {order['orderId']} ({order['type']}) for {trading_pair}")
                            success, _ = await self.binance_exchange.cancel_futures_order(trading_pair, order['orderId'])
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
            parsed_signal = self._parse_parsed_signal(active_trade.get("parsed_signal"))
            coin_symbol = parsed_signal.get("coin_symbol")
            order_id = active_trade.get("exchange_order_id")

            if not coin_symbol or not order_id:
                return False, {"error": f"Missing coin_symbol or order_id for trade {active_trade.get('id')}"}

            logger.info(f"Attempting to cancel order {order_id} for {coin_symbol}")

            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            success, response = await self.binance_exchange.cancel_futures_order(trading_pair, order_id)

            if success:
                logger.info(f"Successfully cancelled order {order_id} for {coin_symbol}")
                return True, response
            else:
                logger.error(f"Failed to cancel order {order_id} for {coin_symbol}. Reason: {response}")
                return False, response

        except Exception as e:
            logger.error(f"Error cancelling order: {e}", exc_info=True)
            return False, {"error": f"Order cancellation failed: {str(e)}"}

    async def is_position_open(self, coin_symbol: str, position_side: str = 'BOTH') -> bool:
        """Check if a position is open for the given symbol and side on Binance Futures."""
        if not coin_symbol:
            logger.error("coin_symbol is required for is_position_open")
            return False
        try:
            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            pos_info = await self.binance_exchange.client.futures_position_information(symbol=trading_pair)  # type: ignore
            for pos in pos_info:
                if pos['positionSide'] == position_side and float(pos['positionAmt']) != 0:
                    logger.info(f"Position is open for {coin_symbol} side {position_side}: {pos['positionAmt']}")
                    return True
            logger.info(f"No open position for {coin_symbol} side {position_side}")
            return False
        except Exception as e:
            logger.error(f"Error checking position status for {coin_symbol}: {e}")
            return False

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
        binance_response = self._safe_parse_binance_response(active_trade.get('binance_response'))
        exchange_order_id = (active_trade.get('exchange_order_id') or (binance_response.get('orderId') if binance_response else None))
        stop_loss_order_id = (active_trade.get('stop_loss_order_id') or ((binance_response.get('stop_loss_order_details') or {}).get('orderId') if binance_response else None))
        parsed_signal = self._parse_parsed_signal(active_trade.get('parsed_signal'))
        coin_symbol = parsed_signal.get('coin_symbol') or active_trade.get('coin_symbol')
        position_type = parsed_signal.get('position_type') or active_trade.get('signal_type')
        entry_price = active_trade.get('entry_price')
        if not coin_symbol or not position_type:
            logger.error(f"Missing coin_symbol or position_type for trade {trade_id}")
            return False, {"error": f"Missing coin_symbol or position_type for trade {trade_id}"}
        trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

        # Check if position is open before acting
        is_open = await self.is_position_open(coin_symbol)
        if not is_open:
            logger.warning(f"Position for {coin_symbol} is already closed. No action taken.")
            return False, {"error": f"Position for {coin_symbol} is already closed."}

        # Partial close logic
        close_pct = details.get('close_percentage', 100.0)
        if close_pct < 100.0:
            amount_to_close = position_size * (close_pct / 100.0)
            logger.info(f"Partial close: closing {close_pct}% of position ({amount_to_close} {coin_symbol})")
        else:
            amount_to_close = position_size
            logger.info(f"Full close: closing 100% of position ({amount_to_close} {coin_symbol})")

        # Multiple TP logic
        if action.startswith('take_profit_'):
            tp_idx = int(action.split('_')[-1])
            tp_price = details.get('tp_price')
            if not tp_price:
                logger.error(f"No TP price provided for TP{tp_idx}")
                return False, {"error": f"No TP price provided for TP{tp_idx}"}
            logger.info(f"Placing TP{tp_idx} for {coin_symbol} at {tp_price} for {amount_to_close}")
            # Place a LIMIT order at tp_price for amount_to_close, reduceOnly
            tp_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            tp_order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=tp_side,
                order_type_market='LIMIT',
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

        # Standard close (market)
        if action in ['take_profit', 'stop_loss_hit', 'position_closed']:
            logger.info(f"Closing position for {coin_symbol} at market. Reason: {action}")


            logger.info(f"Canceling all TP/SL orders for {trading_pair} before closing position")
            cancel_result = await self.cancel_tp_sl_orders(trading_pair)
            if not cancel_result:
                logger.warning(f"Failed to cancel TP/SL orders for {trading_pair} - proceeding with position close")

            close_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            close_order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=close_side,
                order_type_market='MARKET',
                amount=amount_to_close,
                reduce_only=True
            )
            if close_order and 'orderId' in close_order:
                logger.info(f"Position closed: {close_order['orderId']}")
                return True, close_order
            else:
                logger.error(f"Failed to close position: {close_order}")
                return False, {"error": "Failed to close position", "response": close_order}

        # Stop loss update
        if action == 'stop_loss_update':
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
                order_type_market='STOP_MARKET',
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

        logger.error(f"Unknown action: {action}")
        return False, {"error": f"Unknown action: {action}"}

    async def close_position_at_market(self, active_trade: Dict, reason: str = "manual_close", close_percentage: float = 100.0) -> Tuple[bool, Dict]:
        """
        Closes a percentage of an open futures position at the current market price.
        CRITICAL: Cancels all TP/SL orders before closing position to prevent unwanted executions.
        """
        try:
            parsed_signal = self._parse_parsed_signal(active_trade.get("parsed_signal"))
            coin_symbol = parsed_signal.get("coin_symbol")
            position_type = parsed_signal.get("position_type", "SPOT").upper()
            position_size = float(active_trade.get("position_size") or 0.0)

            if position_size <= 0:
                initial_response = active_trade.get("binance_response")
                if isinstance(initial_response, dict):
                    position_size = float(initial_response.get('origQty') or 0.0)

            if not coin_symbol or position_size <= 0:
                return False, {"error": f"Invalid trade data for closing position. Symbol: {coin_symbol}, Size: {position_size}"}

            amount_to_close = position_size * (close_percentage / 100.0)
            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            is_futures = position_type in ['LONG', 'SHORT']

            # Cancel existing TP/SL orders before closing position
            if is_futures:
                if close_percentage >= 100.0:
                    # Full close - cancel all TP/SL orders
                    logger.info(f"Cancelling all TP/SL orders for {trading_pair} before full close")
                    await self.cancel_tp_sl_orders(trading_pair, active_trade)
                else:
                    # Partial close - only cancel specific orders if needed
                    # For now, we'll keep TP/SL orders active for partial closes
                    # but we should update them with the new position size
                    logger.info(f"Partial close ({close_percentage}%) - keeping TP/SL orders active")

                    # TODO: Update TP/SL orders with new position size after partial close
                    # This would require recalculating the remaining position size

            if is_futures:

                logger.info(f"Canceling all TP/SL orders for {trading_pair} before closing position")
                cancel_result = await self.cancel_tp_sl_orders(trading_pair)
                if not cancel_result:
                    logger.warning(f"Failed to cancel TP/SL orders for {trading_pair} - proceeding with position close")

                close_side = SIDE_SELL if position_type == 'LONG' else SIDE_BUY
                close_order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=close_side,
                    order_type_market=FUTURE_ORDER_TYPE_MARKET,
                    amount=amount_to_close,
                    reduce_only=True  # <-- always use reduce_only for market closes
                )
            else:
                close_order = await self.binance_exchange.create_order(
                    pair=trading_pair,
                    side='sell',
                    order_type_market='MARKET',
                    amount=amount_to_close
                )

            if close_order and 'orderId' in close_order:
                logger.info(f"Successfully placed close order for {coin_symbol}: {close_order}")

                # Calculate fill price and executed quantity for PnL calculation
                fill_price = 0.0
                executed_qty = 0.0

                if isinstance(close_order, dict):
                    # Try to get fill information from the order response
                    fills = close_order.get('fills', [])
                    if fills:
                        total_qty = sum(float(fill.get('qty', 0)) for fill in fills)
                        total_price = sum(float(fill.get('price', 0)) * float(fill.get('qty', 0)) for fill in fills)
                        if total_qty > 0:
                            fill_price = total_price / total_qty
                            executed_qty = total_qty
                    else:
                        # Fallback to executedQty and avgPrice if available
                        executed_qty = float(close_order.get('executedQty', amount_to_close))
                        fill_price = float(close_order.get('avgPrice', 0))

                # Prepare response with fill information
                response_data = {
                    **close_order,
                    'fill_price': fill_price,
                    'executed_qty': executed_qty,
                    'close_percentage': close_percentage,
                    'reason': reason
                }

                # Update trade status based on close percentage
                try:
                    trade_id = active_trade.get('id')
                    if trade_id and self.db_manager:
                        if close_percentage >= 100.0:
                            status = "CLOSED"
                            
                            # Set closed_at timestamp when trade is fully closed
                            try:
                                from discord_bot.utils.timestamp_manager import ensure_closed_at
                                await ensure_closed_at(self.db_manager.supabase, trade_id)
                                logger.info(f"✅ Set closed_at timestamp for trade {trade_id} via trading engine closure")
                            except Exception as e:
                                logger.warning(f"Could not set closed_at timestamp: {e}")
                        else:
                            status = "PARTIALLY_CLOSED"

                        await self.db_manager.update_existing_trade(
                            trade_id=trade_id,
                            updates={
                                "status": status,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        logger.info(f"Updated trade {trade_id} status to {status}")
                except Exception as e:
                    logger.warning(f"Could not update trade status: {e}")

                return True, response_data
            else:
                return False, {"error": f"Failed to place close order. Response: {close_order}"}
        except Exception as e:
            logger.error(f"Error closing position: {e}", exc_info=True)
            return False, {"error": str(e)}

    async def update_stop_loss(self, active_trade: Dict, new_sl_price: float) -> Tuple[bool, Dict]:
        """
        Update stop loss for an active position.
        """
        try:
            parsed_signal = self._parse_parsed_signal(active_trade.get("parsed_signal"))
            coin_symbol = parsed_signal.get("coin_symbol")
            position_type = parsed_signal.get("position_type", "SPOT")
            position_size = float(active_trade.get("position_size") or 0.0)
            old_sl_order_id = active_trade.get("stop_loss_order_id")

            # If position_size is 0, try to get it from Binance
            if position_size <= 0:
                initial_response = active_trade.get("binance_response")
                if isinstance(initial_response, dict):
                    position_size = float(initial_response.get('origQty') or 0.0)

                # If still 0, fetch current position from Binance
                if position_size <= 0:
                    trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
                    positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)

                    for position in positions:
                        if position.get('symbol') == trading_pair:
                            position_size = abs(float(position.get('positionAmt', 0)))
                            logger.info(f"Fetched current position size from Binance: {position_size} for {trading_pair}")
                            break

            if not coin_symbol or position_size <= 0:
                return False, {"error": f"Invalid trade data for updating stop loss. Symbol: {coin_symbol}, Size: {position_size}"}

            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

            # Check if stop loss would immediately trigger
            current_price = await self.binance_exchange.get_futures_mark_price(trading_pair)
            if current_price:
                # For LONG positions: SL should be BELOW current price to avoid immediate trigger
                # For SHORT positions: SL should be ABOVE current price to avoid immediate trigger
                if position_type.upper() == 'LONG' and new_sl_price >= current_price:
                    logger.warning(f"Stop loss price {new_sl_price} is above current price {current_price}. This might be intentional (e.g., break-even). Proceeding with order creation.")
                elif position_type.upper() == 'SHORT' and new_sl_price <= current_price:
                    logger.warning(f"Stop loss price {new_sl_price} is below current price {current_price}. This might be intentional (e.g., break-even). Proceeding with order creation.")
                logger.info(f"Current price: {current_price}, Stop loss price: {new_sl_price}, Position type: {position_type}")

            # Try to use position-based TP/SL first (appears in TP/SL column)
            try:
                if self.binance_exchange.client:
                    # Set position-based stop loss
                    response = await self.binance_exchange.client.futures_change_position_tpsl_mode(
                        symbol=trading_pair,
                        dualSidePosition='false',
                        stopLossPrice=f"{new_sl_price}"
                    )

                    if response and response.get('status') == 'OK':
                        logger.info(f"Successfully updated position-based stop loss to {new_sl_price} for {trading_pair}")

                        # Create mock response for consistency
                        mock_response = {
                            'orderId': f"pos_sl_{trading_pair}_{int(time.time())}",
                            'symbol': trading_pair,
                            'status': 'NEW',
                            'type': 'STOP_MARKET',
                            'side': SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY,
                            'price': f"{new_sl_price}",
                            'origQty': str(position_size),
                            'stop_loss_order_id': f"pos_sl_{trading_pair}_{int(time.time())}"
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

            # Cancel existing stop loss order before creating new one
            if old_sl_order_id:
                try:
                    logger.info(f"Cancelling existing stop loss order {old_sl_order_id} before creating new one")
                    cancel_result = await self.binance_exchange.cancel_futures_order(trading_pair, old_sl_order_id)
                    if cancel_result:
                        logger.info(f"Successfully cancelled old stop loss order {old_sl_order_id}")
                    else:
                        logger.info(f"Old stop loss order {old_sl_order_id} may not exist (possibly already filled/cancelled) - proceeding with new order")
                except Exception as e:
                    logger.info(f"Could not cancel old stop loss order {old_sl_order_id}: {e} - proceeding with new order anyway")
                    # Continue anyway - the new order might still work
            else:
                logger.info(f"No existing stop loss order ID found - proceeding with new order creation")

            # Create new stop loss order
            new_sl_side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY
            logger.info(f"Creating new stop loss order: {trading_pair} {new_sl_side} STOP_MARKET {position_size} @ {new_sl_price}")
            logger.info(f"Order parameters: pair={trading_pair}, side={new_sl_side}, type={FUTURE_ORDER_TYPE_STOP_MARKET}, stop_price={new_sl_price}, amount={position_size}, reduce_only=True")

            new_sl_order_result = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=new_sl_side,
                order_type_market=FUTURE_ORDER_TYPE_STOP_MARKET,
                stop_price=new_sl_price,
                amount=position_size,  # Use specific amount for partial positions
                reduce_only=True  # This ensures it only reduces the position by the specified amount
            )

            if new_sl_order_result and 'orderId' in new_sl_order_result:
                logger.info(f"Successfully created new stop loss order: {new_sl_order_result['orderId']}")
                # Add the stop loss order ID to the response for database update
                new_sl_order_result['stop_loss_order_id'] = str(new_sl_order_result['orderId'])
                return True, new_sl_order_result
            else:
                error_msg = f"Failed to create new SL order. Response: {new_sl_order_result}"
                logger.error(error_msg)
                return False, {"error": error_msg}
        except Exception as e:
            logger.error(f"Error updating stop loss: {e}", exc_info=True)
            return False, {"error": f"Stop loss update failed: {str(e)}"}

    async def calculate_2_percent_stop_loss(self, coin_symbol: str, position_type: str) -> Optional[float]:
        """
        Calculate a 2% stop loss price from the current market price.

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')
            position_type: The position type ('LONG' or 'SHORT')

        Returns:
            The calculated stop loss price or None if calculation fails
        """
        return await self.calculate_percentage_stop_loss(coin_symbol, position_type, 2.0)

    async def calculate_percentage_stop_loss(self, coin_symbol: str, position_type: str, percentage: float) -> Optional[float]:
        """
        Calculate a percentage-based stop loss price from the current market price.

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')
            position_type: The position type ('LONG' or 'SHORT')
            percentage: The percentage for stop loss calculation (e.g., 2.0 for 2%)

        Returns:
            The calculated stop loss price or None if calculation fails
        """
        try:
            # Validate percentage input
            if percentage <= 0 or percentage > 50:  # Reasonable range: 0.1% to 50%
                logger.error(f"Invalid stop loss percentage: {percentage}%. Must be between 0.1 and 50.")
                return None

            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            current_price = await self.binance_exchange.get_futures_mark_price(trading_pair)
            precision = await self.binance_exchange.get_symbol_precision(trading_pair)

            if not current_price:
                logger.error(f"Could not get current price for {trading_pair}")
                return None

            # Calculate percentage-based stop loss from current price
            if position_type.upper() == 'LONG':
                stop_loss_price = current_price * (1 - percentage / 100)  # percentage below current price
                logger.info(f"LONG position: Calculated {percentage}% stop loss. Current: {current_price}, SL: {stop_loss_price}")
            elif position_type.upper() == 'SHORT':
                stop_loss_price = current_price * (1 + percentage / 100)  # percentage above current price
                logger.info(f"SHORT position: Calculated {percentage}% stop loss. Current: {current_price}, SL: {stop_loss_price}")
            else:
                logger.error(f"Unknown position type: {position_type}")
                return None
            rounded_stop_loss_price = round(stop_loss_price,precision )
            return rounded_stop_loss_price

        except Exception as e:
            logger.error(f"Error calculating {percentage}% stop loss for {coin_symbol}: {e}")
            return None

    async def close(self):
        """Close all exchange connections."""
        await self.binance_exchange.close_client()
        logger.info("TradingEngine connections closed.")