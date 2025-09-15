#!/usr/bin/env python3
"""
KuCoin Order Book Test Script

Tests the KuCoin order book functionality using the existing integration.
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

from src.exchange.kucoin.kucoin_exchange import KucoinExchange

async def test_order_book():
    """Test KuCoin order book functionality"""
    print("=== KuCoin Order Book Test ===")

    # Get credentials from environment
    api_key = os.getenv("KUCOIN_API_KEY")
    api_secret = os.getenv("KUCOIN_API_SECRET")
    api_passphrase = os.getenv("KUCOIN_API_PASSPHRASE")

    if not all([api_key, api_secret, api_passphrase]):
        print("❌ Missing KuCoin API credentials in .env file")
        return False

    print(f"✅ Found API credentials")

    # Initialize exchange
    exchange = KucoinExchange(api_key, api_secret, api_passphrase, is_testnet=False)

    try:
        # Initialize connection
        print("Initializing KuCoin exchange...")
        success = await exchange.initialize()
        if not success:
            print("❌ Failed to initialize KuCoin exchange")
            return False

        print("✅ KuCoin exchange initialized successfully")

        # Test symbols
        test_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

        for symbol in test_symbols:
            print(f"\n--- Testing Order Book for {symbol} ---")
            try:
                order_book = await exchange.get_order_book(symbol, limit=5)
                if order_book:
                    print(f"✅ Order book retrieved for {symbol}")
                    print(f"Symbol: {order_book.get('symbol', 'N/A')}")
                    print(f"Bids: {len(order_book.get('bids', []))}")
                    print(f"Asks: {len(order_book.get('asks', []))}")

                    if order_book.get('bids'):
                        print(f"Best bid: {order_book['bids'][0]}")
                    if order_book.get('asks'):
                        print(f"Best ask: {order_book['asks'][0]}")
                else:
                    print(f"⚠️  No order book data for {symbol}")
            except Exception as e:
                print(f"❌ Error getting order book for {symbol}: {e}")

        # Test current prices
        print(f"\n--- Testing Current Prices ---")
        try:
            prices = await exchange.get_current_prices(test_symbols)
            if prices:
                print("✅ Current prices retrieved:")
                for symbol, price in prices.items():
                    print(f"  {symbol}: ${price}")
            else:
                print("⚠️  No price data available")
        except Exception as e:
            print(f"❌ Error getting current prices: {e}")

        # Test symbol support
        print(f"\n--- Testing Symbol Support ---")
        for symbol in test_symbols:
            try:
                is_supported = await exchange.is_futures_symbol_supported(symbol)
                print(f"{symbol}: {'✅ Supported' if is_supported else '❌ Not supported'}")
            except Exception as e:
                print(f"❌ Error checking support for {symbol}: {e}")

        print("\n✅ KuCoin order book test completed!")
        return True

    except Exception as e:
        print(f"❌ KuCoin order book test failed: {e}")
        return False
    finally:
        await exchange.close()

async def main():
    """Main entry point"""
    success = await test_order_book()

    if success:
        print("\n🎉 KuCoin order book functionality is working!")
    else:
        print("\n💥 KuCoin order book test failed!")

if __name__ == "__main__":
    asyncio.run(main())
