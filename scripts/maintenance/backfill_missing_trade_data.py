"""
One-time backfill script to populate missing entry_price, exit_price, position_size, and pnl_usd.

Run this once to backfill all historical trades with missing data.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from discord_bot.discord_bot import DiscordBot
from discord_bot.utils.trade_retry_utils import sync_missing_trade_data_comprehensive

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    """Run one-time backfill for missing trade data."""
    logger.info("🚀 Starting one-time backfill for missing trade data...")

    # Initialize clients
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.error("❌ Missing SUPABASE_URL or SUPABASE_KEY in environment")
        return

    supabase: Client = create_client(supabase_url, supabase_key)
    bot = DiscordBot()

    if not bot or not supabase:
        logger.error("❌ Failed to initialize clients")
        return

    logger.info("✅ Clients initialized")

    # Run backfill for different time periods
    periods = [
        (30, "30 days"),
        (90, "90 days"),
        (180, "180 days"),
    ]

    total_updated = 0

    for days, label in periods:
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 Backfilling trades from last {label}...")
        logger.info(f"{'='*60}\n")

        try:
            result = await sync_missing_trade_data_comprehensive(bot, supabase, days_back=days)

            if isinstance(result, dict):
                trades_updated = result.get('trades_updated', 0)
                total_updated += int(trades_updated)

                logger.info(f"\n✅ Completed {label} backfill:")
                logger.info(f"   - Trades updated: {trades_updated}")
                if 'updates_by_field' in result:
                    for field, count in result['updates_by_field'].items() if isinstance(result['updates_by_field'], dict) else {}:
                        logger.info(f"   - {field}: {count} updates")
            else:
                logger.warning(f"Unexpected result format: {result}")

        except Exception as e:
            logger.error(f"❌ Error backfilling {label}: {e}", exc_info=True)

    logger.info(f"\n{'='*60}")
    logger.info(f"🎉 Backfill completed! Total trades updated: {total_updated}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())