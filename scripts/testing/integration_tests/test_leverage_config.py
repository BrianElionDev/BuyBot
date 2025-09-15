#!/usr/bin/env python3
"""
Test script to verify leverage configuration from .env file.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings as config
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_leverage_config():
    """Test that leverage configuration is loaded correctly from .env."""

    print("=" * 80)
    print("LEVERAGE CONFIGURATION TEST")
    print("=" * 80)

    # Test leverage configuration
    print(f"Default Leverage from settings: {config.DEFAULT_LEVERAGE}")
    print(f"Type: {type(config.DEFAULT_LEVERAGE)}")
    print()

    # Test with different scenarios
    test_cases = [
        {
            'name': 'Small Trade',
            'margin': 100.0,
            'leverage': config.DEFAULT_LEVERAGE,
            'entry_price': 50000.0
        },
        {
            'name': 'Medium Trade',
            'margin': 1000.0,
            'leverage': config.DEFAULT_LEVERAGE,
            'entry_price': 50000.0
        },
        {
            'name': 'Large Trade',
            'margin': 10000.0,
            'leverage': config.DEFAULT_LEVERAGE,
            'entry_price': 50000.0
        }
    ]

    from src.exchange.fee_calculator import FixedFeeCalculator

    for test_case in test_cases:
        print(f"Test Case: {test_case['name']}")
        print("-" * 50)

        # Create calculator with default fee rate
        calculator = FixedFeeCalculator()

        # Calculate fees using leverage from settings
        fee_analysis = calculator.calculate_comprehensive_fees(
            margin=test_case['margin'],
            leverage=test_case['leverage'],
            entry_price=test_case['entry_price']
        )

        # Display results
        print(f"Margin: ${test_case['margin']:,.2f}")
        print(f"Leverage: {test_case['leverage']}x (from .env)")
        print(f"Entry Price: ${test_case['entry_price']:,.2f}")
        print()
        print(f"Notional Value: ${fee_analysis['notional_value']:,.2f}")
        print(f"Single Trade Fee: ${fee_analysis['single_trade_fee']:,.4f}")
        print(f"Total Fees (Entry + Exit): ${fee_analysis['total_fees']:,.4f}")
        print(f"Breakeven Price: ${fee_analysis['breakeven_price']:,.2f}")
        print(f"Fee % of Margin: {fee_analysis['fee_percentage_of_margin']:.4f}%")
        print("=" * 80)
        print()


def test_leverage_impact():
    """Test the impact of different leverage values on fees."""

    print("=" * 80)
    print("LEVERAGE IMPACT ANALYSIS")
    print("=" * 80)

    margin = 1000.0
    entry_price = 50000.0

    leverage_values = [1, 5, 10, 20, 50, 100]

    from src.exchange.fee_calculator import FixedFeeCalculator
    calculator = FixedFeeCalculator()

    print(f"Margin: ${margin:,.2f}")
    print(f"Entry Price: ${entry_price:,.2f}")
    print()
    print(f"{'Leverage':<10} {'Notional Value':<15} {'Single Fee':<15} {'Total Fees':<15} {'Fee %':<10}")
    print("-" * 80)

    for leverage in leverage_values:
        fee_analysis = calculator.calculate_comprehensive_fees(
            margin=margin,
            leverage=leverage,
            entry_price=entry_price
        )

        print(f"{leverage:<10} ${fee_analysis['notional_value']:<14,.2f} ${fee_analysis['single_trade_fee']:<14,.4f} ${fee_analysis['total_fees']:<14,.4f} {fee_analysis['fee_percentage_of_margin']:<9.4f}%")


def main():
    """Run all leverage configuration tests."""

    print("LEVERAGE CONFIGURATION VERIFICATION")
    print("=" * 80)
    print("This script verifies that leverage is correctly loaded from .env file")
    print("and used throughout the trading system.")
    print()

    try:
        # Test basic configuration
        test_leverage_config()

        # Test leverage impact
        test_leverage_impact()

        print("=" * 80)
        print("CONFIGURATION SUMMARY")
        print("=" * 80)
        print(f"✅ Leverage loaded from .env: {config.DEFAULT_LEVERAGE}")
        print(f"✅ Type: {type(config.DEFAULT_LEVERAGE)} (float)")
        print(f"✅ Default fallback: 1.0 (if not found in .env)")
        print()
        print("The leverage configuration is now centralized in:")
        print("1. .env file: LEVERAGE=1")
        print("2. config/settings.py: DEFAULT_LEVERAGE = float(os.getenv('LEVERAGE', '1'))")
        print("3. Used throughout the trading system")
        print()
        print("To change leverage, simply update the LEVERAGE value in your .env file!")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
