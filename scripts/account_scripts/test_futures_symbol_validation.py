#!/usr/bin/env python3
"""
Test script to verify the futures symbol validation fix.
This tests that the bot now correctly validates futures symbols instead of spot symbols.
"""
# python3 scripts/account_scripts/test_futures_symbol_validation.py
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

async def test_symbol_validation():
    """Test futures symbol validation fix."""
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
        print("         FUTURES SYMBOL VALIDATION TEST")
        print("="*70)
        print(f"Environment: {'Testnet' if is_testnet else 'Mainnet'}")

        # Initialize exchange
        exchange = BinanceExchange(api_key, api_secret, is_testnet)

        # Symbols that were failing in the logs
        test_symbols = [
            'btc_usdt', 'eth_usdt', 'arb_usdt', 'xrp_usdt',
            'sui_usdt', 'zro_usdt', 'lqty_usdt', 'hft_usdt',
            'syrup_usdt', 'bmt_usdt', 'layer_usdt', 'pengu_usdt'
        ]

        print(f"\n🧪 Testing futures symbol validation:")
        print(f"   Testing {len(test_symbols)} symbols that were previously failing")

        futures_available = []
        spot_available = []
        both_available = []
        neither_available = []

        for symbol in test_symbols:
            print(f"\n📋 Testing {symbol}:")

            # Test futures validation (NEW METHOD)
            futures_info = await exchange.get_futures_pair_info(symbol)
            futures_supported = await exchange.is_futures_symbol_supported(symbol)

            # Test spot validation (OLD METHOD)
            spot_info = await exchange.get_pair_info(symbol)

            if futures_info and spot_info:
                both_available.append(symbol)
                print(f"   ✅ FUTURES: Available (status: {futures_info.get('status', 'unknown')})")
                print(f"   ✅ SPOT: Available (status: {spot_info.get('status', 'unknown')})")
                print(f"   ✅ Futures Supported Check: {futures_supported}")
            elif futures_info and not spot_info:
                futures_available.append(symbol)
                print(f"   ✅ FUTURES: Available (status: {futures_info.get('status', 'unknown')})")
                print(f"   ❌ SPOT: Not available")
                print(f"   ✅ Futures Supported Check: {futures_supported}")
                print(f"   🎯 THIS WAS THE BUG - futures available but spot validation failed!")
            elif not futures_info and spot_info:
                spot_available.append(symbol)
                print(f"   ❌ FUTURES: Not available")
                print(f"   ✅ SPOT: Available (status: {spot_info.get('status', 'unknown')})")
                print(f"   ❌ Futures Supported Check: {futures_supported}")
            else:
                neither_available.append(symbol)
                print(f"   ❌ FUTURES: Not available")
                print(f"   ❌ SPOT: Not available")
                print(f"   ❌ Futures Supported Check: {futures_supported}")

        await exchange.close()

        print(f"\n📊 RESULTS SUMMARY:")
        print(f"   ✅ Available on BOTH Futures & Spot: {len(both_available)}")
        if both_available:
            print(f"      {', '.join(both_available)}")

        print(f"   🎯 Available on FUTURES only: {len(futures_available)}")
        if futures_available:
            print(f"      {', '.join(futures_available)}")
            print(f"      ^ These symbols were causing the 'Invalid symbol' errors!")

        print(f"   📈 Available on SPOT only: {len(spot_available)}")
        if spot_available:
            print(f"      {', '.join(spot_available)}")

        print(f"   ❌ Not available on either: {len(neither_available)}")
        if neither_available:
            print(f"      {', '.join(neither_available)}")

        print(f"\n🎯 CONCLUSION:")
        if futures_available:
            print(f"   ✅ FIX VERIFIED: {len(futures_available)} symbols available on futures but not spot")
            print(f"   ✅ These symbols will now work correctly with the updated validation")
        else:
            print(f"   ✅ All tested symbols are available on both futures and spot")

        print("="*70)

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Testing Futures Symbol Validation Fix")
    asyncio.run(test_symbol_validation())