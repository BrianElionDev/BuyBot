#!/usr/bin/env python3
"""
Test script to verify the new price threshold logic for different coin types.
"""

import os
import sys
import asyncio
import logging
import math
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.bot.trading_engine import TradingEngine
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange
from discord_bot.database import DatabaseManager
from discord_bot.discord_signal_parser import DiscordSignalParser
from config import settings as config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def get_binance_symbols(binance_exchange, limit=100):
    """
    Get available symbols from Binance.
    
    Args:
        binance_exchange: BinanceExchange instance
        limit (int): Maximum number of symbols to return
    
    Returns:
        list: List of symbol dictionaries
    """
    try:
        # Use the existing method to get futures symbols
        symbols = await binance_exchange.get_all_futures_symbols()
        
        # Convert to the format expected by the rest of the code
        symbol_dicts = [{'symbol': symbol, 'status': 'TRADING'} for symbol in symbols]
        
        # Sort by symbol name and limit results
        symbol_dicts.sort(key=lambda x: x['symbol'])
        return symbol_dicts[:limit]
        
    except Exception as e:
        logging.error(f"Error getting symbols: {e}")
        return []





async def test_price_thresholds():
    """Test price threshold logic for different coin types."""
    # Load environment variables
    load_dotenv()

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    is_testnet = os.getenv('BINANCE_TESTNET', 'True').lower() == 'true'

    if not api_key or not api_secret:
        logging.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set")
        return False

    # Initialize components
    price_service = PriceService()
    binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
    
    available_symbols = ["ETHUSDT"]
    for symbol_pair in available_symbols:
        print(f"\n=== Testing {symbol_pair} ===")
        
        try:
            # Test min and max quantity calculation
            print("\n--- Minimum and Maximum Quantity Calculation ---")
            quantities = await binance_exchange.calculate_min_max_market_order_quantity(symbol_pair)
            print(f"MinMax: {quantities['min_quantity']}, {quantities['max_quantity']}")
        except Exception as e:
            logging.error(f"Error calculating quantities for {symbol_pair}: {e}")
            continue
    
    return True
     
async def main():   
    """Main function to run the price threshold test."""
    discordParser = DiscordSignalParser()
    parsed = await discordParser.parse_new_trade_signal('LIMIT|BTC|Entry:|1000|SL:|2150')
    print("Parsed signal:", parsed)
if __name__ == "__main__":
    asyncio.run(main())