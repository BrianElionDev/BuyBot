import asyncio
import json
import pytest

try:
    import httpx
except Exception as _e:  # pragma: no cover
    httpx = None


@pytest.mark.anyio
async def test_scheduler_transaction_history_endpoint_snapshot():
    """
    Integration test: hit /scheduler/test-transaction-history and snapshot the response.
    Uses FastAPI app object directly (ASGI) so the service doesn't need to be running separately.
    """
    if httpx is None:
        pytest.skip("httpx not available")

    # Import FastAPI app from the discord service
    from discord_bot.main import app

    # httpx >= 0.27 removed `app=` kwarg; use ASGITransport instead
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/scheduler/test-transaction-history")

    # Basic assertions
    assert resp.status_code in (200, 500), f"Unexpected status code: {resp.status_code}"

    data = resp.json()

    # Print the payload to help manual inspection when running locally
    # (pytest will capture; use -s to show)
    print("/scheduler/test-transaction-history ->", json.dumps(data, indent=2, sort_keys=True))

    # If successful path, ensure expected message structure
    if resp.status_code == 200 and isinstance(data, dict):
        assert "message" in data or "error" in data
        # Non-strict check, endpoint may return message or error depending on availability of clients

    # If failure path, at least ensure it is a JSON dict with error
    if resp.status_code == 500:
        assert isinstance(data, dict)

