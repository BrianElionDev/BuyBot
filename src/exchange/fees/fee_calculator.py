"""
Binance Futures Fee Calculator

This module provides precise fee calculations for Binance Futures trading,
including leverage considerations and breakeven price calculations. Critical for accurate financial calculations
when handling client funds.

Uses FixedFeeCalculator for simplified fee management with fixed caps.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Union
import logging

logger = logging.getLogger(__name__)


class FixedFeeCalculator:
    """
    Simplified fee calculator with fixed fee caps to reduce calculation errors.

    This calculator uses fixed percentage fees instead of complex formulas,
    making it more predictable and easier to manage as advised by supervisors.
    """

    # Fixed fee caps as recommended by supervisor
    FIXED_FEE_RATE_02 = Decimal('0.0002')  # 0.02% fixed fee cap
    FIXED_FEE_RATE_05 = Decimal('0.0005')  # 0.05% fixed fee cap

    def __init__(self, fee_rate: Optional[Union[float, Decimal]] = None):
        """
        Initialize the fixed fee calculator.

        Args:
            fee_rate: Fixed fee rate to use (0.02% or 0.05%). If None, uses 0.02%
        """
        if fee_rate is None:
            self.fee_rate = self.FIXED_FEE_RATE_02  # Default to 0.02%
        else:
            self.fee_rate = Decimal(str(fee_rate))

        logger.info(f"FixedFeeCalculator initialized with fee rate: {self.fee_rate} ({self.fee_rate * 100}%)")

    def calculate_trading_fee(
        self,
        margin: Union[float, Decimal],
        leverage: Union[float, Decimal] = 1.0
    ) -> Decimal:
        """
        Calculate trading fee using fixed fee rate.

        Formula: Trading Fee = Margin × Leverage × Fixed Fee Rate

        Args:
            margin: Margin amount in USDT
            leverage: Leverage multiplier (default 1.0)

        Returns:
            Trading fee amount in USDT
        """
        try:
            # Convert inputs to Decimal for precise calculations
            margin = Decimal(str(margin))
            leverage = Decimal(str(leverage))

            # Validate inputs
            if margin <= 0:
                raise ValueError("Margin must be positive")
            if leverage <= 0:
                raise ValueError("Leverage must be positive")

            # Calculate notional value
            notional_value = margin * leverage

            # Calculate trading fee using fixed rate
            trading_fee = notional_value * self.fee_rate

            # Round to 8 decimal places (Binance precision)
            trading_fee = trading_fee.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

            logger.info(f"Fixed fee calculated: {trading_fee} USDT "
                        f"(margin: {margin}, leverage: {leverage}, "
                        f"fixed_rate: {self.fee_rate})")

            return trading_fee

        except Exception as e:
            logger.error(f"Error calculating fixed trading fee: {e}")
            raise

    def calculate_total_fees(
        self,
        margin: Union[float, Decimal],
        leverage: Union[float, Decimal] = 1.0
    ) -> Decimal:
        """
        Calculate total fees for entry and exit trades using fixed rate.

        Args:
            margin: Margin amount in USDT
            leverage: Leverage multiplier (default 1.0)

        Returns:
            Total fees for entry + exit trades
        """
        single_trade_fee = self.calculate_trading_fee(margin=margin, leverage=leverage)
        total_fees = single_trade_fee * 2  # Entry + Exit
        return total_fees.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

    def calculate_breakeven_price(
        self,
        entry_price: Union[float, Decimal]
    ) -> Decimal:
        """
        Calculate breakeven price using fixed fee rate.

        Formula: Breakeven Price = Entry Price × (1 + 2 × Fixed Fee Rate)

        Args:
            entry_price: Price at which position was opened

        Returns:
            Breakeven price that covers entry and exit fees
        """
        try:
            entry_price = Decimal(str(entry_price))

            if entry_price <= 0:
                raise ValueError("Entry price must be positive")

            # Calculate breakeven multiplier using fixed fee rate
            # 2 × fee_rate accounts for entry and exit fees
            breakeven_multiplier = Decimal('1') + (Decimal('2') * self.fee_rate)

            # Calculate breakeven price
            breakeven_price = entry_price * breakeven_multiplier

            # Round to appropriate precision
            breakeven_price = breakeven_price.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

            logger.info(f"Fixed fee breakeven price calculated: {breakeven_price} "
                        f"(entry: {entry_price}, fixed_rate: {self.fee_rate}, "
                        f"multiplier: {breakeven_multiplier})")

            return breakeven_price

        except Exception as e:
            logger.error(f"Error calculating fixed fee breakeven price: {e}")
            raise

    def calculate_comprehensive_fees(
        self,
        margin: Union[float, Decimal],
        leverage: Union[float, Decimal] = 1.0,
        entry_price: Optional[Union[float, Decimal]] = None
    ) -> Dict[str, Union[Decimal, str, bool]]:
        """
        Calculate comprehensive fee information using fixed fee rate.

        Args:
            margin: Margin amount in USDT
            leverage: Leverage multiplier (default 1.0)
            entry_price: Entry price of the position (optional)

        Returns:
            Dictionary containing all fee calculations and breakeven information
        """
        try:
            # Calculate all fee components
            single_trade_fee = self.calculate_trading_fee(margin=margin, leverage=leverage)
            total_fees = self.calculate_total_fees(margin=margin, leverage=leverage)

            # Calculate breakeven price if entry price provided
            breakeven_price = None
            if entry_price is not None:
                breakeven_price = self.calculate_breakeven_price(entry_price=entry_price)

            # Calculate notional value
            margin_decimal = Decimal(str(margin))
            leverage_decimal = Decimal(str(leverage))
            notional_value = margin_decimal * leverage_decimal

            result = {
                'margin': margin_decimal,
                'leverage': leverage_decimal,
                'notional_value': notional_value,
                'effective_fee_rate': self.fee_rate,
                'fee_type': 'fixed',
                'bnb_discount_applied': False,  # Fixed fees don't use BNB discount
                'single_trade_fee': single_trade_fee,
                'total_fees': total_fees,
                'fee_percentage_of_margin': (total_fees / margin_decimal) * 100
            }

            if entry_price is not None:
                result['entry_price'] = Decimal(str(entry_price))
                result['breakeven_price'] = breakeven_price
                result['breakeven_multiplier'] = Decimal('1') + (Decimal('2') * self.fee_rate)

            return result

        except Exception as e:
            logger.error(f"Error calculating comprehensive fixed fees: {e}")
            raise
