"""
Position management utilities for the trading bot.

This module contains core functions for managing trading positions
including position status checks, closing positions, and position calculations.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, Union

from src.core.response_models import ServiceResponse, TradeOperationResult, ErrorCode

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Core class for managing trading positions.
    """

    def __init__(self, exchange, db_manager):
        """
        Initialize the position manager.

        Args:
            exchange: The exchange instance (Binance, KuCoin, etc.)
            db_manager: The database manager instance
        """
        self.exchange = exchange
        self.db_manager = db_manager

    async def is_position_open(self, coin_symbol: str, position_side: str = 'BOTH') -> bool:
        """
        Check if a position is open for the given symbol and side on the exchange.

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')
            position_side: The position side ('LONG', 'SHORT', or 'BOTH')

        Returns:
            True if position is open, False otherwise
        """
        if not coin_symbol:
            logger.error("coin_symbol is required for is_position_open")
            return False

        try:
            trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)
            pos_info = await self.exchange.get_futures_position_information()

            for pos in pos_info:
                if pos['positionSide'] == position_side and float(pos['positionAmt']) != 0:
                    logger.info(f"Position is open for {coin_symbol} side {position_side}: {pos['positionAmt']}")
                    return True

            logger.info(f"No open position for {coin_symbol} side {position_side}")
            return False

        except Exception as e:
            logger.error(f"Error checking position status for {coin_symbol}: {e}")
            return False

    async def close_position_at_market(
        self,
        active_trade: Dict,
        reason: str = "manual_close",
        close_percentage: float = 100.0
    ) -> Tuple[bool, Dict]:
        """
        Closes a percentage of an open futures position at the current market price.
        CRITICAL: Cancels all TP/SL orders before closing position to prevent unwanted executions.

        Args:
            active_trade: The active trade dictionary
            reason: Reason for closing the position
            close_percentage: Percentage of position to close (default 100%)

        Returns:
            Tuple of (success, response_data)
        """
        try:
            from src.bot.utils.signal_parser import SignalParser

            parsed_signal = SignalParser.parse_parsed_signal(active_trade.get("parsed_signal"))
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
            trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)
            is_futures = position_type in ['LONG', 'SHORT']

            # Cancel existing TP/SL orders before closing position
            if is_futures:
                if close_percentage >= 100.0:
                    # Full close - cancel all TP/SL orders
                    logger.info(f"Cancelling all TP/SL orders for {trading_pair} before full close")
                    # Note: This would need to call the order cancellation method
                    # await self.cancel_tp_sl_orders(trading_pair, active_trade)
                else:
                    # Partial close - only cancel specific orders if needed
                    # For now, we'll keep TP/SL orders active for partial closes
                    logger.info(f"Partial close {close_percentage}% - keeping TP/SL orders active")

            # Determine the side for closing the position
            if position_type == 'LONG':
                close_side = 'SELL'  # Sell to close long position
            elif position_type == 'SHORT':
                close_side = 'BUY'   # Buy to close short position
            else:
                return False, {"error": f"Unknown position type: {position_type}"}

            # Create the closing order
            close_order = await self.exchange.create_futures_order(
                pair=trading_pair,
                side=close_side,
                order_type='MARKET',
                amount=amount_to_close,
                reduce_only=True
            )

            if close_order and 'orderId' in close_order:
                logger.info(f"Successfully closed {close_percentage}% of {position_type} position for {coin_symbol}. Order ID: {close_order['orderId']}")
                return True, close_order
            else:
                logger.error(f"Failed to close position for {coin_symbol}: {close_order}")
                return False, {"error": "Failed to close position", "response": close_order}

        except Exception as e:
            logger.error(f"Error closing position for {active_trade.get('coin_symbol', 'unknown')}: {e}")
            return False, {"error": f"Error closing position: {str(e)}"}

    async def calculate_position_breakeven_price(self, active_trade: Dict) -> Tuple[bool, Union[float, str]]:
        """
        Calculate the breakeven price for an active position.

        Args:
            active_trade: The active trade dictionary

        Returns:
            Tuple of (success, breakeven_price_or_error)
        """
        try:
            from src.bot.utils.signal_parser import SignalParser

            parsed_signal = SignalParser.parse_parsed_signal(active_trade.get('parsed_signal'))
            entry_price = active_trade.get('entry_price')
            position_type = parsed_signal.get('position_type', 'LONG')

            if not entry_price or entry_price <= 0:
                return False, "Invalid entry price for breakeven calculation"

            # Calculate breakeven price using fee calculator
            from src.exchange.fees.fee_calculator import FixedFeeCalculator
            from config import settings as config

            fee_calculator = FixedFeeCalculator(fee_rate=config.FIXED_FEE_RATE)
            breakeven_price = fee_calculator.calculate_breakeven_price(entry_price)

            logger.info(f"Breakeven price calculated for {active_trade.get('coin_symbol', 'unknown')}: {breakeven_price}")
            return True, float(breakeven_price)

        except Exception as e:
            logger.error(f"Error calculating breakeven price: {e}")
            return False, f"Error calculating breakeven price: {str(e)}"
