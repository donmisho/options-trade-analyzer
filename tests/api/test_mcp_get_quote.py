"""MCP get_quote (OTA-858): passes change, day_high and day_low through."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

import app.api.mcp_routes as mcp_routes


class FakeQuotes:
    def __init__(self, quote):
        self.quote = quote

    async def get_quote(self, symbol):
        return {"symbol": symbol, "timestamp": datetime(2026, 11, 25, 16, 6, tzinfo=timezone.utc), **self.quote}


@pytest.fixture
def patched(monkeypatch):
    @asynccontextmanager
    async def no_db():
        yield None

    async def no_obs(*args, **kwargs):
        return None

    monkeypatch.setattr(mcp_routes, "async_session", no_db)
    monkeypatch.setattr(mcp_routes, "mcp_tool_observability", no_obs)
    monkeypatch.setattr(mcp_routes, "to_api_symbol_cached", lambda s, p: s.upper())

    def use(quote):
        monkeypatch.setattr(mcp_routes, "_get_provider", lambda: FakeQuotes(quote))

    return use


@pytest.mark.asyncio
async def test_day_range_and_change_pass_through(patched):
    patched({"price": 262.8, "volume": 1000, "previous_close": 267.14, "change": -4.34,
             "change_pct": -1.62, "day_high": 267.5, "day_low": 260.84})
    out = await mcp_routes.get_quote("iwm")
    assert out["ticker"] == "IWM" and out["price"] == 262.8 and out["prev_close"] == 267.14
    assert (out["change"], out["day_high"], out["day_low"]) == (-4.34, 267.5, 260.84)
    assert out["change_pct"] == -1.62


@pytest.mark.asyncio
async def test_missing_high_and_low_are_null_not_zero(patched):
    patched({"price": 262.8, "volume": 0, "previous_close": 267.14, "change": 0, "change_pct": 0,
             "day_high": 0, "day_low": 0})
    out = await mcp_routes.get_quote("IWM")
    assert out["day_high"] is None and out["day_low"] is None
    assert out["change"] == 0
