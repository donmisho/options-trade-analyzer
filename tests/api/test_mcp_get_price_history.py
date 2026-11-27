"""MCP get_price_history: Schwab bars through get_bars, forming bar, sessions, ranges, errors."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

import app.api.mcp_routes as mcp_routes

UTC = timezone.utc
# Tuesday 11-24-2026, 15:02:30 UTC = 10:02:30 New York.
NOW = datetime(2026, 11, 24, 15, 2, 30, tzinfo=UTC)
OPEN = datetime(2026, 11, 24, 14, 30, tzinfo=UTC)   # 09:30 New York


def bar(moment, price=100.0, volume=10):
    return {"datetime": int(moment.timestamp() * 1000), "open": price, "high": price + 1,
            "low": price - 1, "close": price + 0.5, "volume": volume}


class FakeBars:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    async def get_bars(self, symbol, frequency, start, end, extended=True):
        self.calls.append((symbol, frequency, start, end, extended))
        if isinstance(self.answer, Exception):
            raise self.answer
        return [b for b in self.answer if start <= datetime.fromtimestamp(b["datetime"] / 1000, tz=UTC) <= end]


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


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
    monkeypatch.setattr(mcp_routes, "datetime", FrozenDatetime)

    def use(answer):
        provider = FakeBars(answer)
        monkeypatch.setattr(mcp_routes, "_get_provider", lambda: provider)
        return provider

    return use


@pytest.mark.asyncio
async def test_latest_session_only_and_forming_bar_left_out(patched):
    yesterday = [bar(OPEN - timedelta(days=1) + timedelta(minutes=i), 90.0) for i in range(3)]
    today = [bar(OPEN + timedelta(minutes=i), 100.0 + i) for i in range(33)]   # 09:30 .. 10:02
    provider = patched(yesterday + today)
    out = await mcp_routes.get_price_history("iwm")
    assert out["ticker"] == "IWM" and out["frequency"] == "1m" and out["source"] == "schwab_pricehistory"
    assert {r["session_date"] for r in out["rows"]} == {"2026-11-24"}
    assert out["count"] == 32                       # 10:02 is still forming
    assert out["rows"][0]["bar_start_utc"] == "2026-11-24T14:30:00Z"
    assert out["rows"][0]["bar_start"].startswith("2026-11-24T08:30:00")   # Central display zone
    assert out["rows"][0]["session"] == "reg" and all(r["complete"] for r in out["rows"])
    assert provider.calls[0][:2] == ("IWM", "1m") and provider.calls[0][4] is False


@pytest.mark.asyncio
async def test_include_forming_marks_the_open_bar(patched):
    patched([bar(OPEN + timedelta(minutes=i)) for i in range(33)])
    out = await mcp_routes.get_price_history("IWM", include_forming=True)
    assert out["count"] == 33
    assert out["rows"][-1]["complete"] is False and out["rows"][-2]["complete"] is True


@pytest.mark.asyncio
async def test_fifteen_minute_bars_are_built_from_five(patched):
    provider = patched([bar(OPEN + timedelta(minutes=5 * i), 100.0 + i, volume=10) for i in range(6)])  # 09:30 .. 09:55
    out = await mcp_routes.get_price_history("IWM", frequency="15m", start_date="2026-11-24", end_date="2026-11-24")
    assert provider.calls[0][1] == "5m"
    assert [r["bar_start_utc"] for r in out["rows"]] == ["2026-11-24T14:30:00Z", "2026-11-24T14:45:00Z"]
    first = out["rows"][0]
    assert (first["open"], first["close"], first["high"], first["low"], first["volume"]) == (100.0, 102.5, 103.0, 99.0, 30)


@pytest.mark.asyncio
async def test_limit_keeps_the_newest_bars(patched):
    patched([bar(OPEN + timedelta(minutes=i), 100.0 + i) for i in range(30)])
    out = await mcp_routes.get_price_history("IWM", limit=5)
    assert out["count"] == 5 and out["truncated"] is True
    assert out["rows"][-1]["bar_start_utc"] == "2026-11-24T14:59:00Z"


@pytest.mark.asyncio
async def test_bad_inputs(patched):
    patched([])
    assert (await mcp_routes.get_price_history("IWM", frequency="2m"))["error_code"] == "BAD_FREQUENCY"
    assert (await mcp_routes.get_price_history("IWM", start_date="11/24/2026"))["error_code"] == "BAD_DATE"
    assert (await mcp_routes.get_price_history("IWM", start_date="2026-11-01", end_date="2026-11-24"))["error_code"] == "BAD_RANGE"
    assert (await mcp_routes.get_price_history("IWM", start_date="2026-11-24", end_date="2026-11-20"))["error_code"] == "BAD_RANGE"


@pytest.mark.asyncio
async def test_empty_is_empty_and_errors_are_error_objects(patched):
    patched([])
    out = await mcp_routes.get_price_history("IWM")
    assert out["rows"] == [] and out["count"] == 0 and out["last_bar"] is None

    patched(RuntimeError("Schwab refresh token expired. Please re-authenticate."))
    out = await mcp_routes.get_price_history("IWM")
    assert out["error"] is True and out["error_code"] == "SCHWAB_AUTH"

    patched(RuntimeError("503 Service Unavailable"))
    assert (await mcp_routes.get_price_history("IWM"))["error_code"] == "SCHWAB_UNAVAILABLE"
