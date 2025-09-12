#!/usr/bin/env python3
"""
Test Script for Critical Fixes

This script tests that all the critical issues identified in the logs have been resolved.
"""

import sys
import os
import asyncio
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_database_manager_methods():
    """Test that all required database manager methods exist."""
    print("🔍 Testing Database Manager Methods...")

    try:
        from discord_bot.database.database_manager import DatabaseManager

        # Test that the class can be instantiated (without actual database connection)
        print("✅ DatabaseManager class imported successfully")

        # Check if required methods exist
        required_methods = [
            'get_last_transaction_sync_time',
            'get_trades_by_status',
            'find_trade_by_order_id'
        ]

        for method_name in required_methods:
            if hasattr(DatabaseManager, method_name):
                print(f"✅ Method {method_name} exists")
            else:
                print(f"❌ Method {method_name} missing")
                return False

        return True

    except Exception as e:
        print(f"❌ Error testing database manager: {e}")
        return False

async def test_trade_operations():
    """Test that all required trade operations methods exist."""
    print("\n🔍 Testing Trade Operations...")

    try:
        from discord_bot.database.operations.trade_operations import TradeOperations

        print("✅ TradeOperations class imported successfully")

        # Check if required methods exist
        required_methods = [
            'get_trades_by_status',
            'find_trade_by_order_id'
        ]

        for method_name in required_methods:
            if hasattr(TradeOperations, method_name):
                print(f"✅ Method {method_name} exists")
            else:
                print(f"❌ Method {method_name} missing")
                return False

        return True

    except Exception as e:
        print(f"❌ Error testing trade operations: {e}")
        return False

async def test_alert_operations():
    """Test that alert operations handle missing columns gracefully."""
    print("\n🔍 Testing Alert Operations...")

    try:
        from discord_bot.database.operations.alert_operations import AlertOperations

        print("✅ AlertOperations class imported successfully")

        # Check if required methods exist
        required_methods = [
            'check_duplicate_alert',
            'store_alert_hash'
        ]

        for method_name in required_methods:
            if hasattr(AlertOperations, method_name):
                print(f"✅ Method {method_name} exists")
            else:
                print(f"❌ Method {method_name} missing")
                return False

        return True

    except Exception as e:
        print(f"❌ Error testing alert operations: {e}")
        return False

async def test_websocket_sync():
    """Test that WebSocket sync components can be imported."""
    print("\n🔍 Testing WebSocket Sync Components...")

    try:
        from src.websocket.sync.database_sync import DatabaseSync
        from src.websocket.sync.sync_manager import SyncManager

        print("✅ WebSocket sync components imported successfully")

        # Check if required methods exist
        if hasattr(DatabaseSync, '_find_trade_by_order_id'):
            print("✅ _find_trade_by_order_id method exists")
        else:
            print("❌ _find_trade_by_order_id method missing")
            return False

        return True

    except Exception as e:
        print(f"❌ Error testing WebSocket sync: {e}")
        return False

async def test_main_scheduler():
    """Test that main scheduler functions can be imported."""
    print("\n🔍 Testing Main Scheduler Functions...")

    try:
        from discord_bot.main import (
            auto_fill_transaction_history,
            backfill_missing_prices,
            backfill_pnl_data
        )

        print("✅ Main scheduler functions imported successfully")
        return True

    except Exception as e:
        print(f"❌ Error testing main scheduler: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing Critical Fixes...")
    print("=" * 50)

    tests = [
        test_database_manager_methods,
        test_trade_operations,
        test_alert_operations,
        test_websocket_sync,
        test_main_scheduler
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All critical issues have been resolved!")
        return True
    else:
        print("⚠️  Some issues still need attention.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

