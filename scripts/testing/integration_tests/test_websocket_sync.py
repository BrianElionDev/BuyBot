#!/usr/bin/env python3
"""
Test WebSocket Sync

This script tests that the WebSocket sync trade order ID mapping works correctly
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

async def test_websocket_sync_find_trade_by_order_id():
    """Test that WebSocket sync can find trades by order ID."""
    print("🔍 Testing WebSocket Sync Find Trade by Order ID...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync

        # Mock database manager
        mock_db_manager = Mock()
        mock_trade = {
            'id': 1,
            'exchange_order_id': '12345',
            'coin_symbol': 'BTC',
            'status': 'OPEN'
        }
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=mock_trade)
        mock_db_manager.supabase = Mock()

        # Create database sync with mocked manager
        db_sync = DatabaseSync(mock_db_manager)

        # Test finding trade by order ID
        result = await db_sync._find_trade_by_order_id("12345")

        assert result is not None, "Should find trade by order ID"
        assert result['id'] == 1, "Should return correct trade"
        assert "12345" in db_sync.order_id_cache, "Should cache order ID mapping"

        print("  ✅ WebSocket sync finds trades by order ID correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket sync find trade by order ID: {e}")
        return False

async def test_websocket_sync_fallback_search():
    """Test that WebSocket sync uses fallback search when exchange_order_id is missing."""
    print("\n🔍 Testing WebSocket Sync Fallback Search...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync

        # Mock database manager
        mock_db_manager = Mock()
        mock_trade = {
            'id': 2,
            'sync_order_response': '{"orderId": "67890", "status": "FILLED"}',
            'coin_symbol': 'ETH',
            'status': 'OPEN'
        }
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=mock_trade)
        mock_db_manager.supabase = Mock()

        # Create database sync with mocked manager
        db_sync = DatabaseSync(mock_db_manager)

        # Test finding trade by fallback search
        result = await db_sync._find_trade_by_order_id("67890")

        assert result is not None, "Should find trade by fallback search"
        assert result['id'] == 2, "Should return correct trade"
        assert "67890" in db_sync.order_id_cache, "Should cache order ID mapping"

        print("  ✅ WebSocket sync uses fallback search correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket sync fallback search: {e}")
        return False

async def test_websocket_sync_update_order_id():
    """Test that WebSocket sync updates exchange_order_id when found in response fields."""
    print("\n🔍 Testing WebSocket Sync Update Order ID...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync

        # Mock database manager
        mock_db_manager = Mock()
        mock_trade = {
            'id': 3,
            'sync_order_response': '{"orderId": "99999", "status": "FILLED"}',
            'coin_symbol': 'ADA',
            'status': 'OPEN'
        }
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=mock_trade)
        mock_db_manager.supabase = Mock()

        # Create database sync with mocked manager
        db_sync = DatabaseSync(mock_db_manager)

        # Mock the _update_trade_order_id method
        db_sync._update_trade_order_id = AsyncMock()

        # Test finding trade and updating order ID
        result = await db_sync._find_trade_by_order_id("99999")

        assert result is not None, "Should find trade"
        assert db_sync._update_trade_order_id.called, "Should call _update_trade_order_id"

        # Verify the update was called with correct parameters
        update_call = db_sync._update_trade_order_id.call_args
        assert update_call[0][0] == 3, "Should update trade ID 3"
        assert update_call[0][1] == "99999", "Should update with order ID 99999"

        print("  ✅ WebSocket sync updates order ID correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket sync update order ID: {e}")
        return False

async def test_websocket_sync_handle_execution_report():
    """Test that WebSocket sync handles execution reports correctly."""
    print("\n🔍 Testing WebSocket Sync Handle Execution Report...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync

        # Mock database manager
        mock_db_manager = Mock()
        mock_trade = {
            'id': 4,
            'exchange_order_id': '11111',
            'coin_symbol': 'SOL',
            'status': 'OPEN'
        }
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=mock_trade)
        mock_db_manager.supabase = Mock()

        # Create database sync with mocked manager
        db_sync = DatabaseSync(mock_db_manager)

        # Mock the _update_trade_status method
        db_sync._update_trade_status = AsyncMock()

        # Test execution report data
        execution_data = {
            'i': '11111',  # order ID
            's': 'SOLUSDT',  # symbol
            'X': 'FILLED',  # status
            'z': '10.5',  # executed quantity
            'ap': '150.25',  # average price
            'Y': '25.50'  # realized PnL
        }

        # Test handling execution report
        result = await db_sync.handle_execution_report(execution_data)

        assert result is not None, "Should return sync data"
        assert result.trade_id == "4", "Should return correct trade ID"
        assert result.order_id == "11111", "Should return correct order ID"
        assert result.symbol == "SOLUSDT", "Should return correct symbol"
        assert result.status == "FILLED", "Should return correct status"

        # Verify trade status was updated
        assert db_sync._update_trade_status.called, "Should call _update_trade_status"

        print("  ✅ WebSocket sync handles execution reports correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket sync handle execution report: {e}")
        return False

async def test_websocket_sync_trade_not_found():
    """Test that WebSocket sync handles trade not found gracefully."""
    print("\n🔍 Testing WebSocket Sync Trade Not Found...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.find_trade_by_order_id = AsyncMock(return_value=None)
        mock_db_manager.supabase = Mock()

        # Create database sync with mocked manager
        db_sync = DatabaseSync(mock_db_manager)

        # Test execution report data for non-existent trade
        execution_data = {
            'i': '99999',  # order ID
            's': 'UNKNOWNUSDT',  # symbol
            'X': 'FILLED',  # status
            'z': '1.0',  # executed quantity
            'ap': '100.0',  # average price
            'Y': '0.0'  # realized PnL
        }

        # Test handling execution report for non-existent trade
        result = await db_sync.handle_execution_report(execution_data)

        assert result is None, "Should return None when trade not found"

        print("  ✅ WebSocket sync handles trade not found gracefully")
        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket sync trade not found: {e}")
        return False

async def main():
    """Run all WebSocket sync tests."""
    print("🚀 Testing WebSocket Sync...")
    print("=" * 60)

    tests = [
        test_websocket_sync_find_trade_by_order_id,
        test_websocket_sync_fallback_search,
        test_websocket_sync_update_order_id,
        test_websocket_sync_handle_execution_report,
        test_websocket_sync_trade_not_found
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
    print("📊 WebSocket Sync Test Results:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All WebSocket sync tests passed!")
        return True
    else:
        print("⚠️  Some WebSocket sync tests failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

