import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

# Import DatabaseManager type for type hints only
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_bot.database import DatabaseManager
from src.exchange import BinanceExchange
from src.services.pricing.price_service import PriceService
from src.exchange import FixedFeeCalculator

# Import modularized components
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

from src.bot.signal_processor.initial_signal_processor import InitialSignalProcessor
from src.bot.signal_processor.followup_signal_processor import FollowupSignalProcessor

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
FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET = 'TAKE_PROFIT_MARKET'

class TradingEngine:
    """
    The core logic for processing signals and executing trades.
    """
    def __init__(self, price_service: PriceService, binance_exchange: BinanceExchange, db_manager: 'DatabaseManager'):
        self.price_service = price_service
        self.binance_exchange = binance_exchange
        self.db_manager = db_manager
        self.trade_cooldowns = {}
        # Add config attribute for signal processors
        self.config = config
        # Use FixedFeeCalculator for simplified fee management
        self.fee_calculator = FixedFeeCalculator(fee_rate=config.FIXED_FEE_RATE)

        # Initialize utility modules
        self.signal_parser = SignalParser()
        self.price_calculator = PriceCalculator()
        self.validation_utils = ValidationUtils()
        self.response_parser = ResponseParser()

        # Initialize core modules
        self.position_manager = PositionManager(binance_exchange, db_manager)
        self.market_data_handler = MarketDataHandler(binance_exchange, price_service)
        self.trade_calculator = TradeCalculator(self.fee_calculator)

        # Initialize risk management modules
        self.stop_loss_manager = StopLossManager(binance_exchange)
        self.take_profit_manager = TakeProfitManager(binance_exchange)
        self.position_auditor = PositionAuditor(binance_exchange)

        # Initialize order management modules
        self.order_creator = OrderCreator(binance_exchange)
        self.order_canceller = OrderCanceller(binance_exchange)
        self.order_updater = OrderUpdater(binance_exchange)

        # Initialize signal processing modules
        self.initial_signal_processor = InitialSignalProcessor(self)
        self.followup_signal_processor = FollowupSignalProcessor(self)

        logger.info(f"Using FixedFeeCalculator with {config.FIXED_FEE_RATE * 100}% fee cap")
        logger.info("TradingEngine initialized with all modularized components.")



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
        return await self.initial_signal_processor.process_signal(
            coin_symbol, signal_price, position_type, order_type, stop_loss,
            take_profits, dca_range, client_order_id, price_threshold_override,
            quantity_multiplier, entry_prices
        )

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
        # Create a mock active_trade dict for the position manager
        active_trade = {
            'entry_price': entry_price,
            'parsed_signal': json.dumps({
                'position_type': position_type,
                'coin_symbol': trading_pair.replace('USDT', '')
            })
        }
        success, result = await self.position_manager.calculate_position_breakeven_price(active_trade)
        if success:
            return {
                'trading_pair': trading_pair,
                'entry_price': entry_price,
                'position_type': position_type,
                'breakeven_price': result
            }
        else:
            return {
                'error': result,
                'breakeven_price': None
            }

    async def _create_tp_sl_orders(self, trading_pair: str, position_type: str, position_size: float,
                                 take_profits: Optional[List[float]] = None, stop_loss: Optional[Union[float, str]] = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Create Take Profit and Stop Loss orders using Binance's position-based TP/SL API.
        This will make them appear in the TP/SL column instead of Open Orders.
        Returns a tuple of (tp_sl_orders, stop_loss_order_id)
        """
        return await self.order_creator.create_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

    async def _create_separate_tp_sl_orders(self, trading_pair: str, position_type: str, position_size: float,
                                          take_profits: Optional[List[float]] = None, stop_loss: Optional[Union[float, str]] = None) -> Tuple[List[Dict], Optional[str]]:
        """
        Fallback method to create separate TP/SL orders (appears in Open Orders).
        This is the original implementation that creates STOP_MARKET and TAKE_PROFIT_MARKET orders.
        """
        return await self.order_creator.create_separate_tp_sl_orders(trading_pair, position_type, position_size, take_profits, stop_loss)

    async def update_tp_sl_orders(self, trading_pair: str, position_type: str,
                                new_take_profits: Optional[List[float]] = None,
                                new_stop_loss: Optional[Union[float, str]] = None) -> Tuple[bool, List[Dict]]:
        """
        Update TP/SL orders by canceling existing ones and creating new ones.
        This follows Binance Futures API requirements where TP/SL orders cannot be updated directly.
        """
        try:
            # Cancel existing TP/SL orders first
            # Create a dummy trade object since OrderCanceller requires it
            dummy_trade = {"tp_sl_orders": []}
            await self.cancel_tp_sl_orders(trading_pair, dummy_trade)

            # Get current position size from Binance
            positions = await self.binance_exchange.get_futures_position_information()
            position_size = 0.0

            for pos in positions:
                if pos['symbol'] == trading_pair and float(pos['positionAmt']) != 0:
                    position_size = abs(float(pos['positionAmt']))
                    break

            if position_size <= 0:
                return False, []

            # Create new TP/SL orders
            tp_sl_orders, stop_loss_order_id = await self._create_tp_sl_orders(trading_pair, position_type, position_size, new_take_profits, new_stop_loss)
            return True, tp_sl_orders

        except Exception as e:
            logger.error(f"Error updating TP/SL orders for {trading_pair}: {e}")
            return False, []

    async def cancel_tp_sl_orders(self, trading_pair: str, active_trade: Dict) -> bool:
        """
        Cancel TP/SL orders for a specific symbol using stored order IDs.
        """
        return await self.order_canceller.cancel_tp_sl_orders(trading_pair, active_trade)

    async def cancel_order(self, active_trade: Dict) -> Tuple[bool, Dict]:
        """
        Cancels an open order associated with a trade.
        """
        return await self.order_canceller.cancel_order(active_trade)

    async def is_position_open(self, coin_symbol: str, position_side: str = 'BOTH') -> bool:
        """Check if a position is open for the given symbol and side on Binance Futures."""
        return await self.position_manager.is_position_open(coin_symbol, position_side)

    async def process_trade_update(self, trade_id: int, action: str, details: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Process updates for an existing trade, like taking profit, moving stop loss, or partial close.
        """
        return await self.followup_signal_processor.process_trade_update(trade_id, action, details)

    async def update_stop_loss(self, active_trade: Dict, new_sl_price: float) -> Tuple[bool, Dict]:
        """
        Update stop loss for an active position.
        """
        return await self.stop_loss_manager.update_stop_loss(active_trade, new_sl_price)

    async def create_stop_loss_order(self, trading_pair: str, position_size: float, new_sl_price: float, position_type: str = "LONG") -> Tuple[bool, Dict]:
        """
        Create a new stop loss order for a position.
        """
        try:
            # Determine the side for stop loss based on position type
            new_sl_side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY

            new_sl_order_result = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=new_sl_side,
                order_type=FUTURE_ORDER_TYPE_STOP_MARKET,
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
        from src.bot.utils.price_calculator import PriceCalculator
        current_price = await self.price_service.get_coin_price(coin_symbol)
        if current_price:
            return PriceCalculator.calculate_percentage_stop_loss(float(current_price), position_type, 2.0)
        return None

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
        from src.bot.utils.price_calculator import PriceCalculator
        current_price = await self.price_service.get_coin_price(coin_symbol)
        if current_price:
            return PriceCalculator.calculate_percentage_stop_loss(float(current_price), position_type, percentage)
        return None

    async def calculate_5_percent_stop_loss(self, coin_symbol: str, position_type: str, entry_price: float) -> Optional[float]:
        """
        Calculate a 5% stop loss price from the entry price (supervisor requirement).

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')
            position_type: The position type ('LONG' or 'SHORT')
            entry_price: The entry price for the position

        Returns:
            The calculated stop loss price or None if calculation fails
        """
        from src.bot.utils.price_calculator import PriceCalculator
        return PriceCalculator.calculate_5_percent_stop_loss(entry_price, position_type)

    async def ensure_stop_loss_for_position(self, coin_symbol: str, position_type: str, position_size: float, entry_price: float, external_sl: Optional[float] = None) -> Tuple[bool, Optional[str]]:
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
        return await self.stop_loss_manager.ensure_stop_loss_for_position(coin_symbol, position_type, position_size, entry_price, external_sl)

    async def _cancel_existing_stop_loss_orders(self, trading_pair: str) -> bool:
        """
        Cancel existing stop loss orders for a trading pair.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if successful, False otherwise
        """
        return await self.stop_loss_manager._cancel_existing_stop_loss_orders(trading_pair)

    async def audit_open_positions_for_stop_loss(self) -> Dict[str, Any]:
        """
        Audit all open positions to ensure they have stop loss orders (supervisor requirement).

        Returns:
            Dictionary with audit results
        """
        return await self.stop_loss_manager.audit_open_positions_for_stop_loss()

    async def _check_position_has_stop_loss(self, trading_pair: str) -> bool:
        """
        Check if a position has active stop loss orders.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if position has stop loss orders, False otherwise
        """
        return await self.position_auditor._check_position_has_stop_loss(trading_pair)

    async def calculate_5_percent_take_profit(self, coin_symbol: str, position_type: str, entry_price: float) -> Optional[float]:
        """
        Calculate a 5% take profit price from the entry price.

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')
            position_type: The position type ('LONG' or 'SHORT')
            entry_price: The entry price for the position

        Returns:
            The calculated take profit price or None if calculation fails
        """
        from src.bot.utils.price_calculator import PriceCalculator
        return PriceCalculator.calculate_5_percent_take_profit(entry_price, position_type)

    async def ensure_take_profit_for_position(self, coin_symbol: str, position_type: str, position_size: float, entry_price: float, external_tp: Optional[float] = None) -> Tuple[bool, Optional[str]]:
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
        return await self.take_profit_manager.ensure_take_profit_for_position(coin_symbol, position_type, position_size, entry_price, external_tp)

    async def _cancel_existing_take_profit_orders(self, trading_pair: str) -> bool:
        """
        Cancel existing take profit orders for a trading pair.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if successful, False otherwise
        """
        return await self.take_profit_manager._cancel_existing_take_profit_orders(trading_pair)

    async def audit_open_positions_for_take_profit(self) -> Dict[str, Any]:
        """
        Audit all open positions to ensure they have take profit orders.

        Returns:
            Dictionary with audit results
        """
        return await self.take_profit_manager.audit_open_positions_for_take_profit()

    async def _check_position_has_take_profit(self, trading_pair: str) -> bool:
        """
        Check if a position has active take profit orders.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if position has take profit orders, False otherwise
        """
        return await self.position_auditor._check_position_has_take_profit(trading_pair)

    async def close(self):
        """Close all exchange connections."""
        await self.binance_exchange.close_client()
        logger.info("TradingEngine connections closed.")

    async def close_position_at_market(self, trade_row: Dict, reason: str = "manual_close", close_percentage: float = 100.0) -> Tuple[bool, Dict]:
        """
        Close a position at market price by delegating to the position manager.

        Args:
            trade_row: The trade dictionary
            reason: Reason for closing the position
            close_percentage: Percentage of position to close (default 100%)

        Returns:
            Tuple of (success, response_data)
        """
        return await self.position_manager.close_position_at_market(trade_row, reason, close_percentage)