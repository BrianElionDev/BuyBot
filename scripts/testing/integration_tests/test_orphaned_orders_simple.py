#!/usr/bin/env python3
"""
Simple test for orphaned orders cleanup logic (no external dependencies)
"""

import unittest
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

class OrphanedOrdersLogic:
    """Simplified version of orphaned orders logic for testing"""

    @staticmethod
    def identify_orphaned_orders(orders, positions):
        """Identify orders for coins without positions"""
        # Get symbols with active positions
        position_symbols = {pos.get('symbol') for pos in positions}

        # Filter orders that are SL/TP orders for symbols without positions
        orphaned = []

        for order in orders:
            symbol = order.get('symbol')
            order_type = order.get('type', '').upper()

            # Check if this is a SL/TP order
            is_sl_tp = (
                order_type in ['STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT'] or
                order.get('reduceOnly', False) or
                order.get('stopPrice') is not None
            )

            # Check if symbol has no position
            has_position = symbol in position_symbols

            if is_sl_tp and not has_position:
                orphaned.append(order)

        return orphaned

class TestOrphanedOrdersLogic(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.logic = OrphanedOrdersLogic()

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

    def test_identify_orphaned_orders_basic(self):
        """Test basic identification of orphaned orders"""
        orphaned = self.logic.identify_orphaned_orders(self.sample_orders, self.sample_positions)

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

        orphaned = self.logic.identify_orphaned_orders(self.sample_orders, positions_with_all)
        self.assertEqual(len(orphaned), 0)

    def test_identify_orphaned_orders_no_positions(self):
        """Test when no positions exist (all SL/TP orders are orphaned)"""
        orphaned = self.logic.identify_orphaned_orders(self.sample_orders, [])

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
        orphaned = self.logic.identify_orphaned_orders(test_orders, [])

        # Should identify 5 orphaned orders (all except TEST6)
        self.assertEqual(len(orphaned), 5)
        symbols = [order['symbol'] for order in orphaned]
        self.assertIn('TEST1', symbols)
        self.assertIn('TEST2', symbols)
        self.assertIn('TEST3', symbols)
        self.assertIn('TEST4', symbols)
        self.assertIn('TEST5', symbols)
        self.assertNotIn('TEST6', symbols)

    def test_edge_cases(self):
        """Test edge cases"""
        # Empty orders
        orphaned = self.logic.identify_orphaned_orders([], self.sample_positions)
        self.assertEqual(len(orphaned), 0)

        # Empty positions
        orphaned = self.logic.identify_orphaned_orders(self.sample_orders, [])
        self.assertEqual(len(orphaned), 2)  # Both SL/TP orders

        # Orders with missing fields
        incomplete_orders = [
            {'symbol': 'TEST1'},  # Missing type
            {'symbol': 'TEST2', 'type': 'STOP_MARKET'},  # Missing stopPrice
            {'symbol': 'TEST3', 'type': 'LIMIT', 'reduceOnly': True},  # Valid reduceOnly
        ]

        orphaned = self.logic.identify_orphaned_orders(incomplete_orders, [])
        self.assertEqual(len(orphaned), 2)  # TEST2 and TEST3 should be orphaned
        symbols = [order['symbol'] for order in orphaned]
        self.assertIn('TEST2', symbols)
        self.assertIn('TEST3', symbols)

    def test_real_world_scenarios(self):
        """Test real-world scenarios"""
        # Scenario 1: Mixed orders with some positions
        real_orders = [
            {'symbol': 'BTCUSDT', 'type': 'STOP_MARKET', 'stopPrice': '50000', 'reduceOnly': True},
            {'symbol': 'ETHUSDT', 'type': 'TAKE_PROFIT_MARKET', 'stopPrice': '4000', 'reduceOnly': True},
            {'symbol': 'ADAUSDT', 'type': 'LIMIT', 'price': '0.5', 'reduceOnly': False},
            {'symbol': 'DOGEUSDT', 'type': 'STOP', 'stopPrice': '0.1', 'reduceOnly': True},
        ]

        real_positions = [
            {'symbol': 'BTCUSDT', 'positionAmt': '0.001'},
            {'symbol': 'ADAUSDT', 'positionAmt': '100'},
        ]

        orphaned = self.logic.identify_orphaned_orders(real_orders, real_positions)

        # Should find ETHUSDT and DOGEUSDT as orphaned (SL/TP without positions)
        self.assertEqual(len(orphaned), 2)
        symbols = [order['symbol'] for order in orphaned]
        self.assertIn('ETHUSDT', symbols)
        self.assertIn('DOGEUSDT', symbols)
        self.assertNotIn('BTCUSDT', symbols)  # Has position
        self.assertNotIn('ADAUSDT', symbols)  # Not SL/TP

def run_tests():
    """Run all tests"""
    print("🧪 Running Orphaned Orders Logic Tests")
    print("=" * 50)

    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOrphanedOrdersLogic)

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
