#!/usr/bin/env python3
"""
Enhanced Orphaned Orders Cleanup Script

This script handles orphaned orders cleanup with position aggregation awareness.
It prevents the removal of orders that belong to aggregated positions.
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

try:
    from config.settings import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET
    from src.exchange import BinanceExchange
    from src.bot.position_management.position_manager import PositionManager
    from src.bot.position_management.database_operations import PositionDatabaseOperations
    from discord_bot.database.database_manager import DatabaseManager
    from supabase import create_client, Client
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running this script from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnhancedOrphanedOrdersCleanup:
    """
    Enhanced orphaned orders cleanup with position aggregation awareness.

    This class prevents the removal of orders that belong to aggregated positions
    and provides better conflict detection.
    """

    def __init__(self):
        self.binance_exchange = None
        self.db_manager = None
        self.position_manager = None
        self.position_db_ops = None
        self.orphaned_orders = []
        self.closed_orders = []
        self.skipped_orders = []

    async def initialize(self):
        """Initialize all required connections."""
        try:
            # Initialize Binance exchange
            api_key = BINANCE_API_KEY
            api_secret = BINANCE_API_SECRET
            is_testnet = BINANCE_TESTNET

            if not api_key or not api_secret:
                logger.error("Binance API credentials not found!")
                return False

            self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
            await self.binance_exchange._init_client()

            # Initialize database manager
            from config.settings import SUPABASE_URL, SUPABASE_KEY
            if not SUPABASE_URL or not SUPABASE_KEY:
                logger.error("Supabase credentials not found!")
                return False
            supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            self.db_manager = DatabaseManager(supabase_client)

            # Initialize position management
            self.position_manager = PositionManager(self.db_manager, self.binance_exchange)
            self.position_db_ops = PositionDatabaseOperations(self.db_manager)

            logger.info(f"Initialized enhanced cleanup for {'Testnet' if is_testnet else 'Mainnet'}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders from Binance."""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return []

            orders = await self.binance_exchange.get_all_open_futures_orders()
            logger.info(f"Found {len(orders)} open orders")
            return orders

        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []

    async def get_positions_with_aggregation(self) -> Dict[str, Dict]:
        """
        Get positions with aggregation awareness.

        Returns:
            Dictionary mapping symbol to position information including trade counts
        """
        try:
            if not self.position_db_ops:
                logger.error("Position database operations not initialized")
                return {}

            # Get position summary from database
            position_summary = await self.position_db_ops.get_position_summary()

            # Create lookup for symbols with positions
            positions = {}
            for position in position_summary.get('positions', []):
                symbol = position['symbol']
                positions[symbol] = {
                    'has_position': True,
                    'side': position['side'],
                    'size': position['total_size'],
                    'trade_count': position['trade_count'],
                    'weighted_entry_price': position['weighted_entry_price']
                }

            logger.info(f"Found {len(positions)} positions with aggregation data")
            return positions

        except Exception as e:
            logger.error(f"Error getting positions with aggregation: {e}")
            return {}

    async def identify_orphaned_orders_enhanced(self, orders: List[Dict], positions: Dict[str, Dict]) -> List[Dict]:
        """
        Identify orphaned orders with position aggregation awareness.

        Args:
            orders: List of open orders
            positions: Dictionary of positions with aggregation data

        Returns:
            List of orphaned orders
        """
        orphaned = []
        skipped = []

        for order in orders:
            symbol = order.get('symbol')
            order_type = order.get('type', '').upper()

            # Check if this is a SL/TP order
            is_sl_tp = (
                order_type in ['STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT'] or
                order.get('reduceOnly', False) or
                order.get('stopPrice') is not None
            )

            if not is_sl_tp:
                continue  # Skip non-SL/TP orders

            # Check if symbol has a position
            if symbol in positions:
                position_info = positions[symbol]

                # Check if this order might belong to an aggregated position
                if position_info['trade_count'] > 1:
                    # This is an aggregated position - be more careful
                    if await self._is_order_legitimate_for_aggregated_position(order, symbol, position_info):
                        skipped.append({
                            'order': order,
                            'reason': f"Order belongs to aggregated position with {position_info['trade_count']} trades"
                        })
                        continue

                # Single trade position - check if order is legitimate
                if await self._is_order_legitimate_for_position(order, symbol, position_info):
                    skipped.append({
                        'order': order,
                        'reason': f"Order belongs to active {position_info['side']} position"
                    })
                    continue

            # Order is orphaned
            orphaned.append(order)
            logger.info(f"Found orphaned order: {symbol} {order_type} (Order ID: {order.get('orderId')})")

        self.orphaned_orders = orphaned
        self.skipped_orders = skipped

        logger.info(f"Identified {len(orphaned)} orphaned orders, skipped {len(skipped)} legitimate orders")
        return orphaned

    async def _is_order_legitimate_for_aggregated_position(self, order: Dict, symbol: str,
                                                         position_info: Dict) -> bool:
        """
        Check if an order is legitimate for an aggregated position.

        This is more complex because aggregated positions can have multiple
        orders from different trades.
        """
        try:
            if not self.position_db_ops:
                logger.error("Position database operations not initialized")
                return False

            # Get all trades for this symbol
            trades = await self.position_db_ops.get_trades_by_symbol_and_side(
                symbol, position_info['side']
            )

            # Check if any trade has this order ID
            order_id = order.get('orderId')
            client_order_id = order.get('clientOrderId')

            for trade in trades:
                if (trade.get('exchange_order_id') == order_id or
                    trade.get('stop_loss_order_id') == order_id or
                    trade.get('client_order_id') == client_order_id):
                    return True

            # Check TP/SL orders in the trade data
            for trade in trades:
                tp_sl_orders = trade.get('tp_sl_orders')
                if tp_sl_orders and isinstance(tp_sl_orders, dict):
                    for order_data in tp_sl_orders.values():
                        if isinstance(order_data, dict) and order_data.get('orderId') == order_id:
                            return True

            return False

        except Exception as e:
            logger.error(f"Error checking order legitimacy for aggregated position: {e}")
            return False

    async def _is_order_legitimate_for_position(self, order: Dict, symbol: str,
                                              position_info: Dict) -> bool:
        """
        Check if an order is legitimate for a single-trade position.
        """
        try:
            if not self.position_db_ops:
                logger.error("Position database operations not initialized")
                return False

            # Get trades for this symbol and side
            trades = await self.position_db_ops.get_trades_by_symbol_and_side(
                symbol, position_info['side']
            )

            if not trades:
                return False

            # Check if any trade has this order ID
            order_id = order.get('orderId')
            client_order_id = order.get('clientOrderId')

            for trade in trades:
                if (trade.get('exchange_order_id') == order_id or
                    trade.get('stop_loss_order_id') == order_id or
                    trade.get('client_order_id') == client_order_id):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking order legitimacy: {e}")
            return False

    async def close_orphaned_order(self, order: Dict) -> bool:
        """Close a single orphaned order."""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return False

            symbol = order.get('symbol')
            order_id = order.get('orderId')
            order_type = order.get('type')

            if not symbol or not order_id:
                logger.error(f"Invalid order data: symbol={symbol}, order_id={order_id}")
                return False

            logger.info(f"Closing orphaned order: {symbol} {order_type} (ID: {order_id})")

            # Cancel the order
            success, result = await self.binance_exchange.cancel_futures_order(symbol, order_id)

            if success:
                logger.info(f"✅ Successfully closed orphaned order: {symbol} {order_type} (ID: {order_id})")
                self.closed_orders.append({
                    'symbol': symbol,
                    'orderId': order_id,
                    'type': order_type,
                    'side': order.get('side'),
                    'quantity': order.get('origQty'),
                    'price': order.get('price'),
                    'stopPrice': order.get('stopPrice'),
                    'closed_at': datetime.now(timezone.utc).isoformat()
                })
                return True
            else:
                logger.error(f"❌ Failed to close orphaned order: {symbol} {order_type} (ID: {order_id}): {result}")
                return False

        except Exception as e:
            logger.error(f"❌ Error closing orphaned order {order.get('symbol')} {order.get('orderId')}: {e}")
            return False

    async def close_all_orphaned_orders(self, dry_run: bool = False) -> Dict:
        """Close all orphaned orders."""
        if not self.orphaned_orders:
            logger.info("No orphaned orders to close")
            return {'closed': 0, 'failed': 0, 'total': 0}

        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Closing {len(self.orphaned_orders)} orphaned orders...")

        closed_count = 0
        failed_count = 0

        for order in self.orphaned_orders:
            if dry_run:
                logger.info(f"[DRY RUN] Would close: {order.get('symbol')} {order.get('type')} (ID: {order.get('orderId')})")
                closed_count += 1
            else:
                success = await self.close_orphaned_order(order)
                if success:
                    closed_count += 1
                else:
                    failed_count += 1

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)

        result = {
            'closed': closed_count,
            'failed': failed_count,
            'total': len(self.orphaned_orders)
        }

        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Cleanup complete: {closed_count} closed, {failed_count} failed, {len(self.orphaned_orders)} total")
        return result

    def display_results(self):
        """Display cleanup results in a formatted table."""
        print("\n" + "=" * 80)
        print("ENHANCED ORPHANED ORDERS CLEANUP RESULTS")
        print("=" * 80)

        # Display orphaned orders
        if self.orphaned_orders:
            print(f"\n⚠️  Orphaned Orders ({len(self.orphaned_orders)}):")
            print("-" * 80)
            print(f"{'Symbol':<12} {'Side':<6} {'Type':<15} {'Quantity':<12} {'Price':<12} {'Order ID':<15}")
            print("-" * 80)

            for order in self.orphaned_orders:
                print(f"{order.get('symbol'):<12} {order.get('side'):<6} {order.get('type'):<15} "
                      f"{float(order.get('origQty', 0)):<12.4f} {float(order.get('price', 0)):<12.4f} "
                      f"{order.get('orderId'):<15}")
        else:
            print("\n✅ No orphaned orders found")

        # Display skipped orders
        if self.skipped_orders:
            print(f"\n🛡️  Skipped Orders ({len(self.skipped_orders)}):")
            print("-" * 80)
            print(f"{'Symbol':<12} {'Type':<15} {'Reason':<50}")
            print("-" * 80)

            for skipped in self.skipped_orders:
                order = skipped['order']
                reason = skipped['reason']
                print(f"{order.get('symbol'):<12} {order.get('type'):<15} {reason:<50}")

        # Display closed orders
        if self.closed_orders:
            print(f"\n✅ Closed Orders ({len(self.closed_orders)}):")
            print("-" * 80)
            print(f"{'Symbol':<12} {'Type':<15} {'Order ID':<15} {'Closed At':<20}")
            print("-" * 80)

            for closed in self.closed_orders:
                print(f"{closed.get('symbol'):<12} {closed.get('type'):<15} "
                      f"{closed.get('orderId'):<15} {closed.get('closed_at', 'N/A'):<20}")

    def save_report(self, filename: Optional[str] = None):
        """Save cleanup report to file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"enhanced_orphaned_orders_cleanup_{timestamp}.json"

        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'orphaned_orders_found': len(self.orphaned_orders),
            'orders_closed': len(self.closed_orders),
            'orders_skipped': len(self.skipped_orders),
            'orphaned_orders': self.orphaned_orders,
            'closed_orders': self.closed_orders,
            'skipped_orders': self.skipped_orders
        }

        try:
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Enhanced cleanup report saved to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    async def run_cleanup(self, dry_run: bool = False, save_report: bool = True):
        """Run the complete enhanced orphaned orders cleanup process."""
        print("🧹 Enhanced Orphaned Orders Cleanup")
        print("=" * 50)

        # Initialize connection
        if not await self.initialize():
            return

        try:
            # Get current state
            orders = await self.get_open_orders()
            positions = await self.get_positions_with_aggregation()

            # Identify orphaned orders with enhanced logic
            orphaned = await self.identify_orphaned_orders_enhanced(orders, positions)

            if not orphaned:
                print("\n✅ No orphaned orders found - all orders have corresponding positions")
                return

            # Display results
            self.display_results()

            # Ask for confirmation (unless dry run)
            if not dry_run:
                print(f"\n⚠️  Found {len(orphaned)} orphaned orders to close")
                response = input("Do you want to proceed with closing these orders? (y/N): ")
                if response.lower() != 'y':
                    print("Cleanup cancelled by user")
                    return

            # Close orphaned orders
            result = await self.close_all_orphaned_orders(dry_run=dry_run)

            # Display final results
            print(f"\n📊 Cleanup Results:")
            print(f"Total orphaned orders: {result['total']}")
            print(f"Successfully closed: {result['closed']}")
            print(f"Failed to close: {result['failed']}")
            print(f"Orders skipped (legitimate): {len(self.skipped_orders)}")

            # Save report
            if save_report and (result['closed'] > 0 or result['failed'] > 0):
                self.save_report()

        except Exception as e:
            logger.error(f"Error during enhanced cleanup: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced Orphaned Orders Cleanup Script')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually closing orders')
    parser.add_argument('--no-report', action='store_true',
                       help='Do not save cleanup report to file')

    args = parser.parse_args()

    cleanup = EnhancedOrphanedOrdersCleanup()
    await cleanup.run_cleanup(dry_run=args.dry_run, save_report=not args.no_report)


if __name__ == "__main__":
    asyncio.run(main())
