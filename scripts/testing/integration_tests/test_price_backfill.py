#!/usr/bin/env python3
"""
Test Price Backfill Fallback

This script tests that the price backfill fallback mechanism works correctly
and doesn't break existing functionality.
"""

import sys
import os
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_price_backfill_import_error():
    """Test that price backfill handles import errors gracefully."""
    print("🔍 Testing Price Backfill Import Error Handling...")

    try:
        from discord_bot.main import backfill_missing_prices

        # Mock bot and supabase
        mock_bot = Mock()
        mock_supabase = Mock()

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.get_trades_by_status = AsyncMock(return_value=[
            {'id': 1, 'coin_symbol': 'BTC', 'entry_price': 50000, 'binance_entry_price': None},
            {'id': 2, 'coin_symbol': 'ETH', 'entry_price': 3000, 'binance_entry_price': None}
        ])
        mock_db_manager.update_trade_with_original_response = AsyncMock(return_value=True)

        # Mock price service
        mock_price_service = Mock()
        mock_price_service.get_coin_price = AsyncMock(side_effect=[51000, 3100])  # Mock prices

        mock_bot.db_manager = mock_db_manager
        mock_bot.price_service = mock_price_service

        # Test with ImportError (simulate missing module)
        with patch('discord_bot.main.HistoricalTradeBackfillManager', side_effect=ImportError("No module named 'src.exchange.binance_exchange'")):
            await backfill_missing_prices(mock_bot, mock_supabase)

        # Verify fallback was used
        assert mock_db_manager.get_trades_by_status.called, "Should call get_trades_by_status in fallback"
        assert mock_price_service.get_coin_price.called, "Should call get_coin_price in fallback"
        assert mock_db_manager.update_trade_with_original_response.called, "Should update trades in fallback"

        print("  ✅ Price backfill handles import errors gracefully")
        return True

    except Exception as e:
        print(f"❌ Error testing price backfill import error handling: {e}")
        return False

async def test_price_backfill_success():
    """Test that price backfill works when module is available."""
    print("\n🔍 Testing Price Backfill Success Path...")

    try:
        from discord_bot.main import backfill_missing_prices

        # Mock bot and supabase
        mock_bot = Mock()
        mock_supabase = Mock()

        # Mock backfill manager
        mock_backfill_manager = Mock()
        mock_backfill_manager.backfill_from_historical_data = AsyncMock(return_value=True)

        # Test with successful import
        with patch('discord_bot.main.HistoricalTradeBackfillManager', return_value=mock_backfill_manager):
            await backfill_missing_prices(mock_bot, mock_supabase)

        # Verify backfill manager was used
        assert mock_backfill_manager.backfill_from_historical_data.called, "Should call backfill_from_historical_data"

        print("  ✅ Price backfill works when module is available")
        return True

    except Exception as e:
        print(f"❌ Error testing price backfill success path: {e}")
        return False

async def test_price_backfill_fallback_logic():
    """Test the fallback price update logic in detail."""
    print("\n🔍 Testing Price Backfill Fallback Logic...")

    try:
        from discord_bot.main import backfill_missing_prices

        # Mock bot and supabase
        mock_bot = Mock()
        mock_supabase = Mock()

        # Mock database manager with specific trade data
        mock_db_manager = Mock()
        mock_trades = [
            {'id': 1, 'coin_symbol': 'BTC', 'entry_price': 50000, 'binance_entry_price': None},  # Needs update
            {'id': 2, 'coin_symbol': 'ETH', 'entry_price': 3000, 'binance_entry_price': 3100},  # Already has price
            {'id': 3, 'coin_symbol': 'ADA', 'entry_price': 1.5, 'binance_entry_price': None}   # Needs update
        ]
        mock_db_manager.get_trades_by_status = AsyncMock(return_value=mock_trades)
        mock_db_manager.update_trade_with_original_response = AsyncMock(return_value=True)

        # Mock price service
        mock_price_service = Mock()
        mock_price_service.get_coin_price = AsyncMock(side_effect=[51000, 0.8])  # BTC and ADA prices

        mock_bot.db_manager = mock_db_manager
        mock_bot.price_service = mock_price_service

        # Test fallback logic
        with patch('discord_bot.main.HistoricalTradeBackfillManager', side_effect=ImportError("Module not found")):
            await backfill_missing_prices(mock_bot, mock_supabase)

        # Verify correct trades were updated
        assert mock_price_service.get_coin_price.call_count == 2, "Should get prices for BTC and ADA only"
        assert mock_db_manager.update_trade_with_original_response.call_count == 2, "Should update 2 trades"

        # Verify update calls
        update_calls = mock_db_manager.update_trade_with_original_response.call_args_list
        assert update_calls[0][0][0] == 1, "Should update trade ID 1 (BTC)"
        assert update_calls[1][0][0] == 3, "Should update trade ID 3 (ADA)"

        print("  ✅ Price backfill fallback logic works correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing price backfill fallback logic: {e}")
        return False

async def test_price_backfill_error_handling():
    """Test that price backfill handles errors gracefully."""
    print("\n🔍 Testing Price Backfill Error Handling...")

    try:
        from discord_bot.main import backfill_missing_prices

        # Mock bot and supabase
        mock_bot = Mock()
        mock_supabase = Mock()

        # Mock database manager that raises an exception
        mock_db_manager = Mock()
        mock_db_manager.get_trades_by_status = AsyncMock(side_effect=Exception("Database error"))

        mock_bot.db_manager = mock_db_manager

        # Test that function doesn't crash on error
        with patch('discord_bot.main.HistoricalTradeBackfillManager', side_effect=ImportError("Module not found")):
            await backfill_missing_prices(mock_bot, mock_supabase)

        print("  ✅ Price backfill handles errors gracefully")
        return True

    except Exception as e:
        print(f"❌ Error testing price backfill error handling: {e}")
        return False

async def main():
    """Run all price backfill tests."""
    print("🚀 Testing Price Backfill Fallback...")
    print("=" * 60)

    tests = [
        test_price_backfill_import_error,
        test_price_backfill_success,
        test_price_backfill_fallback_logic,
        test_price_backfill_error_handling
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("📊 Price Backfill Test Results:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All price backfill tests passed!")
        return True
    else:
        print("⚠️  Some price backfill tests failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

