#!/usr/bin/env python3
"""
KuCoin Futures Inspector

Fetch and display:
- Account overview (equity, available, margins)
- Active positions (size, side, entry price, PnL, margin)
- Active orders (limit/market) with sizes and prices
- Recent fills (last 48h) with side/size/price/fee

Uses production endpoints; sandbox is offline.
"""

import asyncio
import aiohttp
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config.settings import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE  # noqa: E402


class KucoinFuturesClient:
    def __init__(self, api_key: str, api_secret: str, api_passphrase: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.base_url = "https://api-futures.kucoin.com"
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    def _headers(self, method: str, endpoint: str, body: str = "", timestamp_ms: Optional[int] = None) -> Dict[str, str]:
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        payload = f"{timestamp_ms}{method}{endpoint}{body}"
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), payload.encode(), hashlib.sha256).digest()
        ).decode()
        passphrase = base64.b64encode(
            hmac.new(self.api_secret.encode(), self.api_passphrase.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": str(timestamp_ms),
            "KC-API-PASSPHRASE": passphrase,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }

    async def _get(self, endpoint: str) -> Any:
        assert self.session is not None, "Session not initialized"
        headers = self._headers("GET", endpoint)
        async with self.session.get(f"{self.base_url}{endpoint}", headers=headers) as resp:
            data = await resp.json()
            if data.get("code") != "200000":
                raise RuntimeError(f"GET {endpoint} failed: {data}")
            return data.get("data")

    async def get_account_overview(self, currency: str = "USDT") -> Dict[str, Any]:
        return await self._get(f"/api/v1/account-overview?currency={currency}")

    async def get_positions(self) -> List[Dict[str, Any]]:
        return await self._get("/api/v1/positions")

    async def get_orders(self, status: str = "active") -> Dict[str, Any]:
        # Returns { currentPage, pageSize, totalNum, totalPage, items: [...] }
        return await self._get(f"/api/v1/orders?status={status}")

    async def get_fills(self, start: Optional[int] = None, end: Optional[int] = None, page_size: int = 50) -> Dict[str, Any]:
        # Fills endpoint supports optional startAt/endAt (ms). We'll fetch a single page for simplicity.
        params: List[str] = [f"pageSize={page_size}"]
        if start is not None:
            params.append(f"startAt={start}")
        if end is not None:
            params.append(f"endAt={end}")
        query = ("?" + "&".join(params)) if params else ""
        return await self._get(f"/api/v1/fills{query}")


def fmt_ts_ms(ts_ms: Optional[int]) -> str:
    if not ts_ms:
        return "-"
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ts_ms)


def human(n: Any, decimals: int = 8) -> str:
    try:
        return f"{float(n):.{decimals}f}"
    except Exception:
        return str(n)


async def main():
    if not (KUCOIN_API_KEY and KUCOIN_API_SECRET and KUCOIN_API_PASSPHRASE):
        print("❌ Missing KuCoin API credentials in environment/config")
        return

    async with KucoinFuturesClient(KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE) as client:
        # Account
        overview = await client.get_account_overview("USDT")
        print("== ACCOUNT OVERVIEW ==")
        print(json.dumps(overview, indent=2))
        print()

        # Positions
        positions = await client.get_positions()
        print("== ACTIVE POSITIONS ==")
        active_positions = [p for p in positions if float(p.get("currentQty", 0) or 0) != 0]
        if not active_positions:
            print("(none)")
        else:
            for p in active_positions:
                symbol = p.get("symbol")
                side = p.get("side")
                size = p.get("currentQty")
                entry_price = p.get("avgEntryPrice")
                mark_price = p.get("markPrice")
                unreal = p.get("unrealisedPnl")
                margin = p.get("positionMargin")
                leverage = p.get("leverage")
                liq_price = p.get("liquidationPrice")
                u_time = fmt_ts_ms(p.get("updatedAt"))
                print(f"- {symbol} | {side} | size={size} | entry={entry_price} | mark={mark_price} | uPnL={human(unreal)} | margin={human(margin)} | lev={leverage} | liq={liq_price} | updated={u_time}")
        print()

        # Orders (active)
        orders_page = await client.get_orders(status="active")
        print("== ACTIVE ORDERS ==")
        items = (orders_page or {}).get("items", [])
        if not items:
            print("(none)")
        else:
            for o in items:
                symbol = o.get("symbol")
                side = o.get("side")
                ord_type = o.get("type")
                size = o.get("size")
                price = o.get("price")
                status = o.get("status")
                remain = o.get("remainSize")
                funds = o.get("funds")  # margin or cost
                c_time = fmt_ts_ms(o.get("createdAt"))
                print(f"- {symbol} | {side} {ord_type} | size={size} remain={remain} | price={price} | status={status} | funds={funds} | created={c_time}")
        print()

        # Recent fills (last 48h)
        now = datetime.now(tz=timezone.utc)
        start_ms = int((now - timedelta(hours=48)).timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        fills_page = {}
        try:
            fills_page = await client.get_fills(start=start_ms, end=end_ms, page_size=100)
        except RuntimeError as e:
            # Some accounts may not have permission; continue without failing
            print(f"⚠️  Unable to fetch fills: {e}")
        print("== RECENT FILLS (48h) ==")
        fills = (fills_page or {}).get("items", [])
        if not fills:
            print("(none)")
        else:
            for f in fills:
                symbol = f.get("symbol")
                side = f.get("side")
                size = f.get("size")
                price = f.get("price")
                fee = f.get("fee")
                fee_currency = f.get("feeCurrency")
                trade_id = f.get("tradeId")
                ord_id = f.get("orderId")
                ts = fmt_ts_ms(f.get("time"))
                print(f"- {symbol} | {side} | size={size} @ {price} | fee={fee} {fee_currency} | tradeId={trade_id} orderId={ord_id} | time={ts}")


if __name__ == "__main__":
    asyncio.run(main())



