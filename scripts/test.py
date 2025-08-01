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
    price_service = PriceService()
    currentPrice =await binance_exchange.get_futures_mark_price("SQDUSDT")
    tokenPrice = await price_service.get_coin_price("SQD")
    print(f"Current Price in coinGecko: {tokenPrice}")
    print("🔍Current price binance: \n",currentPrice )
    return True
     
async def main():   
    """Main function to run the price threshold test."""
    
    await test_price_thresholds()
if __name__ == "__main__":
    asyncio.run(main())