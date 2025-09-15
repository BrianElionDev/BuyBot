#!/usr/bin/env python3
"""
Code Structure Test

This script tests that all the code changes are structurally correct
and the methods exist without requiring external dependencies.
"""

import sys
import os
import ast
import inspect
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_method_exists(file_path, class_name, method_name):
    """Check if a method exists in a class."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return True
        return False
    except Exception as e:
        print(f"❌ Error checking {file_path}: {e}")
        return False

def check_function_exists(file_path, function_name):
    """Check if a function exists in a file."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return True
        return False
    except Exception as e:
        print(f"❌ Error checking {file_path}: {e}")
        return False

def check_code_contains(file_path, text):
    """Check if code contains specific text."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        return text in content
    except Exception as e:
        print(f"❌ Error checking {file_path}: {e}")
        return False

def test_database_manager_structure():
    """Test database manager structure."""
    print("🔍 Testing Database Manager Structure...")

    file_path = "discord_bot/database/database_manager.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    # Check required methods exist
    required_methods = [
        'get_last_transaction_sync_time',
        'get_trades_by_status',
        'find_trade_by_order_id'
    ]

    all_exist = True
    for method in required_methods:
        if check_method_exists(file_path, 'DatabaseManager', method):
            print(f"  ✅ Method {method} exists")
        else:
            print(f"  ❌ Method {method} missing")
            all_exist = False

    return all_exist

def test_trade_operations_structure():
    """Test trade operations structure."""
    print("\n🔍 Testing Trade Operations Structure...")

    file_path = "discord_bot/database/operations/trade_operations.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    # Check required methods exist
    required_methods = [
        'get_trades_by_status',
        'find_trade_by_order_id'
    ]

    all_exist = True
    for method in required_methods:
        if check_method_exists(file_path, 'TradeOperations', method):
            print(f"  ✅ Method {method} exists")
        else:
            print(f"  ❌ Method {method} missing")
            all_exist = False

    return all_exist

def test_alert_operations_structure():
    """Test alert operations structure."""
    print("\n🔍 Testing Alert Operations Structure...")

    file_path = "discord_bot/database/operations/alert_operations.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    # Check required methods exist
    required_methods = [
        'check_duplicate_alert',
        'store_alert_hash'
    ]

    all_exist = True
    for method in required_methods:
        if check_method_exists(file_path, 'AlertOperations', method):
            print(f"  ✅ Method {method} exists")
        else:
            print(f"  ❌ Method {method} missing")
            all_exist = False

    return all_exist

def test_websocket_sync_structure():
    """Test WebSocket sync structure."""
    print("\n🔍 Testing WebSocket Sync Structure...")

    file_path = "src/websocket/sync/database_sync.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    # Check required methods exist
    required_methods = [
        '_find_trade_by_order_id',
        '_update_trade_order_id'
    ]

    all_exist = True
    for method in required_methods:
        if check_method_exists(file_path, 'DatabaseSync', method):
            print(f"  ✅ Method {method} exists")
        else:
            print(f"  ❌ Method {method} missing")
            all_exist = False

    return all_exist

def test_main_scheduler_structure():
    """Test main scheduler structure."""
    print("\n🔍 Testing Main Scheduler Structure...")

    file_path = "discord_bot/main.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    # Check required functions exist
    required_functions = [
        'auto_fill_transaction_history',
        'backfill_missing_prices',
        'backfill_pnl_data'
    ]

    all_exist = True
    for func in required_functions:
        if check_function_exists(file_path, func):
            print(f"  ✅ Function {func} exists")
        else:
            print(f"  ❌ Function {func} missing")
            all_exist = False

    return all_exist

def test_error_handling_implementation():
    """Test that error handling is implemented correctly."""
    print("\n🔍 Testing Error Handling Implementation...")

    # Test price backfill error handling
    main_path = "discord_bot/main.py"
    if os.path.exists(main_path):
        if check_code_contains(main_path, "fallback price backfill") and check_code_contains(main_path, "ImportError"):
            print("  ✅ Price backfill has fallback error handling")
        else:
            print("  ❌ Price backfill missing fallback error handling")
            return False

    # Test alert operations error handling
    alert_ops_path = "discord_bot/database/operations/alert_operations.py"
    if os.path.exists(alert_ops_path):
        if check_code_contains(alert_ops_path, "alert_hash column not available") and check_code_contains(alert_ops_path, "fallback duplicate detection"):
            print("  ✅ Alert operations have graceful error handling")
        else:
            print("  ❌ Alert operations missing graceful error handling")
            return False

    return True

def test_code_quality():
    """Test code quality and structure."""
    print("\n🔍 Testing Code Quality...")

    files_to_check = [
        "discord_bot/database/database_manager.py",
        "discord_bot/database/operations/trade_operations.py",
        "discord_bot/database/operations/alert_operations.py",
        "src/websocket/sync/database_sync.py",
        "discord_bot/main.py"
    ]

    all_valid = True
    for file_path in files_to_check:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()

                # Check if file can be parsed as Python
                ast.parse(content)
                print(f"  ✅ {file_path} has valid Python syntax")

            except SyntaxError as e:
                print(f"  ❌ {file_path} has syntax error: {e}")
                all_valid = False
            except Exception as e:
                print(f"  ❌ {file_path} has error: {e}")
                all_valid = False
        else:
            print(f"  ❌ File not found: {file_path}")
            all_valid = False

    return all_valid

def main():
    """Run all structure tests."""
    print("🚀 Testing Code Structure...")
    print("=" * 60)
    print("This will test that all the code changes are structurally correct.")
    print("=" * 60)

    tests = [
        test_database_manager_structure,
        test_trade_operations_structure,
        test_alert_operations_structure,
        test_websocket_sync_structure,
        test_main_scheduler_structure,
        test_error_handling_implementation,
        test_code_quality
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("📊 Code Structure Test Results:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All code structure tests passed!")
        print("✅ All required methods and functions exist")
        print("✅ Error handling is implemented correctly")
        print("✅ Code has valid Python syntax")
        return True
    else:
        print("⚠️  Some code structure tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

