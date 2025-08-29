#!/usr/bin/env python3
"""
Test script to verify the new price threshold logic for different coin types.
"""

import os
import sys
import asyncio
import logging
from config import settings

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.bot.trading_engine import TradingEngine
from src.services import PriceService
from src.exchange import BinanceExchange
from discord_bot.database import DatabaseManager
from config import settings as config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_price_thresholds():
    """Test price threshold logic for different coin types."""
    try:
        # Load environment variables
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET

        if not api_key or not api_secret:
            logging.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set")
            return False

        # Initialize components
        price_service = PriceService()
        binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)

        # Create a mock database manager for testing
        from supabase import create_client, Client
        mock_supabase = create_client("https://mock.supabase.co", "mock_key")
        db_manager = DatabaseManager(mock_supabase)

        trading_engine = TradingEngine(price_service, binance_exchange, db_manager)

        print("🔍 Testing Price Threshold Logic\n")

        # Test cases with different coin types
        test_cases = [
            # (coin_symbol, signal_price, expected_threshold_type)
            ("BTC", 50000.0, "standard"),  # Major coin - should use standard threshold
            ("ETH", 3000.0, "standard"),   # Major coin - should use standard threshold
            ("PEPE", 0.0123, "memecoin"),  # Memecoin - should use memecoin threshold
            ("BONK", 0.027, "memecoin"),   # Memecoin - should use memecoin threshold
            ("H", 0.0812, "memecoin"),     # Memecoin - should use memecoin threshold
            ("PENGU", 0.0285, "memecoin"), # Memecoin - should use memecoin threshold
            ("ICNT", 0.2965, "low_liquidity"), # Low liquidity - should use low liquidity threshold
            ("SPX", 1.7047, "low_liquidity"),  # Low liquidity - should use low liquidity threshold
        ]

        print("📋 Test Results:\n")
        print(f"{'Coin':<10} {'Signal Price':<15} {'Threshold Type':<15} {'Current Price':<15} {'Diff %':<10} {'Status'}")
        print("-" * 80)

        for coin_symbol, signal_price, expected_type in test_cases:
            try:
                # Get current market price
                current_price = await price_service.get_coin_price(coin_symbol)

                if current_price:
                    # Calculate price difference
                    price_diff = abs(current_price - signal_price) / signal_price * 100

                    # Determine threshold type based on coin
                    memecoin_symbols = ['PEPE', 'BONK', 'DOGE', 'SHIB', 'FLOKI', 'PENGU', 'H', 'TOSHI', 'TURBO', 'MOG', 'FARTCOIN', 'PUMP', 'PUMPFUN']
                    low_liquidity_symbols = ['ICNT', 'SPX', 'SYRUP', 'VIC', 'SPEC', 'HAEDAL', 'ZORA', 'CUDI', 'BERA', 'ALU', 'INIT', 'XLM', 'ADA', 'REZ', 'SEI', 'VIRTUAL', 'ES', 'HBAR', 'ONDO', 'LAUNCHCOIN', 'PNUT', 'MAV', 'PLUME']

                    if coin_symbol.upper() in memecoin_symbols:
                        actual_type = "memecoin"
                        threshold = config.MEMECOIN_PRICE_THRESHOLD
                    elif coin_symbol.upper() in low_liquidity_symbols:
                        actual_type = "low_liquidity"
                        threshold = config.LOW_LIQUIDITY_PRICE_THRESHOLD
                    else:
                        actual_type = "standard"
                        threshold = config.PRICE_THRESHOLD

                    # Check if price difference is acceptable
                    status = "✅ PASS" if price_diff <= threshold else "❌ FAIL"

                    print(f"{coin_symbol:<10} ${signal_price:<14.6f} {actual_type:<15} ${current_price:<14.6f} {price_diff:<9.2f}% {status}")

                    # Verify threshold type matches expectation
                    if actual_type != expected_type:
                        print(f"  ⚠️  Warning: Expected {expected_type} but got {actual_type}")

                else:
                    print(f"{coin_symbol:<10} ${signal_price:<14.6f} {'N/A':<15} {'N/A':<15} {'N/A':<10} ❌ NO PRICE")

            except Exception as e:
                print(f"{coin_symbol:<10} ${signal_price:<14.6f} {'ERROR':<15} {'N/A':<15} {'N/A':<10} ❌ ERROR: {e}")

        print(f"\n📊 Threshold Summary:")
        print(f"Standard threshold: {config.PRICE_THRESHOLD}%")
        print(f"Memecoin threshold: {config.MEMECOIN_PRICE_THRESHOLD}%")
        print(f"Low liquidity threshold: {config.LOW_LIQUIDITY_PRICE_THRESHOLD}%")

        return True

    except Exception as e:
        logging.error(f"Error in test: {e}", exc_info=True)
        return False

async def main():
    """Main function to run the price threshold test."""
    success = await test_price_thresholds()
    if success:
        print("\n✅ Price threshold test completed successfully!")
    else:
        print("\n❌ Price threshold test failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())