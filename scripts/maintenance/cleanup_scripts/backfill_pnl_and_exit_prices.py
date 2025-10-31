#!/usr/bin/env python3
"""
Backfill PnL and exit prices for existing trades using Binance income history.
This script processes trades using order lifecycle matching for accurate P&L tracking.
"""

import asyncio
import logging
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# Add project root to the Python path (three levels up from cleanup_scripts)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    update_trade_status
)

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BinancePnLBackfiller:
    """Backfill P&L using Binance income history and order lifecycle matching."""

    def __init__(self, bot, supabase):
        self.bot = bot
        self.supabase = supabase
        self.binance_exchange = bot.binance_exchange

    def parse_timestamp(self, timestamp_str: str) -> Optional[int]:
        """Parse timestamp string to milliseconds."""
        try:
            # Handle ISO format
            if 'T' in timestamp_str:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)

            # Handle Unix timestamp
            if timestamp_str.isdigit():
                ts = int(timestamp_str)
                # If it's seconds, convert to milliseconds
                if ts < 1000000000000:  # Before year 2001
                    ts *= 1000
                return ts

            return None
        except Exception:
            return None

    def get_order_lifecycle(self, db_trade: Dict) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Get order start, end, and duration in milliseconds using created_at to closed_at/updated_at range."""
        try:
            # Get timestamps from database - prefer snake_case
            created_at = db_trade.get('created_at') or db_trade.get('createdAt')
            closed_at = db_trade.get('closed_at')
            updated_at = db_trade.get('updated_at') or db_trade.get('updatedAt') or db_trade.get('modified_at')

            if not created_at:
                logger.warning(f"Trade {db_trade.get('id')} has no created_at timestamp")
                return None, None, None

            # Parse start time (created_at)
            start_time = self.parse_timestamp(str(created_at))
            if not start_time:
                logger.warning(f"Trade {db_trade.get('id')} has invalid created_at: {created_at}")
                return None, None, None

            # Parse end time (closed_at with updated_at fallback)
            if not closed_at:
                # If no closed_at, use updated_at as fallback, then created_at
                if updated_at:
                    end_time = self.parse_timestamp(str(updated_at))
                    if not end_time:
                        end_time = start_time
                        duration = 0
                        logger.warning(f"Trade {db_trade.get('id')} has invalid updated_at: {updated_at}")
                    else:
                        duration = end_time - start_time
                    logger.info(f"Trade {db_trade.get('id')} has no closed_at - using updated_at as end time")
                else:
                    # Fallback to created_at if no updated_at either
                    end_time = start_time
                    duration = 0
                    logger.info(f"Trade {db_trade.get('id')} has no closed_at or updated_at - using created_at as end time")
            else:
                # Use closed_at when available
                end_time = self.parse_timestamp(str(closed_at))
                if not end_time:
                    end_time = start_time
                    duration = 0
                    logger.warning(f"Trade {db_trade.get('id')} has invalid closed_at: {closed_at}")
                else:
                    duration = end_time - start_time

            return start_time, end_time, duration

        except Exception as e:
            logger.error(f"Error getting order lifecycle: {e}")
            return None, None, None

    async def get_income_for_trade_period(self, symbol: str, start_time: int, end_time: int) -> List[Dict]:
        """Get income history for a specific trade period."""
        try:
            logger.info(f"Fetching {symbol}USDT income from {start_time} to {end_time}")

            # Add buffer time (1 hour before and after) to catch related income
            buffer_time = 60 * 60 * 1000  # 1 hour in milliseconds
            search_start = start_time - buffer_time
            search_end = end_time + buffer_time

            all_incomes = []
            chunk_start = search_start

            while chunk_start < search_end:
                chunk_end = min(chunk_start + (7 * 24 * 60 * 60 * 1000), search_end)

                try:
                    chunk_incomes = await self.binance_exchange.get_income_history(
                        symbol=f"{symbol}USDT",
                        start_time=chunk_start,
                        end_time=chunk_end,
                        limit=1000,
                    )
                    all_incomes.extend(chunk_incomes)
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.error(f"Error fetching chunk income: {e}")

                chunk_start = chunk_end

            # Filter to exact trade period
            filtered_incomes = []
            for income in all_incomes:
                income_time = income.get('time')
                if income_time and start_time <= int(income_time) <= end_time:
                    filtered_incomes.append(income)

            logger.info(f"Found {len(filtered_incomes)} income records within trade period")
            return filtered_incomes

        except Exception as e:
            logger.error(f"Error getting income for trade period: {e}")
            return []

    def calculate_expected_pnl_range(self, position_size: float, entry_price: float,
                                   exit_price: float, position_type: str) -> Tuple[float, float]:
        """Calculate expected P&L range based on position size and prices."""
        try:
            if not all([position_size, entry_price, exit_price]):
                return 0.0, 0.0

            position_size = float(position_size)
            entry_price = float(entry_price)
            exit_price = float(exit_price)

            # Calculate base P&L
            if position_type.upper() == 'LONG':
                base_pnl = (exit_price - entry_price) * position_size
            else:  # SHORT
                base_pnl = (entry_price - exit_price) * position_size

            # Add 0.1% fee (entry + exit)
            fee = (entry_price + exit_price) * position_size * 0.001

            # Expected range: base P&L ± 20% for slippage and market conditions
            min_pnl = base_pnl - fee - (abs(base_pnl) * 0.2)
            max_pnl = base_pnl - fee + (abs(base_pnl) * 0.2)

            return min_pnl, max_pnl

        except Exception as e:
            logger.error(f"Error calculating expected P&L range: {e}")
            return 0.0, 0.0

    async def process_trade_with_income_history(self, trade: Dict) -> Dict:
        """Process a single trade using Binance income history."""
        trade_id = trade.get('id')
        symbol = trade.get('coin_symbol', '')
        position_size = trade.get('position_size')
        entry_price = trade.get('entry_price')
        exit_price = trade.get('exit_price')
        position_type = trade.get('signal_type', 'LONG')

        # Get order lifecycle
        start_time, end_time, duration = self.get_order_lifecycle(trade)

        if not start_time:
            logger.warning(f"Trade {trade_id} has no valid timestamps, skipping")
            return {'trade_id': trade_id, 'status': 'SKIPPED', 'reason': 'No valid timestamps'}

        # Calculate expected P&L range using binance prices (coerce Nones to 0.0)
        try:
            ps_val = float(position_size or 0)
        except Exception:
            ps_val = 0.0
        try:
            be_val = float(trade.get('binance_entry_price') or 0)
        except Exception:
            be_val = 0.0
        try:
            bx_val = float(trade.get('binance_exit_price') or 0)
        except Exception:
            bx_val = 0.0
        min_expected_pnl, max_expected_pnl = self.calculate_expected_pnl_range(
            ps_val, bx_val, be_val, position_type
        )

        # Get income records for this specific trade period
        income_records = await self.get_income_for_trade_period(symbol, int(start_time), int(end_time or start_time))

        if not income_records:
            logger.info(f"Trade {trade_id} ({symbol}): No income records found during order lifecycle")
            return {
                'trade_id': trade_id,
                'status': 'NO_INCOME',
                'symbol': symbol,
                'total_realized_pnl': 0.0,
                'total_commission': 0.0,
                'total_funding_fee': 0.0,
                'expected_pnl_range': (min_expected_pnl, max_expected_pnl)
            }

        # Group income records by type
        income_by_type = {}
        for income in income_records:
            if not isinstance(income, dict):
                continue

            income_type = income.get('incomeType') or income.get('type')
            if not income_type:
                continue

            if income_type not in income_by_type:
                income_by_type[income_type] = []
            income_by_type[income_type].append(income)

        logger.info(f"Trade {trade_id} ({symbol}): Found income types: {list(income_by_type.keys())}")

        # Calculate totals
        total_realized_pnl = 0.0
        total_commission = 0.0
        total_funding_fee = 0.0

        for income_type, incomes in income_by_type.items():
            for income in incomes:
                income_value = float(income.get('income', 0.0))

                if income_type == 'REALIZED_PNL':
                    total_realized_pnl += income_value
                elif income_type == 'COMMISSION':
                    total_commission += income_value
                elif income_type == 'FUNDING_FEE':
                    total_funding_fee += income_value

        # Calculate NET P&L (including fees)
        net_pnl = total_realized_pnl + total_commission + total_funding_fee

        # Check if P&L is within expected range (use REALIZED_PNL for comparison)
        within_range = min_expected_pnl <= total_realized_pnl <= max_expected_pnl

        logger.info(f"Trade {trade_id} ({symbol}): Summary")
        logger.info(f"  Position Size: {position_size}, Expected P&L Range: [{min_expected_pnl:.6f}, {max_expected_pnl:.6f}]")
        logger.info(f"  REALIZED_PNL: {total_realized_pnl:.6f}")
        logger.info(f"  COMMISSION: {total_commission:.6f}")
        logger.info(f"  FUNDING_FEE: {total_funding_fee:.6f}")
        logger.info(f"  NET P&L: {net_pnl:.6f}")

        # Derive entry/exit prices using strict exchange data precedence
        # 1) Exact orderId lookups (entry and SL/TP reduce-only) from Binance futures
        # 2) Filtered userTrades by orderId where available
        # 3) Fallback to time-bounded side-based weighted averages
        derived_entry = None
        derived_exit = None
        try:
            # Build precise search window with 1h buffer
            buffer_ms = 60 * 60 * 1000
            s_ms = max(0, (start_time or 0) - buffer_ms)
            e_ms = (end_time or start_time or 0) + buffer_ms

            # Fetch user trades; filter by time bounds and, if present, by orderId
            symbol_pair = f"{symbol}USDT" if not str(symbol).endswith("USDT") else str(symbol)

            # Priority 1: exact order lookups from Binance client
            try:
                client = getattr(self.binance_exchange, 'client', None)
                entry_order_id = trade.get('exchange_order_id')
                stop_order_id = trade.get('stop_loss_order_id')
                # Entry order exact
                if client and entry_order_id:
                    try:
                        order = await client.futures_get_order(symbol=symbol_pair, orderId=str(entry_order_id))
                        ap = order.get('avgPrice') or order.get('price') or 0
                        ex_qty = order.get('executedQty') or order.get('cumQty') or 0
                        apf = float(ap or 0)
                        if apf > 0:
                            derived_entry = apf
                    except Exception:
                        pass
                # Exit order (SL/TP) exact
                if client and stop_order_id:
                    try:
                        order = await client.futures_get_order(symbol=symbol_pair, orderId=str(stop_order_id))
                        ap = order.get('avgPrice') or order.get('price') or 0
                        apf = float(ap or 0)
                        if apf > 0:
                            derived_exit = apf
                    except Exception:
                        pass
            except Exception:
                pass

            # Priority 2/3: userTrades with strict filters, only if still missing
            if derived_entry is None or (derived_exit is None and str(position_type or '').upper() in ('LONG', 'SHORT')):
                user_trades = await self.binance_exchange.get_user_trades(symbol=symbol_pair, limit=1000)
                if isinstance(user_trades, list):
                    entry_order_id = trade.get('exchange_order_id')
                    stop_order_id = trade.get('stop_loss_order_id')

                    # Helper accumulators
                    buys: List[Tuple[float, float]] = []
                    sells: List[Tuple[float, float]] = []
                    buy_qty_sum = 0.0
                    sell_qty_sum = 0.0

                    for t in user_trades:
                        try:
                            t_time = int(t.get('time', 0))
                            if t_time < s_ms or t_time > e_ms:
                                continue
                            t_oid = str(t.get('orderId')) if t.get('orderId') is not None else ''
                            # If we have orderIds, constrain matches to them
                            if entry_order_id and stop_order_id:
                                if t_oid not in (str(entry_order_id), str(stop_order_id)):
                                    continue
                            elif entry_order_id:
                                if t_oid != str(entry_order_id):
                                    continue
                            # else: allow time-bounded trades

                            side = str(t.get('side', '')).upper()
                            price = float(t.get('price', 0) or 0)
                            qty = float(t.get('qty', 0) or 0)
                            if price > 0 and qty > 0:
                                if side == 'BUY':
                                    buys.append((price, qty))
                                    buy_qty_sum += qty
                                elif side == 'SELL':
                                    sells.append((price, qty))
                                    sell_qty_sum += qty
                        except Exception:
                            continue

                    def wavg(pairs: List[Tuple[float, float]]):
                        if not pairs:
                            return 0.0
                        tv = sum(p*q for p, q in pairs)
                        tq = sum(q for _, q in pairs)
                        return (tv / tq) if tq > 0 else 0.0

                    pos_type = str(position_type or 'LONG').upper()
                    # Enforce side-position consistency and require qty coverage >= 90% of position_size
                    try:
                        pos_qty = float(position_size or 0)
                    except Exception:
                        pos_qty = 0.0

                    coverage_ok_buy = (pos_qty == 0) or (buy_qty_sum >= 0.9 * pos_qty)
                    coverage_ok_sell = (pos_qty == 0) or (sell_qty_sum >= 0.9 * pos_qty)

                    if pos_type == 'LONG':
                        if derived_entry is None and coverage_ok_buy:
                            derived_entry = wavg(buys)
                        if derived_exit is None and coverage_ok_sell:
                            derived_exit = wavg(sells)
                    else:
                        if derived_entry is None and coverage_ok_sell:
                            derived_entry = wavg(sells)
                        if derived_exit is None and coverage_ok_buy:
                            derived_exit = wavg(buys)

        except Exception as e:
            logger.warning(f"Failed to derive entry/exit from fills: {e}")
        logger.info(f"  Within Expected Range: {within_range}")

        return {
            'trade_id': trade_id,
            'status': 'PROCESSED',
            'symbol': symbol,
            'total_realized_pnl': total_realized_pnl,
            'total_commission': total_commission,
            'total_funding_fee': total_funding_fee,
            'total_net_pnl': net_pnl,
            'expected_pnl_range': (min_expected_pnl, max_expected_pnl),
            'within_range': within_range,
            'income_count': len(income_records),
            'income_records': income_records,
            'income_by_type': income_by_type,
            'derived_entry_price': float(derived_entry or 0),
            'derived_exit_price': float(derived_exit or 0)
        }

    async def backfill_trades_with_income_history(self, days: int = 30, symbol: str = ""):
        """Backfill P&L for trades using Binance income history."""
        logger.info(f"--- Starting P&L Backfill using Binance Income History (last {days} days) ---")

        try:
            # Calculate cutoff date
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # Query for closed trades
            query = self.supabase.from_("trades").select("*").eq("status", "CLOSED").gte("created_at", cutoff_iso)

            if symbol:
                query = query.eq("coin_symbol", symbol)

            response = query.execute()
            closed_trades = response.data or []

            logger.info(f"Found {len(closed_trades)} closed trades to process")

            total_processed = 0
            total_updated = 0
            total_errors = 0

            for trade in closed_trades:
                trade_id = trade.get('id')
                current_pnl = trade.get('pnl_usd') if trade.get('pnl_usd') is not None else trade.get('pnl')
                current_pnl_source = str(trade.get('pnl_source') or '')
                current_pnl_verified = bool(trade.get('pnl_verified'))

                try:
                    # Process trade with income history
                    result = await self.process_trade_with_income_history(trade)

                    if result['status'] == 'PROCESSED':
                        # Decide overwrite policy: prefer exchange-sourced income; overwrite unless already
                        # verified from the same authoritative source and within a small tolerance
                        exchange_realized = float(result['total_realized_pnl'])
                        exchange_net = float(result['total_net_pnl'])
                        epsilon_abs = 0.01
                        epsilon_pct = 0.003  # 0.3%

                        should_overwrite_pnl = (
                            not current_pnl_verified or
                            current_pnl_source != 'binance_income' or
                            (isinstance(current_pnl, (int, float)) and (
                                abs(float(current_pnl) - exchange_realized) > max(epsilon_abs, abs(exchange_realized) * epsilon_pct)
                            )) or
                            (not isinstance(current_pnl, (int, float)))
                        )

                        # Store comprehensive P&L data in database (always include verification and sources when writing)
                        updates = {
                            'pnl_usd': exchange_realized if should_overwrite_pnl else (current_pnl if isinstance(current_pnl, (int, float)) else exchange_realized),
                            'net_pnl': exchange_net if should_overwrite_pnl else trade.get('net_pnl', exchange_net),
                            'commission': result['total_commission'] if should_overwrite_pnl else trade.get('commission', result['total_commission']),
                            'funding_fee': result['total_funding_fee'] if should_overwrite_pnl else trade.get('funding_fee', result['total_funding_fee']),
                            'last_pnl_sync': datetime.now(timezone.utc).isoformat(),
                            'updated_at': datetime.now(timezone.utc).isoformat(),
                            'pnl_verified': True if should_overwrite_pnl else bool(trade.get('pnl_verified', False)),
                            'pnl_source': 'binance_income' if should_overwrite_pnl else (trade.get('pnl_source') or 'binance_income')
                        }

                        # If we derived prices from exact fills, write them into canonical columns
                        try:
                            d_entry = float(result.get('derived_entry_price') or 0)
                            d_exit = float(result.get('derived_exit_price') or 0)
                            # Respect existing verified prices unless we can provide a more authoritative source
                            current_price_verified = bool(trade.get('price_verified'))
                            current_price_source = str(trade.get('price_source') or '')
                            allow_price_overwrite = (not current_price_verified) or (current_price_source != 'binance_user_trades/order_lookup')

                            if (d_entry > 0 or d_exit > 0) and allow_price_overwrite:
                                if d_entry > 0:
                                    updates['entry_price'] = d_entry
                                    updates['binance_entry_price'] = d_entry
                                if d_exit > 0:
                                    updates['exit_price'] = d_exit
                                    updates['binance_exit_price'] = d_exit
                                updates['price_verified'] = True
                                updates['price_source'] = 'binance_user_trades/order_lookup'
                        except Exception:
                            pass

                        # Add additional P&L breakdown if available
                        if result['total_realized_pnl'] != 0:
                            updates['has_binance_pnl'] = True
                            updates['pnl_source'] = 'binance_income_history'
                        else:
                            updates['has_binance_pnl'] = False
                            updates['pnl_source'] = 'no_income_found'

                        await update_trade_status(self.supabase, int(trade_id), updates)

                        # Store detailed income records if available
                        if result.get('income_records'):
                            await self.store_income_records(trade_id, result['income_records'], result['income_by_type'])

                        total_updated += 1

                        if result['total_realized_pnl'] != 0:
                            logger.info(f"✅ Trade {trade_id} updated with P&L: {result['total_realized_pnl']:.6f}")
                        else:
                            logger.info(f"⚠️ Trade {trade_id} processed but no P&L found")

                    total_processed += 1

                    # Rate limiting
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error processing trade {trade_id}: {e}")
                    total_errors += 1

            logger.info(f"--- P&L Backfill Complete ---")
            logger.info(f"Total processed: {total_processed}")
            logger.info(f"Total updated: {total_updated}")
            logger.info(f"Total errors: {total_errors}")

        except Exception as e:
            logger.error(f"Error during backfill: {e}", exc_info=True)

    async def store_income_records(self, trade_id: int, income_records: List[Dict], income_by_type: Dict):
        """Store detailed income records for a trade in the audit table (analytics-only)."""
        try:
            # Create a summary of income records
            income_summary = {
                'trade_id': trade_id,
                'total_records': len(income_records),
                'income_by_type': {},
                'detailed_records': []
            }

            # Process income by type
            for income_type, incomes in income_by_type.items():
                total_value = sum(float(income.get('income', 0.0)) for income in incomes)
                income_summary['income_by_type'][income_type] = {
                    'count': len(incomes),
                    'total_value': total_value,
                    'records': incomes
                }

            # Store detailed records (first 10 to avoid database bloat)
            for income in income_records[:10]:
                income_summary['detailed_records'].append({
                    'time': income.get('time'),
                    'income': income.get('income'),
                    'incomeType': income.get('incomeType'),
                    'asset': income.get('asset'),
                    'info': income.get('info', ''),
                    'tranId': income.get('tranId', ''),
                    'tradeId': income.get('tradeId', '')
                })

            # Insert into audit table to avoid bloating trades
            try:
                payload = {
                    'trade_id': int(trade_id),
                    'exchange': 'binance',
                    'income': income_summary
                }
                self.supabase.table("trades_income_audit").insert(payload).execute()
            except Exception as e:
                logger.error(f"Failed to insert income audit for trade {trade_id}: {e}")
            logger.info(f"Stored {len(income_records)} income records (audit) for trade {trade_id}")

        except Exception as e:
            logger.error(f"Error storing income records for trade {trade_id}: {e}")


async def backfill_pnl_and_exit_prices():
    """Main backfill function using improved Binance income history method."""
    logger.info("--- Starting P&L Backfill using Binance Income History ---")

    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logger.error("Failed to initialize clients.")
        return

    # Initialize Binance client
    if not bot.binance_exchange.client:
        await bot.binance_exchange._init_client()

    if not bot.binance_exchange.client:
        logger.error("Binance client is not initialized.")
        return

    try:
        # Create backfiller instance
        backfiller = BinancePnLBackfiller(bot, supabase)

        # Backfill trades from last 30 days
        await backfiller.backfill_trades_with_income_history(days=30)

    except Exception as e:
        logger.error(f"Error during backfill: {e}", exc_info=True)
    finally:
        if bot and bot.binance_exchange:
            await bot.binance_exchange.close()
            logger.info("Binance client connection closed.")


async def main():
    await backfill_pnl_and_exit_prices()


if __name__ == "__main__":
    asyncio.run(main())