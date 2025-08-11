#!/usr/bin/env python3
"""
Backfill coin_symbol column in trades table from parsed_signal JSON data.
This script extracts the coin_symbol from the parsed_signal JSON and updates the coin_symbol column.
"""

import os
import sys
import json
import logging
from typing import List, Dict, Optional
from config import settings

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from supabase import create_client, Client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_supabase() -> Optional[Client]:
    """Initialize Supabase client."""
    try:
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY

        if not supabase_url or not supabase_key:
            logger.error("Missing Supabase credentials")
            return None

        return create_client(supabase_url, supabase_key)

    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None

def extract_coin_symbol_from_parsed_signal(parsed_signal) -> Optional[str]:
    """Extract coin_symbol from parsed_signal (can be JSON string or dict)."""
    try:
        if not parsed_signal:
            return None

        # Handle different types of parsed_signal
        if isinstance(parsed_signal, dict):
            # Already a dictionary
            signal_data = parsed_signal
        elif isinstance(parsed_signal, str):
            # JSON string - parse it
            if not parsed_signal.strip():
                return None
            signal_data = json.loads(parsed_signal)
        else:
            logger.warning(f"Unexpected parsed_signal type: {type(parsed_signal)}")
            return None

        # Extract coin_symbol
        coin_symbol = signal_data.get('coin_symbol')

        if coin_symbol:
            # Ensure it's uppercase and clean
            return str(coin_symbol).strip().upper()

        return None

    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        logger.warning(f"Failed to parse parsed_signal: {e}")
        return None

def get_trades_without_coin_symbol(supabase: Client, limit: int = 100, offset: int = 0) -> List[Dict]:
    """Get trades that have parsed_signal but missing coin_symbol."""
    try:
        response = supabase.table("trades").select(
            "id, parsed_signal, coin_symbol"
        ).not_.is_("parsed_signal", "null").is_("coin_symbol", "null").range(offset, offset + limit - 1).execute()

        return response.data or []

    except Exception as e:
        logger.error(f"Failed to fetch trades: {e}")
        return []

def update_coin_symbol(supabase: Client, trade_id: int, coin_symbol: str) -> bool:
    """Update coin_symbol for a specific trade."""
    try:
        response = supabase.table("trades").update({
            "coin_symbol": coin_symbol,
            "updated_at": "now()"
        }).eq("id", trade_id).execute()

        return len(response.data) > 0

    except Exception as e:
        logger.error(f"Failed to update trade {trade_id}: {e}")
        return False

def backfill_coin_symbols(batch_size: int = 100):
    """Main function to backfill coin_symbol column."""
    logger.info("🚀 Starting coin_symbol backfill process...")

    # Initialize Supabase
    supabase = initialize_supabase()
    if not supabase:
        logger.error("❌ Failed to initialize Supabase client")
        return

    total_updated = 0
    total_processed = 0
    offset = 0

    while True:
        # Get batch of trades
        trades = get_trades_without_coin_symbol(supabase, batch_size, offset)

        if not trades:
            logger.info(f"✅ No more trades to process. Total processed: {total_processed}, Total updated: {total_updated}")
            break

        logger.info(f"📊 Processing batch of {len(trades)} trades (offset: {offset})")

        batch_updated = 0

        for trade in trades:
            trade_id = trade['id']
            parsed_signal = trade['parsed_signal']

            # Extract coin_symbol from parsed_signal
            coin_symbol = extract_coin_symbol_from_parsed_signal(parsed_signal)

            if coin_symbol:
                # Update the trade
                success = update_coin_symbol(supabase, trade_id, coin_symbol)
                if success:
                    batch_updated += 1
                    logger.info(f"✅ Updated trade {trade_id} with coin_symbol: {coin_symbol}")
                else:
                    logger.warning(f"❌ Failed to update trade {trade_id}")
            else:
                logger.warning(f"⚠️ Could not extract coin_symbol from trade {trade_id}")

        total_updated += batch_updated
        total_processed += len(trades)

        logger.info(f"📈 Batch complete: {batch_updated}/{len(trades)} updated")
        logger.info(f"📊 Progress: {total_updated}/{total_processed} total updated")

        # Move to next batch
        offset += batch_size

        # Add a small delay to avoid overwhelming the database
        import time
        time.sleep(0.1)

    logger.info(f"🎉 Backfill complete! Total trades processed: {total_processed}, Total updated: {total_updated}")

def verify_backfill(supabase: Client, sample_size: int = 10):
    """Verify the backfill by showing some sample results."""
    try:
        logger.info("🔍 Verifying backfill results...")

        # Get some sample trades that were updated
        response = supabase.table("trades").select(
            "id, coin_symbol, parsed_signal"
        ).not_.is_("coin_symbol", "null").not_.is_("parsed_signal", "null").limit(sample_size).execute()

        trades = response.data or []

        logger.info(f"📋 Sample of updated trades:")
        for trade in trades:
            trade_id = trade['id']
            coin_symbol = trade['coin_symbol']
            parsed_signal = trade['parsed_signal']

            # Extract coin_symbol from parsed_signal to verify
            extracted_symbol = extract_coin_symbol_from_parsed_signal(parsed_signal)

            status = "✅" if coin_symbol == extracted_symbol else "❌"
            logger.info(f"{status} Trade {trade_id}: {coin_symbol} (extracted: {extracted_symbol})")

    except Exception as e:
        logger.error(f"Failed to verify backfill: {e}")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill coin_symbol column from parsed_signal")
    parser.add_argument("--batch-size", type=int, default=100, help="Number of trades to process per batch")
    parser.add_argument("--verify", action="store_true", help="Verify the backfill results")

    args = parser.parse_args()

    # Run the backfill
    backfill_coin_symbols(args.batch_size)

    # Verify if requested
    if args.verify:
        supabase = initialize_supabase()
        if supabase:
            verify_backfill(supabase)

if __name__ == "__main__":
    main()