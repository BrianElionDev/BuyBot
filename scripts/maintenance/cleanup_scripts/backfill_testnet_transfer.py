#!/usr/bin/env python3
"""
Script to backfill all trades from before August 7th, 2025 as closed
due to transfer from testnet to mainnet.

This script will:
1. Find all trades with status 'OPEN' or other non-closed statuses
2. Mark them as 'CLOSED' with reason "Transfer from testnet to mainnet"
3. Update order_status to 'CLOSED' as well
4. Set appropriate timestamps and metadata
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config import settings
from supabase import create_client, Client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
CUTOFF_DATE = "2025-08-07T23:59:59.999Z"  # August 7th, 2025 23:59:59
TRANSFER_REASON = "Transfer from testnet to mainnet"

async def backfill_testnet_transfer():
    """
    Backfill all trades from before August 7th, 2025 as closed.
    """
    try:
        # Load environment variables
        load_dotenv()

        # Initialize Supabase client
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY

        if not supabase_url or not supabase_key:
            logger.error("❌ Supabase credentials not found in environment")
            return

        supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("✅ Supabase client initialized")

        # Find all trades that need to be closed
        logger.info("🔍 Finding trades to backfill...")

        # Query for trades that are not already closed and are before the cutoff date
        response = supabase.from_("trades").select("*").or_(
            f"status.neq.CLOSED,order_status.neq.CLOSED"
        ).lt("created_at", CUTOFF_DATE).execute()

        if not response.data:
            logger.info("✅ No trades found that need backfilling")
            return

        trades_to_update = response.data
        logger.info(f"📊 Found {len(trades_to_update)} trades to backfill")

        # Process trades in batches to avoid overwhelming the database
        batch_size = 50
        total_updated = 0

        for i in range(0, len(trades_to_update), batch_size):
            batch = trades_to_update[i:i + batch_size]
            logger.info(f"🔄 Processing batch {i//batch_size + 1}/{(len(trades_to_update) + batch_size - 1)//batch_size}")

            # Update each trade in the batch
            for trade in batch:
                trade_id = trade['id']
                discord_id = trade.get('discord_id', 'Unknown')

                try:
                    # Prepare update data
                    update_data = {
                        'status': 'CLOSED',
                        'order_status': 'CLOSED',
                        'updated_at': datetime.now(timezone.utc).isoformat(),
                        'is_active': False,
                        'manual_verification_needed': False,
                        'sync_issues': [TRANSFER_REASON] if trade.get('sync_issues') else [TRANSFER_REASON]
                    }

                    # Update the trade
                    update_response = supabase.from_("trades").update(update_data).eq("id", trade_id).execute()

                    if update_response.data:
                        total_updated += 1
                        logger.info(f"✅ Updated trade {trade_id} ({discord_id}) - Status: CLOSED")
                    else:
                        logger.warning(f"⚠️ Failed to update trade {trade_id} ({discord_id})")

                except Exception as e:
                    logger.error(f"❌ Error updating trade {trade_id} ({discord_id}): {e}")
                    continue

            # Small delay between batches to be respectful to the database
            if i + batch_size < len(trades_to_update):
                await asyncio.sleep(0.1)

        # Final summary
        logger.info("=" * 60)
        logger.info("🎯 BACKFILL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"📊 Total trades processed: {len(trades_to_update)}")
        logger.info(f"✅ Successfully updated: {total_updated}")
        logger.info(f"❌ Failed updates: {len(trades_to_update) - total_updated}")
        logger.info(f"📅 Cutoff date: {CUTOFF_DATE}")
        logger.info(f"🏷️ Reason: {TRANSFER_REASON}")
        logger.info("=" * 60)

        # Verify the changes
        logger.info("🔍 Verifying changes...")
        verify_response = supabase.from_("trades").select("id, status, order_status").lt("created_at", CUTOFF_DATE).execute()

        if verify_response.data:
            open_trades = [t for t in verify_response.data if t.get('status') != 'CLOSED' or t.get('order_status') != 'CLOSED']
            if open_trades:
                logger.warning(f"⚠️ Found {len(open_trades)} trades still not marked as CLOSED")
                for trade in open_trades[:5]:  # Show first 5
                    logger.warning(f"  - Trade {trade['id']}: status={trade.get('status')}, order_status={trade.get('order_status')}")
            else:
                logger.info("✅ All trades before cutoff date are now marked as CLOSED")

        logger.info("🎉 Backfill process completed successfully!")

    except Exception as e:
        logger.error(f"❌ Fatal error during backfill: {e}")
        raise

async def main():
    """Main function to run the backfill."""
    print("=" * 70)
    print("           TESTNET TO MAINNET TRANSFER BACKFILL")
    print("=" * 70)
    print(f"📅 Cutoff Date: {CUTOFF_DATE}")
    print(f"🏷️ Reason: {TRANSFER_REASON}")
    print("=" * 70)

    # Confirmation prompt
    response = input("\n⚠️  This will mark ALL trades before August 7th, 2025 as CLOSED.\nAre you sure you want to continue? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("❌ Operation cancelled by user")
        return

    print("\n🚀 Starting backfill process...")
    await backfill_testnet_transfer()

if __name__ == "__main__":
    asyncio.run(main())
