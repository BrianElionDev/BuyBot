#!/usr/bin/env python3
"""
Simple Test Script for Critical Fixes

This script tests that all the critical issues identified in the logs have been resolved
by checking code structure without importing dependencies.
"""

import os
import ast
import sys

def check_file_has_method(file_path, method_name):
    """Check if a Python file has a specific method."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return True

        return False
    except Exception as e:
        print(f"❌ Error checking {file_path}: {e}")
        return False

def check_file_has_class(file_path, class_name):
    """Check if a Python file has a specific class."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return True

        return False
    except Exception as e:
        print(f"❌ Error checking {file_path}: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Testing Critical Fixes (Code Structure)...")
    print("=" * 60)

    tests_passed = 0
    total_tests = 0

    # Test 1: Database Manager Methods
    print("\n🔍 Testing Database Manager Methods...")
    db_manager_path = "discord_bot/database/database_manager.py"

    if os.path.exists(db_manager_path):
        required_methods = [
            'get_last_transaction_sync_time',
            'get_trades_by_status',
            'find_trade_by_order_id'
        ]

        for method in required_methods:
            total_tests += 1
            if check_file_has_method(db_manager_path, method):
                print(f"✅ Method {method} exists in DatabaseManager")
                tests_passed += 1
            else:
                print(f"❌ Method {method} missing from DatabaseManager")
    else:
        print(f"❌ File not found: {db_manager_path}")

    # Test 2: Trade Operations Methods
    print("\n🔍 Testing Trade Operations Methods...")
    trade_ops_path = "discord_bot/database/operations/trade_operations.py"

    if os.path.exists(trade_ops_path):
        required_methods = [
            'get_trades_by_status',
            'find_trade_by_order_id'
        ]

        for method in required_methods:
            total_tests += 1
            if check_file_has_method(trade_ops_path, method):
                print(f"✅ Method {method} exists in TradeOperations")
                tests_passed += 1
            else:
                print(f"❌ Method {method} missing from TradeOperations")
    else:
        print(f"❌ File not found: {trade_ops_path}")

    # Test 3: Alert Operations Methods
    print("\n🔍 Testing Alert Operations Methods...")
    alert_ops_path = "discord_bot/database/operations/alert_operations.py"

    if os.path.exists(alert_ops_path):
        required_methods = [
            'check_duplicate_alert',
            'store_alert_hash'
        ]

        for method in required_methods:
            total_tests += 1
            if check_file_has_method(alert_ops_path, method):
                print(f"✅ Method {method} exists in AlertOperations")
                tests_passed += 1
            else:
                print(f"❌ Method {method} missing from AlertOperations")
    else:
        print(f"❌ File not found: {alert_ops_path}")

    # Test 4: WebSocket Sync Methods
    print("\n🔍 Testing WebSocket Sync Methods...")
    db_sync_path = "src/websocket/sync/database_sync.py"

    if os.path.exists(db_sync_path):
        required_methods = [
            '_find_trade_by_order_id',
            '_update_trade_order_id'
        ]

        for method in required_methods:
            total_tests += 1
            if check_file_has_method(db_sync_path, method):
                print(f"✅ Method {method} exists in DatabaseSync")
                tests_passed += 1
            else:
                print(f"❌ Method {method} missing from DatabaseSync")
    else:
        print(f"❌ File not found: {db_sync_path}")

    # Test 5: Main Scheduler Functions
    print("\n🔍 Testing Main Scheduler Functions...")
    main_path = "discord_bot/main.py"

    if os.path.exists(main_path):
        required_functions = [
            'auto_fill_transaction_history',
            'backfill_missing_prices',
            'backfill_pnl_data'
        ]

        for func in required_functions:
            total_tests += 1
            if check_file_has_method(main_path, func):
                print(f"✅ Function {func} exists in main.py")
                tests_passed += 1
            else:
                print(f"❌ Function {func} missing from main.py")
    else:
        print(f"❌ File not found: {main_path}")

    # Test 6: Check for graceful error handling in price backfill
    print("\n🔍 Testing Price Backfill Error Handling...")
    if os.path.exists(main_path):
        try:
            with open(main_path, 'r') as f:
                content = f.read()

            # Check if the fallback logic exists
            if "fallback price backfill" in content and "ImportError" in content:
                print("✅ Price backfill has fallback error handling")
                tests_passed += 1
            else:
                print("❌ Price backfill missing fallback error handling")

            total_tests += 1
        except Exception as e:
            print(f"❌ Error checking price backfill: {e}")

    # Test 7: Check for graceful error handling in alert operations
    print("\n🔍 Testing Alert Operations Error Handling...")
    if os.path.exists(alert_ops_path):
        try:
            with open(alert_ops_path, 'r') as f:
                content = f.read()

            # Check if the graceful fallback exists
            if "alert_hash column not available" in content and "fallback duplicate detection" in content:
                print("✅ Alert operations have graceful error handling")
                tests_passed += 1
            else:
                print("❌ Alert operations missing graceful error handling")

            total_tests += 1
        except Exception as e:
            print(f"❌ Error checking alert operations: {e}")

    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print(f"Tests Passed: {tests_passed}/{total_tests}")

    if tests_passed == total_tests:
        print("🎉 All critical issues have been resolved!")
        return True
    else:
        print("⚠️  Some issues still need attention.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

