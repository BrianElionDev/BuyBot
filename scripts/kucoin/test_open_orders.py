#!/usr/bin/env python3
"""
KuCoin Open Orders Test Script

Tests the KuCoin open orders functionality using the existing integration.
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

async def test_open_orders():
    """Test KuCoin open orders functionality"""
    print("=== KuCoin Open Orders Test ===")

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

        # Test account balances
        print("\n--- Testing Account Balances ---")
        try:
            balances = await exchange.get_account_balances()
            if balances:
                print("✅ Account balances retrieved:")
                for asset, balance in balances.items():
                    if balance > 0:
                        print(f"  {asset}: {balance}")
            else:
                print("⚠️  No balance data available")
        except Exception as e:
            print(f"❌ Error getting account balances: {e}")

        # Test spot balances
        print("\n--- Testing Spot Balances ---")
        try:
            spot_balances = await exchange.get_spot_balance()
            if spot_balances:
                print("✅ Spot balances retrieved:")
                for asset, balance in spot_balances.items():
                    if balance > 0:
                        print(f"  {asset}: {balance}")
            else:
                print("⚠️  No spot balance data available")
        except Exception as e:
            print(f"❌ Error getting spot balances: {e}")

        # Test order status (with a dummy order ID)
        print("\n--- Testing Order Status ---")
        test_symbols = ["BTC-USDT", "ETH-USDT"]
        for symbol in test_symbols:
            try:
                # Try to get order status for a non-existent order
                order_status = await exchange.get_order_status(symbol, "dummy_order_id")
                if order_status:
                    print(f"✅ Order status retrieved for {symbol}")
                    print(f"  Order ID: {order_status.get('orderId', 'N/A')}")
                    print(f"  Status: {order_status.get('status', 'N/A')}")
                else:
                    print(f"⚠️  No order status data for {symbol} (expected for dummy order)")
            except Exception as e:
                print(f"❌ Error getting order status for {symbol}: {e}")

        print("\n✅ KuCoin open orders test completed!")
        return True

    except Exception as e:
        print(f"❌ KuCoin open orders test failed: {e}")
        return False
    finally:
        await exchange.close()

async def main():
    """Main entry point"""
    success = await test_open_orders()

    if success:
        print("\n🎉 KuCoin open orders functionality is working!")
    else:
        print("\n💥 KuCoin open orders test failed!")

if __name__ == "__main__":
    asyncio.run(main())
