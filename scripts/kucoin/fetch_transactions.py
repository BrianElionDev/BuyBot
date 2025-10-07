#!/usr/bin/env python3
"""
Quick KuCoin transactions fetcher.

Usage examples:
  python scripts/kucoin/fetch_transactions.py                # last 24h, all symbols
  python scripts/kucoin/fetch_transactions.py BTCUSDT        # last 24h for BTCUSDT
  python scripts/kucoin/fetch_transactions.py BTCUSDT 48     # last 48h for BTCUSDT
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timezone, timedelta

# Ensure project root is on sys.path so 'src' and 'config' are importable
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import settings
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher


async def run(symbol: str = "", hours: int = 24) -> int:
    api_key = settings.KUCOIN_API_KEY
    api_secret = settings.KUCOIN_API_SECRET
    api_passphrase = settings.KUCOIN_API_PASSPHRASE
    is_testnet = settings.KUCOIN_TESTNET

    if not api_key or not api_secret or not api_passphrase:
        print("ERROR: Missing KuCoin API credentials in environment/config.")
        return 2

    exchange = KucoinExchange(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        is_testnet=is_testnet,
    )

    await exchange.initialize()

    fetcher = KucoinTransactionFetcher(exchange)

    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)

    txns = await fetcher.fetch_transaction_history(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
        limit=1000,
    )

    print(f"Fetched {len(txns)} transactions from KuCoin for symbol='{symbol or 'ALL'}' range={hours}h")
    if not txns:
        return 1

    # Pretty print first 10
    for rec in txns[:10]:
        try:
            print(json.dumps(rec, ensure_ascii=False))
        except Exception:
            print(rec)

    return 0


def main() -> None:
    symbol = ""
    hours = 24
    if len(sys.argv) >= 2:
        symbol = sys.argv[1].strip()
    if len(sys.argv) >= 3:
        try:
            hours = int(sys.argv[2])
        except Exception:
            pass

    exit_code = asyncio.run(run(symbol, hours))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()


