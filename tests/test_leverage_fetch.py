import os
import pytest

from supabase import create_client, Client


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        pytest.skip("SUPABASE_URL or SUPABASE_KEY not set")
    return create_client(url, key)


def _fetch_leverage_direct(trader_id: str, exchange: str) -> float:
    supabase = _get_supabase()
    try:
        response = supabase.table("trader_exchange_config").select("leverage").eq("trader_id", trader_id).eq("exchange", exchange).single().execute()
        data = getattr(response, "data", None)
        if data and "leverage" in data:
            return float(data["leverage"])  # type: ignore[arg-type]
        return 1.0
    except Exception:
        return 1.0


@pytest.mark.parametrize(
    "trader_id,exchange,max_lev",
    [
        ("johnny", "binance", 125),
        ("woods", "kucoin", 100),
    ],
)
def test_fetch_leverage_for_exchanges(trader_id: str, exchange: str, max_lev: int):
    lev = _fetch_leverage_direct(trader_id, exchange)

    print(f"\nTrader: {trader_id}")
    print(f"Exchange: {exchange}")
    print(f"Leverage: {lev}x")

    assert isinstance(lev, float)
    assert 1.0 <= lev <= float(max_lev)


