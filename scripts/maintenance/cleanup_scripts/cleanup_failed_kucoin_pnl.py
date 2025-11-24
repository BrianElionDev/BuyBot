#!/usr/bin/env python3
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from config import settings
from supabase import create_client, Client


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


FAILED_STATUSES = {"FAILED", "CANCELLED", "CANCELED", "REJECTED", "EXPIRED"}
FALLBACK_PRICE_SOURCES = {
    "binance_mark_price_fallback",
    "binance_user_trades_fallback",
}


async def cleanup_failed_kucoin_trades(days_back: int = 365, dry_run: bool = False) -> Dict[str, Any]:
    sup_url = settings.SUPABASE_URL or ""
    sup_key = settings.SUPABASE_KEY or ""
    supabase: Client = create_client(sup_url, sup_key)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_iso = cutoff.isoformat()

    logger.info("Starting FAILED KuCoin PnL cleanup")
    logger.info("Cutoff: %s (last %d days)", cutoff_iso, days_back)

    query = (
        supabase.table("trades")
        .select("*")
        .eq("exchange", "kucoin")
        .gte("created_at", cutoff_iso)
    )
    resp = query.execute()
    trades: List[Dict[str, Any]] = resp.data or []

    logger.info("Loaded %d KuCoin trades in window", len(trades))

    affected: int = 0
    inspected: int = 0

    for tr in trades:
        trade_id = tr.get("id")
        status = str(tr.get("status") or "").upper()
        order_status = str(tr.get("order_status") or "").upper()

        if status not in FAILED_STATUSES and order_status not in FAILED_STATUSES:
            continue

        pnl_usd = tr.get("pnl_usd")
        net_pnl = tr.get("net_pnl")

        has_pnl = False
        try:
            if pnl_usd not in (None, "", "0", "0.0") and float(pnl_usd) != 0.0:
                has_pnl = True
        except Exception:
            has_pnl = True
        try:
            if net_pnl not in (None, "", "0", "0.0") and float(net_pnl) != 0.0:
                has_pnl = True
        except Exception:
            has_pnl = True

        if not has_pnl:
            continue

        inspected += 1

        updates: Dict[str, Any] = {
            "pnl_usd": 0,
            "net_pnl": 0,
            "pnl_verified": False,
            "pnl_source": None,
            "commission": None,
            "funding_fee": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        price_source = tr.get("price_source")
        exit_price = tr.get("exit_price")

        force_clear_exit = (
            price_source in FALLBACK_PRICE_SOURCES
            or exit_price in (None, "", "0", "0.0")
        )
        if force_clear_exit:
            updates["exit_price"] = 0
            updates["price_source"] = None
            updates["price_verified"] = False

        sync_issues = tr.get("sync_issues") or []
        if not isinstance(sync_issues, list):
            sync_issues = [str(sync_issues)]
        sync_issues.append("FAILED_PNL_CLEARED")
        updates["sync_issues"] = sorted({str(x) for x in sync_issues})
        updates["manual_verification_needed"] = True

        logger.info(
            "Trade %s (%s %s) FAILED with non-zero PnL: pnl_usd=%s net_pnl=%s -> clearing",
            trade_id,
            tr.get("coin_symbol"),
            status or order_status,
            pnl_usd,
            net_pnl,
        )

        if not dry_run:
            supabase.table("trades").update(updates).eq("id", trade_id).execute()
            affected += 1

    logger.info(
        "FAILED KuCoin PnL cleanup complete. Inspected=%d, Updated=%d, DryRun=%s",
        inspected,
        affected,
        dry_run,
    )
    return {"inspected": inspected, "updated": affected, "dry_run": dry_run}


async def main():
    await cleanup_failed_kucoin_trades(days_back=365, dry_run=False)


if __name__ == "__main__":
    asyncio.run(main())


