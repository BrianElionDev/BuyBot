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
            api_key=settings.KUCOIN_API_KEY,
            api_secret=settings.KUCOIN_API_SECRET,
            api_passphrase=settings.KUCOIN_API_PASSPHRASE,
            is_testnet=settings.KUCOIN_TESTNET
        )
        logger.info("KuCoinExchange initialized")


async def main():
    """Main reconciliation function"""
    try:
        logger.info("🔄 KuCoin Reconciliation Script")
        logger.info("=" * 50)

        # Initialize components
        bot = MinimalBot()
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

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

        # Sync positions to database
        logger.info("🔄 Syncing positions...")
        await sync_kucoin_positions_to_database_enhanced(bot, supabase, kucoin_positions, kucoin_trades)

        # Clean up closed positions
        logger.info("🧹 Cleaning up closed positions...")
        await cleanup_closed_kucoin_positions_enhanced(bot, supabase, kucoin_positions, kucoin_trades)

        # Backfill missing data from KuCoin history
        logger.info("📜 Backfilling missing data from KuCoin history...")
        await backfill_kucoin_trades_from_history_enhanced(bot, supabase, kucoin_trades)

        logger.info("🔍 Final validation...")

        # Final count
        final_trades_response = supabase.table("trades").select("*").gte("created_at", thirty_days_ago).execute()
        final_trades = final_trades_response.data or []
        final_kucoin_trades = [trade for trade in final_trades if trade.get('exchange') == 'kucoin']

        logger.info("✅ KuCoin reconciliation completed!")
        logger.info(f"KuCoin Orders: {len(kucoin_orders)}")
        logger.info(f"KuCoin Positions: {len(kucoin_positions)}")
        logger.info(f"Database KuCoin Trades: {len(final_kucoin_trades)}")

    except Exception as e:
        logger.error(f"❌ Reconciliation failed: {e}")
        raise
    finally:
        # Close KuCoin client
        if 'bot' in locals() and hasattr(bot.kucoin_exchange, 'close_client'):
            await bot.kucoin_exchange.close_client()
            logger.info("KuCoin client connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
