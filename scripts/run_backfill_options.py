#!/usr/bin/env python3
"""
Script to run the backfill with different options for testing and production use.
"""

import asyncio
import logging
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.backfill_from_historical_trades import HistoricalTradeBackfillManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def run_missing_only(days: int = 14):
    """Run backfill for missing prices only."""
    logger.info(f"=== Running backfill for missing prices only (last {days} days) ===")
    backfill_manager = HistoricalTradeBackfillManager()
    await backfill_manager.backfill_from_historical_data(days=days, update_existing=False)


async def run_existing_only(days: int = 14):
    """Run backfill for existing prices only (for accuracy improvement)."""
    logger.info(f"=== Running backfill for existing prices only (last {days} days) ===")
    backfill_manager = HistoricalTradeBackfillManager()
    await backfill_manager.backfill_from_historical_data(days=days, update_existing=True)


async def run_both_phases(days: int = 14):
    """Run both phases: missing first, then existing for accuracy."""
    logger.info(f"=== Running both phases (last {days} days) ===")
    backfill_manager = HistoricalTradeBackfillManager()
    
    # Phase 1: Missing prices
    logger.info("Phase 1: Filling missing prices...")
    await backfill_manager.backfill_from_historical_data(days=days, update_existing=False)
    
    # Phase 2: Existing prices for accuracy
    logger.info("Phase 2: Updating existing prices for accuracy...")
    await backfill_manager.backfill_from_historical_data(days=days, update_existing=True)


async def main():
    """Main function with options."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Binance price backfill with different options')
    parser.add_argument('--mode', choices=['missing', 'existing', 'both'], default='both',
                       help='Backfill mode: missing (missing only), existing (existing only), both (both phases)')
    parser.add_argument('--days', type=int, default=14,
                       help='Number of days to look back (default: 14)')
    
    args = parser.parse_args()
    
    try:
        if args.mode == 'missing':
            await run_missing_only(args.days)
        elif args.mode == 'existing':
            await run_existing_only(args.days)
        elif args.mode == 'both':
            await run_both_phases(args.days)
        
        logger.info("✅ Backfill completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error during backfill: {e}")


if __name__ == "__main__":
    asyncio.run(main())
