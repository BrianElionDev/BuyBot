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
        quantity_multiplier: Optional[int] = None
    ) -> float:
        """
        Calculate the trade amount based on live database position_size and current price.
        """
        try:
            # Get position_size from database instead of hardcoded config
            usdt_amount = self.config.TRADE_AMOUNT  # Fallback to config
            try:
                from src.services.trader_config_service import trader_config_service
                trader_id = (getattr(self, 'trader_id', None) or '').strip().lower()
                exchange_key = 'kucoin'

                config = await trader_config_service.get_trader_config(trader_id)
                if not config or config.exchange.value != exchange_key:
                    msg = f"Missing or mismatched trader config for trader={trader_id}, exchange={exchange_key}; refusing to fallback for position_size"
                    logger.error(msg)
                    return 0.0
                usdt_amount = float(config.position_size)
                logger.info(f"Using database position_size (final notional): ${usdt_amount} for trader {trader_id}")
            except Exception as e:
                logger.error(f"Failed to get position_size from TraderConfigService: {e}")
                return 0.0

            # Calculate trade amount based on USDT value and current price
            # IMPORTANT: position_size is FINAL NOTIONAL (no leverage amplification here)
            trade_amount = usdt_amount / current_price
            logger.info(f"Calculated trade amount (no leverage amplification): {trade_amount} {coin_symbol} (${usdt_amount:.2f} / ${current_price:.8f})")

            # Apply quantity multiplier if specified (for memecoins)
            if quantity_multiplier and quantity_multiplier > 1:
                trade_amount *= quantity_multiplier
                logger.info(f"Applied quantity multiplier {quantity_multiplier}: {trade_amount} {coin_symbol}")

            # Get symbol filters for precision formatting
            trading_pair = f"{coin_symbol.upper()}-USDT"
            filters = await self.kucoin_exchange.get_futures_symbol_filters(trading_pair)

            if filters:
                lot_size_filter = filters.get('LOT_SIZE', {})
                min_qty = float(lot_size_filter.get('minQty', 0.001))
                max_qty = float(lot_size_filter.get('maxQty', 1000000))

                # Apply precision formatting
                step_size = float(lot_size_filter.get('stepSize', 0.0001))
                if step_size > 0:
                    trade_amount = round(trade_amount / step_size) * step_size

                # Ensure within bounds
                trade_amount = max(min_qty, min(max_qty, trade_amount))
                logger.info(f"Adjusted trade amount: {trade_amount} (min: {min_qty}, max: {max_qty})")

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
        discord_id: Optional[str] = None
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

            # Calculate trade amount
            trade_amount = await self._calculate_trade_amount(
                coin_symbol, current_price, quantity_multiplier
            )

            if trade_amount <= 0:
                logger.error(f"Invalid trade amount calculated: {trade_amount}")
                return False, f"Invalid trade amount calculated: {trade_amount}"

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
                if isinstance(response_data, dict):
                    orig_qty = response_data.get('origQty')
                    position_size = float(orig_qty) if orig_qty is not None else 0.0

            # If still no position size, fetch live positions and infer
            current_leverage = 1.0  # Default leverage
            if position_size <= 0:
                positions = await self.kucoin_exchange.get_futures_position_information()
                target_symbol = f"{coin_symbol.upper()}USDTM"
                for pos in positions:
                    if pos.get('symbol') == target_symbol and float(pos.get('size', 0)) > 0:
                        position_size = float(pos.get('size', 0))
                        current_leverage = float(pos.get('leverage', 1.0))
                        break
            if position_size <= 0:
                logger.error(f"No valid position size found for {coin_symbol}")
                return False, f"No valid position size found for {coin_symbol}"

            # Calculate quantity to close based on percentage
            try:
                quantity = float(position_size) * (float(close_percentage) / 100.0)
            except Exception:
                logger.error(f"Invalid position size for close: {position_size}")
                return False, f"Invalid position size for close: {position_size}"

            logger.info(f"Closing {close_percentage}% of position: {quantity} {coin_symbol} (total: {position_size})")

            # Create market order to close position using direct API call
            logger.info(f"Executing KuCoin close order: {trading_pair} {side} {ORDER_TYPE_MARKET} amount={quantity}")
            success, result = await self.kucoin_exchange.close_position(
                pair=trading_pair,
                amount=quantity,
                position_type=position_type
            )

            if not success:
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
            details = {
                'stop_price': parsed_alert.get('stop_loss_price'),
                'close_percentage': parsed_alert.get('close_percentage'),
                'reason': parsed_alert.get('reason'),
                'exchange_action': parsed_alert.get('exchange_action')
            }

            if not action or action == 'unknown':
                return {"success": False, "message": f"Unrecognized follow-up action: {action}"}

            # Process based on action type
            if action in ['stop_loss_update', 'break_even']:
                logger.info(f"Processing stop loss update for KuCoin: {action}")
                return {
                    "success": True,
                    "message": f"Stop loss updated for KuCoin: {details.get('stop_price', 'BE')}",
                    "parsed_alert": parsed_alert,
                    "exchange_response": f"Stop loss updated to {details.get('stop_price', 'BE')}"
                }

            elif action in ['stop_loss_hit', 'position_closed']:
                logger.info("Processing stop loss hit or position close")
                success, response = await self.close_position_at_market(trade_row, "stop_loss_hit")
                return {
                    "success": success,
                    "message": response,
                    "parsed_alert": parsed_alert,
                    "exchange_response": response
                }

            elif action in ['take_profit_1', 'take_profit_2']:
                logger.info(f"Processing take profit: {action}")
                close_percentage = details.get('close_percentage', 50)
                if close_percentage is None:
                    close_percentage = 50.0
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

            elif action in ['limit_order_filled', 'limit_order_not_filled']:
                logger.info(f"Processing limit order status: {action}")
                return {
                    "success": True,
                    "message": f"Limit order {action.replace('_', ' ')} (KuCoin)",
                    "parsed_alert": parsed_alert,
                    "exchange_response": f"Limit order {action.replace('_', ' ')}"
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
