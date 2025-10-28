"""
Run a full Binance→DB reconciliation to backfill exit price and PnL.

Usage (non-interactive):
    python -m scripts.maintenance.binance_reconcile
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure project root is on sys.path when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main() -> None:
    load_dotenv()

    # Lazy import to avoid heavy deps on module load
    # Avoid importing full DiscordBot to prevent heavy deps (e.g., runtime_config) for this maintenance job
    from supabase import create_client
    from discord_bot.utils.trade_retry_utils import sync_trade_statuses_with_binance  # type: ignore
    from src.exchange.binance.binance_exchange import BinanceExchange  # type: ignore
    from config import settings  # type: ignore

    # Initialize logging
    logging.basicConfig(level=logging.INFO)

    # Supabase client
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY env variables")
    supabase = create_client(url, key)

    # Initialize minimal bot-like carrier with Binance exchange
    binance = BinanceExchange(
        api_key=settings.BINANCE_API_KEY or "",
        api_secret=settings.BINANCE_API_SECRET or "",
        is_testnet=settings.BINANCE_TESTNET,
    )
    # The sync expects a bot-like object with .binance_exchange
    class _Carrier:
        def __init__(self, be: Any):
            self.binance_exchange = be
    bot: Any = _Carrier(binance)

    # Run enhanced sync (orders, positions, cleanup, history)
    await sync_trade_statuses_with_binance(bot, supabase)


if __name__ == "__main__":
    asyncio.run(main())


