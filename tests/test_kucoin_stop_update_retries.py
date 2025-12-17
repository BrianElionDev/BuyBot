import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.exchange.kucoin.kucoin_exchange import KucoinExchange


@pytest.mark.asyncio
async def test_place_stop_loss_retries_on_4008():
    exchange = KucoinExchange("k", "s", "p", False)
    exchange.get_mark_price = AsyncMock(return_value=20500.0)
    exchange._init_client = AsyncMock()
    exchange.create_futures_order = AsyncMock(side_effect=[
        {"error": "Cannot validate notional value: mark price unavailable", "code": -4008},
        {"orderId": "ok"}
    ])

    with patch("asyncio.sleep", AsyncMock()):
        result = await exchange.place_stop_loss_with_retry(
            pair="BTC-USDT",
            side="SELL",
            stop_price=20000.0,
            amount=1.0,
            reduce_only=True,
            max_attempts=3,
            base_delay=0.1
        )

    assert result.get("orderId") == "ok"
    assert exchange.create_futures_order.call_count == 2


@pytest.mark.asyncio
async def test_place_stop_loss_uses_index_fallback_when_mark_missing():
    exchange = KucoinExchange("k", "s", "p", False)
    exchange.get_mark_price = AsyncMock(return_value=None)
    exchange._get_index_price_fallback = AsyncMock(return_value=19000.0)
    exchange._init_client = AsyncMock()
    exchange.create_futures_order = AsyncMock(return_value={"orderId": "ok"})

    with patch("asyncio.sleep", AsyncMock()):
        result = await exchange.place_stop_loss_with_retry(
            pair="BTC-USDT",
            side="SELL",
            stop_price=18900.0,
            amount=1.0,
            reduce_only=True,
            max_attempts=2,
            base_delay=0.1
        )

    assert result.get("orderId") == "ok"
    call_kwargs = exchange.create_futures_order.call_args.kwargs
    assert call_kwargs["validation_price_override"] == 19000.0

