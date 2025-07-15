#!/usr/bin/env python3
"""
Check available Binance Futures symbols on testnet.
This helps identify valid trading pairs and symbol formatting.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from binance.client import Client
from binance.exceptions import BinanceAPIException

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_futures_symbols():
    """Check available futures symbols on Binance testnet."""
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
        print("         BINANCE FUTURES SYMBOLS CHECK")
        print("="*70)
        print(f"Environment: {'Testnet' if is_testnet else 'Mainnet'}")
        print(f"API Key: {api_key[:10]}...{api_key[-5:]}")

        # Initialize client
        client = Client(api_key, api_secret, testnet=is_testnet)

        # Get futures exchange info
        print("\n🔍 Fetching futures exchange info...")
        exchange_info = client.futures_exchange_info()

        symbols = exchange_info.get('symbols', [])
        print(f"📊 Total futures symbols available: {len(symbols)}")

        # Look for ETH-related symbols
        eth_symbols = [s for s in symbols if 'ETH' in s['symbol'] and s['status'] == 'TRADING']

        print(f"\n💰 ETH-related futures symbols ({len(eth_symbols)} found):")
        for symbol in eth_symbols[:10]:  # Show first 10
            print(f"   ✅ {symbol['symbol']:<12} | Base: {symbol['baseAsset']:<5} | Quote: {symbol['quoteAsset']}")

        if len(eth_symbols) > 10:
            print(f"   ... and {len(eth_symbols) - 10} more ETH symbols")

        # Check specific symbols our bot might use
        target_symbols = ['ETHUSDT', 'BTCUSDT', 'ADAUSDT', 'BNBUSDT']
        print(f"\n🎯 Checking common symbols:")

        for target in target_symbols:
            found = next((s for s in symbols if s['symbol'] == target), None)
            if found:
                status = found['status']
                print(f"   ✅ {target:<10} | Status: {status}")
            else:
                print(f"   ❌ {target:<10} | NOT FOUND")

        # Show some other popular symbols
        popular = [s for s in symbols if s['symbol'] in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT', 'DOGEUSDT'] and s['status'] == 'TRADING']

        print(f"\n🔥 Popular trading symbols available:")
        for symbol in popular:
            print(f"   ✅ {symbol['symbol']:<12} | Status: {symbol['status']}")

        # Test if we can get ticker for ETHUSDT
        print(f"\n🧪 Testing ETHUSDT ticker...")
        try:
            ticker = client.futures_symbol_ticker(symbol='ETHUSDT')
            print(f"   ✅ ETHUSDT ticker: ${ticker['price']}")
        except BinanceAPIException as e:
            print(f"   ❌ ETHUSDT ticker failed: {e}")

        print("="*70)

    except BinanceAPIException as e:
        print(f"❌ Binance API Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    check_futures_symbols()