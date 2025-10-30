import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from config import settings
from src.exchange.binance.binance_exchange import BinanceExchange


def _ts_to_ms(ts: str) -> int:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


async def audit_trade(binance: BinanceExchange, trade: Dict[str, Any]) -> Dict[str, Any]:
    symbol = f"{trade['coin_symbol'].upper()}USDT"
    order_id = str(trade['exchange_order_id'])

    created_ms = _ts_to_ms(trade['created_at'].replace(" ", "T")) if "T" not in trade['created_at'] else _ts_to_ms(trade['created_at'])
    closed_ms: Optional[int] = None
    if trade.get('closed_at'):
        closed_ms = _ts_to_ms(trade['closed_at'].replace(" ", "T")) if "T" not in trade['closed_at'] else _ts_to_ms(trade['closed_at'])

    # Expand window around created/closed
    start_time = created_ms - 30 * 60 * 1000
    end_time = (closed_ms or created_ms + 6 * 60 * 60 * 1000) + 30 * 60 * 1000

    order_status = await binance.get_order_status(symbol, order_id)

    user_trades = await binance.get_user_trades(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
        limit=1000,
    )

    # Income history for realized pnl and commissions
    income = await binance.get_income_history(
        symbol=symbol, start_time=start_time, end_time=end_time, limit=1000
    )

    # Summaries
    executed_qty = 0.0
    avg_entry_price = 0.0
    avg_exit_price = 0.0
    fills: List[Dict[str, Any]] = []

    # Separate entry vs reduce-only (exit) by maker/taker side and position side hints if available
    for t in user_trades:
        # Futures trade fields: orderId, side, price, qty, realizedPnl, commission, buyer, maker, ...
        if str(t.get('orderId')) != order_id:
            # Also include fills not tied to parent id (manual exit). We'll capture all fills in window for symbol.
            pass
        fills.append(
            {
                'time': t.get('time'),
                'orderId': t.get('orderId'),
                'side': t.get('side'),
                'price': float(t.get('price', 0)),
                'qty': float(t.get('qty', 0)),
                'realizedPnl': float(t.get('realizedPnl', 0)),
                'commission': float(t.get('commission', 0)),
            }
        )

    # Compute simple aggregates
    total_realized_pnl = 0.0
    total_commission = 0.0
    for f in fills:
        total_realized_pnl += f['realizedPnl']
        total_commission += f['commission']

    # Extract order status info
    status_str = order_status.get('status') if order_status else None
    executed = float(order_status.get('executedQty', 0)) if order_status else 0.0
    avg_price = float(order_status.get('avgPrice', 0)) if order_status else 0.0

    # Determine if position existed: any non-zero qty in trades for this symbol in window
    position_existed = any(float(t.get('qty', 0)) > 0 for t in user_trades)

    return {
        'id': trade['id'],
        'symbol': symbol,
        'exchange_order_id': order_id,
        'db_status': trade.get('status'),
        'db_order_status': trade.get('order_status'),
        'db_entry_price': trade.get('binance_entry_price'),
        'db_exit_price': trade.get('binance_exit_price'),
        'db_pnl_usd': trade.get('pnl_usd'),
        'exchange_status': status_str,
        'exchange_executedQty': executed,
        'exchange_avgPrice': avg_price,
        'fills_count': len(fills),
        'realized_pnl_sum': round(total_realized_pnl, 8),
        'commission_sum': round(total_commission, 8),
        'position_existed': position_existed,
        'sample_fills': fills[:3],
        'income_sample': income[:3],
    }


async def main():
    settings.reload_env()

    api_key = settings.BINANCE_API_KEY
    api_secret = settings.BINANCE_API_SECRET
    is_testnet = settings.BINANCE_TESTNET

    if not api_key or not api_secret:
        raise RuntimeError("BINANCE_API_KEY/SECRET not set in environment")

    binance = BinanceExchange(api_key, api_secret, is_testnet=is_testnet)
    await binance.initialize()

    # Trades to audit (from the user's payload)
    trades = [
        { 'id': 32528, 'coin_symbol': 'TRUMP', 'exchange_order_id': '10643191102', 'created_at': '2025-10-30 00:41:55.306807+00', 'closed_at': '2025-10-30 09:37:14.204297+00', 'status': 'CLOSED', 'order_status': 'FILLED', 'binance_entry_price': 8.533, 'binance_exit_price': 7.8, 'pnl_usd': -10.73112 },
        { 'id': 32515, 'coin_symbol': 'HYPE', 'exchange_order_id': '3141613007', 'created_at': '2025-10-29 15:01:34.119887+00', 'closed_at': '2025-10-30 09:37:14.065073+00', 'status': 'CLOSED', 'order_status': 'NEW', 'binance_entry_price': 0, 'binance_exit_price': 0, 'pnl_usd': 0 },
        { 'id': 32514, 'coin_symbol': 'BTC', 'exchange_order_id': '804615126664', 'created_at': '2025-10-29 14:59:59.995613+00', 'closed_at': '2025-10-30 09:37:13.897853+00', 'status': 'CLOSED', 'order_status': 'NEW', 'binance_entry_price': 0, 'binance_exit_price': 0, 'pnl_usd': 0 },
        { 'id': 32513, 'coin_symbol': 'ETH', 'exchange_order_id': '8389765999537327560', 'created_at': '2025-10-29 14:58:56.547982+00', 'closed_at': '2025-10-30 09:37:13.642036+00', 'status': 'CLOSED', 'order_status': 'NEW', 'binance_entry_price': 0, 'binance_exit_price': 3896.73618605, 'pnl_usd': -0.44217823245 },
        { 'id': 32509, 'coin_symbol': 'TAO', 'exchange_order_id': '7809728793', 'created_at': '2025-10-29 13:26:51.978166+00', 'closed_at': '2025-10-30 09:37:13.424546+00', 'status': 'CLOSED', 'order_status': 'NEW', 'binance_entry_price': 0, 'binance_exit_price': 0, 'pnl_usd': 0 },
    ]

    results: List[Dict[str, Any]] = []
    for trade in trades:
        try:
            summary = await audit_trade(binance, trade)
            results.append(summary)
        except Exception as e:
            results.append({'id': trade['id'], 'error': str(e)})

    await binance.close()

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())


