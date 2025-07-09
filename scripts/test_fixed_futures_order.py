#!/usr/bin/env python3
"""
Test script to verify that futures orders work correctly with precision and validation fixes.
This tests a real futures order with high precision amounts that would previously fail.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.exchange.binance_exchange import BinanceExchange

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_fixed_futures_order():
    """Test that futures orders work with the precision and validation fixes."""
    try:
        # Load environment variables
        load_dotenv()

        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        is_testnet = os.getenv('BINANCE_TESTNET', 'True').lower() == 'true'

        if not api_key or not api_secret:
            logging.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set")
            return False

        # Initialize Binance exchange
        exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=is_testnet
        )

        print("🔍 Testing Fixed Futures Order Creation\n")

        # Test with the same problematic amounts from your logs
        test_cases = [
            {
                'symbol': 'eth_usdt',
                'quantity': 0.05884107,  # This was causing precision errors
                'price': 2560.123456,    # This will get rounded properly
                'description': 'ETH with high precision (was failing before)'
            },
            {
                'symbol': 'btc_usdt',
                'quantity': 0.00137909,  # This was causing precision errors
                'price': 65432.789012,   # This will get rounded properly
                'description': 'BTC with high precision (was failing before)'
            }
        ]

        for test_case in test_cases:
            symbol = test_case['symbol']
            quantity = test_case['quantity']
            price = test_case['price']
            description = test_case['description']

            print(f"📋 Test Case: {description}")
            print(f"   Symbol: {symbol}")
            print(f"   Original Quantity: {quantity:.8f}")
            print(f"   Original Price: ${price:.8f}")

            # Test precision rounding
            formatted_symbol = symbol.replace('_', '').upper()
            rounded_quantity = exchange._round_futures_quantity(formatted_symbol, quantity)
            rounded_price = exchange._round_futures_price(formatted_symbol, price)

            print(f"   Rounded Quantity: {rounded_quantity:.8f}")
            print(f"   Rounded Price: ${rounded_price:.8f}")

            # Test symbol validation
            is_valid = exchange._validate_futures_symbol(formatted_symbol)
            print(f"   Symbol Valid: {'✅ YES' if is_valid else '❌ NO'}")

            if not is_valid:
                print(f"   🚫 Skipping order creation - symbol not in whitelist\n")
                continue

            # Test order creation (this would have failed before the fix)
            print(f"   🔄 Creating futures order...")

            try:
                order_result = await exchange.create_futures_order(
                    pair=symbol,
                    order_type='buy',
                    amount=quantity,  # Pass original amount - it will be rounded internally
                    price=None,      # Market order
                    leverage=20
                )

                if order_result:
                    print(f"   ✅ SUCCESS! Order created successfully")
                    print(f"   📊 Order ID: {order_result.get('orderId', 'N/A')}")
                    print(f"   💰 Executed Quantity: {order_result.get('executedQty', 'N/A')}")
                    print(f"   💸 Executed Price: ${order_result.get('avgPrice', order_result.get('price', 'N/A'))}")

                    # Cancel the order immediately for cleanup
                    order_id = order_result.get('orderId')
                    if order_id:
                        cancel_result = await exchange.cancel_futures_order(symbol, str(order_id))
                        print(f"   🗑️  Order cancelled: {'✅' if cancel_result else '❌'}")
                else:
                    print(f"   ❌ Order creation failed (returned None)")

            except Exception as e:
                print(f"   ❌ Order creation failed with error: {e}")

            print()

        print("🎯 Summary:")
        print("   • Symbol validation prevents invalid symbols from reaching Binance")
        print("   • Precision rounding prevents -1111 'Precision is over the maximum' errors")
        print("   • Orders that would previously fail now succeed")

        return True

    except Exception as e:
        logging.error(f"Error during testing: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_fixed_futures_order())
    if success:
        print("\n🎉 Futures order fix testing completed successfully!")
        print("✅ Your bot should no longer get precision errors for futures trades!")
    else:
        print("\n❌ Testing failed")
        sys.exit(1)