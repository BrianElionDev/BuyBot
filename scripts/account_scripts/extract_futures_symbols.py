#!/usr/bin/env python3
"""
Extract all available Binance Futures symbols on testnet and create a whitelist.
This helps identify valid trading pairs for the bot.
"""

import os
import sys
import json
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

def extract_futures_symbols():
    """Extract all available futures symbols and create whitelist files."""
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
        print("         EXTRACTING BINANCE FUTURES SYMBOLS")
        print("="*70)
        print(f"Environment: {'Testnet' if is_testnet else 'Mainnet'}")

        # Initialize client
        client = Client(api_key, api_secret, testnet=is_testnet)

        # Get futures exchange info
        print("\n🔍 Fetching futures exchange info...")
        exchange_info = client.futures_exchange_info()

        symbols = exchange_info.get('symbols', [])
        print(f"📊 Total futures symbols available: {len(symbols)}")

        # Extract only TRADING symbols with USDT pairs
        usdt_symbols = []
        all_trading_symbols = []
        symbol_details = {}

        for symbol in symbols:
            if symbol['status'] == 'TRADING':
                symbol_name = symbol['symbol']
                all_trading_symbols.append(symbol_name)

                # Store symbol details
                symbol_details[symbol_name] = {
                    'baseAsset': symbol['baseAsset'],
                    'quoteAsset': symbol['quoteAsset'],
                    'status': symbol['status']
                }

                # Filter USDT pairs (most common for trading)
                if symbol['quoteAsset'] == 'USDT':
                    usdt_symbols.append(symbol_name)

        # Sort symbols
        usdt_symbols.sort()
        all_trading_symbols.sort()

        print(f"\n💰 USDT trading pairs found: {len(usdt_symbols)}")
        print(f"📈 Total trading symbols: {len(all_trading_symbols)}")

        # Create whitelists directory
        os.makedirs('config/whitelists', exist_ok=True)

        # Save USDT symbols whitelist (recommended for most trading bots)
        usdt_whitelist_file = 'config/whitelists/binance_futures_usdt_symbols.json'
        with open(usdt_whitelist_file, 'w') as f:
            json.dump({
                'description': 'Available USDT futures symbols on Binance testnet',
                'environment': 'testnet' if is_testnet else 'mainnet',
                'total_count': len(usdt_symbols),
                'symbols': usdt_symbols
            }, f, indent=2)

        # Save all trading symbols
        all_whitelist_file = 'config/whitelists/binance_futures_all_symbols.json'
        with open(all_whitelist_file, 'w') as f:
            json.dump({
                'description': 'All available futures symbols on Binance testnet',
                'environment': 'testnet' if is_testnet else 'mainnet',
                'total_count': len(all_trading_symbols),
                'symbols': all_trading_symbols
            }, f, indent=2)

        # Save detailed symbol information
        details_file = 'config/whitelists/binance_futures_symbol_details.json'
        with open(details_file, 'w') as f:
            json.dump({
                'description': 'Detailed information for all futures symbols',
                'environment': 'testnet' if is_testnet else 'mainnet',
                'symbols': symbol_details
            }, f, indent=2)

        # Create Python whitelist module
        python_whitelist_file = 'config/binance_futures_whitelist.py'
        with open(python_whitelist_file, 'w') as f:
            f.write('"""Binance Futures Symbol Whitelist"""\n\n')
            f.write('# USDT trading pairs (recommended for most bots)\n')
            f.write(f'USDT_FUTURES_SYMBOLS = {usdt_symbols}\n\n')
            f.write('# All available futures symbols\n')
            f.write(f'ALL_FUTURES_SYMBOLS = {all_trading_symbols}\n\n')
            f.write('def is_symbol_supported(symbol: str, usdt_only: bool = True) -> bool:\n')
            f.write('    """Check if a symbol is supported for futures trading."""\n')
            f.write('    symbol = symbol.upper()\n')
            f.write('    if usdt_only:\n')
            f.write('        return symbol in USDT_FUTURES_SYMBOLS\n')
            f.write('    return symbol in ALL_FUTURES_SYMBOLS\n\n')
            f.write('def format_symbol_for_binance(pair: str) -> str:\n')
            f.write('    """Convert pair format to Binance format (e.g., eth_usdt -> ETHUSDT)."""\n')
            f.write('    return pair.replace("_", "").upper()\n')

        # Display some popular symbols
        popular_coins = ['BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'DOGE', 'XRP', 'DOT', 'MATIC', 'LINK']

        print(f"\n🎯 Popular coins available as USDT futures:")
        available_popular = []
        for coin in popular_coins:
            symbol = f"{coin}USDT"
            if symbol in usdt_symbols:
                available_popular.append(symbol)
                print(f"   ✅ {symbol}")
            else:
                print(f"   ❌ {symbol} (not available)")

        print(f"\n📁 Files created:")
        print(f"   📄 {usdt_whitelist_file}")
        print(f"   📄 {all_whitelist_file}")
        print(f"   📄 {details_file}")
        print(f"   🐍 {python_whitelist_file}")

        print(f"\n📊 Summary:")
        print(f"   💰 USDT pairs: {len(usdt_symbols)}")
        print(f"   📈 Total trading pairs: {len(all_trading_symbols)}")
        print(f"   🎯 Popular coins available: {len(available_popular)}/{len(popular_coins)}")

        print("="*70)

    except BinanceAPIException as e:
        print(f"❌ Binance API Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    extract_futures_symbols()