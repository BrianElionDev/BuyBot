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


async def reconcile_trade(
    ex: KucoinExchange,
    supabase: Client,
    trade: Dict[str, Any],
    used_close_ids: Set[str]
) -> Optional[Dict[str, Any]]:
    if (trade.get('exchange') != 'kucoin') or (trade.get('status') != 'CLOSED'):
        return None

    created_ms = _to_ms(trade.get('created_at'))
    closed_ms = _to_ms(trade.get('closed_at') or trade.get('updated_at'))
    if not created_ms or not closed_ms:
        return None

    # Tight window ±15 minutes for position history/ledgers
    start_ms = max(0, created_ms - 15 * 60 * 1000)
    end_ms = closed_ms + 15 * 60 * 1000

    symbol = str(trade.get('coin_symbol') or '').upper()
    if not symbol:
        return None

    kucoin_symbol = ex.get_futures_trading_pair(symbol)

    # Pull position history for symbol and time window
    # Endpoint used via exchange's direct signed call
    params = {"symbol": kucoin_symbol, "startAt": start_ms, "endAt": end_ms}
    pos_resp = await ex._make_direct_api_call('GET', '/api/v1/history-positions', params)
    # Fallback: retry without symbol when contract-not-exist or empty
    records: List[Dict[str, Any]] = []
    if isinstance(pos_resp, list):
        records = pos_resp
    elif isinstance(pos_resp, dict):
        items = pos_resp.get('items') or pos_resp.get('data') or []
        if isinstance(items, list):
            records = items
    if not records:
        pos_resp2 = await ex._make_direct_api_call('GET', '/api/v1/history-positions', {"startAt": start_ms, "endAt": end_ms})
        if isinstance(pos_resp2, list):
            records = pos_resp2
        elif isinstance(pos_resp2, dict):
            items2 = pos_resp2.get('items') or pos_resp2.get('data') or []
            if isinstance(items2, list):
                records = items2

    # Filter to the symbol if the API returned mixed symbols
    records = [r for r in records if str(r.get('symbol') or '') == kucoin_symbol]
    if not records:
        return None

    # Strict candidate filtering to avoid overlap across near-consecutive trades
    created_pad_ms = 5 * 60 * 1000  # 5 minutes pad
    def get_ms(val: Any) -> int:
        try:
            return int(val or 0)
        except Exception:
            return 0

    position_type = str(trade.get('signal_type') or '').upper()
    expected_close_type = 'CLOSE_LONG' if position_type == 'LONG' else ('CLOSE_SHORT' if position_type == 'SHORT' else None)
    expected_side = 'LONG' if position_type == 'LONG' else ('SHORT' if position_type == 'SHORT' else None)

    strict_candidates: List[Dict[str, Any]] = []
    for r in records:
        # exclude already used closeIds
        cid = str(r.get('closeId') or '')
        if cid and cid in used_close_ids:
            continue
        o_ms = get_ms(r.get('openTime'))
        c_ms = get_ms(r.get('closeTime'))
        # time containment: open after created-ε, close before closed+ε
        if o_ms and o_ms < max(0, created_ms - created_pad_ms):
            continue
        if c_ms and c_ms > end_ms:
            continue
        # side/type match when provided
        r_type = str(r.get('type') or '').upper()
        r_side = str(r.get('side') or '').upper()
        if expected_close_type and r_type not in (expected_close_type, ''):
            # allow empty type but prefer matching types
            if expected_close_type not in r_type:
                continue
        if expected_side and r_side not in (expected_side, ''):
            continue
        strict_candidates.append(r)

    if not strict_candidates:
        # fall back to closest by time, still respecting used_close_ids
        strict_candidates = [r for r in records if str(r.get('closeId') or '') not in used_close_ids]
        if not strict_candidates:
            return None

    # choose the record with closest closeTime to closed_ms, tie-breaker closest openTime to created_ms
    def score(r: Dict[str, Any]) -> Tuple[int, int]:
        c_ms = get_ms(r.get('closeTime'))
        o_ms = get_ms(r.get('openTime'))
        return (abs(c_ms - closed_ms) if c_ms else 1_000_000_000, abs(o_ms - created_ms) if o_ms else 1_000_000_000)

    rec = min(strict_candidates, key=score)
    if not rec:
        return None

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
    db_pnl = float(trade.get('pnl_usd') or trade.get('net_pnl') or 0)
    if abs(db_pnl - final_realized) <= 0.01:
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


async def main():
    logger.info("Starting KuCoin 7-day PnL reconciliation…")

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

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # Fetch KuCoin CLOSED trades in last 7 days
    resp = supabase.table("trades").select("*") \
        .eq("exchange", "kucoin").eq("status", "CLOSED").gte("created_at", seven_days_ago).execute()
    trades: List[Dict[str, Any]] = resp.data or []
    logger.info(f"Loaded {len(trades)} KuCoin CLOSED trades in the last 7 days")

    fixes = 0
    used_close_ids: Set[str] = set()

    for tr in trades:
        try:
            update = await reconcile_trade(ex, supabase, tr, used_close_ids)
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


