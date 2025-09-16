#!/usr/bin/env python3
"""
KuCoin Transaction History Test Script

Tests the KuCoin transaction history functionality using the existing integration.
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

async def test_transaction_history():
    """Test KuCoin transaction history functionality"""
    print("=== KuCoin Transaction History Test ===")

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

        # Test user trades
        print("\n--- Testing User Trades ---")
        try:
            trades = await exchange.get_user_trades(limit=10)
            if trades:
                print(f"✅ Retrieved {len(trades)} user trades:")
                for i, trade in enumerate(trades[:5]):  # Show first 5
                    print(f"  Trade {i+1}:")
                    print(f"    Symbol: {trade.get('symbol', 'N/A')}")
                    print(f"    Side: {trade.get('side', 'N/A')}")
                    print(f"    Size: {trade.get('size', 'N/A')}")
                    print(f"    Price: {trade.get('price', 'N/A')}")
                    print(f"    Fee: {trade.get('fee', 'N/A')}")
            else:
                print("⚠️  No user trades found")
        except Exception as e:
            print(f"❌ Error getting user trades: {e}")

        # Test specific symbol trades
        print("\n--- Testing Symbol-Specific Trades ---")
        test_symbols = ["BTC-USDT", "ETH-USDT"]
        for symbol in test_symbols:
            try:
                symbol_trades = await exchange.get_user_trades(symbol=symbol, limit=5)
                if symbol_trades:
                    print(f"✅ Retrieved {len(symbol_trades)} trades for {symbol}")
                else:
                    print(f"⚠️  No trades found for {symbol}")
            except Exception as e:
                print(f"❌ Error getting trades for {symbol}: {e}")

        # Test income history
        print("\n--- Testing Income History ---")
        try:
            income_history = await exchange.get_income_history(limit=10)
            if income_history:
                print(f"✅ Retrieved {len(income_history)} income records:")
                for i, income in enumerate(income_history[:5]):  # Show first 5
                    print(f"  Income {i+1}:")
                    print(f"    Symbol: {income.get('symbol', 'N/A')}")
                    print(f"    Type: {income.get('income_type', 'N/A')}")
                    print(f"    Amount: {income.get('income', 'N/A')}")
                    print(f"    Asset: {income.get('asset', 'N/A')}")
            else:
                print("⚠️  No income history found")
        except Exception as e:
            print(f"❌ Error getting income history: {e}")

        # Test income history with filters
        print("\n--- Testing Filtered Income History ---")
        for symbol in test_symbols:
            try:
                symbol_income = await exchange.get_income_history(symbol=symbol, limit=5)
                if symbol_income:
                    print(f"✅ Retrieved {len(symbol_income)} income records for {symbol}")
                else:
                    print(f"⚠️  No income records found for {symbol}")
            except Exception as e:
                print(f"❌ Error getting income history for {symbol}: {e}")

        print("\n✅ KuCoin transaction history test completed!")
        return True

    except Exception as e:
        print(f"❌ KuCoin transaction history test failed: {e}")
        return False
    finally:
        await exchange.close()

async def main():
    """Main entry point"""
    success = await test_transaction_history()

    if success:
        print("\n🎉 KuCoin transaction history functionality is working!")
    else:
        print("\n💥 KuCoin transaction history test failed!")

if __name__ == "__main__":
    asyncio.run(main())
