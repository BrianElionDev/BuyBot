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
from typing import Optional, Dict, List, Tuple, Set, Any
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
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter

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
            be_val = float(trade.get('entry_price') or 0)
        except Exception:
            be_val = 0.0
        try:
            bx_val = float(trade.get('exit_price') or 0)
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

        # Edge-case validations
        flags: list[str] = []
        try:
            ep = float(entry_price or 0)
            xp = float(exit_price or 0)
            ps = float(position_size or 0)
            pos_type = str(position_type or 'LONG').upper()
        except Exception:
            ep, xp, ps, pos_type = 0.0, 0.0, 0.0, 'LONG'

        # 1) Zero or tiny position size with non-zero PnL
        if ps <= 0 and abs(total_realized_pnl) > 0:
            flags.append("ZERO_SIZE_NONZERO_PNL")

        # 2) Inverted price-PnL logic
        if ep > 0 and xp > 0 and ps > 0:
            if pos_type == 'LONG' and xp < ep and total_realized_pnl > 0:
                flags.append("LONG_NEG_PRICE_POS_PNL")
            if pos_type == 'SHORT' and xp > ep and total_realized_pnl > 0:
                flags.append("SHORT_NEG_PRICE_POS_PNL")

        # 3) Extreme fee ratio relative to realized pnl magnitude
        total_fees = abs(total_commission) + abs(total_funding_fee)
        if abs(total_realized_pnl) > 0 and (total_fees / max(abs(total_realized_pnl), 1e-9)) > 5:
            flags.append("EXCESSIVE_FEES_RATIO")

        # 4) Out of expected range already computed
        if not within_range:
            flags.append("PNL_OUT_OF_RANGE")

        # Prepare structured summary for audit table (NOT the trades table)
        income_summary = {
            'total_realized_pnl': total_realized_pnl,
            'total_commission': total_commission,
            'total_funding_fee': total_funding_fee,
            'net_pnl': net_pnl,
            'expected_pnl_range': (min_expected_pnl, max_expected_pnl)
        }

        # Keep trades table update_data minimal and schema-compliant
        update_data: Dict[str, Any] = {
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        if flags:
            update_data['manual_verification_needed'] = True  # type: ignore[assignment]
            sync_issues = (trade.get('sync_issues') or [])
            if not isinstance(sync_issues, list):
                sync_issues = [str(sync_issues)]
            sync_issues.extend(flags)
            # Ensure unique list of strings
            update_data['sync_issues'] = list(sorted({str(x) for x in sync_issues}))  # type: ignore[assignment]

        # Persist updates
        try:
            # Validate trade_id before update
            trade_id_int: Optional[int] = None
            try:
                if isinstance(trade_id, int):
                    trade_id_int = trade_id
                elif isinstance(trade_id, str) and trade_id.isdigit():
                    trade_id_int = int(trade_id)
            except Exception:
                trade_id_int = None

            if trade_id_int is not None:
                import asyncio as _asyncio
                _asyncio.create_task(update_trade_status(self.supabase, trade_id_int, update_data))
            else:
                logger.error(f"Cannot persist PnL updates: invalid trade_id={trade_id}")
        except Exception as e:
            logger.error(f"Failed to persist PnL updates for trade {trade_id}: {e}")

        status = 'OK' if not flags and within_range else 'FLAGGED'
        return {
            'trade_id': trade_id,
            'status': status,
            'symbol': symbol,
            'summary': income_summary,
            'income_records': income_records,
            'income_by_type': income_by_type,
            'flags': flags,
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
                                if d_exit > 0:
                                    updates['exit_price'] = d_exit
                                updates['price_verified'] = True
                                updates['price_source'] = 'binance_user_trades/order_lookup'
                        except Exception:
                            pass


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


class KucoinPnLBackfiller:
    """Backfill P&L using KuCoin history-positions API with strict matching and symbol normalization."""

    def __init__(self, kucoin_exchange: KucoinExchange, supabase):
        self.kucoin_exchange = kucoin_exchange
        self.supabase = supabase
        self.symbol_converter = KucoinSymbolConverter()
        self.used_close_ids: Set[str] = set()

    def parse_timestamp(self, timestamp_str: str) -> Optional[int]:
        """Parse timestamp string to milliseconds."""
        try:
            if 'T' in timestamp_str:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            if timestamp_str.isdigit():
                ts = int(timestamp_str)
                if ts < 1000000000000:
                    ts *= 1000
                return ts
            return None
        except Exception:
            return None

    def get_order_lifecycle(self, db_trade: Dict) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Get order start, end, and duration in milliseconds."""
        try:
            created_at = db_trade.get('created_at') or db_trade.get('createdAt')
            closed_at = db_trade.get('closed_at')
            updated_at = db_trade.get('updated_at') or db_trade.get('updatedAt')

            if not created_at:
                logger.warning(f"Trade {db_trade.get('id')} has no created_at timestamp")
                return None, None, None

            start_time = self.parse_timestamp(str(created_at))
            if not start_time:
                logger.warning(f"Trade {db_trade.get('id')} has invalid created_at: {created_at}")
                return None, None, None

            if not closed_at:
                if updated_at:
                    end_time = self.parse_timestamp(str(updated_at))
                    if not end_time:
                        end_time = start_time
                        duration = 0
                    else:
                        duration = end_time - start_time
                else:
                    end_time = start_time
                    duration = 0
            else:
                end_time = self.parse_timestamp(str(closed_at))
                if not end_time:
                    end_time = start_time
                    duration = 0
                else:
                    duration = end_time - start_time

            return start_time, end_time, duration
        except Exception as e:
            logger.error(f"Error getting order lifecycle: {e}")
            return None, None, None

    def normalize_symbol_to_kucoin(self, coin_symbol: str) -> str:
        """Normalize coin symbol to KuCoin futures format (BTC -> XBTUSDTM)."""
        try:
            coin_upper = str(coin_symbol).upper().strip()
            if coin_upper == 'BTC':
                return 'XBTUSDTM'
            return f"{coin_upper}USDTM"
        except Exception:
            return f"{coin_symbol}USDTM"

    def normalize_symbol_from_kucoin(self, kucoin_symbol: str) -> str:
        """Normalize KuCoin symbol back to bot format (XBTUSDTM -> BTC)."""
        try:
            if kucoin_symbol == 'XBTUSDTM' or kucoin_symbol.startswith('XBT'):
                return 'BTC'
            return kucoin_symbol.replace('USDTM', '').upper()
        except Exception:
            return kucoin_symbol

    async def fetch_position_history(self, kucoin_symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        """Fetch position history from KuCoin API with fallback logic."""
        try:
            params = {"symbol": kucoin_symbol, "startAt": start_ms, "endAt": end_ms}
            pos_resp = await self.kucoin_exchange._make_direct_api_call('GET', '/api/v1/history-positions', params)

            records: List[Dict] = []
            if isinstance(pos_resp, list):
                records = pos_resp
            elif isinstance(pos_resp, dict):
                items = pos_resp.get('items') or pos_resp.get('data') or []
                if isinstance(items, list):
                    records = items

            if not records:
                params_no_symbol = {"startAt": start_ms, "endAt": end_ms}
                pos_resp2 = await self.kucoin_exchange._make_direct_api_call('GET', '/api/v1/history-positions', params_no_symbol)
                if isinstance(pos_resp2, list):
                    records = pos_resp2
                elif isinstance(pos_resp2, dict):
                    items2 = pos_resp2.get('items') or pos_resp2.get('data') or []
                    if isinstance(items2, list):
                        records = items2

            return [r for r in records if str(r.get('symbol') or '') == kucoin_symbol]
        except Exception as e:
            logger.error(f"Error fetching position history: {e}")
            return []

    def match_position_record(
        self,
        records: List[Dict],
        trade: Dict,
        kucoin_symbol: str,
        created_ms: int,
        closed_ms: int
    ) -> Optional[Dict]:
        """Strictly match a position record to a trade using multiple criteria."""
        if not records:
            return None

        position_type = str(trade.get('signal_type') or '').upper()
        expected_close_type = 'CLOSE_LONG' if position_type == 'LONG' else ('CLOSE_SHORT' if position_type == 'SHORT' else None)
        expected_side = 'LONG' if position_type == 'LONG' else ('SHORT' if position_type == 'SHORT' else None)

        created_pad_ms = 5 * 60 * 1000
        end_pad_ms = 15 * 60 * 1000
        end_ms = closed_ms + end_pad_ms

        def get_ms(val: Any) -> int:
            try:
                return int(val or 0)
            except Exception:
                return 0

        strict_candidates: List[Dict] = []
        for r in records:
            cid = str(r.get('closeId') or '')
            if cid and cid in self.used_close_ids:
                continue

            if str(r.get('symbol') or '') != kucoin_symbol:
                continue

            o_ms = get_ms(r.get('openTime'))
            c_ms = get_ms(r.get('closeTime'))

            if o_ms and o_ms < max(0, created_ms - created_pad_ms):
                continue
            if c_ms and c_ms > end_ms:
                continue

            r_type = str(r.get('type') or '').upper()
            r_side = str(r.get('side') or '').upper()

            if expected_close_type and r_type and expected_close_type not in r_type:
                continue
            if expected_side and r_side and expected_side not in r_side:
                continue

            strict_candidates.append(r)

        if not strict_candidates:
            strict_candidates = [r for r in records if str(r.get('closeId') or '') not in self.used_close_ids and str(r.get('symbol') or '') == kucoin_symbol]
            if not strict_candidates:
                return None

        def score(r: Dict) -> Tuple[int, int]:
            c_ms = get_ms(r.get('closeTime'))
            o_ms = get_ms(r.get('openTime'))
            return (
                abs(c_ms - closed_ms) if c_ms else 1_000_000_000,
                abs(o_ms - created_ms) if o_ms else 1_000_000_000
            )

        return min(strict_candidates, key=score)

    async def process_trade_with_position_history(self, trade: Dict) -> Dict:
        """Process a single trade using KuCoin position history."""
        trade_id = trade.get('id')
        coin_symbol = trade.get('coin_symbol', '').upper()
        position_type = trade.get('signal_type', 'LONG')

        if not coin_symbol:
            logger.warning(f"Trade {trade_id} has no coin_symbol")
            return {'trade_id': trade_id, 'status': 'SKIPPED', 'reason': 'No coin_symbol'}

        start_time, end_time, duration = self.get_order_lifecycle(trade)
        if not start_time or not end_time:
            logger.warning(f"Trade {trade_id} has no valid timestamps")
            return {'trade_id': trade_id, 'status': 'SKIPPED', 'reason': 'No valid timestamps'}

        kucoin_symbol = self.normalize_symbol_to_kucoin(coin_symbol)
        start_ms = max(0, start_time - 15 * 60 * 1000)
        end_ms = end_time + 15 * 60 * 1000

        records = await self.fetch_position_history(kucoin_symbol, start_ms, end_ms)
        if not records:
            logger.info(f"Trade {trade_id} ({coin_symbol}): No position history found")
            return {
                'trade_id': trade_id,
                'status': 'NO_HISTORY',
                'symbol': coin_symbol,
                'kucoin_symbol': kucoin_symbol
            }

        matched_record = self.match_position_record(records, trade, kucoin_symbol, start_time, end_time)
        if not matched_record:
            logger.info(f"Trade {trade_id} ({coin_symbol}): No matching position record found")
            return {
                'trade_id': trade_id,
                'status': 'NO_MATCH',
                'symbol': coin_symbol,
                'kucoin_symbol': kucoin_symbol
            }

        close_id = matched_record.get('closeId')
        if close_id:
            self.used_close_ids.add(str(close_id))

        entry_price_val = matched_record.get('avgEntryPrice') or matched_record.get('openPrice')
        exit_price_val = matched_record.get('closePrice') or matched_record.get('avgExitPrice')
        pnl_val = matched_record.get('pnl') or matched_record.get('realizedPnl') or matched_record.get('realisedPnl')

        fee_candidates = [
            matched_record.get('tradeFee'),
            matched_record.get('fee'),
            matched_record.get('closeFee')
        ]
        total_fees = 0.0
        for fee_val in fee_candidates:
            try:
                if fee_val is not None:
                    total_fees += float(fee_val)
            except Exception:
                pass

        try:
            funding_fee = float(matched_record.get('fundingFee') or 0)
        except Exception:
            funding_fee = 0.0

        try:
            realized_pnl = float(pnl_val) if pnl_val is not None else 0.0
        except Exception:
            realized_pnl = 0.0

        net_pnl = realized_pnl

        logger.info(f"Trade {trade_id} ({coin_symbol}): Position History Match")
        logger.info(f"  Entry Price: {entry_price_val}, Exit Price: {exit_price_val}")
        logger.info(f"  Realized PnL: {realized_pnl}, Fees: {total_fees}, Funding Fee: {funding_fee}")
        logger.info(f"  Net PnL: {net_pnl}, CloseId: {close_id}")

        return {
            'trade_id': trade_id,
            'status': 'PROCESSED',
            'symbol': coin_symbol,
            'kucoin_symbol': kucoin_symbol,
            'entry_price': float(entry_price_val) if entry_price_val else None,
            'exit_price': float(exit_price_val) if exit_price_val else None,
            'realized_pnl': realized_pnl,
            'net_pnl': net_pnl,
            'commission': total_fees,
            'funding_fee': funding_fee,
            'position_record': matched_record,
            'close_id': close_id
        }

    async def backfill_trades_with_position_history(self, days: int = 30, symbol: str = ""):
        """Backfill P&L for KuCoin trades using position history."""
        logger.info(f"--- Starting KuCoin P&L Backfill using Position History (last {days} days) ---")

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            query = self.supabase.from_("trades").select("*").eq("exchange", "kucoin").eq("status", "CLOSED").gte("created_at", cutoff_iso)

            if symbol:
                query = query.eq("coin_symbol", symbol)

            response = query.execute()
            closed_trades = response.data or []

            logger.info(f"Found {len(closed_trades)} closed KuCoin trades to process")

            total_processed = 0
            total_updated = 0
            total_errors = 0

            for trade in closed_trades:
                trade_id = trade.get('id')
                current_pnl = trade.get('pnl_usd') if trade.get('pnl_usd') is not None else trade.get('net_pnl')
                current_entry = trade.get('entry_price')
                current_exit = trade.get('exit_price')
                current_pnl_verified = bool(trade.get('pnl_verified'))
                current_price_verified = bool(trade.get('price_verified'))
                current_pnl_source = str(trade.get('pnl_source') or '')
                current_price_source = str(trade.get('price_source') or '')

                try:
                    result = await self.process_trade_with_position_history(trade)

                    if result['status'] == 'PROCESSED':
                        exchange_pnl = float(result['realized_pnl'])
                        exchange_net = float(result['net_pnl'])
                        exchange_entry = result.get('entry_price')
                        exchange_exit = result.get('exit_price')

                        epsilon_abs = 0.01
                        epsilon_pct = 0.003

                        should_overwrite_pnl = (
                            not current_pnl_verified or
                            current_pnl_source != 'kucoin_history_positions' or
                            (isinstance(current_pnl, (int, float)) and (
                                abs(float(current_pnl) - exchange_pnl) > max(epsilon_abs, abs(exchange_pnl) * epsilon_pct)
                            )) or
                            (not isinstance(current_pnl, (int, float)))
                        )

                        should_overwrite_price = (
                            not current_price_verified or
                            current_price_source != 'kucoin_history_positions' or
                            (exchange_entry and current_entry and abs(float(exchange_entry) - float(current_entry)) > max(epsilon_abs, abs(float(exchange_entry)) * epsilon_pct)) or
                            (exchange_exit and current_exit and abs(float(exchange_exit) - float(current_exit)) > max(epsilon_abs, abs(float(exchange_exit)) * epsilon_pct))
                        )

                        updates: Dict[str, Any] = {
                            'last_pnl_sync': datetime.now(timezone.utc).isoformat(),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }

                        if should_overwrite_pnl:
                            updates['pnl_usd'] = exchange_pnl
                            updates['net_pnl'] = exchange_net
                            updates['commission'] = result.get('commission', 0.0)
                            updates['funding_fee'] = result.get('funding_fee', 0.0)
                            updates['pnl_verified'] = True
                            updates['pnl_source'] = 'kucoin_history_positions'
                        else:
                            updates['pnl_verified'] = current_pnl_verified
                            updates['pnl_source'] = current_pnl_source or 'kucoin_history_positions'

                        if should_overwrite_price:
                            if exchange_entry:
                                updates['entry_price'] = exchange_entry
                            if exchange_exit:
                                updates['exit_price'] = exchange_exit
                            updates['price_verified'] = True
                            updates['price_source'] = 'kucoin_history_positions'
                        else:
                            if exchange_entry and not current_entry:
                                updates['entry_price'] = exchange_entry
                            if exchange_exit and not current_exit:
                                updates['exit_price'] = exchange_exit
                            updates['price_verified'] = current_price_verified
                            updates['price_source'] = current_price_source or 'kucoin_history_positions'

                        await update_trade_status(self.supabase, int(trade_id), updates)

                        if result.get('position_record'):
                            await self.store_position_history_record(trade_id, result['position_record'], result)

                        total_updated += 1

                        if result['realized_pnl'] != 0:
                            logger.info(f"✅ Trade {trade_id} updated with P&L: {result['realized_pnl']:.6f}")
                        else:
                            logger.info(f"⚠️ Trade {trade_id} processed but no P&L found")

                    total_processed += 1
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error processing trade {trade_id}: {e}")
                    total_errors += 1

            logger.info(f"--- KuCoin P&L Backfill Complete ---")
            logger.info(f"Total processed: {total_processed}")
            logger.info(f"Total updated: {total_updated}")
            logger.info(f"Total errors: {total_errors}")

        except Exception as e:
            logger.error(f"Error during KuCoin backfill: {e}", exc_info=True)

    async def store_position_history_record(self, trade_id: int, position_record: Dict, result: Dict):
        """Store detailed position history record in audit table."""
        try:
            audit_data = {
                'trade_id': int(trade_id),
                'exchange': 'kucoin',
                'income': {
                    'source': 'position_history',
                    'position_record': position_record,
                    'close_id': result.get('close_id'),
                    'symbol': result.get('kucoin_symbol'),
                    'entry_price': result.get('entry_price'),
                    'exit_price': result.get('exit_price'),
                    'realized_pnl': result.get('realized_pnl'),
                    'net_pnl': result.get('net_pnl'),
                    'commission': result.get('commission'),
                    'funding_fee': result.get('funding_fee')
                }
            }
            self.supabase.table("trades_income_audit").insert(audit_data).execute()
            logger.info(f"Stored position history record (audit) for trade {trade_id}")
        except Exception as e:
            logger.error(f"Failed to insert position history audit for trade {trade_id}: {e}")


async def backfill_pnl_and_exit_prices():
    """Main backfill function for both Binance and KuCoin."""
    logger.info("--- Starting P&L Backfill for Binance and KuCoin ---")

    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logger.error("Failed to initialize clients.")
        return

    # Initialize Binance client
    binance_initialized = False
    if bot.binance_exchange:
        if not bot.binance_exchange.client:
            await bot.binance_exchange._init_client()
        if bot.binance_exchange.client:
            binance_initialized = True

    # Initialize KuCoin client
    kucoin_initialized = False
    kucoin_exchange = None
    if bot.kucoin_exchange:
        try:
            kucoin_exchange = bot.kucoin_exchange
            await kucoin_exchange.initialize()
            kucoin_initialized = True
        except Exception as e:
            logger.warning(f"Failed to initialize KuCoin client: {e}")
    else:
        try:
            from config import settings
            kucoin_exchange = KucoinExchange(
                api_key=settings.KUCOIN_API_KEY or "",
                api_secret=settings.KUCOIN_API_SECRET or "",
                api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
                is_testnet=False,
            )
            await kucoin_exchange.initialize()
            kucoin_initialized = True
        except Exception as e:
            logger.warning(f"Failed to create KuCoin exchange: {e}")

    try:
        if binance_initialized:
            logger.info("=== Processing Binance trades ===")
            binance_backfiller = BinancePnLBackfiller(bot, supabase)
            await binance_backfiller.backfill_trades_with_income_history(days=30)

        if kucoin_initialized and kucoin_exchange:
            logger.info("=== Processing KuCoin trades ===")
            kucoin_backfiller = KucoinPnLBackfiller(kucoin_exchange, supabase)
            await kucoin_backfiller.backfill_trades_with_position_history(days=30)

    except Exception as e:
        logger.error(f"Error during backfill: {e}", exc_info=True)
    finally:
        if bot and bot.binance_exchange:
            try:
                await bot.binance_exchange.close()
                logger.info("Binance client connection closed.")
            except Exception:
                pass
        if kucoin_exchange:
            try:
                await kucoin_exchange.close()
                logger.info("KuCoin client connection closed.")
            except Exception:
                pass


async def main():
    await backfill_pnl_and_exit_prices()


if __name__ == "__main__":
    asyncio.run(main())