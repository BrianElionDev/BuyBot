#!/usr/bin/env python3
"""
Sync PNL from Binance Income History for Past 30 Days

This script queries Binance income history for the past 30 days and matches
PNL values to trades in the database. Only updates trades with empty/null/0 PNL.

Usage:
    python scripts/maintenance/sync_pnl_from_binance.py
    python scripts/maintenance/sync_pnl_from_binance.py --days 7
    python scripts/maintenance/sync_pnl_from_binance.py --symbol FARTCOIN
"""

import asyncio
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from discord_bot.discord_bot import DiscordBot
from discord_bot.utils.trade_retry_utils import (
    get_order_lifecycle,
    get_income_for_trade_period,
    extract_symbol_from_trade
)
import config.settings as settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BinancePnLSyncer:
    """Syncs PNL from Binance income history to database trades."""

    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        self.bot = None
        self.supabase = None
        self.stats = {
            'total_trades': 0,
            'skipped_has_pnl': 0,
            'skipped_no_symbol': 0,
            'skipped_no_timestamps': 0,
            'skipped_no_income': 0,
            'updated': 0,
            'errors': 0
        }

    async def initialize(self):
        """Initialize bot and database."""
        try:
            self.bot = DiscordBot()
            self.supabase = self.bot.supabase

            if not self.bot.binance_exchange.client:
                await self.bot.binance_exchange._init_client()

            logger.info("✅ Bot and database initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    async def get_trades_needing_pnl(self, symbol: str = "", days: int = 30) -> List[Dict]:
        """Get closed trades from past N days that need PNL (empty/null/0)."""
        try:
            if not self.supabase:
                logger.error("Supabase client not initialized")
                return []

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            query = (
                self.supabase
                .from_("trades")
                .select("*")
                .eq("status", "CLOSED")
                .eq("exchange", "binance")
                .gte("created_at", cutoff_iso)
            )

            if symbol:
                query = query.eq("coin_symbol", symbol)

            response = query.execute()
            all_trades = response.data or []

            trades_needing_pnl = []
            for trade in all_trades:
                pnl_usd = trade.get('pnl_usd')
                if pnl_usd is None or pnl_usd == '' or float(pnl_usd or 0) == 0:
                    trades_needing_pnl.append(trade)
                else:
                    self.stats['skipped_has_pnl'] += 1

            logger.info(f"Found {len(trades_needing_pnl)} trades needing PNL out of {len(all_trades)} total closed trades")
            return trades_needing_pnl

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    async def sync_trade_pnl(self, trade: Dict) -> bool:
        """Sync PNL for a single trade from Binance income history."""
        trade_id = trade.get('id')
        if not trade_id:
            return False

        try:
            symbol = extract_symbol_from_trade(trade)
            if not symbol:
                logger.warning(f"Trade {trade_id}: No symbol found, skipping")
                self.stats['skipped_no_symbol'] += 1
                return False

            start_time, end_time, duration = get_order_lifecycle(trade)
            if not start_time or not end_time:
                logger.warning(f"Trade {trade_id}: No valid timestamps, skipping")
                self.stats['skipped_no_timestamps'] += 1
                return False

            logger.info(f"Trade {trade_id} ({symbol}): Fetching income history from {start_time} to {end_time}")

            income_records = await get_income_for_trade_period(
                self.bot,
                symbol,
                start_time,
                end_time,
                expand=True,
                buffer_after_ms=86400000
            )

            if not income_records:
                logger.warning(f"Trade {trade_id} ({symbol}): No income records found")
                self.stats['skipped_no_income'] += 1
                return False

            total_realized_pnl = 0.0
            total_commission = 0.0
            total_funding_fee = 0.0
            exit_price = 0.0

            for income in income_records:
                if not isinstance(income, dict):
                    continue

                income_type = income.get('incomeType') or income.get('type')
                income_value = float(income.get('income', 0.0))

                if income_type == 'REALIZED_PNL':
                    total_realized_pnl += income_value
                    if income.get('price'):
                        exit_price = float(income.get('price', 0.0))
                elif income_type == 'COMMISSION':
                    total_commission += income_value
                elif income_type == 'FUNDING_FEE':
                    total_funding_fee += income_value

            net_pnl = total_realized_pnl + total_commission + total_funding_fee

            realized_pnl_records = [
                r for r in income_records
                if isinstance(r, dict) and (r.get('incomeType') or r.get('type')) == 'REALIZED_PNL'
            ]

            if not realized_pnl_records:
                logger.warning(f"Trade {trade_id} ({symbol}): No REALIZED_PNL records found")
                self.stats['skipped_no_income'] += 1
                return False

            update_data = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'pnl_usd': str(total_realized_pnl),
                'net_pnl': str(net_pnl),
                'last_pnl_sync': datetime.now(timezone.utc).isoformat(),
                'pnl_source': 'binance_income_history',
                'pnl_verified': True
            }

            if exit_price > 0 and not trade.get('exit_price'):
                update_data['exit_price'] = str(exit_price)
                update_data['price_source'] = 'binance_income_history'

            if not trade.get('closed_at') and trade.get('status') == 'CLOSED':
                from discord_bot.utils.timestamp_manager import fix_historical_timestamps
                await fix_historical_timestamps(self.supabase, trade_id)

            response = self.supabase.from_("trades").update(update_data).eq("id", trade_id).execute()

            if response.data:
                logger.info(
                    f"✅ Trade {trade_id} ({symbol}): Updated PNL={total_realized_pnl:.6f}, "
                    f"NET={net_pnl:.6f} (from {len(realized_pnl_records)} records)"
                )
                self.stats['updated'] += 1
                return True
            else:
                logger.warning(f"Trade {trade_id}: Update returned no data")
                return False

        except Exception as e:
            logger.error(f"Error syncing PNL for trade {trade_id}: {e}", exc_info=True)
            self.stats['errors'] += 1
            return False

    async def sync_all_trades(self, symbol: str = "", days: int = 30):
        """Sync PNL for all trades needing it."""
        try:
            trades = await self.get_trades_needing_pnl(symbol=symbol, days=days)
            self.stats['total_trades'] = len(trades)

            if not trades:
                logger.info("No trades need PNL syncing")
                return

            logger.info(f"Processing {len(trades)} trades...")

            for i, trade in enumerate(trades, 1):
                logger.info(f"[{i}/{len(trades)}] Processing trade {trade.get('id')}")
                await self.sync_trade_pnl(trade)
                await asyncio.sleep(0.5)

            self.print_stats()

        except Exception as e:
            logger.error(f"Error in sync_all_trades: {e}", exc_info=True)

    def print_stats(self):
        """Print synchronization statistics."""
        logger.info("=" * 60)
        logger.info("SYNC STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total trades processed: {self.stats['total_trades']}")
        logger.info(f"✅ Successfully updated: {self.stats['updated']}")
        logger.info(f"⏭️  Skipped (has PNL): {self.stats['skipped_has_pnl']}")
        logger.info(f"⏭️  Skipped (no symbol): {self.stats['skipped_no_symbol']}")
        logger.info(f"⏭️  Skipped (no timestamps): {self.stats['skipped_no_timestamps']}")
        logger.info(f"⏭️  Skipped (no income): {self.stats['skipped_no_income']}")
        logger.info(f"❌ Errors: {self.stats['errors']}")
        logger.info("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='Sync PNL from Binance income history')
    parser.add_argument('--days', type=int, default=30, help='Number of days to look back (default: 30)')
    parser.add_argument('--symbol', type=str, default='', help='Filter by symbol (e.g., FARTCOIN)')
    parser.add_argument('--testnet', action='store_true', help='Use testnet')
    args = parser.parse_args()

    syncer = BinancePnLSyncer(testnet=args.testnet)

    if not await syncer.initialize():
        logger.error("Failed to initialize syncer")
        return

    await syncer.sync_all_trades(symbol=args.symbol, days=args.days)

    if syncer.bot and syncer.bot.binance_exchange:
        try:
            await syncer.bot.binance_exchange.close()
        except Exception:
            pass


if __name__ == '__main__':
    asyncio.run(main())



