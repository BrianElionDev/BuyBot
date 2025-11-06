#!/usr/bin/env python3
"""
Backfill missing Binance entry and exit prices from historical trade data.

This script uses timestamp windows (like PnL calculation) to group related orders
that belong to the same trade, then calculates weighted average prices for entry and exit.

FIXED VERSION:
- Uses signal_type from database to determine LONG/SHORT positions (not execution timing)
- Properly assigns entry/exit prices based on actual position type
- LONG: BUY executions = entry price, SELL executions = exit price
- SHORT: SELL executions = entry price, BUY executions = exit price
- Can update existing records for better accuracy
- Compares existing vs calculated prices and shows improvements
- Two-phase approach: fill missing first, then update existing for accuracy
"""

import asyncio
import logging
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from pathlib import Path

# Add project root to path
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from discord_bot.database import DatabaseManager
from config import settings
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
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
        self.db_manager: Any = DatabaseManager(self.supabase)
        self.binance_exchange: Any = None  # Optionally set by caller
        self.kucoin_exchange: Optional[KucoinExchange] = None  # Optionally set by caller

    # ------------------------
    # KuCoin helpers
    # ------------------------
    def _ms(self, v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

    def _kucoin_time_bounds(self, trade: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
        created_ms = None
        closed_ms = None
        try:
            created_at = trade.get('created_at') or trade.get('createdAt')
            closed_at = trade.get('closed_at') or trade.get('updated_at') or trade.get('closedAt')
            if created_at:
                if isinstance(created_at, str):
                    created_ms = int(datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp() * 1000)
                else:
                    created_ms = int(created_at.timestamp() * 1000)
            if closed_at:
                if isinstance(closed_at, str):
                    closed_ms = int(datetime.fromisoformat(closed_at.replace('Z', '+00:00')).timestamp() * 1000)
                else:
                    closed_ms = int(closed_at.timestamp() * 1000)
        except Exception:
            pass
        return created_ms, closed_ms

    def _pick_kucoin_position(self, records: List[Dict[str, Any]], symbol: str, created_ms: int, closed_ms: int, position_type: str, used_close_ids: Set[str]) -> Optional[Dict[str, Any]]:
        if not records:
            return None
        futures_symbol = str(symbol)
        # strict filter
        created_pad = 5 * 60 * 1000
        end_pad = 15 * 60 * 1000
        end_ms = (closed_ms or 0) + end_pad
        expected_close_type = 'CLOSE_LONG' if position_type == 'LONG' else ('CLOSE_SHORT' if position_type == 'SHORT' else None)
        expected_side = 'LONG' if position_type == 'LONG' else ('SHORT' if position_type == 'SHORT' else None)

        def ok(r: Dict[str, Any]) -> bool:
            if str(r.get('symbol') or '') != futures_symbol:
                return False
            if str(r.get('closeId') or '') in used_close_ids:
                return False
            o_ms = self._ms(r.get('openTime'))
            c_ms = self._ms(r.get('closeTime'))
            if created_ms and o_ms and o_ms < max(0, created_ms - created_pad):
                return False
            if c_ms and c_ms > end_ms:
                return False
            r_type = str(r.get('type') or '').upper()
            r_side = str(r.get('side') or '').upper()
            if expected_close_type and r_type not in (expected_close_type, '') and expected_close_type not in r_type:
                return False
            if expected_side and r_side not in (expected_side, ''):
                return False
            return True

        candidates = [r for r in records if ok(r)]
        if not candidates:
            candidates = [r for r in records if str(r.get('symbol') or '') == futures_symbol and str(r.get('closeId') or '') not in used_close_ids]
            if not candidates:
                return None

        def score(r: Dict[str, Any]) -> Tuple[int, int]:
            c_ms = self._ms(r.get('closeTime'))
            o_ms = self._ms(r.get('openTime'))
            return (abs((closed_ms or 0) - (c_ms or 0)), abs((created_ms or 0) - (o_ms or 0)))

        return min(candidates, key=score)

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

            logger.debug(f"Trade {db_trade.get('id')} lifecycle: {start_time} to {end_time} (duration: {duration}ms)")
            return start_time, end_time, duration

        except Exception as e:
            logger.error(f"Error getting order lifecycle: {e}")
            return None, None, None

    def extract_symbol_from_trade(self, trade: Dict[str, Any]) -> Optional[str]:
        """Extract symbol from trade data with priority order."""
        try:
            # Try to extract symbol from exchange_response first (fallback to legacy)
            raw = trade.get('exchange_response') or trade.get('binance_response', '')
            if raw:
                try:
                    response_data = json.loads(raw) if isinstance(raw, str) else raw
                    symbol = response_data.get('symbol')
                    if symbol:
                        logger.info(f"Extracted symbol '{symbol}' from exchange_response for trade {trade.get('id')}")
                        return symbol
                except json.JSONDecodeError:
                    pass

            # Try to extract from coin_symbol field
            coin_symbol = trade.get('coin_symbol', '')
            if coin_symbol:
                symbol = f"{coin_symbol}USDT"
                logger.debug(f"Extracted symbol '{symbol}' from coin_symbol for trade {trade.get('id')}")
                return symbol

            # Try to extract from parsed_signal
            parsed_signal = trade.get('parsed_signal', '')
            if parsed_signal:
                try:
                    if isinstance(parsed_signal, str):
                        signal_data = json.loads(parsed_signal)
                    else:
                        signal_data = parsed_signal

                    coin_symbol = signal_data.get('coin_symbol', '')
                    if coin_symbol:
                        symbol = f"{coin_symbol}USDT"
                        logger.info(f"Extracted symbol '{symbol}' from parsed_signal for trade {trade.get('id')}")
                        return symbol
                except (json.JSONDecodeError, TypeError):
                    pass

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

    def get_position_type_from_trade(self, trade: Dict[str, Any]) -> str:
        """Get position type from trade data with proper fallback logic."""
        try:
            # First try to get from signal_type field (most reliable)
            signal_type = trade.get('signal_type', '').upper().strip()

            # Normalize variations: "shorted", "shorting" -> "SHORT", "longed", "longing" -> "LONG"
            if signal_type in ['SHORTED', 'SHORTING', 'SHORT']:
                signal_type = 'SHORT'
            elif signal_type in ['LONGED', 'LONGING', 'LONG']:
                signal_type = 'LONG'

            if signal_type in ['LONG', 'SHORT']:
                logger.info(f"Using signal_type '{signal_type}' for trade {trade.get('id')}")
                return signal_type

            # Try to extract from parsed_signal
            parsed_signal = trade.get('parsed_signal', '')
            if parsed_signal:
                try:
                    if isinstance(parsed_signal, str):
                        signal_data = json.loads(parsed_signal)
                    else:
                        signal_data = parsed_signal

                    position_type = signal_data.get('position_type', '').upper().strip()

                    # Normalize variations: "shorted", "shorting" -> "SHORT", "longed", "longing" -> "LONG"
                    if position_type in ['SHORTED', 'SHORTING', 'SHORT']:
                        position_type = 'SHORT'
                    elif position_type in ['LONGED', 'LONGING', 'LONG']:
                        position_type = 'LONG'

                    if position_type in ['LONG', 'SHORT']:
                        logger.info(f"Using position_type '{position_type}' from parsed_signal for trade {trade.get('id')}")
                        return position_type
                except (json.JSONDecodeError, TypeError):
                    pass

            # Default to LONG if we can't determine
            logger.warning(f"Could not determine position type for trade {trade.get('id')}, defaulting to LONG")
            return 'LONG'

        except Exception as e:
            logger.error(f"Error getting position type from trade {trade.get('id')}: {e}")
            return 'LONG'

    async def get_executions_in_trade_window(self, symbol: str, start_time: int, end_time: int) -> Dict[str, List[Dict[str, Any]]]:
        """Get all executions that occurred within the trade's timestamp window."""
        try:
            logger.debug(f"Fetching executions for {symbol}")

            # Convert timestamps to datetime for API calls
            start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)

            # Add buffer to ensure we capture all related executions
            buffer_before = timedelta(hours=1)  # 1 hour before trade start
            buffer_after = timedelta(hours=1)   # 1 hour after trade end

            search_start = start_dt - buffer_before
            search_end = end_dt + buffer_after

            logger.debug(f"Searching executions from {search_start} to {search_end}")

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
                        logger.debug(f"  Buy Fill: price={price}, qty={qty}, time={trade_time}")
                    elif side == 'SELL':
                        sell_executions.append(trade_exec)
                        logger.debug(f"  Sell Fill: price={price}, qty={qty}, time={trade_time}")

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

    def calculate_entry_exit_prices(self, position_type: str, buy_executions: List[Dict], sell_executions: List[Dict]) -> Tuple[float, float]:
        """Calculate entry and exit prices based on position type and executions."""
        buy_avg_price = self.calculate_weighted_average_price(buy_executions)
        sell_avg_price = self.calculate_weighted_average_price(sell_executions)

        # Calculate total quantities
        total_buy_qty = sum(float(execution.get('qty', 0)) for execution in buy_executions)
        total_sell_qty = sum(float(execution.get('qty', 0)) for execution in sell_executions)

        logger.info(f"Position type: {position_type}, buy_qty={total_buy_qty}, sell_qty={total_sell_qty}")
        logger.info(f"Buy avg price: {buy_avg_price}, Sell avg price: {sell_avg_price}")

        # Determine entry and exit prices based on position type
        if position_type.upper() == 'LONG':
            # Long position: BUY is entry, SELL is exit
            entry_price = buy_avg_price
            exit_price = sell_avg_price if total_sell_qty > 0 else 0.0
            logger.info(f"LONG position: entry={entry_price} (from buys), exit={exit_price} (from sells)")
        else:  # SHORT
            # Short position: SELL is entry, BUY is exit
            entry_price = sell_avg_price
            exit_price = buy_avg_price if total_buy_qty > 0 else 0.0
            logger.info(f"SHORT position: entry={entry_price} (from sells), exit={exit_price} (from buys)")

        return entry_price, exit_price

    def compare_prices(self, trade: Dict, new_entry_price: float, new_exit_price: float) -> Dict[str, Any]:
        """Compare existing prices with newly calculated prices."""
        try:
            existing_entry = trade.get('entry_price') or trade.get('binance_entry_price')
            existing_exit = trade.get('exit_price') or trade.get('binance_exit_price')

            comparison = {
                'entry_changed': False,
                'exit_changed': False,
                'entry_diff': 0.0,
                'exit_diff': 0.0,
                'entry_pct_diff': 0.0,
                'exit_pct_diff': 0.0
            }

            if existing_entry and float(existing_entry) > 0:
                existing_entry_float = float(existing_entry)
                if abs(existing_entry_float - new_entry_price) > 0.01:  # Significant difference
                    comparison['entry_changed'] = True
                    comparison['entry_diff'] = new_entry_price - existing_entry_float
                    comparison['entry_pct_diff'] = (comparison['entry_diff'] / existing_entry_float) * 100

            if existing_exit and float(existing_exit) > 0:
                existing_exit_float = float(existing_exit)
                if abs(existing_exit_float - new_exit_price) > 0.01:  # Significant difference
                    comparison['exit_changed'] = True
                    comparison['exit_diff'] = new_exit_price - existing_exit_float
                    comparison['exit_pct_diff'] = (comparison['exit_diff'] / existing_exit_float) * 100

            return comparison

        except Exception as e:
            logger.error(f"Error comparing prices: {e}")
            return {'entry_changed': False, 'exit_changed': False, 'entry_diff': 0.0, 'exit_diff': 0.0, 'entry_pct_diff': 0.0, 'exit_pct_diff': 0.0}

    async def update_trade_prices(self, trade_id: int, entry_price: float, exit_price: float) -> bool:
        """Update trade with calculated entry and exit prices."""
        try:
            updates = {}

            if entry_price > 0:
                updates['entry_price'] = float(entry_price)
                logger.info(f"Setting entry price: {entry_price}")

            if exit_price > 0:
                updates['exit_price'] = float(exit_price)
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

    async def find_trades_with_missing_prices(self, days: int = 7, update_existing: bool = False) -> List[Dict[str, Any]]:
        """Find trades with missing or existing Binance prices from the last N days."""
        try:
            # Calculate cutoff date
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Query for trades with missing prices
            response = self.db_manager.supabase.from_("trades").select(
                "id, discord_id, exchange_order_id, stop_loss_order_id, status, "
                "entry_price, exit_price, exchange_response, binance_response, created_at, coin_symbol, closed_at, updated_at, signal_type, parsed_signal"
            ).not_.is_("exchange_order_id", "null").gte("created_at", cutoff_iso).execute()

            trades_to_process = []

            for trade in response.data:
                # Skip test trades completely
                discord_id = trade.get('discord_id', '')
                if 'test' in str(discord_id).lower():
                    logger.info(f"Skipping test trade {trade.get('id')} with discord_id: {discord_id}")
                    continue

                # Check if prices are missing or if we should update existing ones
                entry_price = trade.get('entry_price') or trade.get('binance_entry_price')
                exit_price = trade.get('exit_price') or trade.get('binance_exit_price')

                missing_prices = not entry_price or float(entry_price or 0) == 0 or not exit_price or float(exit_price or 0) == 0

                if missing_prices or update_existing:
                    trades_to_process.append(trade)
                    if missing_prices:
                        logger.info(f"Found trade {trade.get('id')} (Discord: {discord_id}) with missing prices - Entry: {entry_price}, Exit: {exit_price}")
                    else:
                        logger.debug(f"Found trade {trade.get('id')} with existing prices - Entry: {entry_price}, Exit: {exit_price} (will recalculate for accuracy)")

            logger.debug(f"Found {len(trades_to_process)} trades to process ({'including existing' if update_existing else 'missing only'})")
            return trades_to_process

        except Exception as e:
            logger.error(f"Error finding trades with missing prices: {e}")
            return []

    async def backfill_from_historical_data(self, days: int = 7, update_existing: bool = False):
        """Backfill missing prices using timestamp windows to group related orders."""
        try:
            mode = "missing and existing" if update_existing else "missing only"
            logger.info(f"Starting backfill for trades from last {days} days ({mode})")

            # Initialize Binance client when available
            if not self.binance_exchange:
                logger.info("Binance exchange client not set; skipping Binance price backfill")
                return
            try:
                await self.binance_exchange._init_client()
            except Exception:
                logger.warning("Failed to init Binance client; skipping Binance price backfill")
                return

            # Find trades with missing prices (and optionally existing ones)
            trades = await self.find_trades_with_missing_prices(days, update_existing)
            if not trades:
                logger.info("No trades found with missing prices")
                return

            stats = {
                'total_trades': len(trades),
                'trades_updated': 0,
                'trades_failed': 0,
                'entry_prices_filled': 0,
                'exit_prices_filled': 0,
                'entry_prices_corrected': 0,
                'exit_prices_corrected': 0,
                'trades_with_changes': 0
            }

            for trade in trades:
                trade_id = trade.get('id')
                discord_id = trade.get('discord_id', '')

                logger.debug(f"Processing trade {trade_id}")

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

                logger.debug(f"Trade {trade_id} lifecycle: {start_time} to {end_time} (duration: {duration}ms)")

                # Get all executions within the trade window
                safe_end = end_time if end_time is not None else start_time
                executions = await self.get_executions_in_trade_window(symbol, int(start_time), int(safe_end))
                buy_executions = executions['buys']
                sell_executions = executions['sells']

                if not buy_executions and not sell_executions:
                    logger.warning(f"No executions found in trade window for trade {trade_id}")
                    stats['trades_failed'] += 1
                    continue

                # Get position type from database (most reliable method)
                position_type = self.get_position_type_from_trade(trade)
                logger.info(f"Trade {trade_id} position type: {position_type}")

                # Calculate entry and exit prices based on position type
                entry_price, exit_price = self.calculate_entry_exit_prices(
                    position_type, buy_executions, sell_executions
                )

                # Compare with existing prices if updating existing records
                price_comparison = self.compare_prices(trade, entry_price, exit_price)

                # Update trade with calculated prices
                if trade_id is None:
                    stats['trades_failed'] += 1
                    continue
                success = await self.update_trade_prices(int(trade_id), entry_price, exit_price)
                if success:
                    if entry_price > 0:
                        stats['entry_prices_filled'] += 1
                        if price_comparison['entry_changed']:
                            stats['entry_prices_corrected'] += 1
                            logger.info(f"Trade {trade_id}: Entry price corrected by {price_comparison['entry_diff']:.4f} ({price_comparison['entry_pct_diff']:.2f}%)")

                    if exit_price > 0:
                        stats['exit_prices_filled'] += 1
                        if price_comparison['exit_changed']:
                            stats['exit_prices_corrected'] += 1
                            logger.info(f"Trade {trade_id}: Exit price corrected by {price_comparison['exit_diff']:.4f} ({price_comparison['exit_pct_diff']:.2f}%)")

                    if price_comparison['entry_changed'] or price_comparison['exit_changed']:
                        stats['trades_with_changes'] += 1

                    stats['trades_updated'] += 1
                else:
                    stats['trades_failed'] += 1

            # Print summary
            logger.info("=== Fixed Backfill Summary ===")
            logger.info(f"Total trades processed: {stats['total_trades']}")
            logger.info(f"Trades updated: {stats['trades_updated']}")
            logger.info(f"Trades failed: {stats['trades_failed']}")
            logger.info(f"Entry prices filled: {stats['entry_prices_filled']}")
            logger.info(f"Exit prices filled: {stats['exit_prices_filled']}")
            if update_existing:
                logger.info(f"Entry prices corrected: {stats['entry_prices_corrected']}")
                logger.info(f"Exit prices corrected: {stats['exit_prices_corrected']}")
                logger.info(f"Trades with price changes: {stats['trades_with_changes']}")
            logger.info("✅ Now using signal_type from database for accurate LONG/SHORT detection")
        except Exception as e:
            logger.error(f"Error during backfill: {e}")

    async def backfill_kucoin_prices(self, days: int = 7, update_existing: bool = False):
        """
        DEPRECATED: Use backfill_pnl_and_exit_prices.py KucoinPnLBackfiller instead.

        This method is kept for backwards compatibility but the consolidated
        implementation in backfill_pnl_and_exit_prices.py should be used instead.

        Backfill KuCoin entry/exit prices using strict position history matching.
        """
        try:
            if not self.kucoin_exchange:
                logger.warning("KuCoin exchange client not set; skipping KuCoin backfill")
                return
            await self.kucoin_exchange.initialize()

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            resp = self.db_manager.supabase.from_("trades").select(
                "id, exchange, status, coin_symbol, signal_type, created_at, updated_at, closed_at, entry_price, exit_price"
            ).eq("exchange", "kucoin").gte("created_at", cutoff_iso).execute()

            trades = resp.data or []
            if not trades:
                logger.info("No KuCoin trades found for backfill window")
                return

            used_close_ids: Set[str] = set()
            updated = 0
            for tr in trades:
                tid = tr.get('id')
                # Skip if complete and not updating existing
                e = tr.get('entry_price')
                x = tr.get('exit_price')
                if not update_existing and e and float(e or 0) > 0 and x and float(x or 0) > 0:
                    continue

                symbol = str(tr.get('coin_symbol') or '').upper()
                if not symbol:
                    continue
                fut_symbol = self.kucoin_exchange.get_futures_trading_pair(symbol)

                created_ms, closed_ms = self._kucoin_time_bounds(tr)
                if not created_ms or not closed_ms:
                    continue

                # fetch position history with fallback (with/without symbol)
                params = {"symbol": fut_symbol, "startAt": created_ms - 15*60*1000, "endAt": closed_ms + 15*60*1000}
                pos = await self.kucoin_exchange._make_direct_api_call('GET', '/api/v1/history-positions', params)
                records: List[Dict[str, Any]] = []
                if isinstance(pos, list):
                    records = pos
                elif isinstance(pos, dict):
                    items = pos.get('items') or pos.get('data') or []
                    if isinstance(items, list):
                        records = items
                if not records:
                    pos2 = await self.kucoin_exchange._make_direct_api_call('GET', '/api/v1/history-positions', {"startAt": created_ms - 15*60*1000, "endAt": closed_ms + 15*60*1000})
                    if isinstance(pos2, list):
                        records = pos2
                    elif isinstance(pos2, dict):
                        items2 = pos2.get('items') or pos2.get('data') or []
                        if isinstance(items2, list):
                            records = items2
                if not records:
                    continue

                position_type = str(tr.get('signal_type') or '').upper()
                rec = self._pick_kucoin_position(records, fut_symbol, created_ms, closed_ms, position_type, used_close_ids)
                if not rec:
                    continue

                # Extract prices and PnL where available (source-of-truth from KuCoin)
                try:
                    entry_price_val = rec.get('avgEntryPrice') or rec.get('openPrice')
                    exit_price_val = rec.get('closePrice') or rec.get('avgExitPrice')
                    pnl_val = rec.get('pnl') or rec.get('realizedPnl') or rec.get('realisedPnl')
                    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
                    if entry_price_val:
                        updates['entry_price'] = float(entry_price_val)
                    if exit_price_val:
                        updates['exit_price'] = float(exit_price_val)
                    # Mark verification and sources when we have authoritative values
                    if entry_price_val or exit_price_val:
                        updates['price_verified'] = True
                        updates['price_source'] = 'kucoin_history_positions'
                    if pnl_val is not None:
                        try:
                            updates['pnl_usd'] = float(pnl_val)
                            updates['net_pnl'] = float(pnl_val)
                            updates['last_pnl_sync'] = datetime.now(timezone.utc).isoformat()
                            updates['pnl_verified'] = True
                            updates['pnl_source'] = 'kucoin_history_positions'
                        except Exception:
                            pass
                    if len(updates) > 1:
                        self.db_manager.supabase.table("trades").update(updates).eq("id", tid).execute()
                        updated += 1
                        cid = rec.get('closeId')
                        if cid:
                            used_close_ids.add(str(cid))
                        logger.info(f"KuCoin trade {tid} backfilled prices: {updates}")
                except Exception:
                    continue

            logger.info(f"KuCoin price backfill completed: {updated} trades updated")
        except Exception as e:
            logger.error(f"Error during KuCoin price backfill: {e}")


async def main():
    """Main function to run the backfill."""
    try:
        backfill_manager = HistoricalTradeBackfillManager()

        # Try KuCoin client for standalone runs
        try:
            backfill_manager.kucoin_exchange = KucoinExchange(
                api_key=settings.KUCOIN_API_KEY or "",
                api_secret=settings.KUCOIN_API_SECRET or "",
                api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
                is_testnet=False,
            )
        except Exception:
            backfill_manager.kucoin_exchange = None

        # Binance phase runs only if a Binance client is provided externally
        logger.info("=== Phase 1: Filling Missing Prices (Binance, if client available) ===")
        await backfill_manager.backfill_from_historical_data(days=7, update_existing=False)

        logger.info("\n=== Phase 2: Updating Existing Prices for Accuracy (Binance, if client available) ===")
        await backfill_manager.backfill_from_historical_data(days=7, update_existing=True)

        # KuCoin price backfill using position history
        logger.info("\n=== Phase 3: KuCoin Price Backfill (Position History) ===")
        await backfill_manager.backfill_kucoin_prices(days=7, update_existing=False)
        logger.info("\n=== Phase 4: KuCoin Price Correction for Accuracy (Position History) ===")
        await backfill_manager.backfill_kucoin_prices(days=7, update_existing=True)

    except Exception as e:
        logger.error(f"Error in main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
