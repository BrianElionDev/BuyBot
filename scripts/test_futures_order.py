#!/usr/bin/env python3
"""
Test script to verify that the futures order creation bug has been fixed.
This tests the symbol formatting issue that was causing "Invalid symbol" errors.
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

async def test_futures_order_creation():
    """Test futures order creation with the bug fix."""
    try:
        # Load environment variables
        load_dotenv()

        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        is_testnet = os.getenv("BINANCE_TESTNET", "True").lower() == "true"

        if not api_key or not api_secret:
            print("❌ No API credentials found")
            return

        print("="*70)
        print("           FUTURES ORDER CREATION TEST")
        print("="*70)
        print(f"Environment: {'Testnet' if is_testnet else 'Mainnet'}")
        print(f"API Key: {api_key[:10]}...{api_key[-5:]}")

        # Initialize exchange
        exchange = BinanceExchange(api_key, api_secret, is_testnet)

        # Test parameters (minimum amount to meet Binance requirements)
        test_pair = "eth_usdt"  # This should be converted to ETHUSDT
        test_amount = 0.009  # Larger amount to meet $20 minimum (0.009 * $2300 = $20.70)
        test_price = 2300.0  # Below current market price (won't execute)

        print(f"\n🧪 Testing futures order creation:")
        print(f"   Pair: {test_pair} → Should become ETHUSDT")
        print(f"   Amount: {test_amount} ETH")
        print(f"   Price: ${test_price} (limit order)")
        print(f"   Notional value: ~${test_amount * test_price:.2f} (must be ≥$20)")
        print(f"   Type: LONG position")

        # Test the create_futures_order method
        print(f"\n🔄 Attempting to create futures order...")

        order_result = await exchange.create_futures_order(
            pair=test_pair,
            order_type='buy',
            amount=test_amount,
            price=test_price,
            leverage=1
        )

        if order_result:
            print(f"✅ SUCCESS: Futures order created successfully!")
            print(f"   Order ID: {order_result.get('orderId', 'N/A')}")
            print(f"   Symbol: {order_result.get('symbol', 'N/A')}")
            print(f"   Status: {order_result.get('status', 'N/A')}")

            # Clean up - cancel the order immediately
            if 'orderId' in order_result:
                try:
                    cancel_result = await exchange.cancel_futures_order(
                        pair=test_pair,
                        order_id=str(order_result['orderId'])
                    )
                    print(f"🗑️ Order cancelled for cleanup: {cancel_result}")
                except Exception as e:
                    print(f"⚠️ Could not cancel order (manual cleanup needed): {e}")
        else:
            print(f"❌ FAILED: Could not create futures order")
            print(f"   The bug might still exist or there's another issue")

        await exchange.close()
        print("="*70)

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

async def test_symbol_formatting():
    """Test just the symbol formatting logic."""
    print("\n" + "="*50)
    print("       SYMBOL FORMATTING TEST")
    print("="*50)

    test_cases = [
        "eth_usdt",
        "btc_usdt",
        "ada_usdt",
        "ETH_USDT",
        "ETHUSDT"
    ]

    for test_pair in test_cases:
        formatted = test_pair.replace('_', '').upper()
        print(f"   {test_pair:<10} → {formatted}")

    print("="*50)

if __name__ == "__main__":
    print("🚀 Starting Futures Order Bug Fix Verification")

    # Test symbol formatting first
    asyncio.run(test_symbol_formatting())

    # Test actual order creation
    asyncio.run(test_futures_order_creation())