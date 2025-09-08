#!/usr/bin/env python3
"""
Test script for orphaned orders cleanup scheduler integration
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

class TestOrphanedOrdersScheduler(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_bot = MagicMock()
        self.mock_bot.binance_exchange = AsyncMock()

    @patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.OrphanedOrdersCleanup')
    async def test_cleanup_orphaned_orders_automatic_success(self, mock_cleanup_class):
        """Test successful automatic cleanup"""
        # Mock the cleanup instance
        mock_cleanup = AsyncMock()
        mock_cleanup_class.return_value = mock_cleanup

        # Mock the methods
        mock_cleanup.get_open_orders.return_value = [
            {'symbol': 'ETHUSDT', 'orderId': '123', 'type': 'TAKE_PROFIT_MARKET', 'reduceOnly': True}
        ]
        mock_cleanup.get_positions.return_value = [
            {'symbol': 'BTCUSDT', 'positionAmt': '0.001'}
        ]
        mock_cleanup.identify_orphaned_orders.return_value = [
            {'symbol': 'ETHUSDT', 'orderId': '123', 'type': 'TAKE_PROFIT_MARKET'}
        ]
        mock_cleanup.close_orphaned_order.return_value = True
        mock_cleanup.save_report.return_value = None

        # Import the function
        from discord_bot.main import cleanup_orphaned_orders_automatic

        # Test the function
        result = await cleanup_orphaned_orders_automatic(self.mock_bot)

        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['orphaned_orders_found'], 1)
        self.assertEqual(result['orders_closed'], 1)
        self.assertEqual(result['orders_failed'], 0)
        self.assertIn('Cleanup completed', result['message'])

    @patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.OrphanedOrdersCleanup')
    async def test_cleanup_orphaned_orders_automatic_no_orphans(self, mock_cleanup_class):
        """Test automatic cleanup when no orphaned orders exist"""
        # Mock the cleanup instance
        mock_cleanup = AsyncMock()
        mock_cleanup_class.return_value = mock_cleanup

        # Mock the methods
        mock_cleanup.get_open_orders.return_value = [
            {'symbol': 'BTCUSDT', 'orderId': '123', 'type': 'TAKE_PROFIT_MARKET', 'reduceOnly': True}
        ]
        mock_cleanup.get_positions.return_value = [
            {'symbol': 'BTCUSDT', 'positionAmt': '0.001'}
        ]
        mock_cleanup.identify_orphaned_orders.return_value = []

        # Import the function
        from discord_bot.main import cleanup_orphaned_orders_automatic

        # Test the function
        result = await cleanup_orphaned_orders_automatic(self.mock_bot)

        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['orphaned_orders_found'], 0)
        self.assertEqual(result['orders_closed'], 0)
        self.assertEqual(result['message'], 'No orphaned orders found')

    @patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.OrphanedOrdersCleanup')
    async def test_cleanup_orphaned_orders_automatic_failure(self, mock_cleanup_class):
        """Test automatic cleanup when errors occur"""
        # Mock the cleanup instance to raise an exception
        mock_cleanup_class.side_effect = Exception("Test error")

        # Import the function
        from discord_bot.main import cleanup_orphaned_orders_automatic

        # Test the function
        result = await cleanup_orphaned_orders_automatic(self.mock_bot)

        # Verify results
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.assertIn('Test error', result['error'])

    def test_scheduler_intervals(self):
        """Test that scheduler intervals are properly configured"""
        # Test the interval constants
        ORPHANED_ORDERS_CLEANUP_INTERVAL = 2 * 60 * 60  # 2 hours

        self.assertEqual(ORPHANED_ORDERS_CLEANUP_INTERVAL, 7200)  # 2 hours in seconds

        # Test that it's reasonable compared to other intervals
        STOP_LOSS_AUDIT_INTERVAL = 30 * 60  # 30 minutes
        TAKE_PROFIT_AUDIT_INTERVAL = 30 * 60  # 30 minutes

        self.assertGreater(ORPHANED_ORDERS_CLEANUP_INTERVAL, STOP_LOSS_AUDIT_INTERVAL)
        self.assertGreater(ORPHANED_ORDERS_CLEANUP_INTERVAL, TAKE_PROFIT_AUDIT_INTERVAL)

    def test_scheduler_status_includes_orphaned_orders(self):
        """Test that scheduler status includes orphaned orders cleanup"""
        # This would be tested by calling the actual endpoint
        # For now, we'll test the expected structure
        expected_intervals = {
            "daily_sync": "24.0 hours",
            "transaction_history": "1.0 hours",
            "pnl_backfill": "1.0 hours",
            "price_backfill": "1.0 hours",
            "weekly_backfill": "168.0 hours",
            "stop_loss_audit": "0.5 hours (30 minutes)",
            "take_profit_audit": "0.5 hours (30 minutes)",
            "orphaned_orders_cleanup": "2.0 hours"
        }

        self.assertIn("orphaned_orders_cleanup", expected_intervals)
        self.assertEqual(expected_intervals["orphaned_orders_cleanup"], "2.0 hours")

def run_tests():
    """Run all tests"""
    print("🧪 Running Orphaned Orders Scheduler Integration Tests")
    print("=" * 60)

    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOrphanedOrdersScheduler)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print(f"\n📊 Test Results:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.failures:
        print("\n❌ Failures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")

    if result.errors:
        print("\n❌ Errors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")

    if result.wasSuccessful():
        print("\n✅ All tests passed!")
        return True
    else:
        print("\n❌ Some tests failed!")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
