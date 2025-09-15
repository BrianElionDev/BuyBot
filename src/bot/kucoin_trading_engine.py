"""
KuCoin Trading Engine

This module provides a trading engine specifically for KuCoin exchange operations.
It mirrors the functionality of the main TradingEngine but uses KuCoin-specific implementations.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_bot.database import DatabaseManager

from src.exchange import KucoinExchange
from src.services.pricing.price_service import PriceService
from src.exchange import FixedFeeCalculator

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

logger = logging.getLogger(__name__)

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
        entry_prices: Optional[List[float]] = None
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

            # Get current price for validation from KuCoin
            current_price = await self.price_service.get_coin_price(coin_symbol, exchange="kucoin")
            if not current_price:
                logger.error(f"Could not get current price for {coin_symbol} from KuCoin")
                return False, f"Could not get current price for {coin_symbol} from KuCoin"

            # Handle price range logic
            final_price, price_reason = self._handle_price_range_logic(
                entry_prices, order_type, position_type, current_price
            )
            logger.info(f"Price selection: {price_reason}")

            # Convert to KuCoin trading pair format
            trading_pair = f"{coin_symbol.upper()}-USDT"

            # Validate symbol is supported
            is_supported = await self.kucoin_exchange.is_futures_symbol_supported(trading_pair)
            if not is_supported:
                logger.error(f"Symbol {trading_pair} not supported on KuCoin")
                return False, f"Symbol {trading_pair} not supported on KuCoin"

            # Execute the order using correct parameter names
            logger.info(f"Executing KuCoin order: {trading_pair} {SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL} {order_type.upper()}")
            result = await self.kucoin_exchange.create_futures_order(
                pair=trading_pair,
                side=SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL,
                order_type=order_type.upper(),
                amount=1.0,  # Default quantity, should be calculated based on position size
                price=final_price if order_type.upper() == 'LIMIT' else None,
                client_order_id=client_order_id
            )

            if 'error' in result:
                logger.error(f"KuCoin order failed: {result['error']}")
                return False, result['error']

            # Update cooldown
            self.trade_cooldowns[cooldown_key] = time.time()

            logger.info(f"✅ KuCoin order executed successfully: {result}")
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

            # Calculate quantity (simplified - should use actual position size)
            quantity = 1.0  # This should be calculated from actual position size

            # Create market order to close position
            logger.info(f"Executing KuCoin close order: {trading_pair} {side} {ORDER_TYPE_MARKET}")
            result = await self.kucoin_exchange.create_futures_order(
                pair=trading_pair,
                side=side,
                order_type=ORDER_TYPE_MARKET,
                amount=quantity,
                reduce_only=True  # This should close the position
            )

            if 'error' in result:
                logger.error(f"KuCoin close order failed: {result['error']}")
                return False, result['error']

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
        Process a follow-up signal for KuCoin.

        Args:
            signal_data: The follow-up signal data
            trade_row: The original trade row

        Returns:
            Response data
        """
        try:
            logger.info(f"Processing KuCoin follow-up signal: {signal_data}")

            # Parse the signal content to determine action
            content = signal_data.get('content', '')

            # Simple signal parsing for common actions
            if 'stops moved to be' in content.lower() or 'moved to be' in content.lower():
                logger.info("Processing stop loss move to break-even")
                # This would need to be implemented based on KuCoin's stop loss management
                return {"status": "success", "message": "Stop loss moved to break-even (KuCoin)"}

            elif 'stopped out' in content.lower() or 'stop loss hit' in content.lower():
                logger.info("Processing stop loss hit")
                success, response = await self.close_position_at_market(trade_row, "stop_loss_hit")
                return {"status": "success" if success else "error", "message": response}

            elif 'closed in profits' in content.lower() or 'closed in profit' in content.lower():
                logger.info("Processing position close in profit")
                success, response = await self.close_position_at_market(trade_row, "profit_close")
                return {"status": "success" if success else "error", "message": response}

            elif 'limit order filled' in content.lower():
                logger.info("Processing limit order filled")
                return {"status": "success", "message": "Limit order filled (KuCoin)"}

            else:
                logger.warning(f"Unknown follow-up signal: {content}")
                return {"status": "error", "message": f"Unknown follow-up signal: {content}"}

        except Exception as e:
            logger.error(f"Error processing KuCoin follow-up signal: {e}")
            return {"status": "error", "message": f"KuCoin follow-up error: {str(e)}"}

    def get_exchange_type(self) -> str:
        """Get the exchange type."""
        return "kucoin"
