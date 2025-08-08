#!/usr/bin/env python3
"""
Optimized Sync Script for Hybrid WebSocket + Sync Architecture.

This script handles only the functionality that WebSocket cannot cover:
- Historical data backfill
- Database validation and cleanup
- Initial data loading
- Error recovery

WebSocket handles real-time updates for:
- Order status changes
- Position updates
- PnL calculations
- Trade status changes
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from discord_bot.utils.trade_retry_utils import initialize_clients, sync_trade_statuses_with_binance

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [OptimizedSync] - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizedSyncManager:
    """
    Manages optimized sync operations that complement WebSocket real-time updates.
    """

    def __init__(self):
        load_dotenv()
        self.bot, self.supabase = initialize_clients()
        if not self.bot or not self.supabase:
            raise ValueError("Failed to initialize clients")

        self.last_sync_time = None
        self.sync_stats = {
            'historical_backfills': 0,
            'validations': 0,
            'cleanups': 0,
            'errors': 0
        }

    async def run_daily_maintenance(self):
        """
        Run daily maintenance tasks that WebSocket cannot handle.
        """
        try:
            logger.info("🔄 Starting daily maintenance sync (WebSocket handles real-time updates)")

            # 1. Database validation and cleanup
            logger.info("📊 Running database validation and cleanup...")
            await self._validate_and_cleanup_database()

            # 2. Historical data backfill (weekly)
            if self._should_run_weekly_backfill():
                logger.info("📜 Running weekly historical data backfill...")
                await self._backfill_historical_data()

            # 3. Error recovery
            logger.info("🔧 Running error recovery...")
            await self._recover_failed_trades()

            self.last_sync_time = datetime.now(timezone.utc)
            logger.info("✅ Daily maintenance sync completed")

        except Exception as e:
            logger.error(f"❌ Error in daily maintenance sync: {e}")
            self.sync_stats['errors'] += 1

    async def _validate_and_cleanup_database(self):
        """
        Validate database accuracy and cleanup stale data.
        """
        try:
            # Use the existing sync function but with optimized queries
            await sync_trade_statuses_with_binance(self.bot, self.supabase)
            self.sync_stats['validations'] += 1

        except Exception as e:
            logger.error(f"Error in database validation: {e}")
            raise

    async def _backfill_historical_data(self):
        """
        Backfill historical data for trades older than 7 days.
        """
        try:
            # Get trades older than 7 days that need backfill
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            cutoff_iso = cutoff.isoformat()

            # Query for trades that need historical backfill
            response = self.supabase.from_("trades").select("*").lt("createdAt", cutoff_iso).eq("status", "OPEN").execute()

            if response.data:
                logger.info(f"Found {len(response.data)} trades needing historical backfill")

                # Process each trade for historical data
                for trade in response.data:
                    await self._backfill_single_trade(trade)

                self.sync_stats['historical_backfills'] += len(response.data)
            else:
                logger.info("No trades need historical backfill")

        except Exception as e:
            logger.error(f"Error in historical backfill: {e}")
            raise

    async def _backfill_single_trade(self, trade):
        """
        Backfill historical data for a single trade.
        """
        try:
            trade_id = trade['id']
            symbol = trade.get('coin_symbol', '')

            if not symbol:
                logger.warning(f"Trade {trade_id} missing coin_symbol, skipping backfill")
                return

            # Get historical data from Binance
            trading_pair = f"{symbol}USDT"

            # Check if symbol is supported
            is_supported = await self.bot.binance_exchange.is_futures_symbol_supported(trading_pair)
            if not is_supported:
                logger.warning(f"Symbol {trading_pair} not supported, skipping backfill for trade {trade_id}")
                return

            # Get user trades for this symbol
            user_trades = await self.bot.binance_exchange.get_user_trades(symbol=trading_pair, limit=1000)

            if user_trades:
                # Find matching trade by order ID
                order_id = trade.get('exchange_order_id')
                if order_id:
                    matching_trade = next((t for t in user_trades if str(t.get('orderId')) == str(order_id)), None)

                    if matching_trade:
                        # Update trade with historical data
                        updates = {
                            'entry_price': float(matching_trade.get('price', 0)),
                            'realized_pnl': float(matching_trade.get('realizedPnl', 0)),
                            'last_historical_sync': datetime.now(timezone.utc).isoformat(),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }

                        await self.bot.db_manager.update_existing_trade(trade_id, updates)
                        logger.info(f"Backfilled historical data for trade {trade_id}")

        except Exception as e:
            logger.error(f"Error backfilling trade {trade.get('id')}: {e}")

    async def _recover_failed_trades(self):
        """
        Recover trades that failed due to errors.
        """
        try:
            # Find trades with sync errors
            response = self.supabase.from_("trades").select("*").gt("sync_error_count", 0).gte("createdAt", (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()).execute()

            if response.data:
                logger.info(f"Found {len(response.data)} trades with sync errors to recover")

                for trade in response.data:
                    await self._recover_single_trade(trade)

                self.sync_stats['cleanups'] += len(response.data)
            else:
                logger.info("No trades need error recovery")

        except Exception as e:
            logger.error(f"Error in error recovery: {e}")
            raise

    async def _recover_single_trade(self, trade):
        """
        Recover a single failed trade.
        """
        try:
            trade_id = trade['id']
            order_id = trade.get('exchange_order_id')

            if not order_id:
                logger.warning(f"Trade {trade_id} missing order ID, cannot recover")
                return

            # Try to get order status from Binance
            symbol = trade.get('coin_symbol', '')
            if symbol:
                trading_pair = f"{symbol}USDT"

                try:
                    order_status = await self.bot.binance_exchange.get_order_status(trading_pair, order_id)

                    if order_status:
                        # Update trade with recovered data
                        updates = {
                            'order_status': order_status.get('status'),
                            'sync_error_count': 0,
                            'sync_issues': [],
                            'manual_verification_needed': False,
                            'last_successful_sync': datetime.now(timezone.utc).isoformat(),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }

                        await self.bot.db_manager.update_existing_trade(trade_id, updates)
                        logger.info(f"Recovered trade {trade_id}")

                except Exception as e:
                    logger.warning(f"Could not recover trade {trade_id}: {e}")

        except Exception as e:
            logger.error(f"Error recovering trade {trade.get('id')}: {e}")

    def _should_run_weekly_backfill(self) -> bool:
        """
        Check if weekly backfill should run (once per week).
        """
        if not self.last_sync_time:
            return True

        # Run weekly backfill if it's been more than 7 days
        days_since_last = (datetime.now(timezone.utc) - self.last_sync_time).days
        return days_since_last >= 7

    def get_sync_stats(self) -> dict:
        """
        Get sync statistics.
        """
        return {
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'sync_stats': self.sync_stats.copy(),
            'next_weekly_backfill': self._should_run_weekly_backfill()
        }

async def main():
    """Main function to run the optimized sync."""
    try:
        logger.info("🚀 Starting Optimized Sync Manager...")

        sync_manager = OptimizedSyncManager()

        # Run daily maintenance
        await sync_manager.run_daily_maintenance()

        # Print statistics
        stats = sync_manager.get_sync_stats()
        logger.info(f"📊 Sync Statistics: {stats}")

        logger.info("✅ Optimized sync completed successfully")

    except Exception as e:
        logger.error(f"❌ Optimized sync failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)