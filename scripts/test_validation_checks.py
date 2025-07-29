#!/usr/bin/env python3
"""
Test script for quantity/notional and position/leverage validation
"""

import asyncio
import sys
import os

from supabase._sync.client import SyncClient
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bot.trading_engine import TradingEngine
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange
from discord_bot.database import DatabaseManager
import config.settings as config

async def test_validation_checks():
    """Test the new validation logic"""

    # Initialize components
    price_service = PriceService()
    binance_exchange = BinanceExchange(
        api_key=str(config.BINANCE_API_KEY),
        api_secret=str(config.BINANCE_API_SECRET),  # Fixed attribute name
        is_testnet=bool(config.BINANCE_TESTNET)  # Fixed attribute name
    )
    db_manager = DatabaseManager(SyncClient("dummy", "dummy"))  # Pass valid SyncClient

    trading_engine = TradingEngine(price_service, binance_exchange, db_manager)

    # Test cases
    test_cases = [
        {
            "name": "BTC - Normal trade",
            "coin_symbol": "BTC",
            "signal_price": 50000.0,
            "position_type": "LONG",
            "order_type": "MARKET"
        },
        {
            "name": "SOL - Small quantity test",
            "coin_symbol": "SOL",
            "signal_price": 100.0,
            "position_type": "LONG",
            "order_type": "MARKET"
        },
        {
            "name": "ETH - Limit order test",
            "coin_symbol": "ETH",
            "signal_price": 3000.0,
            "position_type": "LONG",
            "order_type": "LIMIT"
        }
    ]

    print("Testing validation checks...")
    print("=" * 50)

    for test_case in test_cases:
        print(f"\nTest: {test_case['name']}")
        print(f"Symbol: {test_case['coin_symbol']}")
        print(f"Price: ${test_case['signal_price']}")
        print(f"Type: {test_case['position_type']}")
        print(f"Order: {test_case['order_type']}")

        try:
            success, result = await trading_engine.process_signal(
                coin_symbol=test_case['coin_symbol'],
                signal_price=test_case['signal_price'],
                position_type=test_case['position_type'],
                order_type=test_case['order_type']
            )

            if success:
                print("✅ SUCCESS: Order would be placed")
                if isinstance(result, dict) and 'orderId' in result:
                    print(f"   Order ID: {result['orderId']}")
            else:
                print("❌ FAILED: Order blocked by validation")
                print(f"   Reason: {result}")

        except Exception as e:
            print(f"❌ ERROR: {e}")

        print("-" * 30)

    # Cleanup
    await trading_engine.close()
    await binance_exchange.close_client()

if __name__ == "__main__":
    asyncio.run(test_validation_checks())