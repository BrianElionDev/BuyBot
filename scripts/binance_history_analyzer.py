#!/usr/bin/env python3
"""
Binance History Backfiller
Script to backfill the trades table with PnL and exit price data from Binance history.
Uses exchange_order_id to link Binance data with database records.

Usage:
    python scripts/binance_history_analyzer.py --days 30
    python scripts/binance_history_analyzer.py --symbol BTCUSDT --days 7
    python scripts/binance_history_analyzer.py --backfill-only
"""

import asyncio
import argparse
import json
import logging
from datetime import datetime, timezone, timedelta
import os
from typing import Dict, List, Any, Optional
import pandas as pd
from pathlib import Path

# Add the project root to the path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.exchange.binance_exchange import BinanceExchange
from discord_bot.utils.trade_retry_utils import initialize_clients, safe_parse_binance_response

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BinanceHistoryBackfiller:
    """Backfills trades table with PnL and exit price data from Binance history."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.binance_exchange = BinanceExchange(api_key, api_secret, testnet)
        self.results_dir = Path("logs/binance_history")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.bot, self.supabase = initialize_clients()
        if not self.supabase:
            raise ValueError("Failed to initialize Supabase client")

    async def initialize(self):
        """Initialize the Binance client."""
        try:
            await self.binance_exchange._init_client()
            logger.info("✅ Binance client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Binance client: {e}")
            return False

    def calculate_pnl(self, entry_price: float, exit_price: float, position_size: float, position_type: str, fees: float = 0.001) -> float:
        """Calculate PnL for a trade."""
        try:
            if position_type.upper() == 'LONG':
                # For long positions: (exit_price - entry_price) * position_size - fees
                pnl = (exit_price - entry_price) * position_size
            else:
                # For short positions: (entry_price - exit_price) * position_size - fees
                pnl = (entry_price - exit_price) * position_size

            # Subtract fees
            pnl -= (entry_price * position_size * fees) + (exit_price * position_size * fees)

            return pnl
        except Exception as e:
            logger.error(f"Error calculating PnL: {e}")
            return 0.0

    async def get_trades_needing_backfill(self, days: int = 30) -> List[Dict]:
        """Get trades from database that need PnL/exit price backfilling."""
        try:
            if not self.supabase:
                logger.error("Supabase client not initialized")
                return []

            # Get trades from last N days that are closed but missing PnL or exit price
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Query for closed trades missing PnL or exit price data
            response = self.supabase.from_("trades").select("*").eq("status", "CLOSED").gte("createdAt", cutoff_iso).execute()
            trades = response.data or []

            # Filter for trades missing PnL or exit price
            trades_needing_backfill = []
            for trade in trades:
                pnl = trade.get('pnl_usd')
                exit_price = trade.get('binance_exit_price')
                order_id = trade.get('exchange_order_id')

                # Include if missing PnL or exit price and has order ID
                if order_id and (pnl is None or pnl == 0 or exit_price is None or exit_price == 0):
                    trades_needing_backfill.append(trade)

            logger.info(f"Found {len(trades_needing_backfill)} trades needing backfill out of {len(trades)} closed trades")
            return trades_needing_backfill

        except Exception as e:
            logger.error(f"Error fetching trades needing backfill: {e}")
            return []

    async def get_binance_trade_history(self, symbol: str = "", limit: int = 1000,
                                       from_id: int = 0, start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """Get user trade history from Binance with 7-day chunking to comply with API limits."""
        try:
            logger.info(f"📊 Fetching Binance trade history for {symbol or 'all symbols'}...")

            all_trades = []

            # If we have a time range, fetch in 7-day chunks
            if start_time > 0 and end_time > start_time:
                chunk_start = start_time
                while chunk_start < end_time:
                    chunk_end = min(chunk_start + (7 * 24 * 60 * 60 * 1000), end_time)  # 7 days in milliseconds

                    logger.info(f"Fetching trades from {datetime.fromtimestamp(chunk_start/1000, tz=timezone.utc)} to {datetime.fromtimestamp(chunk_end/1000, tz=timezone.utc)}")

                    try:
                        chunk_trades = await self.binance_exchange.get_user_trades(
                            symbol=symbol,
                            limit=limit,
                            from_id=from_id,
                            start_time=chunk_start,
                            end_time=chunk_end
                        )
                        all_trades.extend(chunk_trades)
                        await asyncio.sleep(0.5)  # Rate limiting between chunks
                    except Exception as e:
                        logger.error(f"Error fetching chunk trades: {e}")

                    chunk_start = chunk_end
            else:
                # Single request without time range
                all_trades = await self.binance_exchange.get_user_trades(
                    symbol=symbol,
                    limit=limit,
                    from_id=from_id,
                    start_time=start_time,
                    end_time=end_time
                )

            logger.info(f"✅ Retrieved {len(all_trades)} trade records from Binance")
            return all_trades

        except Exception as e:
            logger.error(f"❌ Error fetching Binance trade history: {e}")
            return []

    async def get_binance_order_history(self, symbol: str = "", limit: int = 500,
                                       start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """Get order history from Binance with 7-day chunking to comply with API limits."""
        try:
            logger.info(f"📋 Fetching Binance order history for {symbol or 'all symbols'}...")

            all_orders = []

            # If we have a time range, fetch in 7-day chunks
            if start_time > 0 and end_time > start_time:
                chunk_start = start_time
                while chunk_start < end_time:
                    chunk_end = min(chunk_start + (7 * 24 * 60 * 60 * 1000), end_time)  # 7 days in milliseconds

                    logger.info(f"Fetching orders from {datetime.fromtimestamp(chunk_start/1000, tz=timezone.utc)} to {datetime.fromtimestamp(chunk_end/1000, tz=timezone.utc)}")

                    try:
                        chunk_orders = await self.binance_exchange.get_order_history(
                            symbol=symbol,
                            limit=limit,
                            start_time=chunk_start,
                            end_time=chunk_end
                        )
                        all_orders.extend(chunk_orders)
                        await asyncio.sleep(0.5)  # Rate limiting between chunks
                    except Exception as e:
                        logger.error(f"Error fetching chunk orders: {e}")

                    chunk_start = chunk_end
            else:
                # Single request without time range
                all_orders = await self.binance_exchange.get_order_history(
                    symbol=symbol,
                    limit=limit,
                    start_time=start_time,
                    end_time=end_time
                )

            logger.info(f"✅ Retrieved {len(all_orders)} order records from Binance")
            return all_orders

        except Exception as e:
            logger.error(f"❌ Error fetching Binance order history: {e}")
            return []

    async def backfill_trade_data(self, trade: Dict, binance_trades: List[Dict], binance_orders: List[Dict]) -> bool:
        """Backfill a single trade with PnL and exit price data."""
        try:
            trade_id = trade.get('id')
            order_id = trade.get('exchange_order_id')
            symbol = trade.get('coin_symbol')

            if not order_id or not symbol:
                logger.warning(f"Trade {trade_id} missing order_id or symbol")
                return False

            # Find matching Binance trades for this order
            matching_trades = [t for t in binance_trades if str(t.get('orderId')) == str(order_id)]

            if not matching_trades:
                logger.warning(f"No Binance trades found for order {order_id} (trade {trade_id})")
                return False

            # Find matching Binance order
            matching_order = None
            for order in binance_orders:
                if str(order.get('orderId')) == str(order_id):
                    matching_order = order
                    break

            # Calculate exit price and PnL
            exit_price = 0.0
            realized_pnl = 0.0

            # Use Binance realized PnL if available
            for binance_trade in matching_trades:
                realized_pnl += float(binance_trade.get('realizedPnl', 0.0))
                # Use the last trade's price as exit price
                exit_price = float(binance_trade.get('price', 0.0))

            # If no realized PnL from Binance, calculate it
            if realized_pnl == 0.0 and exit_price > 0:
                entry_price = trade.get('entry_price', 0.0)
                position_size = trade.get('position_size', 0.0)
                position_type = trade.get('signal_type', 'LONG')

                if entry_price > 0 and position_size > 0:
                    realized_pnl = self.calculate_pnl(entry_price, exit_price, position_size, position_type)

            # Prepare update data
            update_data = {
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Only update if we have valid data
            if exit_price > 0:
                update_data['binance_exit_price'] = str(exit_price)

            if realized_pnl != 0:
                update_data['pnl_usd'] = str(realized_pnl)
                update_data['realized_pnl'] = str(realized_pnl)

            # Update the trade in database
            if len(update_data) > 1:  # More than just updated_at
                if not self.supabase:
                    logger.error("Supabase client not initialized")
                    return False
                self.supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                logger.info(f"✅ Updated trade {trade_id} - Exit Price: {exit_price}, PnL: {realized_pnl}")
                return True
            else:
                logger.warning(f"No valid data to update for trade {trade_id}")
                return False

        except Exception as e:
            logger.error(f"Error backfilling trade {trade.get('id')}: {e}")
            return False

    async def backfill_trades_from_history(self, days: int = 30, symbol: str = "") -> Dict[str, Any]:
        """Main function to backfill trades with history data."""
        logger.info(f"🚀 Starting trade backfill for last {days} days")

        # Calculate time range
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

        # Get trades needing backfill
        trades_needing_backfill = await self.get_trades_needing_backfill(days)

        if not trades_needing_backfill:
            logger.info("No trades need backfilling")
            return {"status": "success", "trades_processed": 0, "trades_updated": 0}

        # Get Binance history data
        binance_trades = await self.get_binance_trade_history(
            symbol=f"{symbol}USDT" if symbol else "",
            start_time=start_time,
            end_time=end_time
        )

        binance_orders = await self.get_binance_order_history(
            symbol=f"{symbol}USDT" if symbol else "",
            start_time=start_time,
            end_time=end_time
        )

        # Process each trade
        trades_updated = 0
        for trade in trades_needing_backfill:
            success = await self.backfill_trade_data(trade, binance_trades, binance_orders)
            if success:
                trades_updated += 1
            await asyncio.sleep(0.1)  # Rate limiting

        logger.info(f"✅ Backfill completed: {trades_updated}/{len(trades_needing_backfill)} trades updated")

        return {
            "status": "success",
            "trades_processed": len(trades_needing_backfill),
            "trades_updated": trades_updated,
            "binance_trades_fetched": len(binance_trades),
            "binance_orders_fetched": len(binance_orders)
        }

    def analyze_backfill_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze backfill results for reporting."""
        return {
            "backfill_summary": {
                "total_trades_processed": results.get("trades_processed", 0),
                "trades_successfully_updated": results.get("trades_updated", 0),
                "success_rate": f"{(results.get('trades_updated', 0) / max(results.get('trades_processed', 1), 1)) * 100:.1f}%",
                "binance_data_availability": {
                    "trades_fetched": results.get("binance_trades_fetched", 0),
                    "orders_fetched": results.get("binance_orders_fetched", 0)
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def save_analysis_results(self, analysis: Dict[str, Any], timestamp: str = "") -> None:
        """Save only the analysis results (not raw data)."""
        timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save analysis
        analysis_file = self.results_dir / f"backfill_analysis_{timestamp}.json"
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        logger.info(f"📊 Analysis saved to: {analysis_file}")

    async def run_backfill(self, days: int = 30, symbol: str = "", backfill_only: bool = False) -> None:
        """Run the backfill process."""
        logger.info(f"🚀 Starting Binance history backfill for {days} days")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Run backfill
        logger.info("=" * 50)
        logger.info("📊 TRADE BACKFILL PROCESS")
        logger.info("=" * 50)

        backfill_results = await self.backfill_trades_from_history(days=days, symbol=symbol)

        # Analyze results
        analysis = self.analyze_backfill_results(backfill_results)

        # Save analysis (only analysis, not raw data)
        self.save_analysis_results(analysis, timestamp)

        # Print summary
        print(f"\n📊 Backfill Summary:")
        print(f"   Total Trades Processed: {analysis['backfill_summary']['total_trades_processed']}")
        print(f"   Trades Successfully Updated: {analysis['backfill_summary']['trades_successfully_updated']}")
        print(f"   Success Rate: {analysis['backfill_summary']['success_rate']}")
        print(f"   Binance Trades Fetched: {analysis['backfill_summary']['binance_data_availability']['trades_fetched']}")
        print(f"   Binance Orders Fetched: {analysis['backfill_summary']['binance_data_availability']['orders_fetched']}")

        logger.info("✅ Backfill process completed!")

    async def close(self):
        """Close the Binance client connection."""
        await self.binance_exchange.close_client()


async def main():
    """Main function to run the Binance history backfiller."""
    parser = argparse.ArgumentParser(description="Binance History Backfiller")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back")
    parser.add_argument("--symbol", default="", help="Trading pair symbol (e.g., BTCUSDT)")
    parser.add_argument("--backfill-only", action="store_true", help="Only run backfill, no analysis files")
    parser.add_argument("--testnet", action="store_true", help="Use Binance testnet")

    args = parser.parse_args()

    # Initialize backfiller
    backfiller = BinanceHistoryBackfiller(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "false") == "true"
    )

    try:
        # Initialize connection
        if not await backfiller.initialize():
            logger.error("Failed to initialize Binance connection")
            return

        # Run backfill
        await backfiller.run_backfill(
            days=args.days,
            symbol=args.symbol,
            backfill_only=args.backfill_only
        )

    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        await backfiller.close()


if __name__ == "__main__":
    asyncio.run(main())