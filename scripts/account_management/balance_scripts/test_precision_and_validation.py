#!/usr/bin/env python3
"""
Test script to verify precision handling and symbol validation fixes.
This tests both the symbol whitelist validation and quantity/price precision rounding.
"""

import os
import sys
import asyncio
import logging
from config import settings

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.exchange import BinanceExchange

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_precision_and_validation():
    """Test precision handling and symbol validation."""
    try:
        # Load environment variables
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET

        if not api_key or not api_secret:
            logging.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set")
            return False

        # Initialize Binance exchange
        exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=is_testnet
        )

        print("🔍 Testing Symbol Validation and Precision Handling\n")

        # Test symbols - mix of valid and invalid
        test_symbols = [
            ('BTCUSDT', 0.00137909, 65432.123456),  # Should work, high precision
            ('ETHUSDT', 0.05884107, 2560.123456),   # Should work, high precision
            ('ADAUSDT', 12.345678, 0.987654),       # Should work, different precision
            ('DOGEUSDT', 1234.567890, 0.123456),    # Should work, different precision
            ('INVALIDUSDT', 1.0, 100.0),            # Should fail validation
            ('FAKECOINUSDT', 10.0, 50.0),           # Should fail validation
        ]

        print("📋 Test Results:\n")

        for symbol, test_quantity, test_price in test_symbols:
            print(f"Testing {symbol}:")

            # Test symbol validation
            is_valid = exchange.validate_symbol(symbol)
            print(f"   ✅ Symbol validation: {'PASS' if is_valid else 'FAIL'}")

            if is_valid:
                # Test precision handling
                rounded_qty = exchange.round_quantity(symbol, test_quantity)
                rounded_price = exchange.round_price(symbol, test_price)

                qty_precision = exchange.get_quantity_precision(symbol)
                price_precision = exchange.get_price_precision(symbol)

                print(f"   📊 Quantity: {test_quantity:.8f} -> {rounded_qty:.8f} ({qty_precision} decimals)")
                print(f"   💰 Price: {test_price:.8f} -> {rounded_price:.8f} ({price_precision} decimals)")

                # Verify precision is correct
                qty_str = f"{rounded_qty:.10f}".rstrip('0').rstrip('.')
                price_str = f"{rounded_price:.10f}".rstrip('0').rstrip('.')

                actual_qty_decimals = len(qty_str.split('.')[1]) if '.' in qty_str else 0
                actual_price_decimals = len(price_str.split('.')[1]) if '.' in price_str else 0

                qty_ok = actual_qty_decimals <= qty_precision
                price_ok = actual_price_decimals <= price_precision

                print(f"   ✅ Quantity precision check: {'PASS' if qty_ok else 'FAIL'}")
                print(f"   ✅ Price precision check: {'PASS' if price_ok else 'FAIL'}")

            print()

        # Test precision rules for common symbols
        print("🎯 Precision Rules for Common Symbols:")
        common_symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOGEUSDT', 'SOLUSDT', 'XRPUSDT']

        for symbol in common_symbols:
            if exchange.validate_symbol(symbol):
                qty_precision = exchange.get_quantity_precision(symbol)
                price_precision = exchange.get_price_precision(symbol)
                print(f"   {symbol}: Qty={qty_precision} decimals, Price={price_precision} decimals")

        print("\n✅ Precision and validation testing completed!")
        return True

    except Exception as e:
        logging.error(f"Error during testing: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_precision_and_validation())
    if success:
        print("\n🎉 All tests completed successfully!")
    else:
        print("\n❌ Testing failed")
        sys.exit(1)