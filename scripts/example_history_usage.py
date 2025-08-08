#!/usr/bin/env python3
"""
Example usage of the Binance History Analyzer
This script demonstrates how to use the history analyzer for different scenarios.
"""

import asyncio
import sys
from pathlib import Path
import os

# Add the project root to the path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.binance_history_analyzer import BinanceHistoryBackfiller


async def example_usage():
    """Example usage of the Binance History Analyzer."""

    # Initialize the analyzer
    analyzer = BinanceHistoryBackfiller(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "false") == "true"
    )

    try:
        # Initialize connection
        if not await analyzer.initialize():
            print("❌ Failed to initialize Binance connection")
            return

        print("🚀 Binance History Analyzer Examples")
        print("=" * 50)

        # Example 1: Get all history for the last 7 days
        print("\n📊 Example 1: All history for last 7 days")
        await analyzer.run_backfill(days=7)

        # Example 2: Get trade history for a specific symbol
        print("\n📊 Example 2: Trade history for BTCUSDT (last 30 days)")
        await analyzer.run_backfill(symbol="BTCUSDT", days=30)

        # Example 3: Get order history for all symbols
        print("\n📋 Example 3: Order history for all symbols (last 1 day)")
        await analyzer.run_backfill(days=1)

        # Example 4: Get transaction history
        print("\n💰 Example 4: Transaction history (last 90 days)")
        await analyzer.run_backfill(days=90)

        print("\n✅ All examples completed! Check the logs/binance_history/ directory for results.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await analyzer.close()


if __name__ == "__main__":
    asyncio.run(example_usage())