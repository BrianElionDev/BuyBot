#!/usr/bin/env python3
"""
Standalone script to backfill trades table with PnL and exit price data from Binance history.
This script can be run independently of the main sync process.

Usage:
    python scripts/backfill_trades_from_history.py --days 30
    python scripts/backfill_trades_from_history.py --symbol BTCUSDT --days 7
    python scripts/backfill_trades_from_history.py --all-symbols --days 14
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from discord_bot.utils.trade_retry_utils import initialize_clients, backfill_trades_from_binance_history

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    """Main function to run the trade backfill."""
    parser = argparse.ArgumentParser(description="Backfill trades from Binance history")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back")
    parser.add_argument("--symbol", default="", help="Trading pair symbol (e.g., BTCUSDT)")
    parser.add_argument("--all-symbols", action="store_true", help="Process all symbols (overrides --symbol)")

    args = parser.parse_args()

    logging.info("--- Starting Trade Backfill from Binance History ---")

    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logging.error("Failed to initialize clients.")
        return

    try:
        if args.all_symbols:
            # Process all symbols (empty string means all symbols)
            symbol = ""
            logging.info(f"Backfilling trades for all symbols from last {args.days} days")
        else:
            symbol = args.symbol
            if symbol:
                logging.info(f"Backfilling trades for {symbol} from last {args.days} days")
            else:
                logging.info(f"Backfilling trades for all symbols from last {args.days} days")

        await backfill_trades_from_binance_history(bot, supabase, days=args.days, symbol=symbol)
        logging.info("--- Trade Backfill Complete ---")

    except Exception as e:
        logging.error(f"Error during backfill: {e}", exc_info=True)
    finally:
        if bot and bot.binance_exchange:
            await bot.binance_exchange.close()
            logging.info("Binance client connection closed.")

if __name__ == "__main__":
    asyncio.run(main())