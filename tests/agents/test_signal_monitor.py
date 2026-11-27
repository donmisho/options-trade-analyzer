"""Entry signal monitor: the one-minute run against in-memory SQLite with a fake provider, and get_signals."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.agents.signal_monitor as signal_monitor
import app.api.mcp_routes as mcp_routes
from app.agents.signal_monitor import SignalMonitor, in_signal_hours, watched_symbols
from app.core.config import settings
from app.models.database import Base, EntrySignal, User

UTC = timezone.utc
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OPEN = datetime(2026, 11, 24, 14, 30, tzinfo=UTC)    # Tuesday 09:30 New York
NOW = OPEN + timedelta(minutes=40, seconds=10)       # 10:10:10

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_sessions = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def ms(moment):
    return int(moment.timestamp() * 1000)


def minute(i, open_, close, volume=100):
    return {"datetime": ms(OPEN + timedelta(minutes=i)), "open": open_, "high": max(open_, close) + 0.01,
            "low": min(open_, close) - 0.01, "close": close, "volume": volume}


def pushing_session(push=0.5, push_volume=300):
    """Drifts up a cent a minute from 100.00, then the 10:05 bar moves `push`."""
    bars, price = [], 100.0
    for i in range(35):
        bars.append(minute(i, price, price + 0.01))
        price += 0.01
    for i in range(35, 40):
        bars.append(minute(i, price, price + push / 5, push_volume))
        price += push / 5
    return bars


def daily_candles():
    """Twenty sessions before 11-24 with a 4.00 range and a 100.00 close: D ATR 4.00."""
    day = datetime(2026, 11, 23, 5, 0, tzinfo=UTC)
    out = []
    while len(out) < 20:
        if day.weekday() < 5:
            out.append({"datetime": ms(day), "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000})
        day -= timedelta(days=1)
    return out


def call(dte, delta, bid, ask, symbol="IWM   261201C00100000"):
    return {"symbol": symbol, "expiration": "2026-12-01", "dte": dte, "strike": 100.0, "option_type": "call",
            "bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 4), "delta": delta}


class FakeProvider:
    def __init__(self, minute_bars, chain=None):
        self.minute_bars = minute_bars       # symbol -> bars, or an Exception
        self.chain = chain or []
        self.bar_calls, self.chain_calls = [], []

    async def get_bars(self, symbol, frequency, start, end, extended=True):
        self.bar_calls.append((symbol, frequency))
        if frequency == "1d":
            return daily_candles()
        answer = self.minute_bars.get(symbol, [])
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def get_chain(self, symbol, min_dte=0, max_dte=90, strike_range_pct=10.0, option_type=None):
        self.chain_calls.append((symbol, min_dte, max_dte, option_type))
        return {"underlying": symbol, "contracts": self.chain}


@pytest_asyncio.fixture
async def db(monkeypatch):
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _sessions() as session:
        session.add(User(id=USER, username="a", email="a@example.com", role="admin", is_active=True))
        await session.commit()
    monkeypatch.setattr(settings, "broker_activity_user_id", USER)
    monkeypatch.setattr(settings, "signal_monitor_symbols", "IWM,SPY")
    monkeypatch.setattr(signal_monitor, "to_api_symbol_cached", lambda s, p: s.upper())
    monkeypatch.setattr(signal_monitor, "canonicalize", lambda s: s.upper())
    async with _sessions() as session:
        yield session


async def rows_by_symbol(session):
    session.expire_all()
    return {r.symbol: r for r in (await session.execute(select(EntrySignal))).scalars().all()}


def test_signal_hours():
    assert in_signal_hours(OPEN + timedelta(minutes=5))
    assert not in_signal_hours(OPEN + timedelta(minutes=4))
    assert not in_signal_hours(datetime(2026, 11, 24, 21, 0, tzinfo=UTC))            # 16:00 New York
    assert not in_signal_hours(datetime(2026, 11, 28, 15, 0, tzinfo=UTC))            # Saturday
    early = frozenset({datetime(2026, 11, 27).date()})
    assert in_signal_hours(datetime(2026, 11, 27, 17, 59, tzinfo=UTC), early)        # 12:59 on the early close
    assert not in_signal_hours(datetime(2026, 11, 27, 18, 0, tzinfo=UTC), early)


def test_watched_symbols_fall_back_to_the_price_bar_list(monkeypatch):
    monkeypatch.setattr(signal_monitor, "canonicalize", lambda s: s.upper())
    monkeypatch.setattr(settings, "signal_monitor_symbols", "")
    monkeypatch.setattr(settings, "price_bars_symbols", "iwm, spy,IWM")
    assert watched_symbols() == ["IWM", "SPY"]


@pytest.mark.asyncio
async def test_a_run_writes_one_row_per_symbol_and_reads_the_chain_only_when_ready(db):
    provider = FakeProvider({"IWM": pushing_session(), "SPY": pushing_session(push=0.05, push_volume=100)},
                            chain=[call(7, 0.55, 2.99, 3.01)])
    result = await SignalMonitor(provider, now=lambda: NOW).run(db)
    assert (result.status, result.symbols, result.signals, result.errors) == ("ok", 2, 1, 0)

    rows = await rows_by_symbol(db)
    iwm, spy = rows["IWM"], rows["SPY"]
    assert iwm.status == "signal" and iwm.direction == "call" and iwm.user_id == USER
    assert iwm.atr == 4.0 and iwm.prev_close == 100.0 and iwm.push_pct_atr == 12.5 and iwm.volume_ratio == 3.0
    assert (iwm.gate_trend, iwm.gate_push, iwm.gate_volume, iwm.gate_room, iwm.gate_contract) == (True,) * 5
    assert iwm.option_symbol == "IWM   261201C00100000" and iwm.dte == 7 and iwm.spread_pct == 0.67
    assert iwm.push_bar_at == (OPEN + timedelta(minutes=35)).replace(tzinfo=None)
    assert spy.status == "watch" and spy.gate_push is False and spy.option_symbol is None
    assert provider.chain_calls == [("IWM", 2, 14, "call")]


@pytest.mark.asyncio
async def test_rows_are_rewritten_not_added_and_daily_levels_are_read_once(db):
    provider = FakeProvider({"IWM": pushing_session(), "SPY": pushing_session()}, chain=[call(7, 0.55, 2.99, 3.01)])
    clock = {"now": NOW}
    monitor = SignalMonitor(provider, now=lambda: clock["now"])
    await monitor.run(db)
    first = (await rows_by_symbol(db))["IWM"].status_since
    clock["now"] = NOW + timedelta(minutes=1)
    await monitor.run(db)

    rows = await rows_by_symbol(db)
    assert len(rows) == 2
    assert rows["IWM"].status_since == first                                   # still the same signal
    assert rows["IWM"].evaluated_at == (NOW + timedelta(minutes=1)).replace(tzinfo=None)
    assert sum(1 for c in provider.bar_calls if c[1] == "1d") == 2             # once per symbol, not per run


@pytest.mark.asyncio
async def test_no_contract_and_a_dropped_symbol(db, monkeypatch):
    provider = FakeProvider({"IWM": pushing_session(), "SPY": pushing_session()}, chain=[call(7, 0.55, 2.00, 2.40)])
    monitor = SignalMonitor(provider, now=lambda: NOW)
    await monitor.run(db)
    rows = await rows_by_symbol(db)
    assert rows["IWM"].status == "no_contract" and rows["IWM"].gate_contract is False
    assert rows["IWM"].message == "no call with a spread within 3% of the mid"

    monkeypatch.setattr(settings, "signal_monitor_symbols", "IWM")
    await monitor.run(db)
    assert set(await rows_by_symbol(db)) == {"IWM"}


@pytest.mark.asyncio
async def test_one_failed_symbol_is_an_error_row_and_auth_failure_marks_the_run(db):
    provider = FakeProvider({"IWM": pushing_session(), "SPY": RuntimeError("503 Service Unavailable")},
                            chain=[call(7, 0.55, 2.99, 3.01)])
    result = await SignalMonitor(provider, now=lambda: NOW).run(db)
    rows = await rows_by_symbol(db)
    assert result.status == "ok" and result.errors == 1 and result.message == "failed: SPY"
    assert rows["SPY"].status == "error" and "503" in rows["SPY"].message and rows["IWM"].status == "signal"

    expired = RuntimeError("Schwab refresh token expired. Please re-authenticate.")
    result = await SignalMonitor(FakeProvider({"IWM": expired, "SPY": expired}), now=lambda: NOW).run(db)
    assert result.status == "auth_error"


@pytest.mark.asyncio
async def test_stale_bars_and_out_of_hours(db):
    old = [b for b in pushing_session() if b["datetime"] < ms(OPEN + timedelta(minutes=30))]
    provider = FakeProvider({"IWM": old, "SPY": old})
    await SignalMonitor(provider, now=lambda: NOW).run(db)
    iwm = (await rows_by_symbol(db))["IWM"]
    assert iwm.status == "no_data" and "minutes old" in iwm.message

    night = datetime(2026, 11, 24, 23, 0, tzinfo=UTC)
    result = await SignalMonitor(provider, now=lambda: night).run(db)
    assert result.status == "skipped"
    assert (await SignalMonitor(provider, now=lambda: night).run(db, force=True)).status == "ok"


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        moment = NOW + timedelta(seconds=30)
        return moment if tz else moment.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_get_signals_serves_only_the_callers_rows(db, monkeypatch):
    provider = FakeProvider({"IWM": pushing_session(), "SPY": pushing_session(push=0.05, push_volume=100)},
                            chain=[call(7, 0.55, 2.99, 3.01)])
    monitor = SignalMonitor(provider, now=lambda: NOW)
    await monitor.run(db)
    db.add(User(id=OTHER, username="b", email="b@example.com", role="user", is_active=True))
    db.add(EntrySignal(user_id=OTHER, symbol="TSLA", status="signal", evaluated_at=NOW.replace(tzinfo=None),
                       status_since=NOW.replace(tzinfo=None)))
    await db.commit()

    @asynccontextmanager
    async def session():
        async with _sessions() as s:
            yield s

    async def no_obs(*args, **kwargs):
        return None

    monkeypatch.setattr(mcp_routes, "async_session", session)
    monkeypatch.setattr(mcp_routes, "mcp_tool_observability", no_obs)
    monkeypatch.setattr(mcp_routes, "_get_mcp_user_id", lambda: USER)
    monkeypatch.setattr(mcp_routes, "datetime", FrozenDatetime)
    mcp_routes.init_mcp_signal_monitor(monitor)
    try:
        out = await mcp_routes.get_signals()
        assert [r["symbol"] for r in out["rows"]] == ["IWM", "SPY"]              # signals first, no other user's row
        assert out["fresh"] is True and out["count"] == 2 and out["source"] == "entry_signals"
        iwm = out["rows"][0]
        assert list(iwm) == out["columns"]
        assert iwm["status"] == "signal" and iwm["age_seconds"] == 30
        assert iwm["evaluated_at"].startswith("2026-11-24T09:10:10")              # Central display zone
        assert iwm["push_bar_at"].startswith("2026-11-24T09:05:00")
        assert out["rules"]["push_min_pct_atr"] == 10.0 and out["rules"]["spread_max_pct"] == 3.0
        assert out["monitor"]["enabled"] is True and out["monitor"]["last_run"]["signals"] == 1

        assert [r["symbol"] for r in (await mcp_routes.get_signals(status="watch"))["rows"]] == ["SPY"]
        assert [r["symbol"] for r in (await mcp_routes.get_signals(symbols="iwm"))["rows"]] == ["IWM"]

        monkeypatch.setattr(mcp_routes, "_get_mcp_user_id", lambda: None)
        assert (await mcp_routes.get_signals())["error_code"] == "UNAUTHENTICATED"
    finally:
        mcp_routes.init_mcp_signal_monitor(None)
