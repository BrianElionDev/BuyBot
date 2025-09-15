"""
Trade calculation utilities for the trading bot.

This module contains core functions for calculating trade-related values
including trade amounts, quantities, and fee calculations.
"""

import logging
from typing import Dict, Any, Optional, Tuple, Union
from decimal import Decimal

logger = logging.getLogger(__name__)


class TradeCalculator:
    """
    Core class for trade calculations.
    """

    def __init__(self, fee_calculator):
        """
        Initialize the trade calculator.

        Args:
            fee_calculator: The fee calculator instance
        """
        self.fee_calculator = fee_calculator

    def calculate_trade_amount(
        self,
        signal_price: float,
        position_type: str,
        order_type: str,
        entry_prices: Optional[list] = None,
        current_price: Optional[float] = None
    ) -> Tuple[Optional[float], str]:
        """
        Calculate the effective trade amount based on signal parameters.

        Args:
            signal_price: The signal price
            position_type: The position type ('LONG' or 'SHORT')
            order_type: The order type ('MARKET' or 'LIMIT')
            entry_prices: List of entry prices (optional)
            current_price: Current market price (optional)

        Returns:
            Tuple of (effective_price, decision_reason)
        """
        try:
            from src.bot.utils.price_calculator import PriceCalculator

            if entry_prices and current_price:
                result = PriceCalculator.handle_price_range_logic(
                    entry_prices, order_type, position_type, current_price
                )
                # Handle None case
                if result[0] is None:
                    return signal_price, f"Price range logic rejected, using signal price: ${signal_price:.8f}"
                return result
            else:
                # Use signal price directly
                return signal_price, f"Using signal price directly: ${signal_price:.8f}"

        except Exception as e:
            logger.error(f"Error calculating trade amount: {e}")
            return signal_price, f"Error in calculation, using signal price: ${signal_price:.8f}"

    def calculate_position_quantity(
        self,
        trade_amount: float,
        entry_price: float,
        leverage: float = 1.0
    ) -> float:
        """
        Calculate the position quantity based on trade amount and entry price.

        Args:
            trade_amount: The trade amount in USDT
            entry_price: The entry price
            leverage: The leverage multiplier (default 1.0)

        Returns:
            Position quantity
        """
        try:
            if entry_price <= 0:
                logger.error(f"Invalid entry price: {entry_price}")
                return 0.0

            # Calculate notional value
            notional_value = trade_amount * leverage

            # Calculate quantity
            quantity = notional_value / entry_price

            logger.debug(f"Position quantity calculated: {quantity} (amount: {trade_amount}, price: {entry_price}, leverage: {leverage})")
            return quantity

        except Exception as e:
            logger.error(f"Error calculating position quantity: {e}")
            return 0.0

    def calculate_breakeven_price(
        self,
        entry_price: float,
        margin: float,
        leverage: float = 1.0
    ) -> Optional[float]:
        """
        Calculate the breakeven price for a position.

        Args:
            entry_price: The entry price
            margin: The margin amount in USDT
            leverage: The leverage multiplier (default 1.0)

        Returns:
            Breakeven price or None if calculation fails
        """
        try:
            breakeven_price = self.fee_calculator.calculate_breakeven_price(entry_price)
            logger.debug(f"Breakeven price calculated: {breakeven_price} (entry: {entry_price})")
            return float(breakeven_price)

        except Exception as e:
            logger.error(f"Error calculating breakeven price: {e}")
            return None

    def calculate_comprehensive_fees(
        self,
        margin: float,
        leverage: float = 1.0,
        entry_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive fee information for a trade.

        Args:
            margin: The margin amount in USDT
            leverage: The leverage multiplier (default 1.0)
            entry_price: The entry price (optional)

        Returns:
            Dictionary containing fee calculations
        """
        try:
            fee_analysis = self.fee_calculator.calculate_comprehensive_fees(
                margin=margin,
                leverage=leverage,
                entry_price=entry_price
            )

            logger.debug(f"Comprehensive fees calculated: {fee_analysis}")
            return fee_analysis

        except Exception as e:
            logger.error(f"Error calculating comprehensive fees: {e}")
            return {
                'error': f"Error calculating fees: {str(e)}",
                'margin': margin,
                'leverage': leverage,
                'total_fees': 0.0,
                'breakeven_price': None
            }

    def validate_trade_parameters(
        self,
        trade_amount: float,
        min_amount: float = 10.0,
        max_amount: float = 1000.0
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate trade parameters.

        Args:
            trade_amount: The trade amount to validate
            min_amount: Minimum acceptable amount
            max_amount: Maximum acceptable amount

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            from src.bot.utils.validation_utils import ValidationUtils
            return ValidationUtils.validate_trade_amount(trade_amount, min_amount, max_amount)

        except Exception as e:
            logger.error(f"Error validating trade parameters: {e}")
            return False, f"Error in validation: {str(e)}"

    def round_quantity_to_precision(
        self,
        quantity: float,
        precision: int
    ) -> float:
        """
        Round quantity to the specified precision.

        Args:
            quantity: The quantity to round
            precision: The precision to round to

        Returns:
            Rounded quantity
        """
        try:
            if precision < 0:
                logger.warning(f"Invalid precision {precision}, using 0")
                precision = 0

            rounded_quantity = round(quantity, precision)
            logger.debug(f"Quantity rounded: {quantity} -> {rounded_quantity} (precision: {precision})")
            return rounded_quantity

        except Exception as e:
            logger.error(f"Error rounding quantity: {e}")
            return quantity
