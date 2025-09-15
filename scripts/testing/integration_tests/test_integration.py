#!/usr/bin/env python3
"""
Integration Test

This script tests that all the fixes work together correctly
and don't break existing functionality.
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

async def test_scheduler_integration():
    """Test that the scheduler functions work together correctly."""
    print("🔍 Testing Scheduler Integration...")

    try:
        from discord_bot.main import (
            auto_fill_transaction_history,
            backfill_missing_prices,
            backfill_pnl_data
        )

        # Mock bot and supabase
        mock_bot = Mock()
        mock_supabase = Mock()

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.get_last_transaction_sync_time = AsyncMock(return_value=1640995200000)
        mock_db_manager.get_trades_by_status = AsyncMock(return_value=[])
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=None)

        # Mock price service
        mock_price_service = Mock()
        mock_price_service.get_coin_price = AsyncMock(return_value=50000)

        mock_bot.db_manager = mock_db_manager
        mock_bot.price_service = mock_price_service

        # Test auto_fill_transaction_history
        print("  Testing auto_fill_transaction_history...")
        with patch('discord_bot.main.TransactionHistoryFiller') as mock_filler_class:
            mock_filler = Mock()
            mock_filler.fill_transaction_history_manual = AsyncMock(return_value={'success': True, 'inserted': 5})
            mock_filler_class.return_value = mock_filler

            await auto_fill_transaction_history(mock_bot, mock_supabase)

            assert mock_filler.fill_transaction_history_manual.called, "Should call fill_transaction_history_manual"

        # Test backfill_missing_prices with fallback
        print("  Testing backfill_missing_prices with fallback...")
        with patch('discord_bot.main.HistoricalTradeBackfillManager', side_effect=ImportError("Module not found")):
            await backfill_missing_prices(mock_bot, mock_supabase)

            assert mock_db_manager.get_trades_by_status.called, "Should call get_trades_by_status in fallback"

        # Test backfill_pnl_data
        print("  Testing backfill_pnl_data...")
        with patch('discord_bot.main.backfill_trades_from_binance_history') as mock_backfill:
            mock_backfill.return_value = AsyncMock()

            await backfill_pnl_data(mock_bot, mock_supabase)

            assert mock_backfill.called, "Should call backfill_trades_from_binance_history"

        print("  ✅ Scheduler integration works correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing scheduler integration: {e}")
        return False

async def test_database_operations_integration():
    """Test that all database operations work together correctly."""
    print("\n🔍 Testing Database Operations Integration...")

    try:
        from discord_bot.database.database_manager import DatabaseManager
        from discord_bot.database.operations.trade_operations import TradeOperations
        from discord_bot.database.operations.alert_operations import AlertOperations

        # Mock Supabase client
        mock_supabase = Mock()

        # Mock responses
        mock_trade_response = Mock()
        mock_trade_response.data = [{'id': 1, 'status': 'OPEN', 'coin_symbol': 'BTC'}]

        mock_alert_response = Mock()
        mock_alert_response.data = []

        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_trade_response
        mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_trade_response
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_alert_response

        # Test database manager
        print("  Testing database manager...")
        db_manager = DatabaseManager(mock_supabase)

        # Test trade operations
        print("  Testing trade operations...")
        trade_ops = TradeOperations(mock_supabase)

        trades = await trade_ops.get_trades_by_status("OPEN", limit=10)
        assert isinstance(trades, list), "Should return list of trades"

        trade = await trade_ops.find_trade_by_order_id("12345")
        assert trade is not None, "Should find trade by order ID"

        # Test alert operations
        print("  Testing alert operations...")
        alert_ops = AlertOperations(mock_supabase)

        # Test with missing column
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("column alerts.alert_hash does not exist")

        result = await alert_ops.check_duplicate_alert("test_hash")
        assert result is False, "Should handle missing column gracefully"

        # Test database manager methods
        print("  Testing database manager methods...")
        sync_time = await db_manager.get_last_transaction_sync_time()
        assert isinstance(sync_time, int), "Should return sync time"

        trades = await db_manager.get_trades_by_status("OPEN", limit=10)
        assert isinstance(trades, list), "Should return list of trades"

        trade = await db_manager.find_trade_by_order_id("12345")
        assert trade is not None, "Should find trade by order ID"

        print("  ✅ Database operations integration works correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing database operations integration: {e}")
        return False

async def test_websocket_database_integration():
    """Test that WebSocket sync integrates with database operations correctly."""
    print("\n🔍 Testing WebSocket Database Integration...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync
        from discord_bot.database.database_manager import DatabaseManager

        # Mock Supabase client
        mock_supabase = Mock()

        # Mock database manager
        mock_db_manager = Mock()
        mock_trade = {
            'id': 1,
            'exchange_order_id': '12345',
            'coin_symbol': 'BTC',
            'status': 'OPEN'
        }
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=mock_trade)
        mock_db_manager.supabase = mock_supabase

        # Create database sync
        db_sync = DatabaseSync(mock_db_manager)

        # Test execution report handling
        print("  Testing execution report handling...")
        execution_data = {
            'i': '12345',  # order ID
            's': 'BTCUSDT',  # symbol
            'X': 'FILLED',  # status
            'z': '0.1',  # executed quantity
            'ap': '50000',  # average price
            'Y': '50.0'  # realized PnL
        }

        # Mock the _update_trade_status method
        db_sync._update_trade_status = AsyncMock()

        result = await db_sync.handle_execution_report(execution_data)

        assert result is not None, "Should return sync data"
        assert result.trade_id == "1", "Should return correct trade ID"
        assert result.order_id == "12345", "Should return correct order ID"

        # Verify trade status was updated
        assert db_sync._update_trade_status.called, "Should call _update_trade_status"

        print("  ✅ WebSocket database integration works correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket database integration: {e}")
        return False

async def test_error_handling_integration():
    """Test that error handling works correctly across all components."""
    print("\n🔍 Testing Error Handling Integration...")

    try:
        from discord_bot.main import backfill_missing_prices
        from discord_bot.database.operations.alert_operations import AlertOperations

        # Mock bot and supabase
        mock_bot = Mock()
        mock_supabase = Mock()

        # Test price backfill error handling
        print("  Testing price backfill error handling...")
        mock_db_manager = Mock()
        mock_db_manager.get_trades_by_status = AsyncMock(side_effect=Exception("Database error"))

        mock_bot.db_manager = mock_db_manager

        # Should not crash on error
        with patch('discord_bot.main.HistoricalTradeBackfillManager', side_effect=ImportError("Module not found")):
            await backfill_missing_prices(mock_bot, mock_supabase)

        # Test alert operations error handling
        print("  Testing alert operations error handling...")
        mock_supabase = Mock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("Database error")

        alert_ops = AlertOperations(mock_supabase)

        result = await alert_ops.check_duplicate_alert("test_hash")
        assert result is False, "Should handle database errors gracefully"

        print("  ✅ Error handling integration works correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing error handling integration: {e}")
        return False

async def main():
    """Run all integration tests."""
    print("🚀 Testing Integration...")
    print("=" * 60)

    tests = [
        test_scheduler_integration,
        test_database_operations_integration,
        test_websocket_database_integration,
        test_error_handling_integration
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
    print("📊 Integration Test Results:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All integration tests passed!")
        return True
    else:
        print("⚠️  Some integration tests failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

