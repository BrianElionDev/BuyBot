#!/usr/bin/env python3
"""
Test script for orphaned orders cleanup functionality
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

from scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders import OrphanedOrdersCleanup

class TestOrphanedOrdersCleanup(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.cleanup = OrphanedOrdersCleanup()

        # Mock sample data
        self.sample_orders = [
            {
                'symbol': 'BTCUSDT',
                'orderId': '12345',
                'type': 'STOP_MARKET',
                'side': 'SELL',
                'origQty': '0.001',
                'price': '0',
                'stopPrice': '50000',
                'reduceOnly': True,
                'clientOrderId': 'test_client_1'
            },
            {
                'symbol': 'ETHUSDT',
                'orderId': '12346',
                'type': 'TAKE_PROFIT_MARKET',
                'side': 'SELL',
                'origQty': '0.1',
                'price': '0',
                'stopPrice': '4000',
                'reduceOnly': True,
                'clientOrderId': 'test_client_2'
            },
            {
                'symbol': 'ADAUSDT',
                'orderId': '12347',
                'type': 'LIMIT',
                'side': 'BUY',
                'origQty': '100',
                'price': '0.5',
                'stopPrice': None,
                'reduceOnly': False,
                'clientOrderId': 'test_client_3'
            }
        ]

        self.sample_positions = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.001',
                'entryPrice': '45000',
                'markPrice': '46000',
                'unRealizedProfit': '1.0'
            }
            # Note: ETHUSDT and ADAUSDT have no positions
        ]

    def test_identify_orphaned_orders(self):
        """Test identification of orphaned orders"""
        orphaned = self.cleanup.identify_orphaned_orders(self.sample_orders, self.sample_positions)

        # Should find ETHUSDT order as orphaned (SL/TP without position)
        # Should NOT find BTCUSDT order (has position)
        # Should NOT find ADAUSDT order (not SL/TP)

        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0]['symbol'], 'ETHUSDT')
        self.assertEqual(orphaned[0]['orderId'], '12346')

    def test_identify_orphaned_orders_no_orphans(self):
        """Test when no orphaned orders exist"""
        # All orders have positions
        positions_with_all = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.001',
                'entryPrice': '45000',
                'markPrice': '46000',
                'unRealizedProfit': '1.0'
            },
            {
                'symbol': 'ETHUSDT',
                'positionAmt': '0.1',
                'entryPrice': '3500',
                'markPrice': '3600',
                'unRealizedProfit': '10.0'
            }
        ]

        orphaned = self.cleanup.identify_orphaned_orders(self.sample_orders, positions_with_all)
        self.assertEqual(len(orphaned), 0)

    def test_identify_orphaned_orders_no_positions(self):
        """Test when no positions exist (all SL/TP orders are orphaned)"""
        orphaned = self.cleanup.identify_orphaned_orders(self.sample_orders, [])

        # Should find both SL/TP orders as orphaned
        self.assertEqual(len(orphaned), 2)
        symbols = [order['symbol'] for order in orphaned]
        self.assertIn('BTCUSDT', symbols)
        self.assertIn('ETHUSDT', symbols)

    def test_order_type_classification(self):
        """Test proper classification of SL/TP orders"""
        # Test different order types
        test_orders = [
            {'symbol': 'TEST1', 'type': 'STOP_MARKET', 'reduceOnly': False, 'stopPrice': '100'},
            {'symbol': 'TEST2', 'type': 'STOP', 'reduceOnly': False, 'stopPrice': '100'},
            {'symbol': 'TEST3', 'type': 'TAKE_PROFIT_MARKET', 'reduceOnly': False, 'stopPrice': '100'},
            {'symbol': 'TEST4', 'type': 'TAKE_PROFIT', 'reduceOnly': False, 'stopPrice': '100'},
            {'symbol': 'TEST5', 'type': 'LIMIT', 'reduceOnly': True, 'stopPrice': None},
            {'symbol': 'TEST6', 'type': 'MARKET', 'reduceOnly': False, 'stopPrice': None},
        ]

        # No positions, so all SL/TP orders should be orphaned
        orphaned = self.cleanup.identify_orphaned_orders(test_orders, [])

        # Should identify 5 orphaned orders (all except TEST6)
        self.assertEqual(len(orphaned), 5)
        symbols = [order['symbol'] for order in orphaned]
        self.assertIn('TEST1', symbols)
        self.assertIn('TEST2', symbols)
        self.assertIn('TEST3', symbols)
        self.assertIn('TEST4', symbols)
        self.assertIn('TEST5', symbols)
        self.assertNotIn('TEST6', symbols)

    @patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BinanceExchange')
    async def test_initialize_success(self, mock_exchange_class):
        """Test successful initialization"""
        mock_exchange = AsyncMock()
        mock_exchange._init_client = AsyncMock()
        mock_exchange_class.return_value = mock_exchange

        with patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BINANCE_API_KEY', 'test_key'), \
             patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BINANCE_API_SECRET', 'test_secret'), \
             patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BINANCE_TESTNET', True):

            result = await self.cleanup.initialize()
            self.assertTrue(result)
            self.assertIsNotNone(self.cleanup.binance_exchange)

    @patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BinanceExchange')
    async def test_initialize_missing_credentials(self, mock_exchange_class):
        """Test initialization with missing credentials"""
        with patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BINANCE_API_KEY', None), \
             patch('scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders.BINANCE_API_SECRET', None):

            result = await self.cleanup.initialize()
            self.assertFalse(result)
            self.assertIsNone(self.cleanup.binance_exchange)

    async def test_close_orphaned_order_success(self):
        """Test successful order closure"""
        # Mock the binance exchange
        self.cleanup.binance_exchange = AsyncMock()
        self.cleanup.binance_exchange.cancel_order = AsyncMock(return_value=True)

        order = {
            'symbol': 'ETHUSDT',
            'orderId': '12346',
            'type': 'TAKE_PROFIT_MARKET',
            'side': 'SELL',
            'origQty': '0.1',
            'price': '0',
            'stopPrice': '4000'
        }

        result = await self.cleanup.close_orphaned_order(order)

        self.assertTrue(result)
        self.assertEqual(len(self.cleanup.closed_orders), 1)
        self.assertEqual(self.cleanup.closed_orders[0]['symbol'], 'ETHUSDT')
        self.assertEqual(self.cleanup.closed_orders[0]['orderId'], '12346')

    async def test_close_orphaned_order_failure(self):
        """Test failed order closure"""
        # Mock the binance exchange to return failure
        self.cleanup.binance_exchange = AsyncMock()
        self.cleanup.binance_exchange.cancel_order = AsyncMock(return_value=False)

        order = {
            'symbol': 'ETHUSDT',
            'orderId': '12346',
            'type': 'TAKE_PROFIT_MARKET',
            'side': 'SELL',
            'origQty': '0.1',
            'price': '0',
            'stopPrice': '4000'
        }

        result = await self.cleanup.close_orphaned_order(order)

        self.assertFalse(result)
        self.assertEqual(len(self.cleanup.closed_orders), 0)

    async def test_close_all_orphaned_orders_dry_run(self):
        """Test dry run mode"""
        self.cleanup.orphaned_orders = [
            {'symbol': 'ETHUSDT', 'orderId': '12346', 'type': 'TAKE_PROFIT_MARKET'},
            {'symbol': 'ADAUSDT', 'orderId': '12347', 'type': 'STOP_MARKET'}
        ]

        result = await self.cleanup.close_all_orphaned_orders(dry_run=True)

        self.assertEqual(result['closed'], 2)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['total'], 2)
        self.assertEqual(len(self.cleanup.closed_orders), 0)  # No actual closures in dry run

    def test_display_orphaned_orders_empty(self):
        """Test display with no orphaned orders"""
        # This should not raise an exception
        self.cleanup.display_orphaned_orders([])

    def test_display_orphaned_orders_with_data(self):
        """Test display with orphaned orders"""
        # This should not raise an exception
        self.cleanup.display_orphaned_orders(self.sample_orders[:1])

    def test_display_positions_empty(self):
        """Test display with no positions"""
        # This should not raise an exception
        self.cleanup.display_positions([])

    def test_display_positions_with_data(self):
        """Test display with positions"""
        # This should not raise an exception
        self.cleanup.display_positions(self.sample_positions)

    def test_save_report(self):
        """Test report saving functionality"""
        self.cleanup.orphaned_orders = [{'symbol': 'ETHUSDT', 'orderId': '12346'}]
        self.cleanup.closed_orders = [{'symbol': 'ETHUSDT', 'orderId': '12346', 'closed_at': '2024-01-01T00:00:00'}]

        # Test with temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_filename = f.name

        try:
            self.cleanup.save_report(temp_filename)

            # Verify file was created and contains expected data
            import json
            with open(temp_filename, 'r') as f:
                report = json.load(f)

            self.assertEqual(report['orphaned_orders_found'], 1)
            self.assertEqual(report['orders_closed'], 1)
            self.assertEqual(len(report['orphaned_orders']), 1)
            self.assertEqual(len(report['closed_orders']), 1)

        finally:
            # Clean up temporary file
            import os
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)

def run_tests():
    """Run all tests"""
    print("🧪 Running Orphaned Orders Cleanup Tests")
    print("=" * 50)

    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOrphanedOrdersCleanup)

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
