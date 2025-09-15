#!/usr/bin/env python3
"""
Orphaned Orders Cleanup Script
Checks for open orders (SL/TP) for coins without positions and closes them
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

# Import with error handling
try:
    from config.settings import *
    from src.exchange import BinanceExchange
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running this script from the project root directory")
    print("or that all dependencies are properly installed.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OrphanedOrdersCleanup:
    def __init__(self):
        self.binance_exchange = None
        self.orphaned_orders = []
        self.closed_orders = []

    async def initialize(self):
        """Initialize the Binance exchange connection"""
        try:
            # Get credentials from environment variables
            api_key = BINANCE_API_KEY
            api_secret = BINANCE_API_SECRET
            is_testnet = BINANCE_TESTNET

            if not api_key or not api_secret:
                logger.error("Binance API credentials not found in environment variables!")
                logger.error("Please set BINANCE_API_KEY and BINANCE_API_SECRET")
                return False

            self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
            await self.binance_exchange._init_client()

            logger.info(f"Connected to Binance {'Testnet' if is_testnet else 'Mainnet'}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Binance connection: {e}")
            return False

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
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

    async def get_positions(self) -> List[Dict]:
        """Get all active positions"""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return []

            positions = await self.binance_exchange.get_futures_position_information()

            # Filter out positions with zero size
            active_positions = [
                pos for pos in positions
                if float(pos.get('positionAmt', 0)) != 0
            ]

            logger.info(f"Found {len(active_positions)} active positions out of {len(positions)} total")
            return active_positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def identify_orphaned_orders(self, orders: List[Dict], positions: List[Dict]) -> List[Dict]:
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
                logger.info(f"Found orphaned order: {symbol} {order_type} (Order ID: {order.get('orderId')})")

        self.orphaned_orders = orphaned
        return orphaned

    async def close_orphaned_order(self, order: Dict) -> bool:
        """Close a single orphaned order"""
        try:
            symbol = order.get('symbol')
            order_id = order.get('orderId')
            order_type = order.get('type')

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
                    'closed_at': datetime.now().isoformat()
                })
                return True
            else:
                logger.error(f"❌ Failed to close orphaned order: {symbol} {order_type} (ID: {order_id}): {result}")
                return False

        except Exception as e:
            logger.error(f"❌ Error closing orphaned order {order.get('symbol')} {order.get('orderId')}: {e}")
            return False

    async def close_all_orphaned_orders(self, dry_run: bool = False) -> Dict:
        """Close all orphaned orders"""
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

    def display_orphaned_orders(self, orders: List[Dict]):
        """Display orphaned orders in a formatted table"""
        if not orders:
            print("\n✅ No orphaned orders found")
            return

        print(f"\n⚠️  Orphaned Orders ({len(orders)}):")
        print("=" * 160)
        print(f"{'Symbol':<12} {'Side':<6} {'Type':<15} {'Quantity':<12} {'Price':<12} {'Stop Price':<12} {'Order ID':<15} {'Client ID':<15}")
        print("-" * 160)

        for order in orders:
            client_id = order.get('clientOrderId', 'N/A')[:14] if order.get('clientOrderId') else 'N/A'
            print(f"{order.get('symbol'):<12} {order.get('side'):<6} {order.get('type'):<15} "
                  f"{float(order.get('origQty', 0)):<12.4f} {float(order.get('price', 0)):<12.4f} "
                  f"{float(order.get('stopPrice', 0)) if order.get('stopPrice') else 'N/A':<12} "
                  f"{order.get('orderId'):<15} {client_id:<15}")

    def display_positions(self, positions: List[Dict]):
        """Display active positions"""
        if not positions:
            print("\n💰 No active positions found")
            return

        print(f"\n💰 Active Positions ({len(positions)}):")
        print("=" * 100)
        print(f"{'Symbol':<12} {'Side':<6} {'Size':<12} {'Entry Price':<12} {'Mark Price':<12} {'PnL':<12}")
        print("-" * 100)

        for position in positions:
            position_amt = float(position.get('positionAmt', 0))
            side = 'LONG' if position_amt > 0 else 'SHORT'
            size = abs(position_amt)
            entry_price = float(position.get('entryPrice', 0))
            mark_price = float(position.get('markPrice', 0))
            unrealized_pnl = float(position.get('unRealizedProfit', 0))

            pnl_color = "🟢" if unrealized_pnl >= 0 else "🔴"
            print(f"{position.get('symbol'):<12} {side:<6} {size:<12.4f} "
                  f"{entry_price:<12.4f} {mark_price:<12.4f} {pnl_color} {unrealized_pnl:<10.2f}")

    def save_report(self, filename: Optional[str] = None):
        """Save cleanup report to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"orphaned_orders_cleanup_{timestamp}.json"

        report = {
            'timestamp': datetime.now().isoformat(),
            'orphaned_orders_found': len(self.orphaned_orders),
            'orders_closed': len(self.closed_orders),
            'orphaned_orders': self.orphaned_orders,
            'closed_orders': self.closed_orders
        }

        try:
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Cleanup report saved to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    async def run_cleanup(self, dry_run: bool = False, save_report: bool = True):
        """Run the complete orphaned orders cleanup process"""
        print("🧹 Orphaned Orders Cleanup")
        print("=" * 50)

        # Initialize connection
        if not await self.initialize():
            return

        try:
            # Get current state
            orders = await self.get_open_orders()
            positions = await self.get_positions()

            # Display current state
            self.display_positions(positions)
            self.display_orphaned_orders(orders)

            # Identify orphaned orders
            orphaned = self.identify_orphaned_orders(orders, positions)

            if not orphaned:
                print("\n✅ No orphaned orders found - all orders have corresponding positions")
                return

            # Display orphaned orders
            self.display_orphaned_orders(orphaned)

            # Ask for confirmation (unless dry run)
            if not dry_run:
                print(f"\n⚠️  Found {len(orphaned)} orphaned orders to close")
                response = input("Do you want to proceed with closing these orders? (y/N): ")
                if response.lower() != 'y':
                    print("Cleanup cancelled by user")
                    return

            # Close orphaned orders
            result = await self.close_all_orphaned_orders(dry_run=dry_run)

            # Display results
            print(f"\n📊 Cleanup Results:")
            print(f"Total orphaned orders: {result['total']}")
            print(f"Successfully closed: {result['closed']}")
            print(f"Failed to close: {result['failed']}")

            # Save report
            if save_report and (result['closed'] > 0 or result['failed'] > 0):
                self.save_report()

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()

async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Orphaned Orders Cleanup Script')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually closing orders')
    parser.add_argument('--no-report', action='store_true',
                       help='Do not save cleanup report to file')

    args = parser.parse_args()

    cleanup = OrphanedOrdersCleanup()
    await cleanup.run_cleanup(dry_run=args.dry_run, save_report=not args.no_report)

if __name__ == "__main__":
    asyncio.run(main())
