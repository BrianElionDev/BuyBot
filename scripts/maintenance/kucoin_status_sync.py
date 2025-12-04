#!/usr/bin/env python3
"""
KuCoin Status Sync Script

This script ensures trade statuses accurately reflect the current state on KuCoin exchange.
It:
1. Fetches current positions and orders from KuCoin
2. Compares with database trades
3. Closes trades that are no longer active on exchange
4. Ensures closed trades stay closed (prevents re-activation)

Usage:
    python3 scripts/maintenance/kucoin_status_sync.py
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
    extract_symbol_from_trade,
)
from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
from src.core.unified_status_updater import update_trade_status_safely
from src.core.data_enrichment import enrich_trade_data_before_close

SUPABASE_URL = settings.SUPABASE_URL or ""
SUPABASE_KEY = settings.SUPABASE_KEY or ""

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_symbol_converter = KucoinSymbolConverter()


class MinimalBot:
    """Minimal bot instance for KuCoin status sync"""
    def __init__(self):
        self.kucoin_exchange = KucoinExchange(
            api_key=settings.KUCOIN_API_KEY or "",
            api_secret=settings.KUCOIN_API_SECRET or "",
            api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
            is_testnet=False
        )
        logger.info("KuCoinExchange initialized")


async def get_active_symbols_from_exchange(kucoin_positions: List[Dict[str, Any]]) -> set:
    """
    Convert KuCoin position symbols to bot symbols for comparison.

    Args:
        kucoin_positions: List of position dictionaries from KuCoin

    Returns:
        Set of bot symbols (e.g., {'BTC', 'ETH', 'BNB'})
    """
    active_symbols = set()
    for pos in kucoin_positions:
        kucoin_symbol = pos.get('symbol', '')
        position_size = float(pos.get('size', 0))
        if kucoin_symbol and position_size != 0:
            bot_symbol = _symbol_converter.convert_kucoin_to_bot(kucoin_symbol)
            if bot_symbol.endswith('USDT'):
                bot_symbol = bot_symbol[:-4]
            if bot_symbol:
                active_symbols.add(bot_symbol)
                logger.debug(f"Active position: {kucoin_symbol} -> {bot_symbol}")

    return active_symbols


async def sync_statuses_accurately(bot: MinimalBot, supabase: Client):
    """
    Main function to sync trade statuses with KuCoin exchange state.

    This function:
    1. Fetches current positions and orders from KuCoin
    2. Gets all KuCoin trades from database
    3. Closes trades that are not active on exchange
    4. Ensures closed trades stay closed
    """
    try:
        logger.info("🔄 Starting KuCoin Status Sync")
        logger.info("=" * 60)

        # Initialize exchange
        init_success = await bot.kucoin_exchange.initialize()
        if not init_success:
            logger.error("❌ Failed to initialize KuCoin exchange")
            return

        logger.info("✅ KuCoin exchange initialized")

        # Fetch current state from exchange
        logger.info("📊 Fetching current state from KuCoin...")
        kucoin_positions = await bot.kucoin_exchange.get_futures_position_information()
        kucoin_orders = await bot.kucoin_exchange.get_all_open_futures_orders()

        logger.info(f"Found {len(kucoin_positions)} active positions on KuCoin")
        logger.info(f"Found {len(kucoin_orders)} open orders on KuCoin")

        # Get active symbols from exchange
        active_symbols = await get_active_symbols_from_exchange(kucoin_positions)
        logger.info(f"Active symbols on exchange: {active_symbols}")

        # Get all KuCoin trades from database (last 30 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        response = supabase.table("trades").select("*").gte("created_at", cutoff).eq("exchange", "kucoin").execute()
        db_trades = response.data or []

        logger.info(f"Found {len(db_trades)} KuCoin trades in database")

        # Step 1: Sync orders and positions (this updates position data)
        logger.info("🔄 Step 1: Syncing orders and positions...")
        await sync_kucoin_orders_to_database_enhanced(bot, supabase, kucoin_orders, db_trades)
        await sync_kucoin_positions_to_database_enhanced(bot, supabase, kucoin_positions, db_trades)
        logger.info("✅ Orders and positions synced")

        # Step 2: Close trades that are not active on exchange
        logger.info("🔄 Step 2: Closing trades not active on exchange...")
        await cleanup_closed_kucoin_positions_enhanced(bot, supabase, kucoin_positions, db_trades)
        logger.info("✅ Closed trades cleanup completed")

        # Step 3: Ensure closed trades stay closed (prevent re-activation)
        logger.info("🔄 Step 3: Ensuring closed trades stay closed...")
        await ensure_closed_trades_stay_closed(supabase, db_trades, active_symbols)
        logger.info("✅ Closed trades verification completed")

        # Step 4: Final verification
        logger.info("🔄 Step 4: Final verification...")
        await verify_status_accuracy(supabase, active_symbols)

        logger.info("=" * 60)
        logger.info("✅ KuCoin Status Sync completed successfully!")

    except Exception as e:
        logger.error(f"❌ Status sync failed: {e}", exc_info=True)
        raise
    finally:
        if hasattr(bot.kucoin_exchange, 'close_client'):
            await bot.kucoin_exchange.close_client()
            logger.info("KuCoin client connection closed.")


async def ensure_closed_trades_stay_closed(
    supabase: Client,
    db_trades: List[Dict[str, Any]],
    active_symbols: set
):
    """
    Ensure trades with closed_at timestamp remain CLOSED.

    This prevents the sync functions from re-activating closed trades.
    """
    updates_made = 0

    for trade in db_trades:
        try:
            trade_id = trade.get('id')
            status = str(trade.get('status', '')).upper()
            closed_at = trade.get('closed_at')
            symbol = extract_symbol_from_trade(trade)

            # If trade has closed_at but status is not CLOSED/CANCELLED/FAILED, fix it
            if closed_at and status not in ['CLOSED', 'CANCELLED', 'FAILED']:
                logger.warning(
                    f"Trade {trade_id} ({symbol}) has closed_at={closed_at} but status={status}. "
                    f"Fixing to CLOSED..."
                )

                # Use unified status updater
                success, update_data = await update_trade_status_safely(
                    supabase=supabase,
                    trade_id=trade_id,
                    trade=trade,
                    force_closed=True,
                    bot=None  # Not needed for force_closed=True
                )

                if success:
                    update_data['is_active'] = False
                    update_data['status'] = 'CLOSED'
                    if not update_data.get('order_status'):
                        update_data['order_status'] = 'FILLED'

                    supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                    updates_made += 1
                    logger.info(f"✅ Fixed trade {trade_id} status to CLOSED")
                else:
                    logger.error(f"❌ Failed to update trade {trade_id} status safely")

        except Exception as e:
            logger.error(f"Error ensuring trade {trade.get('id')} stays closed: {e}")

    logger.info(f"Fixed {updates_made} trades that had closed_at but wrong status")


async def verify_status_accuracy(supabase: Client, active_symbols: set):
    """
    Verify that trade statuses match exchange state.

    Reports any inconsistencies found.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    response = supabase.table("trades").select("*").gte("created_at", cutoff).eq("exchange", "kucoin").execute()
    db_trades = response.data or []

    inconsistencies = []

    for trade in db_trades:
        status = str(trade.get('status', '')).upper()
        symbol = extract_symbol_from_trade(trade)
        closed_at = trade.get('closed_at')

        # Check 1: Trade marked ACTIVE but symbol not in active positions
        if status == 'ACTIVE' and symbol:
            if symbol not in active_symbols:
                inconsistencies.append({
                    'trade_id': trade.get('id'),
                    'symbol': symbol,
                    'issue': f'Status is ACTIVE but {symbol} not in active positions',
                    'status': status
                })

        # Check 2: Trade has closed_at but status is not CLOSED
        if closed_at and status not in ['CLOSED', 'CANCELLED', 'FAILED']:
            inconsistencies.append({
                'trade_id': trade.get('id'),
                'symbol': symbol,
                'issue': f'Has closed_at but status is {status}',
                'status': status,
                'closed_at': closed_at
            })

    if inconsistencies:
        logger.warning(f"⚠️  Found {len(inconsistencies)} status inconsistencies:")
        for inc in inconsistencies[:10]:  # Show first 10
            logger.warning(f"  - Trade {inc['trade_id']} ({inc['symbol']}): {inc['issue']}")
        if len(inconsistencies) > 10:
            logger.warning(f"  ... and {len(inconsistencies) - 10} more")
    else:
        logger.info("✅ All trade statuses are accurate!")


async def main():
    """Main entry point"""
    try:
        bot = MinimalBot()
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        await sync_statuses_accurately(bot, supabase)

    except Exception as e:
        logger.error(f"❌ Script failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

