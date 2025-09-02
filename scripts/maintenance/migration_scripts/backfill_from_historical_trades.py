#!/usr/bin/env python3
"""
Backfill missing Binance entry and exit prices from historical trade data.

This script uses timestamp windows (like PnL calculation) to group related orders
that belong to the same trade, then calculates weighted average prices for entry and exit.
"""

import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from discord_bot.database import DatabaseManager
from config import settings
from supabase import create_client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HistoricalTradeBackfillManager:
    """Manages backfilling of missing Binance prices using timestamp windows."""

    def __init__(self):
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        self.supabase = create_client(supabase_url, supabase_key)
        self.db_manager = DatabaseManager(self.supabase)
        self.binance_exchange = None  # Will be set by the caller

    def get_order_lifecycle(self, db_trade: Dict) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Get order start, end, and duration in milliseconds using created_at to updated_at range."""
        try:
            # Get timestamps from database - prefer snake_case
            created_at = db_trade.get('created_at') or db_trade.get('createdAt')
            updated_at = db_trade.get('updated_at') or db_trade.get('updatedAt')

            if not created_at:
                logger.warning(f"Trade {db_trade.get('id')} has no created_at timestamp")
                return None, None, None

            # Parse start time (created_at)
            if isinstance(created_at, str):
                if 'T' in created_at:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    start_time = int(dt.timestamp() * 1000)
                else:
                    start_time = int(float(created_at) * 1000)
            else:
                start_time = int(created_at.timestamp() * 1000)

            # Parse end time (updated_at) - more reliable than closed_at
            if not updated_at:
                # Fallback to created_at if no updated_at
                end_time = start_time
                duration = 0
                logger.warning(f"Trade {db_trade.get('id')} has no updated_at - using created_at as end time")
            else:
                if isinstance(updated_at, str):
                    if 'T' in updated_at:
                        dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        end_time = int(dt.timestamp() * 1000)
                    else:
                        end_time = int(float(updated_at) * 1000)
                else:
                    end_time = int(updated_at.timestamp() * 1000)
                duration = end_time - start_time

            logger.info(f"Trade {db_trade.get('id')} lifecycle: {start_time} to {end_time} (duration: {duration}ms)")
            return start_time, end_time, duration

        except Exception as e:
            logger.error(f"Error getting order lifecycle: {e}")
            return None, None, None

    def extract_symbol_from_trade(self, trade: Dict[str, Any]) -> Optional[str]:
        """Extract symbol from trade data with priority order."""
        try:
            # Try to extract symbol from binance_response first
            binance_response = trade.get('binance_response', '')
            if binance_response:
                try:
                    response_data = json.loads(binance_response)
                    symbol = response_data.get('symbol')
                    if symbol:
                        logger.info(f"Extracted symbol '{symbol}' from binance_response for trade {trade.get('id')}")
                        return symbol
                except json.JSONDecodeError:
                    pass

            # Try to extract from coin_symbol field
            coin_symbol = trade.get('coin_symbol', '')
            if coin_symbol:
                symbol = f"{coin_symbol}USDT"
                logger.info(f"Extracted symbol '{symbol}' from coin_symbol for trade {trade.get('id')}")
                return symbol

            # Try to extract from discord_id as fallback
            discord_id = trade.get('discord_id', '')

            # Common patterns in your data
            if 'BTC' in str(discord_id):
                symbol = 'BTCUSDT'
                logger.info(f"Extracted symbol '{symbol}' from discord_id pattern for trade {trade.get('id')}")
                return symbol
            elif 'ETH' in str(discord_id):
                symbol = 'ETHUSDT'
                logger.info(f"Extracted symbol '{symbol}' from discord_id pattern for trade {trade.get('id')}")
                return symbol
            elif 'LINK' in str(discord_id):
                symbol = 'LINKUSDT'
                logger.info(f"Extracted symbol '{symbol}' from discord_id pattern for trade {trade.get('id')}")
                return symbol

            logger.warning(f"Could not extract symbol for trade {trade.get('id')} with discord_id: {discord_id}")
            return None

        except Exception as e:
            logger.error(f"Error extracting symbol from trade {trade.get('id')}: {e}")
            return None

    async def get_executions_in_trade_window(self, symbol: str, start_time: int, end_time: int) -> Dict[str, List[Dict[str, Any]]]:
        """Get all executions that occurred within the trade's timestamp window."""
        try:
            logger.info(f"Fetching executions for {symbol} between {start_time} and {end_time}")

            # Convert timestamps to datetime for API calls
            start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)

            # Add buffer to ensure we capture all related executions
            buffer_before = timedelta(hours=1)  # 1 hour before trade start
            buffer_after = timedelta(hours=1)   # 1 hour after trade end

            search_start = start_dt - buffer_before
            search_end = end_dt + buffer_after

            logger.info(f"Searching executions from {search_start} to {search_end}")

            # Get all user trades for the symbol
            all_trades = []

            # First batch - get most recent trades
            trades = await self.binance_exchange.get_user_trades(symbol=symbol, limit=1000)
            all_trades.extend(trades)

            # If we got 1000 trades, there might be more
            if len(trades) == 1000:
                oldest_id = min(trade['id'] for trade in trades)
                older_trades = await self.binance_exchange.get_user_trades(
                    symbol=symbol, limit=1000, fromId=oldest_id - 1000
                )
                all_trades.extend(older_trades)

            logger.info(f"Fetched {len(all_trades)} total trades for {symbol}")

            # Filter trades within our search window
            buy_executions = []
            sell_executions = []

            for trade_exec in all_trades:
                # Convert trade time to datetime
                trade_time = datetime.fromtimestamp(trade_exec['time'] / 1000, tz=timezone.utc)

                # Check if trade is within our search window
                if search_start <= trade_time <= search_end:
                    side = trade_exec.get('side', '').upper()
                    price = float(trade_exec.get('price', 0))
                    qty = float(trade_exec.get('qty', 0))

                    if side == 'BUY':
                        buy_executions.append(trade_exec)
                        logger.info(f"  Buy Fill: price={price}, qty={qty}, time={trade_time}")
                    elif side == 'SELL':
                        sell_executions.append(trade_exec)
                        logger.info(f"  Sell Fill: price={price}, qty={qty}, time={trade_time}")

            logger.info(f"Found {len(buy_executions)} buy and {len(sell_executions)} sell execution(s) in trade window")

            return {
                'buys': buy_executions,
                'sells': sell_executions
            }

        except Exception as e:
            logger.error(f"Error getting executions in trade window: {e}")
            return {'buys': [], 'sells': []}

    def calculate_weighted_average_price(self, executions: List[Dict[str, Any]]) -> float:
        """Calculate weighted average price from multiple executions."""
        if not executions:
            return 0.0

        total_value = 0.0
        total_qty = 0.0

        for execution in executions:
            price = float(execution.get('price', 0))
            qty = float(execution.get('qty', 0))

            if price > 0 and qty > 0:
                total_value += price * qty
                total_qty += qty

        if total_qty > 0:
            return total_value / total_qty
        else:
            return 0.0

    async def update_trade_prices(self, trade_id: int, entry_price: float, exit_price: float) -> bool:
        """Update trade with calculated entry and exit prices."""
        try:
            updates = {}

            if entry_price > 0:
                updates['binance_entry_price'] = str(entry_price)
                logger.info(f"Setting entry price: {entry_price}")

            if exit_price > 0:
                updates['binance_exit_price'] = str(exit_price)
                logger.info(f"Setting exit price: {exit_price}")

            if updates:
                updates['updated_at'] = datetime.now(timezone.utc).isoformat()
                success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
                if success:
                    logger.info(f"Successfully updated trade {trade_id}")
                    return True
                else:
                    logger.error(f"Failed to update trade {trade_id}")
                    return False
            else:
                logger.warning(f"No prices to update for trade {trade_id}")
                return False

        except Exception as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return False

    async def find_trades_with_missing_prices(self, days: int = 7) -> List[Dict[str, Any]]:
        """Find trades with missing Binance prices from the last N days."""
        try:
            # Calculate cutoff date
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Query for trades with missing prices
            response = self.db_manager.supabase.from_("trades").select(
                "id, discord_id, exchange_order_id, stop_loss_order_id, status, "
                "binance_entry_price, binance_exit_price, binance_response, created_at, coin_symbol, closed_at, updated_at"
            ).not_.is_("exchange_order_id", "null").gte("created_at", cutoff_iso).execute()

            trades_to_process = []

            for trade in response.data:
                # Skip test trades completely
                discord_id = trade.get('discord_id', '')
                if 'test' in str(discord_id).lower():
                    logger.info(f"Skipping test trade {trade.get('id')} with discord_id: {discord_id}")
                    continue

                # Check if prices are missing
                entry_price = trade.get('binance_entry_price')
                exit_price = trade.get('binance_exit_price')

                if not entry_price or float(entry_price) == 0 or not exit_price or float(exit_price) == 0:
                    trades_to_process.append(trade)
                    logger.info(f"Found trade {trade.get('id')} (Discord: {discord_id}) with missing prices - Entry: {entry_price}, Exit: {exit_price}")

            logger.info(f"Found {len(trades_to_process)} trades with missing prices")
            return trades_to_process

        except Exception as e:
            logger.error(f"Error finding trades with missing prices: {e}")
            return []

    async def backfill_from_historical_data(self, days: int = 7):
        """Backfill missing prices using timestamp windows to group related orders."""
        try:
            logger.info(f"Starting backfill for trades from last {days} days")

            # Initialize Binance client
            await self.binance_exchange._init_client()

            # Find trades with missing prices
            trades = await self.find_trades_with_missing_prices(days)

            if not trades:
                logger.info("No trades found with missing prices")
                return

            stats = {
                'total_trades': len(trades),
                'trades_updated': 0,
                'trades_failed': 0,
                'entry_prices_filled': 0,
                'exit_prices_filled': 0
            }

            for trade in trades:
                trade_id = trade.get('id')
                discord_id = trade.get('discord_id', '')

                logger.info(f"Processing trade {trade_id} (Discord: {discord_id})")

                # Extract symbol
                symbol = self.extract_symbol_from_trade(trade)
                if not symbol:
                    logger.warning(f"Could not extract symbol for trade {trade_id}")
                    stats['trades_failed'] += 1
                    continue

                # Get trade lifecycle window
                start_time, end_time, duration = self.get_order_lifecycle(trade)
                if not start_time:
                    logger.warning(f"Could not get lifecycle for trade {trade_id}")
                    stats['trades_failed'] += 1
                    continue

                logger.info(f"Trade {trade_id} lifecycle: {start_time} to {end_time} (duration: {duration}ms)")

                # Get all executions within the trade window
                executions = await self.get_executions_in_trade_window(symbol, start_time, end_time)
                buy_executions = executions['buys']
                sell_executions = executions['sells']

                if not buy_executions and not sell_executions:
                    logger.warning(f"No executions found in trade window for trade {trade_id}")
                    stats['trades_failed'] += 1
                    continue

                # Calculate weighted average prices and total quantities
                buy_avg_price = self.calculate_weighted_average_price(buy_executions)
                sell_avg_price = self.calculate_weighted_average_price(sell_executions)

                # Calculate total quantities
                total_buy_qty = sum(float(execution.get('qty', 0)) for execution in buy_executions)
                total_sell_qty = sum(float(execution.get('qty', 0)) for execution in sell_executions)

                logger.info(f"Trade {trade_id}: buy_qty={total_buy_qty}, sell_qty={total_sell_qty}")

                # Determine if this is a long or short position based on timing
                # For longs: BUYs are entries, SELLs are exits
                # For shorts: SELLs are entries, BUYs are exits
                is_long = len(buy_executions) > 0 and (len(sell_executions) == 0 or
                                     buy_executions[0]['time'] < sell_executions[0]['time'])

                logger.info(f"Trade {trade_id}: is_long={is_long}, buy_price={buy_avg_price}, sell_price={sell_avg_price}")

                # Check if trade is closed (quantities match)
                is_closed = abs(total_buy_qty - total_sell_qty) < 0.000001  # Small tolerance for floating point

                if is_long:
                    # Long position: BUY is entry, SELL is exit
                    entry_price = buy_avg_price
                    exit_price = sell_avg_price if is_closed else 0.0
                else:
                    # Short position: SELL is entry, BUY is exit
                    entry_price = sell_avg_price
                    exit_price = buy_avg_price if is_closed else 0.0

                if not is_closed:
                    logger.warning(f"Trade {trade_id} is not closed - buy_qty={total_buy_qty}, sell_qty={total_sell_qty}")
                    # Only set entry price, not exit price
                    success = await self.update_trade_prices(trade_id, entry_price, 0.0)
                else:
                    logger.info(f"Trade {trade_id} is closed - setting both entry and exit prices")
                    # Set both entry and exit prices
                    success = await self.update_trade_prices(trade_id, entry_price, exit_price)
                if success:
                    if entry_price > 0:
                        stats['entry_prices_filled'] += 1
                    if exit_price > 0:
                        stats['exit_prices_filled'] += 1
                    stats['trades_updated'] += 1
                else:
                    stats['trades_failed'] += 1

            # Print summary
            logger.info("=== Backfill Summary ===")
            logger.info(f"Total trades processed: {stats['total_trades']}")
            logger.info(f"Trades updated: {stats['trades_updated']}")
            logger.info(f"Trades failed: {stats['trades_failed']}")
            logger.info(f"Entry prices filled: {stats['entry_prices_filled']}")
            logger.info(f"Exit prices filled: {stats['exit_prices_filled']}")

        except Exception as e:
            logger.error(f"Error during backfill: {e}")


async def main():
    """Main function to run the backfill."""
    try:
        backfill_manager = HistoricalTradeBackfillManager()
        await backfill_manager.backfill_from_historical_data(days=7)
    except Exception as e:
        logger.error(f"Error in main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
