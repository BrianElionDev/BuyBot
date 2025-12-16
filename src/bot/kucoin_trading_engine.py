"""
KuCoin Trading Engine

This module provides a trading engine specifically for KuCoin exchange operations.
It mirrors the functionality of the main TradingEngine but uses KuCoin-specific implementations.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_bot.database import DatabaseManager

from src.config import runtime_config
from src.exchange import KucoinExchange
from src.services.pricing.price_service import PriceService
from src.exchange import FixedFeeCalculator
from config.logging_config import get_trade_logger

from src.bot.utils.signal_parser import SignalParser
from src.bot.utils.price_calculator import PriceCalculator
from src.bot.utils.validation_utils import ValidationUtils
from src.bot.utils.response_parser import ResponseParser

from src.core.position_manager import PositionManager
from src.core.market_data_handler import MarketDataHandler
from src.core.trade_calculator import TradeCalculator

from src.bot.risk_management.stop_loss_manager import StopLossManager
from src.bot.risk_management.take_profit_manager import TakeProfitManager
from src.bot.risk_management.position_auditor import PositionAuditor

from src.bot.order_management.order_creator import OrderCreator
from src.bot.order_management.order_canceller import OrderCanceller
from src.bot.order_management.order_update import OrderUpdater

# Note: KuCoin uses its own signal processing logic
# from src.bot.signal_processor.initial_signal_processor import InitialSignalProcessor
# from src.bot.signal_processor.followup_signal_processor import FollowupSignalProcessor

from config import settings as config
import json

logger = get_trade_logger()

SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'
FUTURE_ORDER_TYPE_MARKET = 'MARKET'
FUTURE_ORDER_TYPE_LIMIT = 'LIMIT'
FUTURE_ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET = 'TAKE_PROFIT_MARKET'


class KucoinTradingEngine:
    """
    KuCoin-specific trading engine.

    Provides the same interface as the main TradingEngine but uses KuCoin exchange.
    """

    def __init__(self, price_service: PriceService, kucoin_exchange: KucoinExchange, db_manager: 'DatabaseManager'):
        """
        Initialize KuCoin trading engine.

        Args:
            price_service: The price service instance
            kucoin_exchange: The KuCoin exchange instance
            db_manager: The database manager instance
        """
        self.price_service = price_service
        self.kucoin_exchange = kucoin_exchange
        self.db_manager = db_manager
        self.trade_cooldowns = {}
        self.config = config
        self.fee_calculator = FixedFeeCalculator(fee_rate=config.FIXED_FEE_RATE)

        # Initialize utility modules
        self.signal_parser = SignalParser()
        self.price_calculator = PriceCalculator()
        self.validation_utils = ValidationUtils()
        self.response_parser = ResponseParser()

        # Initialize core modules with KuCoin exchange
        self.position_manager = PositionManager(kucoin_exchange, db_manager)
        self.market_data_handler = MarketDataHandler(kucoin_exchange, price_service)
        self.trade_calculator = TradeCalculator(self.fee_calculator)

        # Initialize risk management modules with KuCoin exchange
        self.stop_loss_manager = StopLossManager(kucoin_exchange)
        self.take_profit_manager = TakeProfitManager(kucoin_exchange)
        self.position_auditor = PositionAuditor(kucoin_exchange)

        # Initialize order management modules with KuCoin exchange
        self.order_creator = OrderCreator(kucoin_exchange)
        self.order_canceller = OrderCanceller(kucoin_exchange)
        self.order_updater = OrderUpdater(kucoin_exchange)

        # Note: KuCoin uses its own signal processing logic
        # The InitialSignalProcessor and FollowupSignalProcessor are Binance-specific
        # and expect binance_exchange attribute which KucoinTradingEngine doesn't have

        logger.info(f"KuCoin TradingEngine initialized with {config.FIXED_FEE_RATE * 100}% fee cap")
        logger.info("KuCoin TradingEngine initialized with all modularized components.")

    async def _calculate_trade_amount(
        self,
        coin_symbol: str,
        current_price: float,
        quantity_multiplier: Optional[int] = None,
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
                    trader_id = getattr(self, 'trader_id', None) or ''
                    if not trader_id:
                        logger.error("trader_id not set on trading engine, cannot retrieve position_size")
                        return 0.0

                    exchange_key = 'kucoin'

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

            # Apply quantity multiplier if specified (for memecoins)
            if quantity_multiplier and quantity_multiplier > 1:
                trade_amount *= quantity_multiplier
                logger.info(f"Applied quantity multiplier {quantity_multiplier}: {trade_amount} {coin_symbol}")

            # Get symbol filters for precision formatting and contract conversion
            trading_pair = f"{coin_symbol.upper()}-USDT"
            filters = await self.kucoin_exchange.get_futures_symbol_filters(trading_pair)

            if filters:
                lot_size_filter = filters.get('LOT_SIZE', {})
                try:
                    mult = float(filters.get('multiplier', 1)) if filters else 1.0
                except (TypeError, ValueError):
                    mult = 1.0
                    logger.warning(f"Could not get multiplier from filters, using default 1.0")

                # LOT_SIZE values are in contracts; convert to asset units
                try:
                    step_contracts = float(lot_size_filter.get('stepSize', 1))
                except (TypeError, ValueError):
                    step_contracts = 1.0
                try:
                    min_contracts = float(lot_size_filter.get('minQty', 1))
                except (TypeError, ValueError):
                    min_contracts = 1.0
                try:
                    max_contracts = float(lot_size_filter.get('maxQty', 1000000))
                except (TypeError, ValueError):
                    max_contracts = 1000000.0

                # CRITICAL: KuCoin ALWAYS uses exactly 1 contract regardless of position_size
                # Calculate ideal contracts for logging/diagnostics, but hard-clamp to 1.0
                original_assets = trade_amount
                ideal_contracts = trade_amount / mult if mult > 0 else trade_amount
                logger.info(f"KuCoin contract calculation - Ideal: {ideal_contracts:.8f} contracts from {original_assets:.8f} assets (mult={mult})")

                # ALWAYS use 1 contract for KuCoin - this is a hard requirement
                contracts = 1.0

                # Calculate what 1 contract represents in assets and notional for logging
                one_contract_assets = contracts * mult
                one_contract_notional = one_contract_assets * current_price
                ideal_notional = original_assets * current_price

                logger.info(f"KuCoin contract override: ideal={ideal_contracts:.8f} contracts -> using fixed 1.0 contract")
                logger.info(f"  Ideal position: {original_assets:.8f} assets = ${ideal_notional:.2f} notional")
                logger.info(f"  Actual position: {one_contract_assets:.8f} assets = ${one_contract_notional:.2f} notional (1 contract × {mult} multiplier)")

                # Convert back to asset units for return value (purely for logging/consistency)
                trade_amount = one_contract_assets
            else:
                logger.warning(f"No filters found for {trading_pair}, skipping contract conversion - this may cause validation errors")

            return trade_amount

        except Exception as e:
            logger.error(f"Failed to calculate trade amount: {e}")
            return 0.0

    def _handle_price_range_logic(
        self,
        entry_prices: Optional[List[float]],
        order_type: str,
        position_type: str,
        current_price: float
    ) -> Tuple[Optional[float], str]:
        """
        Handle price range logic for KuCoin.

        Args:
            entry_prices: List of entry prices
            order_type: Type of order (MARKET, LIMIT)
            position_type: LONG or SHORT
            current_price: Current market price

        Returns:
            Tuple of (price, reason)
        """
        if not entry_prices or len(entry_prices) == 0:
            return current_price, "No entry prices provided, using current market price"

        if order_type.upper() == "MARKET":
            return current_price, "Market order, using current market price"

        if len(entry_prices) == 1:
            return entry_prices[0], "Single entry price provided"

        # Handle multiple entry prices
        if position_type.upper() == "LONG":
            # For long positions, use the highest price (most conservative)
            price = max(entry_prices)
            return price, f"Long position with multiple entries, using highest price: {price}"
        else:
            # For short positions, use the lowest price (most conservative)
            price = min(entry_prices)
            return price, f"Short position with multiple entries, using lowest price: {price}"

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
        Process a KuCoin trading signal.

        Args:
            coin_symbol: The cryptocurrency symbol
            signal_price: The signal price
            position_type: LONG or SHORT
            order_type: MARKET or LIMIT
            stop_loss: Stop loss price
            take_profits: List of take profit prices
            dca_range: DCA range prices
            client_order_id: Client order ID
            price_threshold_override: Price threshold override
            quantity_multiplier: Quantity multiplier
            entry_prices: List of entry prices
            discord_id: Optional Discord message id for traceability

        Returns:
            Tuple of (success, response)
        """
        try:
            logger.info(f"Processing KuCoin signal: {coin_symbol} {position_type} at {signal_price}")

            # Check cooldown
            cooldown_key = f"kucoin_{coin_symbol}"
            if time.time() - self.trade_cooldowns.get(cooldown_key, 0) < self.config.TRADE_COOLDOWN:
                reason = f"Trade cooldown active for {coin_symbol}"
                logger.info(reason)
                return False, reason

            current_price = await self.price_service.get_coin_price(coin_symbol, exchange="kucoin")
            if not current_price:
                try:
                    current_price = await self.price_service.get_coin_price(coin_symbol, exchange="binance")
                except Exception:
                    current_price = None
            if not current_price:
                logger.error(f"Could not get current price for {coin_symbol} from KuCoin (and fallback failed)")
                return False, f"Could not get current price for {coin_symbol} from KuCoin"

            # Handle price range logic
            final_price, price_reason = self._handle_price_range_logic(
                entry_prices, order_type, position_type, current_price
            )
            logger.info(f"Price selection: {price_reason}")

            # Convert to KuCoin trading pair format
            trading_pair = f"{coin_symbol.upper()}-USDT"

            # Use symbol converter to get the correct KuCoin symbol format
            from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(trading_pair)
            logger.info(f"Converted {trading_pair} to KuCoin symbol: {kucoin_symbol}")

            # Validate symbol is supported using the converted symbol
            is_supported = await self.kucoin_exchange.is_futures_symbol_supported(trading_pair)
            if not is_supported:
                logger.error(f"Symbol {trading_pair} (converted to {kucoin_symbol}) not listed on KuCoin Futures")
                return False, f"Symbol {trading_pair} not listed on KuCoin Futures"

            # Normalize stop loss to float if provided
            if stop_loss is not None:
                try:
                    stop_loss_val = self._normalize_stop_loss_value(stop_loss)
                    if stop_loss_val and stop_loss_val > 0:
                        stop_loss = stop_loss_val
                    else:
                        logger.warning(f"Parsed stop loss is invalid from value: {stop_loss}")
                except Exception as e:
                    logger.warning(f"Failed to normalize stop loss '{stop_loss}': {e}")

            # Get minimum quantity for validation
            trading_pair = f"{coin_symbol.upper()}-USDT"
            filters = await self.kucoin_exchange.get_futures_symbol_filters(trading_pair)
            min_qty = 0.001
            if filters:
                lot_size_filter = filters.get('LOT_SIZE', {})
                min_qty = float(lot_size_filter.get('minQty', 0.001))

            # Calculate trade amount (this applies minimum adjustment internally)
            trade_amount = await self._calculate_trade_amount(
                coin_symbol, current_price, quantity_multiplier, position_size_override
            )

            if trade_amount <= 0:
                logger.error(f"Invalid trade amount calculated: {trade_amount}")
                return False, f"Invalid trade amount calculated: {trade_amount}"

            # CRITICAL: Validate final position size using the ORDER PRICE (not current price)
            # For LIMIT orders, KuCoin calculates margin based on limit price, not mark price
            order_price_for_validation = final_price if (order_type.upper() == 'LIMIT' and final_price) else current_price
            if not order_price_for_validation or order_price_for_validation <= 0:
                logger.warning("Cannot validate position size: no valid price available")
                order_price_for_validation = current_price
            final_position_notional = trade_amount * order_price_for_validation

            # Get original position_size to compare
            try:
                from src.services.trader_config_service import trader_config_service
                trader_id = (getattr(self, 'trader_id', None) or '').strip().lower()
                exchange_key = 'kucoin'
                config = await trader_config_service.get_trader_config(trader_id)
                original_position_size = float(config.position_size) if config and config.exchange.value == exchange_key else 0.0
            except Exception:
                original_position_size = 0.0

            if original_position_size > 0:
                # Calculate expected margin (notional / leverage)
                leverage_value_temp = 3.0  # Will be fetched below, but use default for now
                try:
                    from src.services.trader_config_service import trader_config_service
                    trader_id_temp = (getattr(self, 'trader_id', None) or '').strip().lower()
                    exchange_key_temp = 'kucoin'
                    config_temp = await trader_config_service.get_trader_config(trader_id_temp)
                    if config_temp and config_temp.exchange.value == exchange_key_temp:
                        leverage_value_temp = float(config_temp.leverage)
                except Exception:
                    pass

                expected_margin = final_position_notional / leverage_value_temp if leverage_value_temp > 0 else final_position_notional
                tolerance_factor = 1.5  # Allow 50% tolerance for margin calculation differences

                logger.info(f"Position size validation: Final notional ${final_position_notional:.2f} at ${order_price_for_validation:.2f}, expected margin ${expected_margin:.2f} (intended position_size: ${original_position_size:.2f})")

                if expected_margin > original_position_size * tolerance_factor:
                    error_msg = f"Position size validation failed: Expected margin ${expected_margin:.2f} exceeds intended position_size ${original_position_size:.2f} by more than {tolerance_factor*100:.0f}%. Final notional: ${final_position_notional:.2f} at ${order_price_for_validation:.2f}. Please increase position_size in trader_exchange_config."
                    logger.error(error_msg)
                    return False, error_msg

            # Get leverage from database
            leverage_value = 1.0  # Default leverage
            try:
                from src.services.trader_config_service import trader_config_service
                trader_id = (getattr(self, 'trader_id', None) or '').strip().lower()
                exchange_key = 'kucoin'

                config = await trader_config_service.get_trader_config(trader_id)
                if config and config.exchange.value == exchange_key:
                    leverage_value = float(config.leverage)
                    logger.info(f"Using leverage from database: {leverage_value}x for trader {trader_id}")
                else:
                    logger.warning(f"No leverage config found for trader {trader_id}, using default 1x")
            except Exception as e:
                logger.error(f"Failed to get leverage from TraderConfigService: {e}")

            # Execute the order using correct parameter names and KuCoin symbol format
            logger.info(f"Executing KuCoin order: {kucoin_symbol} {SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL} {order_type.upper()} amount={trade_amount} leverage={leverage_value}x")
            result = await self.kucoin_exchange.create_futures_order(
                pair=kucoin_symbol,  # Use the correct KuCoin symbol format
                side=SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL,
                order_type=order_type.upper(),
                amount=trade_amount,
                price=final_price if order_type.upper() == 'LIMIT' else None,
                client_order_id=client_order_id,
                leverage=leverage_value
            )

            if 'error' in result:
                logger.error(f"KuCoin order failed: {result['error']}")
                return False, result['error']

            # CRITICAL: Get order status immediately after placement to get execution details
            order_id = result.get('orderId') or result.get('order_id')
            if order_id:
                logger.info(f"Order placed successfully, checking status for order ID: {order_id}")

                await asyncio.sleep(2)  # Wait a bit longer for order processing

                try:
                    status_result = await self.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
                except Exception as status_error:
                    logger.warning(f"Order status check failed for {order_id}: {status_error}")
                    status_result = None

                if status_result:
                    logger.info(f"Retrieved order status: {status_result}")

                    filled_size = float(status_result.get('filledSize', 0))
                    filled_value = float(status_result.get('filledValue', 0))

                    actual_entry_price = 0.0
                    if filled_size > 0 and filled_value > 0:
                        actual_entry_price = filled_value / filled_size
                        logger.info(f"Calculated actual entry price: {actual_entry_price} (filled_value: {filled_value}, filled_size: {filled_size})")
                    elif filled_size > 0 and final_price:
                        actual_entry_price = final_price
                        logger.info(f"Using final price as entry price: {actual_entry_price}")

                    result.update({
                        'filledSize': filled_size,
                        'filledValue': filled_value,
                        'actualEntryPrice': actual_entry_price,
                        'orderStatus': status_result.get('status'),
                        'executionDetails': status_result
                    })

                    # Add contract multiplier for asset quantity conversion
                    filters = await self.kucoin_exchange.get_futures_symbol_filters(trading_pair)
                    contract_multiplier = 1
                    if filters and 'multiplier' in filters:
                        contract_multiplier = int(filters['multiplier'])

                    # Add multiplier to execution details
                    if isinstance(result['executionDetails'], dict):
                        result['executionDetails']['contract_multiplier'] = contract_multiplier
                    else:
                        result['executionDetails'] = {
                            'contract_multiplier': contract_multiplier,
                            'original_details': result['executionDetails']
                        }

                    logger.info(f"✅ KuCoin order executed with details - Size: {filled_size}, Entry Price: {actual_entry_price}")
                else:
                    logger.warning(f"Could not retrieve order status for {order_id}, using original result")
                    if final_price and trade_amount:
                        # Get contract multiplier for fallback case
                        filters = await self.kucoin_exchange.get_futures_symbol_filters(trading_pair)
                        contract_multiplier = 1
                        if filters and 'multiplier' in filters:
                            contract_multiplier = int(filters['multiplier'])

                        result.update({
                            'filledSize': 0,  # No fill yet for NEW orders
                            'filledValue': 0,  # No fill yet for NEW orders
                            'actualEntryPrice': final_price,
                            'orderStatus': 'NEW',
                            'executionDetails': {
                                'note': 'Status check failed, using order data - order not yet filled',
                                'contract_multiplier': contract_multiplier
                            }
                        })
                        logger.info(f"Added fallback execution details - Order placed but not yet filled, Entry Price: {final_price}")
            else:
                logger.warning("No order ID found in result, cannot check execution details")

            # Update cooldown
            self.trade_cooldowns[cooldown_key] = time.time()

            logger.info(f"✅ KuCoin order executed successfully: {result}")

            # Log execution details for debugging
            if 'filledSize' in result and 'actualEntryPrice' in result:
                logger.info(f"📊 Execution Summary - Symbol: {coin_symbol}, Size: {result['filledSize']}, Entry Price: {result['actualEntryPrice']}, Order ID: {order_id}")

            return True, result

        except Exception as e:
            logger.error(f"Error processing KuCoin signal: {e}")
            return False, f"KuCoin signal processing error: {str(e)}"

    def _normalize_stop_loss_value(self, value: Union[float, str]) -> Optional[float]:
        """Parse stop loss that may include percentage e.g. '40190 (7.14%)' into float price."""
        try:
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip()
            import re
            m = re.search(r"-?\d+(?:\.\d+)?", text)
            if not m:
                return None
            return float(m.group(0))
        except Exception:
            return None

    async def close_position_at_market(
        self,
        trade_row: Dict[str, Any],
        reason: str = "manual_close",
        close_percentage: float = 100.0
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Close a position at market price on KuCoin.

        Args:
            trade_row: Trade row from database
            reason: Reason for closing
            close_percentage: Percentage of position to close

        Returns:
            Tuple of (success, response)
        """
        try:
            logger.info(f"Closing KuCoin position: {reason} ({close_percentage}%)")

            # Get coin symbol from trade data
            coin_symbol = trade_row.get('coin_symbol')
            if not coin_symbol:
                logger.error("No coin symbol found in trade row")
                return False, "No coin symbol found in trade row"

            # Convert to KuCoin trading pair
            trading_pair = f"{coin_symbol.upper()}-USDT"

            # Determine side based on position type
            position_type = trade_row.get('signal_type', 'LONG')
            side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY

            # Get actual position size from trade data
            position_size_raw = trade_row.get('position_size')
            position_size = float(position_size_raw) if position_size_raw is not None else 0.0

            # If no position size in trade data, try to get it from the response
            if position_size <= 0:
                response_data = trade_row.get('kucoin_response', {})
                if isinstance(response_data, str):
                    import json
                    try:
                        response_data = json.loads(response_data)
                    except:
                        response_data = {}
                if isinstance(response_data, dict):
                    orig_qty = response_data.get('origQty') or response_data.get('size')
                    position_size = float(orig_qty) if orig_qty is not None else 0.0

            # If still no position size, fetch live positions from exchange
            if position_size <= 0:
                try:
                    positions = await self.kucoin_exchange.get_futures_position_information()
                    target_symbol = f"{coin_symbol.upper()}USDTM"
                    for pos in positions:
                        if pos.get('symbol') == target_symbol:
                            pos_size = float(pos.get('size', 0))
                            if pos_size != 0:
                                position_size = abs(pos_size)
                                logger.info(f"Fetched live position size from exchange: {position_size} for {coin_symbol}")
                                break
                except Exception as e:
                    logger.warning(f"Could not fetch live position size: {e}")

            if position_size <= 0:
                logger.info(f"Position for {coin_symbol} is already closed or has zero size. Treating as acknowledged.")
                return True, {"message": "Position already closed, no action needed"}

            # Validate close_percentage
            if close_percentage is None or not isinstance(close_percentage, (float, int)) or close_percentage <= 0 or close_percentage > 100:
                logger.error(f"Invalid close_percentage: {close_percentage}. Must be between 0 and 100")
                return False, f"Invalid close_percentage: {close_percentage}. Must be between 0 and 100"

            # Calculate quantity to close based on percentage
            try:
                quantity = float(position_size) * (float(close_percentage) / 100.0)
                if quantity <= 0:
                    logger.error(f"Calculated quantity to close is invalid: {quantity}")
                    return False, f"Calculated quantity to close is invalid: {quantity}"
            except (TypeError, ValueError) as e:
                logger.error(f"Invalid position size or close_percentage for close: position_size={position_size}, close_percentage={close_percentage}, error={e}")
                return False, f"Invalid position size or close_percentage for close: {str(e)}"

            logger.info(f"Closing {close_percentage}% of position: {quantity} {coin_symbol} (total: {position_size})")

            # Check if position exists before attempting to close (idempotency)
            try:
                positions = await self.kucoin_exchange.get_futures_position_information()
                target_symbol = f"{coin_symbol.upper()}USDTM"
                position_exists = False
                for pos in positions:
                    if pos.get('symbol') == target_symbol:
                        pos_size = float(pos.get('size', 0))
                        if pos_size != 0:
                            position_exists = True
                            break

                if not position_exists:
                    logger.info(f"Position for {coin_symbol} does not exist on exchange - already closed")
                    return True, {"message": "Position already closed, no action needed"}
            except Exception as e:
                logger.warning(f"Could not check position existence before close: {e}")

            # Create market order to close position using direct API call
            logger.info(f"Executing KuCoin close order: {trading_pair} {side} {ORDER_TYPE_MARKET} amount={quantity}")
            success, result = await self.kucoin_exchange.close_position(
                pair=trading_pair,
                amount=quantity,
                position_type=position_type
            )

            if not success:
                # Check if error indicates position already closed
                error_msg = str(result) if isinstance(result, (str, dict)) else ''
                if isinstance(result, dict):
                    error_msg = result.get('error', '') or result.get('message', '') or str(result)

                # KuCoin error codes for "no position" scenarios
                if any(indicator in error_msg.lower() for indicator in [
                    'no open positions', 'position already closed', 'no position',
                    '300009', 'position not found', 'position does not exist'
                ]):
                    logger.info(f"Position already closed on KuCoin: {error_msg}")
                    return True, {"message": "Position already closed, no action needed"}

                logger.error(f"KuCoin close order failed: {result}")
                return False, result

            logger.info(f"✅ KuCoin position closed successfully: {result}")
            return True, result

        except Exception as e:
            logger.error(f"Error closing KuCoin position: {e}")
            return False, f"KuCoin position close error: {str(e)}"

    async def process_followup_signal(
        self,
        signal_data: Dict[str, Any],
        trade_row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a follow-up signal for KuCoin using dynamic parsing.

        Args:
            signal_data: The follow-up signal data
            trade_row: The original trade row

        Returns:
            Response data
        """
        try:
            logger.info(f"Processing KuCoin follow-up signal: {signal_data}")

            # Use dynamic alert parser for consistent parsing
            from src.core.dynamic_alert_parser import DynamicAlertParser
            parser = DynamicAlertParser()

            content = signal_data.get('content', '')
            if not content:
                return {"success": False, "message": "No content provided in signal data"}

            # Parse the alert content dynamically
            parsed_alert = await parser.parse_alert_content(content, trade_row)
            if not parsed_alert:
                return {"success": False, "message": "Failed to parse alert content"}

            logger.info(f"Dynamic parsing result: {parsed_alert}")

            # Update signal_data with parsed alert
            signal_data['parsed_alert'] = parsed_alert

            # Extract action and details from parsed result
            action = parsed_alert.get('action_type')
            try:
                from src.core.action_normalizer import ActionNormalizer
                action = ActionNormalizer.normalize(action)
            except Exception:
                action = action or 'unknown'
            details = {
                'stop_price': parsed_alert.get('stop_loss_price'),
                'reason': parsed_alert.get('reason'),
                'exchange_action': parsed_alert.get('exchange_action')
            }
            try:
                cp = parsed_alert.get('close_percentage')
                if isinstance(cp, (int, float)) and cp > 0:
                    details['close_percentage'] = float(cp)
            except Exception:
                pass

            # Ensure coin_symbol present in trade_row for downstream operations
            try:
                if not trade_row.get('coin_symbol') and parsed_alert.get('coin_symbol'):
                    trade_row['coin_symbol'] = parsed_alert.get('coin_symbol')
            except Exception:
                pass

            if not action or action == 'unknown':
                return {"success": False, "message": f"Unrecognized follow-up action: {action}"}

            # Process based on action type
            if action in ['stop_loss_update', 'break_even']:
                logger.info(f"Processing stop loss update for KuCoin: {action}")

                stop_price = details.get('stop_price')
                entry_price = trade_row.get('entry_price')
                coin_symbol = trade_row.get('coin_symbol')
                position_size = float(trade_row.get('position_size') or 0.0)

                # Handle break-even: use entry_price when stop_price is None, 'BE', or 'break_even'
                if stop_price in (None, 'BE', 'break_even') or str(stop_price).lower() == 'be':
                    if entry_price and entry_price > 0:
                        stop_price = entry_price
                    else:
                        # Try to fetch from exchange
                        try:
                            if coin_symbol:
                                positions = await self.kucoin_exchange.get_futures_position_information()
                                target_symbol = f"{coin_symbol.upper()}USDTM"
                                for pos in positions:
                                    if pos.get('symbol') == target_symbol:
                                        pos_size = float(pos.get('size', 0))
                                        if pos_size != 0:
                                            fetched_entry = float(pos.get('avgEntryPrice', 0) or pos.get('entryPrice', 0))
                                            if fetched_entry > 0:
                                                stop_price = fetched_entry
                                                position_size = abs(pos_size)
                                                logger.info(f"Fetched entry price {fetched_entry} from exchange for break-even")
                                                break
                        except Exception as e:
                            logger.warning(f"Could not fetch entry price from exchange: {e}")

                    if not isinstance(stop_price, (float, int)) or stop_price <= 0:
                        return {
                            "success": False,
                            "message": f"Could not determine break-even price: entry_price not available",
                            "parsed_alert": parsed_alert,
                            "exchange_response": "Could not determine break-even price"
                        }

                if not isinstance(stop_price, (float, int)) or stop_price <= 0:
                    return {
                        "success": False,
                        "message": f"Invalid stop price: {stop_price}",
                        "parsed_alert": parsed_alert,
                        "exchange_response": f"Invalid stop price: {stop_price}"
                    }

                if not coin_symbol or position_size <= 0:
                    return {
                        "success": False,
                        "message": f"Invalid trade data for stop loss update: coin_symbol={coin_symbol}, position_size={position_size}",
                        "parsed_alert": parsed_alert,
                        "exchange_response": "Invalid trade data"
                    }

                trading_pair = self.kucoin_exchange.get_futures_trading_pair(coin_symbol)

                # Cancel existing stop loss orders
                try:
                    open_orders = await self.kucoin_exchange.get_all_open_futures_orders()
                    for order in open_orders:
                        if (order.get('symbol') == trading_pair or
                            order.get('symbol') == f"{coin_symbol.upper()}USDTM") and \
                           order.get('type', '').upper() in ['STOP', 'STOP_MARKET']:
                            await self.kucoin_exchange.cancel_futures_order(trading_pair, order.get('orderId', ''))
                            logger.info(f"Cancelled existing stop loss order: {order.get('orderId')}")
                except Exception as e:
                    logger.warning(f"Could not cancel existing stop loss orders: {e}")

                # Create new stop loss order
                new_sl_order = await self.kucoin_exchange.create_futures_order(
                    pair=trading_pair,
                    side=SIDE_SELL,
                    order_type='MARKET',
                    stop_price=stop_price,
                    amount=position_size,
                    reduce_only=True
                )

                if new_sl_order and 'orderId' in new_sl_order:
                    logger.info(f"Stop loss updated for KuCoin: {stop_price}, order ID: {new_sl_order['orderId']}")
                    return {
                        "success": True,
                        "message": f"Stop loss updated for KuCoin: {stop_price}",
                        "parsed_alert": parsed_alert,
                        "exchange_response": new_sl_order
                    }
                else:
                    error_msg = new_sl_order.get('error', str(new_sl_order)) if isinstance(new_sl_order, dict) else str(new_sl_order)
                    logger.error(f"Failed to update stop loss on KuCoin: {error_msg}")
                    return {
                        "success": False,
                        "message": f"Failed to update stop loss: {error_msg}",
                        "parsed_alert": parsed_alert,
                        "exchange_response": new_sl_order
                    }

            elif action in ['stop_loss_hit', 'position_closed']:
                logger.info("Processing stop loss hit or position close")

                # Check if position is already closed
                try:
                    coin_symbol = trade_row.get('coin_symbol')
                    if coin_symbol:
                        positions = await self.kucoin_exchange.get_futures_position_information()
                        target_symbol = f"{coin_symbol.upper()}USDTM"
                        has_open = False
                        for pos in positions:
                            if pos.get('symbol') == target_symbol:
                                pos_size = float(pos.get('size', 0))
                                if pos_size != 0:
                                    has_open = True
                                    break

                        if not has_open:
                            logger.info(f"Position for {coin_symbol} is already closed. Treating as acknowledged.")
                            return {
                                "success": True,
                                "message": "Position already closed, no action needed",
                                "parsed_alert": parsed_alert,
                                "exchange_response": "Position already closed"
                            }
                except Exception as e:
                    logger.warning(f"Could not check position status: {e}")

                success, response = await self.close_position_at_market(trade_row, action.replace('_', ' '))
                return {
                    "success": success,
                    "message": response,
                    "parsed_alert": parsed_alert,
                    "exchange_response": response
                }

            elif action in ['take_profit_1', 'take_profit_2']:
                logger.info(f"Processing take profit: {action}")

                # Set default close percentage if not provided
                tp_idx = int(action.split('_')[-1])
                close_percentage = details.get('close_percentage')
                if close_percentage is None:
                    close_percentage = 50.0 if tp_idx == 1 else 25.0
                    logger.info(f"Using default close percentage {close_percentage}% for TP{tp_idx}")

                success, response = await self.close_position_at_market(trade_row, "take_profit", float(close_percentage))
                return {
                    "success": success,
                    "message": response,
                    "parsed_alert": parsed_alert,
                    "exchange_response": response
                }

            elif action == 'tp1_and_break_even':
                logger.info("Processing TP1 and break-even")
                # Process TP1 first
                success1, response1 = await self.close_position_at_market(trade_row, "take_profit", 50)
                if success1:
                    return {
                        "success": True,
                        "message": "TP1 processed and stop loss moved to break-even",
                        "parsed_alert": parsed_alert,
                        "exchange_response": f"TP1: {response1}, Stop loss moved to BE"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"TP1 processing failed: {response1}",
                        "parsed_alert": parsed_alert
                    }

            elif action in ['limit_order_cancelled']:
                logger.info("Processing limit order cancel")
                return {
                    "success": True,
                    "message": "Limit order cancel acknowledged (KuCoin)",
                    "parsed_alert": parsed_alert,
                    "exchange_response": "Limit order cancel acknowledged"
                }

            elif action in ['order_filled', 'limit_order_filled', 'limit_order_not_filled']:
                # Normalize messaging regardless of exact variant
                readable = action.replace('_', ' ')
                logger.info(f"Processing informational order status: {readable}")
                return {
                    "success": True,
                    "message": f"{readable} (KuCoin)",
                    "parsed_alert": parsed_alert,
                    "exchange_response": f"{readable}"
                }

            else:
                logger.warning(f"Unknown follow-up signal: {content}")
                return {
                    "success": False,
                    "message": f"Unknown follow-up signal: {content}",
                    "parsed_alert": parsed_alert,
                    "exchange_response": f"Unknown signal: {content}"
                }

        except Exception as e:
            logger.error(f"Error processing KuCoin follow-up signal: {e}")
            return {
                "success": False,
                "message": f"KuCoin follow-up error: {str(e)}",
                "parsed_alert": signal_data.get('parsed_alert'),
                "exchange_response": f"Error: {str(e)}"
            }

    def get_exchange_type(self) -> str:
        """Get the exchange type."""
        return "kucoin"
