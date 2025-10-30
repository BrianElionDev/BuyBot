#!/usr/bin/env python3
"""
KuCoin Reconciliation Script

This script reconciles KuCoin trades with the database, ensuring:
1. Missing exit prices are populated from KuCoin order/trade history
2. Missing position sizes are populated from KuCoin order details
3. Closed trades are properly marked as CLOSED
4. PnL values are accurate and complete

Usage:
    python3 scripts/maintenance/kucoin_reconcile.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from config import settings
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from supabase import create_client, Client
from discord_bot.utils.trade_retry_utils import (
    sync_kucoin_orders_to_database_enhanced,
    sync_kucoin_positions_to_database_enhanced,
    cleanup_closed_kucoin_positions_enhanced,
    backfill_kucoin_trades_from_history_enhanced
)

sup_url = settings.SUPABASE_URL or ""
sup_key = settings.SUPABASE_KEY or ""

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MinimalBot:
    """Minimal bot instance for KuCoin reconciliation"""
    def __init__(self):
        self.kucoin_exchange = KucoinExchange(
            api_key=settings.KUCOIN_API_KEY or "",
            api_secret=settings.KUCOIN_API_SECRET or "",
            api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
            is_testnet=False
        )
        logger.info("KuCoinExchange initialized")


async def analyze_trades_before_backfill(trades: List[Dict]) -> Dict[str, Any]:
    """Analyze trades before backfill to show what needs to be fixed"""
    stats = {
        'total': len(trades),
        'closed': 0,
        'missing_exit_price': 0,
        'missing_entry_price': 0,
        'missing_pnl': 0,
        'missing_position_size': 0,
        'same_pnl_value': 0
    }

    pnl_values = {}

    for trade in trades:
        status = trade.get('status', '')
        if status == 'CLOSED':
            stats['closed'] += 1

            if not trade.get('exit_price') or float(trade.get('exit_price', 0) or 0) == 0:
                stats['missing_exit_price'] += 1

            if not trade.get('entry_price') or float(trade.get('entry_price', 0) or 0) == 0:
                stats['missing_entry_price'] += 1

            pnl = trade.get('pnl_usd')
            if not pnl or float(pnl or 0) == 0:
                stats['missing_pnl'] += 1
            else:
                pnl_val = str(pnl)
                pnl_values[pnl_val] = pnl_values.get(pnl_val, 0) + 1

            if not trade.get('position_size') or float(trade.get('position_size', 0) or 0) == 0:
                stats['missing_position_size'] += 1

    # Check for duplicate PnL values (the bug we're fixing)
    duplicate_pnl = {pnl: count for pnl, count in pnl_values.items() if count > 1}
    if duplicate_pnl:
        stats['same_pnl_value'] = sum(count for count in duplicate_pnl.values() if count > 1)
        logger.warning(f"⚠️  Found {len(duplicate_pnl)} duplicate PnL values affecting {stats['same_pnl_value']} trades")
        for pnl, count in list(duplicate_pnl.items())[:5]:  # Show first 5
            logger.warning(f"   PnL {pnl} appears {count} times")

    return stats


async def analyze_trades_after_backfill(trades: List[Dict], before_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze trades after backfill to show improvements"""
    after_stats = await analyze_trades_before_backfill(trades)

    improvements = {
        'exit_price_fixed': before_stats['missing_exit_price'] - after_stats['missing_exit_price'],
        'entry_price_fixed': before_stats['missing_entry_price'] - after_stats['missing_entry_price'],
        'pnl_fixed': before_stats['missing_pnl'] - after_stats['missing_pnl'],
        'position_size_fixed': before_stats['missing_position_size'] - after_stats['missing_position_size'],
        'duplicate_pnl_fixed': before_stats['same_pnl_value'] - after_stats['same_pnl_value']
    }

    return after_stats, improvements


async def main():
    """Main reconciliation function"""
    try:
        logger.info("🔄 KuCoin Reconciliation Script")
        logger.info("=" * 50)

        # Initialize components
        bot = MinimalBot()

        # Initialize KuCoin exchange
        logger.info("🔌 Initializing KuCoin exchange...")
        init_success = await bot.kucoin_exchange.initialize()
        if not init_success:
            logger.error("❌ Failed to initialize KuCoin exchange")
            return

        logger.info("✅ KuCoin exchange initialized")

        supabase = create_client(sup_url, sup_key)

        logger.info("📊 Fetching data...")

        # Get recent trades from database (last 30 days)
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        db_trades_response = supabase.table("trades").select("*").gte("created_at", thirty_days_ago).execute()
        db_trades = db_trades_response.data or []

        # Filter for KuCoin trades
        kucoin_trades = [trade for trade in db_trades if trade.get('exchange') == 'kucoin']

        logger.info(f"Found {len(kucoin_trades)} KuCoin trades in database")

        if not kucoin_trades:
            logger.info("No KuCoin trades found to reconcile")
            return

        # Analyze trades before backfill
        logger.info("📈 Analyzing trades before backfill...")
        before_stats = await analyze_trades_before_backfill(kucoin_trades)
        logger.info(f"   Total trades: {before_stats['total']}")
        logger.info(f"   Closed trades: {before_stats['closed']}")
        logger.info(f"   Missing exit prices: {before_stats['missing_exit_price']}")
        logger.info(f"   Missing entry prices: {before_stats['missing_entry_price']}")
        logger.info(f"   Missing PnL: {before_stats['missing_pnl']}")
        logger.info(f"   Missing position size: {before_stats['missing_position_size']}")

        # Get active KuCoin positions
        try:
            kucoin_positions = await bot.kucoin_exchange.get_futures_position_information()
            logger.info(f"Retrieved {len(kucoin_positions)} active positions from KuCoin")
        except Exception as e:
            logger.error(f"Failed to get KuCoin positions: {e}")
            kucoin_positions = []

        # Get open KuCoin orders
        try:
            kucoin_orders = await bot.kucoin_exchange.get_all_open_futures_orders()
            logger.info(f"Retrieved {len(kucoin_orders)} open orders from KuCoin")
        except Exception as e:
            logger.error(f"Failed to get KuCoin orders: {e}")
            kucoin_orders = []

        logger.info("🔍 Validating database accuracy...")

        # Sync orders to database
        logger.info("🔄 Syncing orders...")
        await sync_kucoin_orders_to_database_enhanced(bot, supabase, kucoin_orders, kucoin_trades)
        logger.info("✅ Order sync completed")

        # Sync positions to database
        logger.info("🔄 Syncing positions...")
        await sync_kucoin_positions_to_database_enhanced(bot, supabase, kucoin_positions, kucoin_trades)
        logger.info("✅ Position sync completed")

        # Clean up closed positions
        logger.info("🧹 Cleaning up closed positions...")
        await cleanup_closed_kucoin_positions_enhanced(bot, supabase, kucoin_positions, kucoin_trades)
        logger.info("✅ Closed positions cleanup completed")

        # Backfill missing data from KuCoin history
        logger.info("📜 Backfilling missing data from KuCoin history...")
        logger.info("   This will:")
        logger.info("   - Match entry/exit trades by time window and side")
        logger.info("   - Calculate exit prices from closing trades")
        logger.info("   - Calculate PnL including fees")
        logger.info("   - Update entry prices and position sizes if found")

        # Filter closed trades that need backfilling
        closed_trades_needing_backfill = [
            t for t in kucoin_trades
            if t.get('status') == 'CLOSED' and (
                not t.get('exit_price') or float(t.get('exit_price', 0) or 0) == 0 or
                not t.get('pnl_usd') or float(t.get('pnl_usd', 0) or 0) == 0
            )
        ]

        logger.info(f"   Found {len(closed_trades_needing_backfill)} closed trades needing backfill")

        await backfill_kucoin_trades_from_history_enhanced(bot, supabase, kucoin_trades)
        logger.info("✅ Backfill completed")

        logger.info("🔍 Final validation...")

        # Get updated trades
        final_trades_response = supabase.table("trades").select("*").gte("created_at", thirty_days_ago).execute()
        final_trades = final_trades_response.data or []
        final_kucoin_trades = [trade for trade in final_trades if trade.get('exchange') == 'kucoin']

        # Analyze trades after backfill
        logger.info("📈 Analyzing trades after backfill...")
        after_stats, improvements = await analyze_trades_after_backfill(final_kucoin_trades, before_stats)

        logger.info("=" * 50)
        logger.info("📊 Reconciliation Results:")
        logger.info("=" * 50)
        logger.info(f"KuCoin Orders: {len(kucoin_orders)}")
        logger.info(f"KuCoin Positions: {len(kucoin_positions)}")
        logger.info(f"Database KuCoin Trades: {len(final_kucoin_trades)}")
        logger.info("")
        logger.info("📈 Backfill Improvements:")
        logger.info(f"   Exit prices fixed: {improvements['exit_price_fixed']}")
        logger.info(f"   Entry prices fixed: {improvements['entry_price_fixed']}")
        logger.info(f"   PnL values fixed: {improvements['pnl_fixed']}")
        logger.info(f"   Position sizes fixed: {improvements['position_size_fixed']}")
        logger.info(f"   Duplicate PnL values fixed: {improvements['duplicate_pnl_fixed']}")
        logger.info("")
        logger.info("📊 Current Status:")
        logger.info(f"   Closed trades with exit prices: {after_stats['closed'] - after_stats['missing_exit_price']}/{after_stats['closed']}")
        logger.info(f"   Closed trades with PnL: {after_stats['closed'] - after_stats['missing_pnl']}/{after_stats['closed']}")
        logger.info("")
        logger.info("✅ KuCoin reconciliation completed!")

    except Exception as e:
        logger.error(f"❌ Reconciliation failed: {e}", exc_info=True)
        raise
    finally:
        # Close KuCoin client
        if 'bot' in locals() and hasattr(bot.kucoin_exchange, 'close_client'):
            await bot.kucoin_exchange.close_client()
            logger.info("KuCoin client connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
