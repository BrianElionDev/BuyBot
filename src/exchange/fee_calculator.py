"""
Binance Futures Fee Calculator

This module provides precise fee calculations for Binance Futures trading,
including leverage considerations, maker/taker fees, BNB discounts, and
breakeven price calculations. Critical for accurate financial calculations
when handling client funds.

Now includes a FixedFeeCalculator for simplified fee management with fixed caps.
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

            logger.debug(f"Fixed fee calculated: {trading_fee} USDT "
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

            logger.debug(f"Fixed fee breakeven price calculated: {breakeven_price} "
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

    def get_fee_info(self) -> Dict[str, Union[Decimal, str]]:
        """
        Get information about the current fixed fee configuration.

        Returns:
            Dictionary with fee configuration details
        """
        return {
            'fee_rate': self.fee_rate,
            'fee_percentage': self.fee_rate * 100,
            'fee_type': 'fixed',
            'description': f"Fixed fee rate of {self.fee_rate * 100}%"
        }


class BinanceFuturesFeeCalculator:
    """
    Comprehensive fee calculator for Binance Futures trading.

    Handles:
    - Leverage-based fee calculations
    - Maker vs Taker fees
    - BNB fee discounts
    - Breakeven price calculations
    - Multiple entry scenarios
    """

    # Standard Binance Futures fee rates
    MAKER_FEE_RATE = Decimal('0.0002')  # 0.02%
    TAKER_FEE_RATE = Decimal('0.0005')  # 0.05%

    # BNB discount rate (10% discount)
    BNB_DISCOUNT_RATE = Decimal('0.9')

    def __init__(self, use_bnb_for_fees: bool = False):
        """
        Initialize the fee calculator.

        Args:
            use_bnb_for_fees: Whether to apply BNB discount for fee payments
        """
        self.use_bnb_for_fees = use_bnb_for_fees

    def calculate_trading_fee(
        self,
        margin: Union[float, Decimal],
        leverage: Union[float, Decimal],
        fee_rate: Optional[Union[float, Decimal]] = None,
        is_maker: bool = False,
        use_bnb: Optional[bool] = None
    ) -> Decimal:
        """
        Calculate trading fee for a single trade execution.

        Formula: Trading Fee = Margin × Leverage × Fee Rate

        Args:
            margin: Margin amount in USDT
            leverage: Leverage multiplier
            fee_rate: Custom fee rate (if None, uses standard maker/taker rates)
            is_maker: Whether this is a maker order (limit order that adds liquidity)
            use_bnb: Whether to apply BNB discount (overrides instance setting)

        Returns:
            Trading fee amount in USDT

        Raises:
            ValueError: If invalid parameters are provided
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

            # Determine fee rate
            if fee_rate is not None:
                fee_rate = Decimal(str(fee_rate))
            else:
                fee_rate = self.MAKER_FEE_RATE if is_maker else self.TAKER_FEE_RATE

            # Apply BNB discount if specified
            bnb_discount = use_bnb if use_bnb is not None else self.use_bnb_for_fees
            if bnb_discount:
                fee_rate *= self.BNB_DISCOUNT_RATE

            # Calculate notional value
            notional_value = margin * leverage

            # Calculate trading fee
            trading_fee = notional_value * fee_rate

            # Round to 8 decimal places (Binance precision)
            trading_fee = trading_fee.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

            logger.debug(f"Trading fee calculated: {trading_fee} USDT "
                        f"(margin: {margin}, leverage: {leverage}, "
                        f"fee_rate: {fee_rate}, is_maker: {is_maker})")

            return trading_fee

        except Exception as e:
            logger.error(f"Error calculating trading fee: {e}")
            raise

    def calculate_total_fees(
        self,
        margin: Union[float, Decimal],
        leverage: Union[float, Decimal],
        fee_rate: Optional[Union[float, Decimal]] = None,
        is_maker: bool = False,
        use_bnb: Optional[bool] = None
    ) -> Decimal:
        """
        Calculate total fees for entry and exit trades.

        Args:
            margin: Margin amount in USDT
            leverage: Leverage multiplier
            fee_rate: Custom fee rate (if None, uses standard maker/taker rates)
            is_maker: Whether this is a maker order
            use_bnb: Whether to apply BNB discount

        Returns:
            Total fees for entry + exit trades
        """
        single_trade_fee = self.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            fee_rate=fee_rate,
            is_maker=is_maker,
            use_bnb=use_bnb
        )

        total_fees = single_trade_fee * 2  # Entry + Exit
        return total_fees.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

    def calculate_breakeven_price(
        self,
        entry_price: Union[float, Decimal],
        fee_rate: Optional[Union[float, Decimal]] = None,
        is_maker: bool = False,
        use_bnb: Optional[bool] = None
    ) -> Decimal:
        """
        Calculate breakeven price after accounting for trading fees.

        Formula: Breakeven Price = Entry Price × (1 + 2 × Trading Fee %)

        Args:
            entry_price: Price at which position was opened
            fee_rate: Custom fee rate (if None, uses standard maker/taker rates)
            is_maker: Whether this is a maker order
            use_bnb: Whether to apply BNB discount

        Returns:
            Breakeven price that covers entry and exit fees
        """
        try:
            entry_price = Decimal(str(entry_price))

            if entry_price <= 0:
                raise ValueError("Entry price must be positive")

            # Determine fee rate
            if fee_rate is not None:
                fee_rate = Decimal(str(fee_rate))
            else:
                fee_rate = self.MAKER_FEE_RATE if is_maker else self.TAKER_FEE_RATE

            # Apply BNB discount if specified
            bnb_discount = use_bnb if use_bnb is not None else self.use_bnb_for_fees
            if bnb_discount:
                fee_rate *= self.BNB_DISCOUNT_RATE

            # Calculate breakeven multiplier
            # 2 × fee_rate accounts for entry and exit fees
            breakeven_multiplier = Decimal('1') + (Decimal('2') * fee_rate)

            # Calculate breakeven price
            breakeven_price = entry_price * breakeven_multiplier

            # Round to appropriate precision (typically 8 decimal places for crypto)
            breakeven_price = breakeven_price.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

            logger.debug(f"Breakeven price calculated: {breakeven_price} "
                        f"(entry: {entry_price}, fee_rate: {fee_rate}, "
                        f"multiplier: {breakeven_multiplier})")

            return breakeven_price

        except Exception as e:
            logger.error(f"Error calculating breakeven price: {e}")
            raise

    def calculate_weighted_breakeven_price(
        self,
        entries: list[Dict[str, Union[float, Decimal]]],
        fee_rate: Optional[Union[float, Decimal]] = None,
        is_maker: bool = False,
        use_bnb: Optional[bool] = None
    ) -> Decimal:
        """
        Calculate breakeven price for multiple entries at different prices.

        Args:
            entries: List of dicts with 'price' and 'quantity' keys
            fee_rate: Custom fee rate (if None, uses standard maker/taker rates)
            is_maker: Whether these are maker orders
            use_bnb: Whether to apply BNB discount

        Returns:
            Weighted average breakeven price
        """
        try:
            if not entries:
                raise ValueError("Entries list cannot be empty")

            total_quantity = Decimal('0')
            weighted_price_sum = Decimal('0')

            for entry in entries:
                price = Decimal(str(entry['price']))
                quantity = Decimal(str(entry['quantity']))

                if price <= 0 or quantity <= 0:
                    raise ValueError("Price and quantity must be positive")

                total_quantity += quantity
                weighted_price_sum += price * quantity

            # Calculate weighted average entry price
            weighted_entry_price = weighted_price_sum / total_quantity

            # Calculate breakeven price using weighted average
            breakeven_price = self.calculate_breakeven_price(
                entry_price=weighted_entry_price,
                fee_rate=fee_rate,
                is_maker=is_maker,
                use_bnb=use_bnb
            )

            logger.debug(f"Weighted breakeven price calculated: {breakeven_price} "
                        f"(weighted entry: {weighted_entry_price}, "
                        f"total quantity: {total_quantity})")

            return breakeven_price

        except Exception as e:
            logger.error(f"Error calculating weighted breakeven price: {e}")
            raise

    def calculate_comprehensive_fees(
        self,
        margin: Union[float, Decimal],
        leverage: Union[float, Decimal],
        entry_price: Union[float, Decimal],
        fee_rate: Optional[Union[float, Decimal]] = None,
        is_maker: bool = False,
        use_bnb: Optional[bool] = None
    ) -> Dict[str, Union[Decimal, str, bool]]:
        """
        Calculate comprehensive fee information for a position.

        Args:
            margin: Margin amount in USDT
            leverage: Leverage multiplier
            entry_price: Entry price of the position
            fee_rate: Custom fee rate (if None, uses standard maker/taker rates)
            is_maker: Whether this is a maker order
            use_bnb: Whether to apply BNB discount

        Returns:
            Dictionary containing all fee calculations and breakeven information
        """
        try:
            # Calculate all fee components
            single_trade_fee = self.calculate_trading_fee(
                margin=margin,
                leverage=leverage,
                fee_rate=fee_rate,
                is_maker=is_maker,
                use_bnb=use_bnb
            )

            total_fees = self.calculate_total_fees(
                margin=margin,
                leverage=leverage,
                fee_rate=fee_rate,
                is_maker=is_maker,
                use_bnb=use_bnb
            )

            breakeven_price = self.calculate_breakeven_price(
                entry_price=entry_price,
                fee_rate=fee_rate,
                is_maker=is_maker,
                use_bnb=use_bnb
            )

            # Determine effective fee rate used
            if fee_rate is not None:
                effective_fee_rate = Decimal(str(fee_rate))
            else:
                effective_fee_rate = self.MAKER_FEE_RATE if is_maker else self.TAKER_FEE_RATE

            if use_bnb if use_bnb is not None else self.use_bnb_for_fees:
                effective_fee_rate *= self.BNB_DISCOUNT_RATE

            # Calculate notional value
            margin_decimal = Decimal(str(margin))
            leverage_decimal = Decimal(str(leverage))
            notional_value = margin_decimal * leverage_decimal

            return {
                'margin': margin_decimal,
                'leverage': leverage_decimal,
                'notional_value': notional_value,
                'entry_price': Decimal(str(entry_price)),
                'effective_fee_rate': effective_fee_rate,
                'fee_type': 'maker' if is_maker else 'taker',
                'bnb_discount_applied': use_bnb if use_bnb is not None else self.use_bnb_for_fees,
                'single_trade_fee': single_trade_fee,
                'total_fees': total_fees,
                'breakeven_price': breakeven_price,
                'breakeven_multiplier': Decimal('1') + (Decimal('2') * effective_fee_rate),
                'fee_percentage_of_margin': (total_fees / margin_decimal) * 100
            }

        except Exception as e:
            logger.error(f"Error calculating comprehensive fees: {e}")
            raise


# Convenience functions for common calculations
def calculate_fees_and_breakeven(
    entry_price: Union[float, Decimal],
    margin: Union[float, Decimal],
    leverage: Union[float, Decimal],
    fee_rate: Optional[Union[float, Decimal]] = None,
    is_maker: bool = False,
    use_bnb: bool = False
) -> Dict[str, Union[Decimal, str, bool]]:
    """
    Convenience function to calculate fees and breakeven price.

    Args:
        entry_price: Entry price of the position
        margin: Margin amount in USDT
        leverage: Leverage multiplier
        fee_rate: Custom fee rate (if None, uses standard maker/taker rates)
        is_maker: Whether this is a maker order
        use_bnb: Whether to apply BNB discount

    Returns:
        Dictionary with fee calculations and breakeven information
    """
    calculator = BinanceFuturesFeeCalculator(use_bnb_for_fees=use_bnb)
    return calculator.calculate_comprehensive_fees(
        margin=margin,
        leverage=leverage,
        entry_price=entry_price,
        fee_rate=fee_rate,
        is_maker=is_maker,
        use_bnb=use_bnb
    )


def validate_fee_calculation(
    margin: Union[float, Decimal],
    leverage: Union[float, Decimal],
    expected_fee: Union[float, Decimal],
    tolerance: Union[float, Decimal] = Decimal('0.01')
) -> bool:
    """
    Validate that a fee calculation is within expected tolerance.

    Args:
        margin: Margin amount in USDT
        leverage: Leverage multiplier
        expected_fee: Expected fee amount
        tolerance: Acceptable tolerance for validation

    Returns:
        True if fee is within tolerance, False otherwise
    """
    try:
        calculator = BinanceFuturesFeeCalculator()
        calculated_fee = calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage
        )

        expected_fee = Decimal(str(expected_fee))
        tolerance = Decimal(str(tolerance))

        difference = abs(calculated_fee - expected_fee)
        is_valid = difference <= tolerance

        if not is_valid:
            logger.warning(f"Fee validation failed: calculated={calculated_fee}, "
                          f"expected={expected_fee}, difference={difference}")

        return is_valid

    except Exception as e:
        logger.error(f"Error validating fee calculation: {e}")
        return False
