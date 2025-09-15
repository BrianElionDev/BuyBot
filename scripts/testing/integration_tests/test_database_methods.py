#!/usr/bin/env python3
"""
Test Database Methods

This script tests that all the database methods we added work correctly
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

async def test_database_manager_methods():
    """Test that all database manager methods work correctly."""
    print("🔍 Testing Database Manager Methods...")

    try:
        from discord_bot.database.database_manager import DatabaseManager

        # Mock Supabase client
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = [{'time': 1640995200000}]  # Mock timestamp
        mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_response

        # Create database manager with mocked client
        db_manager = DatabaseManager(mock_supabase)

        # Test get_last_transaction_sync_time
        print("  Testing get_last_transaction_sync_time...")
        sync_time = await db_manager.get_last_transaction_sync_time()
        assert isinstance(sync_time, int), "get_last_transaction_sync_time should return int"
        assert sync_time > 0, "Sync time should be positive"
        print("  ✅ get_last_transaction_sync_time works correctly")

        # Test get_trades_by_status
        print("  Testing get_trades_by_status...")
        mock_trades_response = Mock()
        mock_trades_response.data = [
            {'id': 1, 'status': 'OPEN', 'coin_symbol': 'BTC'},
            {'id': 2, 'status': 'OPEN', 'coin_symbol': 'ETH'}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_trades_response

        trades = await db_manager.get_trades_by_status("OPEN", limit=10)
        assert isinstance(trades, list), "get_trades_by_status should return list"
        print("  ✅ get_trades_by_status works correctly")

        # Test find_trade_by_order_id
        print("  Testing find_trade_by_order_id...")
        mock_trade_response = Mock()
        mock_trade_response.data = [{'id': 1, 'exchange_order_id': '12345', 'coin_symbol': 'BTC'}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_trade_response

        trade = await db_manager.find_trade_by_order_id("12345")
        assert trade is not None, "find_trade_by_order_id should find trade"
        print("  ✅ find_trade_by_order_id works correctly")

        print("✅ All database manager methods work correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing database manager methods: {e}")
        return False

async def test_trade_operations_methods():
    """Test that all trade operations methods work correctly."""
    print("\n🔍 Testing Trade Operations Methods...")

    try:
        from discord_bot.database.operations.trade_operations import TradeOperations

        # Mock Supabase client
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = [
            {'id': 1, 'status': 'OPEN', 'coin_symbol': 'BTC'},
            {'id': 2, 'status': 'CLOSED', 'coin_symbol': 'ETH'}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_response

        # Create trade operations with mocked client
        trade_ops = TradeOperations(mock_supabase)

        # Test get_trades_by_status
        print("  Testing get_trades_by_status...")
        trades = await trade_ops.get_trades_by_status("OPEN", limit=10)
        assert isinstance(trades, list), "get_trades_by_status should return list"
        assert len(trades) == 2, "Should return correct number of trades"
        print("  ✅ get_trades_by_status works correctly")

        # Test find_trade_by_order_id with exchange_order_id
        print("  Testing find_trade_by_order_id with exchange_order_id...")
        mock_trade_response = Mock()
        mock_trade_response.data = [{'id': 1, 'exchange_order_id': '12345', 'coin_symbol': 'BTC'}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_trade_response

        trade = await trade_ops.find_trade_by_order_id("12345")
        assert trade is not None, "Should find trade by exchange_order_id"
        print("  ✅ find_trade_by_order_id with exchange_order_id works correctly")

        # Test find_trade_by_order_id with fallback search
        print("  Testing find_trade_by_order_id with fallback search...")
        mock_fallback_response = Mock()
        mock_fallback_response.data = [
            {'id': 1, 'sync_order_response': '{"orderId": "67890"}', 'coin_symbol': 'BTC'},
            {'id': 2, 'binance_response': '{"orderId": "67890"}', 'coin_symbol': 'ETH'}
        ]
        mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_fallback_response

        trade = await trade_ops.find_trade_by_order_id("67890")
        assert trade is not None, "Should find trade by fallback search"
        print("  ✅ find_trade_by_order_id with fallback search works correctly")

        print("✅ All trade operations methods work correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing trade operations methods: {e}")
        return False

async def test_alert_operations_methods():
    """Test that alert operations handle missing columns gracefully."""
    print("\n🔍 Testing Alert Operations Methods...")

    try:
        from discord_bot.database.operations.alert_operations import AlertOperations

        # Mock Supabase client
        mock_supabase = Mock()

        # Create alert operations with mocked client
        alert_ops = AlertOperations(mock_supabase)

        # Test check_duplicate_alert with missing column
        print("  Testing check_duplicate_alert with missing column...")
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("column alerts.alert_hash does not exist")

        result = await alert_ops.check_duplicate_alert("test_hash")
        assert result is False, "Should return False when column is missing"
        print("  ✅ check_duplicate_alert handles missing column gracefully")

        # Test check_duplicate_alert with existing column
        print("  Testing check_duplicate_alert with existing column...")
        mock_response = Mock()
        mock_response.data = []  # No duplicates found
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = await alert_ops.check_duplicate_alert("test_hash")
        assert result is False, "Should return False when no duplicates found"
        print("  ✅ check_duplicate_alert works with existing column")

        # Test store_alert_hash
        print("  Testing store_alert_hash...")
        mock_insert_response = Mock()
        mock_insert_response.data = [{'id': 1, 'alert_hash': 'test_hash'}]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_insert_response

        result = await alert_ops.store_alert_hash("test_hash")
        assert result is True, "Should successfully store alert hash"
        print("  ✅ store_alert_hash works correctly")

        print("✅ All alert operations methods work correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing alert operations methods: {e}")
        return False

async def main():
    """Run all database method tests."""
    print("🚀 Testing Database Methods...")
    print("=" * 60)

    tests = [
        test_database_manager_methods,
        test_trade_operations_methods,
        test_alert_operations_methods
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
    print("📊 Database Methods Test Results:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All database methods work correctly!")
        return True
    else:
        print("⚠️  Some database methods need attention.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

