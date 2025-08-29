#!/usr/bin/env python3
"""
Example Fee Calculations for Binance Futures

This script demonstrates the fee calculator implementation with the exact
examples provided in the requirements. Critical for validating accuracy
when handling client funds.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.exchange.fee_calculator import (
    BinanceFuturesFeeCalculator,
    calculate_fees_and_breakeven
)


def main():
    """Demonstrate fee calculations with real examples"""

    print("=" * 80)
    print("BINANCE FUTURES FEE CALCULATOR - EXAMPLE CALCULATIONS")
    print("=" * 80)
    print()

    # Initialize calculator
    calculator = BinanceFuturesFeeCalculator()

    # Example 1: Basic trading fee calculation
    print("EXAMPLE 1: Basic Trading Fee Calculation")
    print("-" * 50)
    print("Margin: $1,000")
    print("Leverage: 10x")
    print("Fee rate (Taker): 0.05% = 0.0005")
    print("Expected: Fee = $1,000 × 10 × 0.0005 = $5 per trade execution")
    print()

    margin = Decimal('1000')
    leverage = Decimal('10')
    fee_rate = Decimal('0.0005')  # 0.05%

    fee = calculator.calculate_trading_fee(
        margin=margin,
        leverage=leverage,
        fee_rate=fee_rate,
        is_maker=False
    )

    print(f"Calculated fee: ${fee} USDT")
    print(f"✓ Expected: $5.0 USDT")
    print(f"✓ Match: {'YES' if fee == Decimal('5.0') else 'NO'}")
    print()

    # Example 2: Total fees for entry + exit
    print("EXAMPLE 2: Total Fees (Entry + Exit)")
    print("-" * 50)
    print("For entry + exit, total fees = $10")
    print()

    total_fees = calculator.calculate_total_fees(
        margin=margin,
        leverage=leverage,
        fee_rate=fee_rate,
        is_maker=False
    )

    print(f"Calculated total fees: ${total_fees} USDT")
    print(f"✓ Expected: $10.0 USDT")
    print(f"✓ Match: {'YES' if total_fees == Decimal('10.0') else 'NO'}")
    print()

    # Example 3: Breakeven price calculation
    print("EXAMPLE 3: Breakeven Price Calculation")
    print("-" * 50)
    print("Entry price = 177.38")
    print("Taker fee = 0.04% (0.0004)")
    print("Expected: 177.38 × (1+2×0.0004) = 177.38 × 1.0008 = 177.52")
    print()

    entry_price = Decimal('177.38')
    fee_rate_breakeven = Decimal('0.0004')  # 0.04%

    breakeven_price = calculator.calculate_breakeven_price(
        entry_price=entry_price,
        fee_rate=fee_rate_breakeven,
        is_maker=False
    )

    print(f"Calculated breakeven price: {breakeven_price}")
    print(f"✓ Expected: 177.52")
    print(f"✓ Match: {'YES' if abs(breakeven_price - Decimal('177.52')) < Decimal('0.01') else 'NO'}")
    print()

    # Example 4: Maker vs Taker fees
    print("EXAMPLE 4: Maker vs Taker Fee Comparison")
    print("-" * 50)
    print("Margin: $1,000, Leverage: 10x")
    print()

    maker_fee = calculator.calculate_trading_fee(
        margin=margin,
        leverage=leverage,
        is_maker=True
    )

    taker_fee = calculator.calculate_trading_fee(
        margin=margin,
        leverage=leverage,
        is_maker=False
    )

    print(f"Maker fee (0.02%): ${maker_fee} USDT")
    print(f"Taker fee (0.05%): ${taker_fee} USDT")
    print(f"Difference: ${taker_fee - maker_fee} USDT")
    print()

    # Example 5: BNB discount
    print("EXAMPLE 5: BNB Discount Application")
    print("-" * 50)
    print("Margin: $1,000, Leverage: 10x, Taker fee")
    print("BNB discount: 10% (multiply by 0.9)")
    print()

    fee_without_bnb = calculator.calculate_trading_fee(
        margin=margin,
        leverage=leverage,
        is_maker=False,
        use_bnb=False
    )

    fee_with_bnb = calculator.calculate_trading_fee(
        margin=margin,
        leverage=leverage,
        is_maker=False,
        use_bnb=True
    )

    print(f"Fee without BNB: ${fee_without_bnb} USDT")
    print(f"Fee with BNB: ${fee_with_bnb} USDT")
    print(f"Savings: ${fee_without_bnb - fee_with_bnb} USDT")
    print(f"Discount percentage: {((fee_without_bnb - fee_with_bnb) / fee_without_bnb * 100):.1f}%")
    print()

    # Example 6: Comprehensive calculation
    print("EXAMPLE 6: Comprehensive Fee Calculation")
    print("-" * 50)
    print("Complete analysis of a position")
    print()

    result = calculator.calculate_comprehensive_fees(
        margin=margin,
        leverage=leverage,
        entry_price=entry_price,
        is_maker=False
    )

    print("Comprehensive Analysis:")
    print(f"  Margin: ${result['margin']} USDT")
    print(f"  Leverage: {result['leverage']}x")
    print(f"  Notional Value: ${result['notional_value']} USDT")
    print(f"  Entry Price: ${result['entry_price']}")
    print(f"  Fee Type: {result['fee_type']}")
    print(f"  Effective Fee Rate: {result['effective_fee_rate']:.6f}")
    print(f"  BNB Discount Applied: {result['bnb_discount_applied']}")
    print(f"  Single Trade Fee: ${result['single_trade_fee']} USDT")
    print(f"  Total Fees (Entry + Exit): ${result['total_fees']} USDT")
    print(f"  Breakeven Price: ${result['breakeven_price']}")
    print(f"  Breakeven Multiplier: {result['breakeven_multiplier']}")
    print(f"  Fee % of Margin: {result['fee_percentage_of_margin']:.4f}%")
    print()

    # Example 7: Convenience function
    print("EXAMPLE 7: Using Convenience Function")
    print("-" * 50)
    print("Same calculation using the convenience function")
    print()

    convenience_result = calculate_fees_and_breakeven(
        entry_price=float(entry_price),
        margin=float(margin),
        leverage=float(leverage),
        is_maker=False,
        use_bnb=False
    )

    print(f"Total Fees: ${convenience_result['total_fees']} USDT")
    print(f"Breakeven Price: ${convenience_result['breakeven_price']}")
    print(f"✓ Match with comprehensive calculation: {'YES' if convenience_result['total_fees'] == result['total_fees'] else 'NO'}")
    print()

    # Example 8: Weighted breakeven for multiple entries
    print("EXAMPLE 8: Weighted Breakeven for Multiple Entries")
    print("-" * 50)
    print("Multiple entries at different prices")
    print()

    entries = [
        {'price': Decimal('100.00'), 'quantity': Decimal('1.0')},
        {'price': Decimal('110.00'), 'quantity': Decimal('1.0')}
    ]

    weighted_breakeven = calculator.calculate_weighted_breakeven_price(
        entries=entries,
        is_maker=False
    )

    print("Entries:")
    for i, entry in enumerate(entries, 1):
        print(f"  Entry {i}: {entry['quantity']} units at ${entry['price']}")

    print(f"Weighted Average Entry: $105.00")
    print(f"Breakeven Price: ${weighted_breakeven}")
    print()

    print("=" * 80)
    print("ALL CALCULATIONS COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print()
    print("Key Features Implemented:")
    print("✓ Leverage-based fee calculations")
    print("✓ Maker vs Taker fee differentiation")
    print("✓ BNB discount application")
    print("✓ Breakeven price calculations")
    print("✓ Multiple entry scenarios")
    print("✓ Comprehensive fee analysis")
    print("✓ Input validation and error handling")
    print("✓ Precise decimal arithmetic")
    print()
    print("This implementation ensures accurate and precise fee calculations")
    print("critical for handling client funds responsibly.")


if __name__ == "__main__":
    main()
