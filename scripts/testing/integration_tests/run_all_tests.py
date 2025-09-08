#!/usr/bin/env python3
"""
Master Test Runner

This script runs all the tests to ensure the fixes work correctly
and don't break existing functionality.
"""

import sys
import os
import asyncio
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_test_script(script_name, description):
    """Run a test script and return the result."""
    print(f"\n{'='*80}")
    print(f"🧪 Running {description}")
    print(f"{'='*80}")

    try:
        # Import and run the test
        if script_name == "test_database_methods":
            from scripts.test_database_methods import main as test_main
        elif script_name == "test_price_backfill":
            from scripts.test_price_backfill import main as test_main
        elif script_name == "test_websocket_sync":
            from scripts.test_websocket_sync import main as test_main
        elif script_name == "test_integration":
            from scripts.test_integration import main as test_main
        else:
            print(f"❌ Unknown test script: {script_name}")
            return False

        result = await test_main()
        return result

    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Running All Tests for Critical Fixes")
    print("=" * 80)
    print("This will test that all the fixes work correctly and don't break existing functionality.")
    print("=" * 80)

    # Define all tests to run
    tests = [
        ("test_database_methods", "Database Methods Tests"),
        ("test_price_backfill", "Price Backfill Tests"),
        ("test_websocket_sync", "WebSocket Sync Tests"),
        ("test_integration", "Integration Tests")
    ]

    results = []
    total_tests = len(tests)

    for script_name, description in tests:
        result = await run_test_script(script_name, description)
        results.append((script_name, description, result))

    # Print summary
    print(f"\n{'='*80}")
    print("📊 FINAL TEST RESULTS SUMMARY")
    print(f"{'='*80}")

    passed = 0
    for script_name, description, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {description}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{total_tests} test suites passed")

    if passed == total_tests:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ All critical issues have been resolved")
        print("✅ All fixes work correctly")
        print("✅ No existing functionality has been broken")
        print("\nThe trading bot should now operate without the errors that were appearing in the logs.")
        return True
    else:
        print(f"\n⚠️  {total_tests - passed} test suite(s) failed.")
        print("Some issues may still need attention.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

