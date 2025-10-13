#!/usr/bin/env python3
import asyncio
import json
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure project root is importable when running as a script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


async def call_endpoint():
    # Calls the FastAPI endpoint and prints the JSON
    from discord_bot.main import app
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=None) as client:
        resp = await client.post("/scheduler/test-transaction-history")
        print(json.dumps(resp.json(), indent=2, sort_keys=True, default=str))


async def fetch_kucoin_direct(symbol: str | None, hours: int, limit: int):
    # Directly calls KuCoin fetcher and prints items
    from discord_bot.discord_bot import DiscordBot
    from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher

    bot = DiscordBot()
    if not getattr(bot, "kucoin_exchange", None):
        print("KuCoin exchange not configured.")
        return

    fetcher = KucoinTransactionFetcher(bot.kucoin_exchange)
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)

    tx = await fetcher.fetch_transaction_history(
        symbol=symbol or "",
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    print(json.dumps(tx, indent=2, sort_keys=True, default=str))


async def main():
    parser = argparse.ArgumentParser(description="Show transaction history output")
    parser.add_argument("mode", choices=["endpoint", "kucoin"], help="Call endpoint or fetch KuCoin directly")
    parser.add_argument("--symbol", dest="symbol", default=None, help="Symbol like BTCUSDT (KuCoin mode)")
    parser.add_argument("--hours", dest="hours", type=int, default=24, help="Lookback hours (KuCoin mode)")
    parser.add_argument("--limit", dest="limit", type=int, default=1000, help="Limit per window (KuCoin mode)")
    args = parser.parse_args()

    if args.mode == "endpoint":
        await call_endpoint()
    else:
        await fetch_kucoin_direct(args.symbol, args.hours, args.limit)


if __name__ == "__main__":
    asyncio.run(main())


