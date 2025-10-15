import asyncio
import json
import logging
import os
from typing import Any, Dict

from supabase import create_client


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_exchange_response")


def get_supabase():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY not set")
    return create_client(url, key)


def normalize_response(resp: Any) -> Dict[str, Any]:
    if not resp:
        return {}
    if isinstance(resp, dict):
        return resp
    if isinstance(resp, str):
        try:
            data = json.loads(resp)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


START_ISO = "2025-09-01T00:00:00Z"
END_EXCLUSIVE_ISO = "2025-11-01T00:00:00Z"  # up to end of October 2025


async def backfill():
    supabase = get_supabase()
    logger.info("Fetching trades (2025-09-01..2025-10-31) with empty exchange_response...")
    resp = (
        supabase
        .from_("trades")
        .select("id, exchange, created_at, exchange_response, binance_response, kucoin_response")
        .gte("created_at", START_ISO)
        .lt("created_at", END_EXCLUSIVE_ISO)
        .or_("exchange_response.is.null,exchange_response.eq.")
        .execute()
    )
    trades = getattr(resp, 'data', []) or []
    if not trades:
        logger.info("No trades to backfill")
        return

    updated = 0
    for t in trades:
        try:
            if t.get("exchange_response"):
                continue
            br = normalize_response(t.get("binance_response"))
            kr = normalize_response(t.get("kucoin_response"))

            # Prefer exchange-specific response if exchange is set
            exch = (t.get("exchange") or "").strip().lower()
            if exch == "binance":
                merged = br if br else kr
            elif exch == "kucoin":
                merged = kr if kr else br
            else:
                merged = br if br else kr
            if not merged:
                continue
            logger.info(f"Backfilling exchange_response for trade {t['id']}")
            supabase.from_("trades").update({"exchange_response": json.dumps(merged)}).eq("id", t["id"]).execute()
            updated += 1
        except Exception as e:
            logger.warning(f"Failed to backfill trade {t.get('id')}: {e}")

    logger.info(f"Backfill complete. Updated {updated} trades.")


if __name__ == "__main__":
    asyncio.run(backfill())


