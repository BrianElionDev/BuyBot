#!/usr/bin/env python3
"""
KuCoin 7-Day PnL Reconciliation

Fixes incorrect/overlapping PnL for CLOSED KuCoin trades in the past 7 days by:
- Pulling exact futures fills via get_user_trades(symbol, start, end) and computing realized PnL
- Optionally using futures account ledgers when clear realized PnL entries exist
- Preventing fill reuse across trades within the run
- Updating only mismatched CLOSED trades; persists used fill ids in sync_issues

Usage:
  python3 scripts/maintenance/kucoin_pnl_reconcile_7d.py
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Set

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from config import settings
from supabase import create_client, Client
from src.exchange.kucoin.kucoin_exchange import KucoinExchange

sup_url = settings.SUPABASE_URL or ""
sup_key = settings.SUPABASE_KEY or ""
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _parse_exchange_response_order_ids(exchange_response: Any) -> Tuple[Optional[str], Optional[str]]:
    order_id = None
    client_oid = None
    if not exchange_response:
        return order_id, client_oid
    try:
        data = exchange_response
        if isinstance(exchange_response, str):
            data = json.loads(exchange_response)
        if isinstance(data, dict):
            order_id = str(data.get('orderId') or '') or None
            client_oid = str(data.get('clientOrderId') or '') or None
    except Exception:
        pass
    return order_id, client_oid


def _to_ms(dt: Any) -> int:
    if not dt:
        return 0
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except Exception:
            return 0
        return int(parsed.timestamp() * 1000)
    if isinstance(dt, datetime):
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    return 0


def _hash_fill_ids(fill_ids: List[str]) -> str:
    enc = json.dumps(sorted(fill_ids)).encode('utf-8')
    return hashlib.sha256(enc).hexdigest()[:32]


def _pick_position_record(records: List[Dict[str, Any]], closed_ms: int) -> Optional[Dict[str, Any]]:
    if not records:
        return None
    # choose the record closest to closed_ms
    def rec_time_ms(r: Dict[str, Any]) -> int:
        t = r.get('updatedAt') or r.get('createdAt') or r.get('time') or 0
        try:
            return int(t)
        except Exception:
            return 0
    return min(records, key=lambda r: abs(rec_time_ms(r) - closed_ms))


async def fetch_all_position_history(
    ex: KucoinExchange,
    kucoin_symbol: str,
    start_ms: int,
    end_ms: int
) -> List[Dict[str, Any]]:
    """
    Fetch all position history records with pagination support.

    Args:
        ex: KuCoin exchange instance
        kucoin_symbol: KuCoin futures symbol (e.g., XBTUSDTM)
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds

    Returns:
        List of position history records
    """
    all_records: List[Dict[str, Any]] = []
    current_page = 1
    page_size = 50
    max_pages = 100  # Safety limit

    logger.info(
        f"Fetching position history for {kucoin_symbol} "
        f"from {datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).isoformat()} "
        f"to {datetime.fromtimestamp(end_ms/1000, tz=timezone.utc).isoformat()}"
    )

    while current_page <= max_pages:
        params = {
            "symbol": kucoin_symbol,
            "startAt": start_ms,
            "endAt": end_ms,
            "currentPage": current_page,
            "pageSize": page_size
        }

        try:
            logger.debug(
                f"Fetching page {current_page} of position history for {kucoin_symbol} "
                f"(params: {json.dumps(params, default=str)})"
            )
            pos_resp = await ex._make_direct_api_call('GET', '/api/v1/history-positions', params)

            # Log raw response structure for debugging
            if current_page == 1:
                logger.debug(f"Raw API response type: {type(pos_resp)}, structure: {str(pos_resp)[:200] if pos_resp else 'None'}")

            # Handle different response formats
            page_records: List[Dict[str, Any]] = []

            if isinstance(pos_resp, list):
                page_records = pos_resp
            elif isinstance(pos_resp, dict):
                # Check for paginated response structure
                if 'items' in pos_resp:
                    page_records = pos_resp.get('items', [])
                elif 'data' in pos_resp:
                    data = pos_resp.get('data')
                    if isinstance(data, list):
                        page_records = data
                    elif isinstance(data, dict) and 'items' in data:
                        page_records = data.get('items', [])
                else:
                    # Try to extract from root level
                    items = pos_resp.get('items') or pos_resp.get('data') or []
                    if isinstance(items, list):
                        page_records = items

            if not page_records:
                # Try fallback without symbol filter
                if current_page == 1:
                    logger.debug(f"No records with symbol filter, trying without symbol for page {current_page}")
                    params_no_symbol = {
                        "startAt": start_ms,
                        "endAt": end_ms,
                        "currentPage": current_page,
                        "pageSize": page_size
                    }
                    pos_resp2 = await ex._make_direct_api_call('GET', '/api/v1/history-positions', params_no_symbol)

                    if isinstance(pos_resp2, list):
                        page_records = pos_resp2
                    elif isinstance(pos_resp2, dict):
                        if 'items' in pos_resp2:
                            page_records = pos_resp2.get('items', [])
                        elif 'data' in pos_resp2:
                            data2 = pos_resp2.get('data')
                            if isinstance(data2, list):
                                page_records = data2
                            elif isinstance(data2, dict) and 'items' in data2:
                                page_records = data2.get('items', [])

                # Filter to symbol if we got mixed results
                if page_records:
                    page_records = [r for r in page_records if str(r.get('symbol') or '') == kucoin_symbol]

            if not page_records:
                logger.debug(f"No more records found at page {current_page}")
                break

            all_records.extend(page_records)
            logger.debug(f"Page {current_page}: Found {len(page_records)} records (total: {len(all_records)})")

            # Check if there are more pages
            # KuCoin API typically returns fewer records than pageSize when on last page
            if len(page_records) < page_size:
                logger.debug(f"Last page reached (got {len(page_records)} < {page_size} records)")
                break

            current_page += 1

        except Exception as e:
            logger.error(
                f"Error fetching position history page {current_page} for {kucoin_symbol}: {e}",
                exc_info=True
            )
            break

    logger.info(f"Fetched {len(all_records)} total position history records across {current_page} page(s)")
    return all_records


async def calculate_pnl_from_fills(
    ex: KucoinExchange,
    trade: Dict[str, Any],
    kucoin_symbol: str,
    start_ms: int,
    end_ms: int,
    used_fill_ids: Set[str]
) -> Optional[Dict[str, Any]]:
    """
    Calculate PnL from fills/trades when position history is not available.

    Args:
        ex: KuCoin exchange instance
        trade: Trade dictionary from database
        kucoin_symbol: KuCoin futures symbol
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds
        used_fill_ids: Set of fill IDs already used (to prevent double-counting)

    Returns:
        Update dictionary with PnL and related fields, or None if calculation fails
    """
    symbol = str(trade.get('coin_symbol') or '').upper()
    position_type = str(trade.get('signal_type') or '').upper()

    logger.info(
        f"Trade {trade.get('id')} ({symbol}): Calculating PnL from fills for {kucoin_symbol} "
        f"({position_type} position)"
    )

    try:
        # Fetch all fills in the time window
        fills = await ex.get_user_trades(
            symbol=kucoin_symbol,
            start_time=start_ms,
            end_time=end_ms,
            limit=1000
        )

        if not fills:
            logger.warning(f"Trade {trade.get('id')} ({symbol}): No fills found in time window")
            return None

        logger.info(f"Trade {trade.get('id')} ({symbol}): Found {len(fills)} fills")

        # Determine expected entry and exit sides
        if position_type == 'LONG':
            entry_side = 'BUY'
            exit_side = 'SELL'
        elif position_type == 'SHORT':
            entry_side = 'SELL'
            exit_side = 'BUY'
        else:
            logger.warning(f"Trade {trade.get('id')} ({symbol}): Unknown position type: {position_type}")
            return None

        # Filter fills by side and check if already used
        entry_fills: List[Dict[str, Any]] = []
        exit_fills: List[Dict[str, Any]] = []

        # Get exchange order ID to match fills
        exchange_order_id = str(trade.get('exchange_order_id') or trade.get('kucoin_order_id') or '')

        for fill in fills:
            fill_id = str(fill.get('tradeId') or fill.get('id') or fill.get('orderId') or '')
            if fill_id and fill_id in used_fill_ids:
                continue

            # Check side - handle various field names and formats
            fill_side = str(fill.get('side') or fill.get('liquidity') or '').upper()
            fill_order_id = str(fill.get('orderId') or fill.get('order_id') or '')

            # If we have an order ID, prefer matching by order ID first
            if exchange_order_id and fill_order_id:
                if fill_order_id == exchange_order_id:
                    # This fill belongs to our trade
                    if fill_side in (entry_side, 'MAKER', 'TAKER'):
                        entry_fills.append(fill)
                    elif fill_side in (exit_side, 'MAKER', 'TAKER'):
                        exit_fills.append(fill)
                    continue

            # Fallback to side matching
            if fill_side == entry_side:
                entry_fills.append(fill)
            elif fill_side == exit_side:
                exit_fills.append(fill)
            # Also check for reduce-only orders (exits)
            elif fill.get('reduceOnly') or fill.get('reduce_only'):
                exit_fills.append(fill)

        if not entry_fills and not exit_fills:
            logger.warning(f"Trade {trade.get('id')} ({symbol}): No matching fills found (entry: {len(entry_fills)}, exit: {len(exit_fills)})")
            return None

        # Calculate realized PnL from exit fills
        # KuCoin fills include realizedPnl field for exit trades
        total_realized_pnl = 0.0
        total_commission = 0.0
        total_entry_value = 0.0
        total_exit_value = 0.0
        entry_qty = 0.0
        exit_qty = 0.0

        # Process entry fills
        for fill in entry_fills:
            try:
                qty = float(fill.get('size') or fill.get('qty') or 0)
                price = float(fill.get('price') or 0)
                commission = float(fill.get('fee') or fill.get('commission') or 0)

                entry_qty += qty
                total_entry_value += qty * price
                total_commission += commission
            except (ValueError, TypeError) as e:
                logger.warning(f"Error processing entry fill: {e}")

        # Process exit fills (these contain realized PnL)
        exit_fill_ids: List[str] = []
        for fill in exit_fills:
            try:
                fill_id = str(fill.get('tradeId') or fill.get('id') or '')
                if fill_id:
                    exit_fill_ids.append(fill_id)

                # Try to get realized PnL directly from fill
                realized_pnl = fill.get('realizedPnl') or fill.get('realisedPnl') or fill.get('pnl')
                if realized_pnl is not None:
                    total_realized_pnl += float(realized_pnl)
                else:
                    # Calculate from price difference if PnL not directly available
                    qty = float(fill.get('size') or fill.get('qty') or 0)
                    price = float(fill.get('price') or 0)
                    exit_qty += qty
                    total_exit_value += qty * price

                commission = float(fill.get('fee') or fill.get('commission') or 0)
                total_commission += commission
            except (ValueError, TypeError) as e:
                logger.warning(f"Error processing exit fill: {e}")

        # If we didn't get realized PnL directly, calculate it
        if total_realized_pnl == 0.0 and total_entry_value > 0 and total_exit_value > 0:
            if position_type == 'LONG':
                total_realized_pnl = total_exit_value - total_entry_value
            else:  # SHORT
                total_realized_pnl = total_entry_value - total_exit_value

        # Net PnL = realized PnL - commissions
        net_pnl = total_realized_pnl - total_commission

        # Calculate average entry and exit prices
        avg_entry_price = total_entry_value / entry_qty if entry_qty > 0 else None
        avg_exit_price = total_exit_value / exit_qty if exit_qty > 0 else None

        # If we don't have exit price from fills, try to get it from trade data
        if not avg_exit_price:
            exit_price_val = trade.get('exit_price')
            if exit_price_val:
                try:
                    avg_exit_price = float(exit_price_val)
                except (ValueError, TypeError):
                    pass

        logger.info(
            f"Trade {trade.get('id')} ({symbol}): Fills-based PnL calculation - "
            f"Realized: {total_realized_pnl:.8f}, Commission: {total_commission:.8f}, "
            f"Net: {net_pnl:.8f}, Entry Qty: {entry_qty}, Exit Qty: {exit_qty}"
        )

        # Mark fill IDs as used
        for fill_id in exit_fill_ids:
            if fill_id:
                used_fill_ids.add(fill_id)

        # Compare with existing PnL - don't overwrite correct values
        db_pnl = float(trade.get('pnl_usd') or trade.get('net_pnl') or 0)
        pnl_diff = abs(db_pnl - net_pnl)
        pnl_diff_pct = abs(pnl_diff / net_pnl) if net_pnl != 0 else 1.0

        # Don't update if PnL already matches or is close
        if pnl_diff <= 0.01:
            logger.info(
                f"Trade {trade.get('id')} ({symbol}): PNL already matches "
                f"(db={db_pnl:.8f}, calculated={net_pnl:.8f}, diff={pnl_diff:.8f})"
            )
            return None

        # If existing PnL is non-zero and reasonably close, don't overwrite
        if db_pnl != 0 and (pnl_diff <= 0.10 or pnl_diff_pct <= 0.05):
            logger.info(
                f"Trade {trade.get('id')} ({symbol}): PNL is close to existing value, not overwriting "
                f"(db={db_pnl:.8f}, calculated={net_pnl:.8f}, diff={pnl_diff:.8f}, diff_pct={pnl_diff_pct*100:.2f}%)"
            )
            return None

        # Prepare update data
        summary = {
            "source": "FILLS",
            "symbol": kucoin_symbol,
            "realized_pnl": total_realized_pnl,
            "commission": total_commission,
            "entry_fills": len(entry_fills),
            "exit_fills": len(exit_fills),
            "avg_entry_price": avg_entry_price,
            "avg_exit_price": avg_exit_price
        }
        sync_text = f"{summary}"

        update_data: Dict[str, Any] = {
            "pnl_usd": round(net_pnl, 8),
            "net_pnl": round(net_pnl, 8),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sync_order_response": sync_text
        }

        # Set entry/exit prices if available
        if avg_entry_price is not None:
            update_data["entry_price"] = avg_entry_price
        if avg_exit_price is not None:
            update_data["exit_price"] = avg_exit_price

        return update_data

    except Exception as e:
        logger.error(f"Error calculating PnL from fills for trade {trade.get('id')}: {e}")
        return None


async def reconcile_trade(
    ex: KucoinExchange,
    supabase: Client,
    trade: Dict[str, Any],
    used_close_ids: Set[str],
    used_fill_ids: Optional[Set[str]] = None
) -> Optional[Dict[str, Any]]:
    if (trade.get('exchange') != 'kucoin') or (trade.get('status') != 'CLOSED'):
        return None

    created_ms = _to_ms(trade.get('created_at'))
    closed_ms = _to_ms(trade.get('closed_at') or trade.get('updated_at'))
    if not created_ms or not closed_ms:
        return None

    # Wider time window for position history/ledgers to account for execution delays
    # ±30 minutes for entry, ±30 minutes for exit
    start_ms = max(0, created_ms - 30 * 60 * 1000)
    end_ms = closed_ms + 30 * 60 * 1000

    symbol = str(trade.get('coin_symbol') or '').upper()
    if not symbol:
        return None
    # Normalize bot coin symbol to KuCoin futures symbol.
    # Use the same BTC→XBT mapping as other KuCoin backfill code to avoid
    # missing BTC position history (XBTUSDTM vs BTCUSDTM).
    if symbol == 'BTC':
        kucoin_symbol = 'XBTUSDTM'
    else:
        kucoin_symbol = f"{symbol}USDTM"

    logger.info(
        f"Trade {trade.get('id')} ({symbol}): Normalized to {kucoin_symbol}, "
        f"time window: {datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).isoformat()} "
        f"to {datetime.fromtimestamp(end_ms/1000, tz=timezone.utc).isoformat()}"
    )

    # Pull position history for symbol and time window with pagination support
    records = await fetch_all_position_history(ex, kucoin_symbol, start_ms, end_ms)

    if not records:
        logger.warning(
            f"Trade {trade.get('id')} ({symbol}): No position history records found for {kucoin_symbol} "
            f"in time window [{datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).isoformat()} "
            f"to {datetime.fromtimestamp(end_ms/1000, tz=timezone.utc).isoformat()}]. "
            f"Will try fills-based PnL calculation as fallback."
        )
        # Fallback to fills-based calculation
        if used_fill_ids is None:
            used_fill_ids = set()
        return await calculate_pnl_from_fills(ex, trade, kucoin_symbol, start_ms, end_ms, used_fill_ids)

    logger.info(f"Trade {trade.get('id')} ({symbol}): Found {len(records)} position history records")

    # Time window padding for matching position history
    # Widen windows to account for execution delays and order processing time
    created_pad_ms = 10 * 60 * 1000  # 10 minutes pad for entry (was 2 minutes - too strict)
    close_pad_ms = 30 * 60 * 1000  # 30 minutes pad for exit (was 15 minutes)
    def get_ms(val: Any) -> int:
        try:
            return int(val or 0)
        except Exception:
            return 0

    position_type = str(trade.get('signal_type') or '').upper()
    expected_close_type = 'CLOSE_LONG' if position_type == 'LONG' else ('CLOSE_SHORT' if position_type == 'SHORT' else None)
    expected_side = 'LONG' if position_type == 'LONG' else ('SHORT' if position_type == 'SHORT' else None)

    # Get position size and order ID from trade for better matching
    position_size = None
    try:
        pos_size_str = trade.get('position_size')
        if pos_size_str:
            position_size = float(pos_size_str)
    except (ValueError, TypeError):
        pass

    # Get exchange order ID to distinguish trades
    exchange_order_id = str(trade.get('exchange_order_id') or trade.get('kucoin_order_id') or '')

    strict_candidates: List[Dict[str, Any]] = []
    filtered_reasons = {
        'used_closeId': 0,
        'openTime_too_far': 0,
        'closeTime_too_far': 0,
        'type_mismatch': 0,
        'side_mismatch': 0,
        'size_mismatch': 0
    }

    for r in records:
        # Exclude already used closeIds to prevent double-counting
        cid = str(r.get('closeId') or '')
        if cid and cid in used_close_ids:
            filtered_reasons['used_closeId'] += 1
            continue

        o_ms = get_ms(r.get('openTime'))
        c_ms = get_ms(r.get('closeTime'))

        # Time window matching with wider tolerance
        # openTime should be reasonably close to created_at (accounting for order processing)
        if o_ms:
            open_time_diff = abs(o_ms - created_ms)
            if open_time_diff > created_pad_ms:
                filtered_reasons['openTime_too_far'] += 1
                continue

        # closeTime should be reasonably close to closed_at
        if c_ms:
            close_time_diff = abs(c_ms - closed_ms)
            if close_time_diff > close_pad_ms:
                filtered_reasons['closeTime_too_far'] += 1
                continue

        # Position size matching (if available) - helps distinguish consecutive similar trades
        if position_size is not None:
            try:
                rec_size = float(r.get('size', 0))
                if rec_size > 0:
                    size_diff_pct = abs(position_size - rec_size) / position_size if position_size > 0 else 1.0
                    # Allow up to 20% size difference (for partial fills, adjustments, etc.)
                    if size_diff_pct > 0.20:
                        filtered_reasons['size_mismatch'] += 1
                        continue
            except (ValueError, TypeError):
                pass

        # Side/type matching when provided
        r_type = str(r.get('type') or '').upper()
        r_side = str(r.get('side') or '').upper()
        if expected_close_type and r_type not in (expected_close_type, ''):
            # Allow empty type but prefer matching types
            if expected_close_type not in r_type:
                filtered_reasons['type_mismatch'] += 1
                continue
        if expected_side and r_side not in (expected_side, ''):
            filtered_reasons['side_mismatch'] += 1
            continue

        strict_candidates.append(r)

    if not strict_candidates:
        logger.info(
            f"Trade {trade.get('id')} ({symbol}): No strict candidates. "
            f"Filtered: {filtered_reasons}, total records: {len(records)}"
        )
        # fall back to closest by time, still respecting used_close_ids and time windows
        fallback_candidates = []
        for r in records:
            cid = str(r.get('closeId') or '')
            if cid and cid in used_close_ids:
                continue
            o_ms = get_ms(r.get('openTime'))
            c_ms = get_ms(r.get('closeTime'))
            # Still require reasonable time windows even in fallback (wider tolerance)
            if o_ms and abs(o_ms - created_ms) > created_pad_ms * 2:  # Allow 20 minutes in fallback
                continue
            if c_ms and abs(c_ms - closed_ms) > close_pad_ms * 2:  # Allow 60 minutes in fallback
                continue
            fallback_candidates.append(r)
        strict_candidates = fallback_candidates
        if not strict_candidates:
            logger.warning(
                f"Trade {trade.get('id')} ({symbol}): No position history candidates found after filtering. "
                f"Created: {datetime.fromtimestamp(created_ms/1000, tz=timezone.utc).isoformat()}, "
                f"Closed: {datetime.fromtimestamp(closed_ms/1000, tz=timezone.utc).isoformat()}, "
                f"Filter reasons: {filtered_reasons}, Total records: {len(records)}. "
                f"Will try fills-based PnL calculation as fallback."
            )
            # Fallback to fills-based calculation
            if used_fill_ids is None:
                used_fill_ids = set()
            return await calculate_pnl_from_fills(ex, trade, kucoin_symbol, start_ms, end_ms, used_fill_ids)
        logger.info(f"Trade {trade.get('id')} ({symbol}): Using {len(fallback_candidates)} fallback candidates")

    # Enhanced scoring function: considers close time, open time, and position size match
    def score(r: Dict[str, Any]) -> Tuple[int, int, int]:
        c_ms = get_ms(r.get('closeTime'))
        o_ms = get_ms(r.get('openTime'))
        # Primary: close time proximity
        close_score = abs(c_ms - closed_ms) if c_ms else 1_000_000_000
        # Secondary: open time proximity
        open_score = abs(o_ms - created_ms) if o_ms else 1_000_000_000
        # Tertiary: position size match penalty (if both available)
        size_penalty = 0
        if position_size is not None:
            try:
                rec_size = float(r.get('size', 0))
                if rec_size > 0:
                    size_diff = abs(position_size - rec_size)
                    # Penalize if size difference is more than 1% of trade size
                    if size_diff > max(0.01, position_size * 0.01):
                        size_penalty = 1_000_000
            except (ValueError, TypeError):
                pass
        return (close_score, open_score, size_penalty)

    if not strict_candidates:
        logger.warning(f"Trade {trade.get('id')}: No candidates available for scoring")
        # Fallback to fills-based calculation
        if used_fill_ids is None:
            used_fill_ids = set()
        return await calculate_pnl_from_fills(ex, trade, kucoin_symbol, start_ms, end_ms, used_fill_ids)

    rec = min(strict_candidates, key=score)
    if not rec:
        logger.warning(f"Trade {trade.get('id')}: No record selected after scoring")
        # Fallback to fills-based calculation
        if used_fill_ids is None:
            used_fill_ids = set()
        return await calculate_pnl_from_fills(ex, trade, kucoin_symbol, start_ms, end_ms, used_fill_ids)

    # Log matching details for debugging
    c_ms = get_ms(rec.get('closeTime'))
    o_ms = get_ms(rec.get('openTime'))
    close_diff_min = abs(c_ms - closed_ms) / (60 * 1000) if c_ms else None
    open_diff_min = abs(o_ms - created_ms) / (60 * 1000) if o_ms else None
    rec_size = rec.get('size')
    size_match = "N/A"
    if position_size is not None and rec_size:
        try:
            size_diff = abs(position_size - float(rec_size))
            size_match = f"diff={size_diff:.4f}" if size_diff > 0.01 else "match"
        except (ValueError, TypeError):
            size_match = "N/A"

    logger.info(
        f"Trade {trade.get('id')} ({symbol}): Matched position record "
        f"(closeId={rec.get('closeId')}, closeTime_diff={close_diff_min:.2f}min, "
        f"openTime_diff={open_diff_min:.2f}min, size_match={size_match}, "
        f"candidates={len(strict_candidates)})"
    )

    # Extract realized PnL and fees robustly
    realized_candidates = [
        rec.get('pnl'),
        rec.get('realisedPnl'),
        rec.get('realizedPnl'),
        rec.get('realisedPNL'),
    ]
    realized_val = 0.0
    for c in realized_candidates:
        try:
            if c is None:
                continue
            realized_val = float(c)
            break
        except Exception:
            continue

    fee_candidates = [
        rec.get('tradeFee'),
        rec.get('fee'),
        rec.get('closeFee'),
    ]
    total_fees = 0.0
    for c in fee_candidates:
        try:
            if c is None:
                continue
            total_fees += float(c)
        except Exception:
            pass

    # Some records include fundingFee; include if present in definition of net
    try:
        funding_fee = float(rec.get('fundingFee') or 0)
        total_fees += funding_fee
    except Exception:
        pass

    # If realized already net of fees, avoid double-subtraction. Heuristic: when realised ~ (close-open)*size and separate fees exist.
    # We keep realized_val as reported and only subtract fees if realized appears to exclude them (could be zero while fees non-zero).
    final_realized = realized_val if abs(realized_val) > 0 else -total_fees

    # Compare and patch if mismatched
    # Only update if PnL is missing/zero or significantly different (don't overwrite correct values)
    db_pnl = float(trade.get('pnl_usd') or trade.get('net_pnl') or 0)
    pnl_diff = abs(db_pnl - final_realized)
    pnl_diff_pct = abs(pnl_diff / final_realized) if final_realized != 0 else 1.0

    # Don't update if:
    # 1. PnL already matches (within 0.01 USDT)
    # 2. Existing PnL is non-zero and close to calculated (within 5% or 0.10 USDT)
    if pnl_diff <= 0.01:
        logger.info(
            f"Trade {trade.get('id')} ({symbol}): PNL already matches "
            f"(db={db_pnl:.8f}, record={final_realized:.8f}, diff={pnl_diff:.8f})"
        )
        return None

    # If existing PnL is non-zero and reasonably close, don't overwrite
    if db_pnl != 0 and (pnl_diff <= 0.10 or pnl_diff_pct <= 0.05):
        logger.info(
            f"Trade {trade.get('id')} ({symbol}): PNL is close to existing value, not overwriting "
            f"(db={db_pnl:.8f}, calculated={final_realized:.8f}, diff={pnl_diff:.8f}, diff_pct={pnl_diff_pct*100:.2f}%)"
        )
        return None

    # Prepare a concise text payload to avoid array/JSON type issues in DB
    summary = {
        "source": "POSITION_HISTORY",
        "symbol": rec.get('symbol'),
        "closeId": rec.get('closeId'),
        "pnl": realized_val,
        "fees": total_fees,
        "openPrice": rec.get('openPrice'),
        "closePrice": rec.get('closePrice')
    }
    sync_text = f"{summary}"

    update_data: Dict[str, Any] = {
        "pnl_usd": round(final_realized, 8),
        "net_pnl": round(final_realized, 8),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sync_order_response": sync_text
    }
    # Set entry/exit if present to avoid None assignment
    try:
        entry_price_val = rec.get('avgEntryPrice') or rec.get('openPrice')
        if entry_price_val is not None:
            update_data["entry_price"] = float(entry_price_val)
    except Exception:
        pass
    try:
        exit_price_val = rec.get('closePrice') or rec.get('avgExitPrice')
        if exit_price_val is not None:
            update_data["exit_price"] = float(exit_price_val)
    except Exception:
        pass

    # Mark this closeId as used to prevent overlap in this run
    cid = rec.get('closeId')
    if cid:
        used_close_ids.add(str(cid))

    return update_data


async def main(days: Optional[int] = None, missing_pnl_only: bool = False):
    """
    Main function for KuCoin PnL reconciliation.

    Args:
        days: Number of days to look back (default: 7, use 0 for all trades, None to use argparse)
        missing_pnl_only: Only process trades with missing or zero PnL
    """
    # If called from command line, use argparse
    if days is None:
        import argparse
        parser = argparse.ArgumentParser(description='KuCoin PnL Reconciliation')
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to look back (default: 7, use 0 for all trades)'
        )
        parser.add_argument(
            '--missing-pnl-only',
            action='store_true',
            help='Only process trades with missing or zero PnL'
        )
        args = parser.parse_args()
        days = args.days
        missing_pnl_only = args.missing_pnl_only

    # Ensure days is not None at this point
    if days is None:
        days = 7

    logger.info(f"Starting KuCoin PnL reconciliation (days={days if days > 0 else 'all'})…")

    supabase: Client = create_client(sup_url, sup_key)
    ex = KucoinExchange(
        api_key=settings.KUCOIN_API_KEY or "",
        api_secret=settings.KUCOIN_API_SECRET or "",
        api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
        is_testnet=False,
    )

    init_ok = await ex.initialize()
    if not init_ok:
        logger.error("Failed to initialize KuCoin exchange")
        return

    # Build query
    query = supabase.table("trades").select("*") \
        .eq("exchange", "kucoin").eq("status", "CLOSED")

    # Add time filter if days > 0
    if days > 0:
        now = datetime.now(timezone.utc)
        days_ago = (now - timedelta(days=days)).isoformat()
        query = query.gte("created_at", days_ago)
        logger.info(f"Filtering trades from last {days} days")
    else:
        logger.info("Processing all CLOSED KuCoin trades (no time limit)")

    resp = query.execute()
    trades: List[Dict[str, Any]] = resp.data or []

    # Filter for missing PnL if requested (done in Python for simplicity)
    if missing_pnl_only:
        original_count = len(trades)
        trades = [
            t for t in trades
            if (t.get('pnl_usd') is None or t.get('pnl_usd') == 0) and
               (t.get('net_pnl') is None or t.get('net_pnl') == 0)
        ]
        logger.info(f"Filtered to {len(trades)} trades with missing or zero PnL (from {original_count} total)")

    logger.info(f"Loaded {len(trades)} KuCoin CLOSED trades for processing")

    fixes = 0
    used_close_ids: Set[str] = set()
    used_fill_ids: Set[str] = set()

    for tr in trades:
        try:
            update = await reconcile_trade(ex, supabase, tr, used_close_ids, used_fill_ids)
            if not update:
                continue
            # Update only fields we computed
            supabase.table("trades").update(update).eq("id", tr['id']).execute()
            fixes += 1
            logger.info(f"Updated trade {tr['id']} with corrected PnL: {update['pnl_usd']}")
        except Exception as e:
            logger.warning(f"Failed to reconcile trade {tr.get('id')}: {e}")

    logger.info(f"Completed. Corrected {fixes} trades.")

    # Cleanly close client
    try:
        await ex.close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())


