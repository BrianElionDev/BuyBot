#!/usr/bin/env python3
"""
Example usage of the Orphaned Orders Cleanup Script
"""

import asyncio
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

from scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders import OrphanedOrdersCleanup

async def example_dry_run():
    """Example: Run a dry run to see what would be cleaned up"""
    print("🔍 Example: Dry Run - Check for Orphaned Orders")
    print("=" * 60)

    cleanup = OrphanedOrdersCleanup()
    await cleanup.run_cleanup(dry_run=True, save_report=False)

    print("\n💡 This shows what orders would be closed without actually closing them")
    print("   Use this to verify the cleanup logic before running for real")

async def example_real_cleanup():
    """Example: Run actual cleanup (commented out for safety)"""
    print("⚠️  Example: Real Cleanup (DISABLED FOR SAFETY)")
    print("=" * 60)

    print("To run actual cleanup, uncomment the code below and run:")
    print("python3 scripts/maintenance/cleanup_scripts/cleanup_orphaned_orders.py")

    # Uncomment below to run actual cleanup
    # cleanup = OrphanedOrdersCleanup()
    # await cleanup.run_cleanup(dry_run=False, save_report=True)

async def example_manual_analysis():
    """Example: Manual analysis of orders and positions"""
    print("📊 Example: Manual Analysis")
    print("=" * 60)

    cleanup = OrphanedOrdersCleanup()

    if not await cleanup.initialize():
        print("❌ Failed to initialize Binance connection")
        return

    try:
        # Get current state
        orders = await cleanup.get_open_orders()
        positions = await cleanup.get_positions()

        print(f"📋 Found {len(orders)} open orders")
        print(f"💰 Found {len(positions)} active positions")

        # Analyze manually
        position_symbols = {pos.get('symbol') for pos in positions}

        print(f"\n🔍 Position Symbols: {sorted(position_symbols)}")

        # Check each order
        orphaned_count = 0
        for order in orders:
            symbol = order.get('symbol')
            order_type = order.get('type', '').upper()

            is_sl_tp = (
                order_type in ['STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT'] or
                order.get('reduceOnly', False) or
                order.get('stopPrice') is not None
            )

            has_position = symbol in position_symbols

            status = "✅ OK" if not is_sl_tp or has_position else "⚠️  ORPHANED"
            if not is_sl_tp or has_position:
                pass  # OK
            else:
                orphaned_count += 1

            print(f"  {symbol:<12} {order_type:<15} {status}")

        print(f"\n📊 Summary: {orphaned_count} orphaned orders found")

    except Exception as e:
        print(f"❌ Error during analysis: {e}")
    finally:
        if cleanup.binance_exchange:
            await cleanup.binance_exchange.close_client()

async def main():
    """Main function to run examples"""
    print("🧹 Orphaned Orders Cleanup - Usage Examples")
    print("=" * 70)

    # Run examples
    await example_dry_run()
    print("\n" + "="*70 + "\n")

    await example_real_cleanup()
    print("\n" + "="*70 + "\n")

    await example_manual_analysis()

    print("\n" + "="*70)
    print("💡 Usage Tips:")
    print("1. Always run with --dry-run first to see what would be cleaned up")
    print("2. Check the report file after cleanup for audit trail")
    print("3. Use the manual analysis to understand your current state")
    print("4. Run cleanup regularly to prevent accumulation of orphaned orders")

if __name__ == "__main__":
    asyncio.run(main())
