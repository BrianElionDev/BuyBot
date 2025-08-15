"""
Test suite for Binance Futures Fee Calculator

This test suite validates the fee calculator implementation with precise
mathematical calculations and real-world examples to ensure accuracy
when handling client funds.
"""

import unittest
from decimal import Decimal
from src.exchange.fee_calculator import (
    BinanceFuturesFeeCalculator,
    calculate_fees_and_breakeven,
    validate_fee_calculation
)


class TestBinanceFuturesFeeCalculator(unittest.TestCase):
    """Test cases for Binance Futures Fee Calculator"""

    def setUp(self):
        """Set up test fixtures"""
        self.calculator = BinanceFuturesFeeCalculator()
        self.calculator_with_bnb = BinanceFuturesFeeCalculator(use_bnb_for_fees=True)

    def test_standard_fee_rates(self):
        """Test that standard fee rates are correctly set"""
        self.assertEqual(self.calculator.MAKER_FEE_RATE, Decimal('0.0002'))
        self.assertEqual(self.calculator.TAKER_FEE_RATE, Decimal('0.0005'))
        self.assertEqual(self.calculator.BNB_DISCOUNT_RATE, Decimal('0.9'))

    def test_basic_trading_fee_calculation(self):
        """Test basic trading fee calculation with the provided example"""
        # Example from requirements:
        # Margin: $1,000, Leverage: 10x, Fee rate (Taker): 0.05% = 0.0005
        # Fee = $1,000 × 10 × 0.0005 = $5 per trade execution

        margin = Decimal('1000')
        leverage = Decimal('10')
        fee_rate = Decimal('0.0005')  # 0.05%

        fee = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            fee_rate=fee_rate,
            is_maker=False
        )

        expected_fee = Decimal('5.0')
        self.assertEqual(fee, expected_fee)

    def test_taker_fee_calculation(self):
        """Test taker fee calculation using standard rates"""
        margin = Decimal('1000')
        leverage = Decimal('10')

        fee = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=False  # Taker order
        )

        # Expected: 1000 * 10 * 0.0005 = 5.0
        expected_fee = Decimal('5.0')
        self.assertEqual(fee, expected_fee)

    def test_maker_fee_calculation(self):
        """Test maker fee calculation using standard rates"""
        margin = Decimal('1000')
        leverage = Decimal('10')

        fee = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=True  # Maker order
        )

        # Expected: 1000 * 10 * 0.0002 = 2.0
        expected_fee = Decimal('2.0')
        self.assertEqual(fee, expected_fee)

    def test_bnb_discount_calculation(self):
        """Test BNB discount application"""
        margin = Decimal('1000')
        leverage = Decimal('10')

        # Without BNB discount
        fee_without_bnb = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=False,
            use_bnb=False
        )

        # With BNB discount
        fee_with_bnb = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=False,
            use_bnb=True
        )

        # BNB discount should be 10% (multiply by 0.9)
        expected_discounted_fee = fee_without_bnb * Decimal('0.9')
        self.assertEqual(fee_with_bnb, expected_discounted_fee)

    def test_total_fees_calculation(self):
        """Test total fees for entry and exit trades"""
        margin = Decimal('1000')
        leverage = Decimal('10')

        total_fees = self.calculator.calculate_total_fees(
            margin=margin,
            leverage=leverage,
            is_maker=False
        )

        # Single trade fee: 1000 * 10 * 0.0005 = 5.0
        # Total fees (entry + exit): 5.0 * 2 = 10.0
        expected_total_fees = Decimal('10.0')
        self.assertEqual(total_fees, expected_total_fees)

    def test_breakeven_price_calculation(self):
        """Test breakeven price calculation with the provided example"""
        # Example from requirements:
        # Entry price = 177.38, Taker fee = 0.04% (0.0004)
        # Breakeven price: 177.38 × (1+2×0.0004) = 177.38 × 1.0008 = 177.52

        entry_price = Decimal('177.38')
        fee_rate = Decimal('0.0004')  # 0.04%

        breakeven_price = self.calculator.calculate_breakeven_price(
            entry_price=entry_price,
            fee_rate=fee_rate,
            is_maker=False
        )

        expected_breakeven = Decimal('177.52')
        # Allow for small rounding differences
        self.assertAlmostEqual(breakeven_price, expected_breakeven, places=2)

    def test_breakeven_price_with_standard_rates(self):
        """Test breakeven price with standard maker/taker rates"""
        entry_price = Decimal('100.00')

        # Taker breakeven
        taker_breakeven = self.calculator.calculate_breakeven_price(
            entry_price=entry_price,
            is_maker=False
        )

        # Maker breakeven
        maker_breakeven = self.calculator.calculate_breakeven_price(
            entry_price=entry_price,
            is_maker=True
        )

        # Taker: 100 * (1 + 2 * 0.0005) = 100 * 1.001 = 100.1
        expected_taker_breakeven = Decimal('100.1')
        self.assertEqual(taker_breakeven, expected_taker_breakeven)

        # Maker: 100 * (1 + 2 * 0.0002) = 100 * 1.0004 = 100.04
        expected_maker_breakeven = Decimal('100.04')
        self.assertEqual(maker_breakeven, expected_maker_breakeven)

    def test_breakeven_price_with_bnb_discount(self):
        """Test breakeven price calculation with BNB discount"""
        entry_price = Decimal('100.00')

        # Without BNB discount
        breakeven_without_bnb = self.calculator.calculate_breakeven_price(
            entry_price=entry_price,
            is_maker=False,
            use_bnb=False
        )

        # With BNB discount
        breakeven_with_bnb = self.calculator.calculate_breakeven_price(
            entry_price=entry_price,
            is_maker=False,
            use_bnb=True
        )

        # BNB discount should result in lower breakeven price
        self.assertLess(breakeven_with_bnb, breakeven_without_bnb)

    def test_weighted_breakeven_price(self):
        """Test weighted breakeven price for multiple entries"""
        entries = [
            {'price': Decimal('100.00'), 'quantity': Decimal('1.0')},
            {'price': Decimal('110.00'), 'quantity': Decimal('1.0')}
        ]

        breakeven_price = self.calculator.calculate_weighted_breakeven_price(
            entries=entries,
            is_maker=False
        )

        # Weighted average entry: (100*1 + 110*1) / 2 = 105
        # Breakeven: 105 * (1 + 2 * 0.0005) = 105 * 1.001 = 105.105
        expected_breakeven = Decimal('105.105')
        self.assertEqual(breakeven_price, expected_breakeven)

    def test_comprehensive_fees_calculation(self):
        """Test comprehensive fee calculation with all components"""
        margin = Decimal('1000')
        leverage = Decimal('10')
        entry_price = Decimal('100.00')

        result = self.calculator.calculate_comprehensive_fees(
            margin=margin,
            leverage=leverage,
            entry_price=entry_price,
            is_maker=False
        )

        # Verify all expected keys are present
        expected_keys = {
            'margin', 'leverage', 'notional_value', 'entry_price',
            'effective_fee_rate', 'fee_type', 'bnb_discount_applied',
            'single_trade_fee', 'total_fees', 'breakeven_price',
            'breakeven_multiplier', 'fee_percentage_of_margin'
        }
        self.assertEqual(set(result.keys()), expected_keys)

        # Verify specific values
        self.assertEqual(result['margin'], margin)
        self.assertEqual(result['leverage'], leverage)
        self.assertEqual(result['notional_value'], Decimal('10000'))
        self.assertEqual(result['entry_price'], entry_price)
        self.assertEqual(result['fee_type'], 'taker')
        self.assertFalse(result['bnb_discount_applied'])
        self.assertEqual(result['single_trade_fee'], Decimal('5.0'))
        self.assertEqual(result['total_fees'], Decimal('10.0'))
        self.assertEqual(result['breakeven_price'], Decimal('100.1'))

    def test_convenience_function(self):
        """Test the convenience function"""
        result = calculate_fees_and_breakeven(
            entry_price=100.00,
            margin=1000.0,
            leverage=10.0,
            is_maker=False,
            use_bnb=False
        )

        # Should return the same result as comprehensive_fees
        self.assertIn('total_fees', result)
        self.assertIn('breakeven_price', result)
        self.assertEqual(result['total_fees'], Decimal('10.0'))
        self.assertEqual(result['breakeven_price'], Decimal('100.1'))

    def test_validation_function(self):
        """Test fee validation function"""
        # Valid calculation
        is_valid = validate_fee_calculation(
            margin=1000,
            leverage=10,
            expected_fee=5.0,
            tolerance=0.01
        )
        self.assertTrue(is_valid)

        # Invalid calculation
        is_valid = validate_fee_calculation(
            margin=1000,
            leverage=10,
            expected_fee=10.0,  # Wrong expected fee
            tolerance=0.01
        )
        self.assertFalse(is_valid)

    def test_input_validation(self):
        """Test input validation for edge cases"""
        # Test negative margin
        with self.assertRaises(ValueError):
            self.calculator.calculate_trading_fee(
                margin=-1000,
                leverage=10
            )

        # Test negative leverage
        with self.assertRaises(ValueError):
            self.calculator.calculate_trading_fee(
                margin=1000,
                leverage=-10
            )

        # Test negative entry price
        with self.assertRaises(ValueError):
            self.calculator.calculate_breakeven_price(
                entry_price=-100.00
            )

        # Test empty entries list
        with self.assertRaises(ValueError):
            self.calculator.calculate_weighted_breakeven_price(
                entries=[]
            )

    def test_precision_handling(self):
        """Test that calculations maintain appropriate precision"""
        margin = Decimal('1000.12345678')
        leverage = Decimal('10.5')

        fee = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=False
        )

        # Should be rounded to 8 decimal places
        self.assertEqual(fee.as_tuple().exponent, -8)

    def test_large_numbers(self):
        """Test calculations with large numbers"""
        margin = Decimal('1000000')  # 1M USDT
        leverage = Decimal('100')     # 100x leverage

        fee = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=False
        )

        # Expected: 1,000,000 * 100 * 0.0005 = 50,000
        expected_fee = Decimal('50000.0')
        self.assertEqual(fee, expected_fee)

    def test_small_numbers(self):
        """Test calculations with small numbers"""
        margin = Decimal('10')      # 10 USDT
        leverage = Decimal('1')     # 1x leverage

        fee = self.calculator.calculate_trading_fee(
            margin=margin,
            leverage=leverage,
            is_maker=False
        )

        # Expected: 10 * 1 * 0.0005 = 0.005
        expected_fee = Decimal('0.005')
        self.assertEqual(fee, expected_fee)


if __name__ == '__main__':
    unittest.main()
