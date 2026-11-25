"""GET /api/v1/market/bars/pull (OTA-859): streamed CSV, trailers, errors, default symbols."""

import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.api.market_routes as market_routes
from app.api.price_bar_routes import router as price_bar_router, stream_bars
from app.models.database import Base, BrokerTransaction, User

UTC = timezone.utc
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_sessions = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def ms(moment):
    return int(moment.timestamp() * 1000)


def bar(moment, price=100.0, volume=10):
    return {"datetime": ms(moment), "open": price, "high": price + 1, "low": price - 1, "close": price + 0.5, "volume": volume}


class FakeBars:
    """get_bars by symbol: a list of bars returned on every window, or an exception to raise."""

    def __init__(self, by_symbol):
        self.by_symbol = by_symbol
        self.calls = []

    async def get_bars(self, symbol, frequency, start, end, extended=True):
        self.calls.append((symbol, frequency, start, end, extended))
        answer = self.by_symbol.get(symbol, [])
        if isinstance(answer, Exception):
            raise answer
        return [b for b in answer if start <= datetime.fromtimestamp(b["datetime"] / 1000, tz=UTC) <= end]


class NoBars:
    pass


class StubRegistry:
    def __init__(self, provider):
        self.provider = provider

    def get_market_data(self, name, user_id=None):
        return self.provider


def parse(text):
    rows, meta = [], []
    for line in text.splitlines():
        (meta if line.startswith("#") else rows).append(line)
    return list(csv.reader(io.StringIO("\n".join(rows)))), meta


async def collect(gen):
    return "".join([chunk async for chunk in gen])


# ── The generator, with a fixed clock ─────────────────────────────────────────

NOW = datetime(2026, 11, 25, 16, 6, 30, tzinfo=UTC)          # 11:06:30 ET


@pytest.mark.asyncio
async def test_rows_trailers_and_done():
    iwm = [bar(datetime(2026, 11, 25, 16, 4, tzinfo=UTC)), bar(datetime(2026, 11, 25, 16, 5, tzinfo=UTC)),
           bar(datetime(2026, 11, 25, 16, 6, tzinfo=UTC)),                       # forming at NOW
           bar(datetime(2026, 11, 25, 12, 0, tzinfo=UTC))]                       # 07:00 ET, pre-market
    spy = [bar(datetime(2026, 11, 24, 20, 59, tzinfo=UTC)), bar(datetime(2026, 11, 24, 21, 0, tzinfo=UTC))]
    provider = FakeBars({"IWM": iwm, "SPY": spy})
    text = await collect(stream_bars(provider, ["IWM", "SPY"], "1m", date(2026, 11, 24), date(2026, 11, 25),
                                     True, frozenset(), 100000, now_fn=lambda: NOW))
    rows, meta = parse(text)
    assert rows[0] == ["symbol", "frequency", "bar_start_utc", "session_date", "session", "open", "high", "low", "close", "volume"]
    body = rows[1:]
    assert [r[0] for r in body] == ["IWM", "IWM", "IWM", "SPY", "SPY"]
    assert ["2026-11-25T16:06:00Z" not in r for r in body] == [True] * 5
    assert {(r[2], r[4]) for r in body if r[0] == "IWM"} == {
        ("2026-11-25T12:00:00Z", "pre"), ("2026-11-25T16:04:00Z", "reg"), ("2026-11-25T16:05:00Z", "reg")}
    assert [r[4] for r in body if r[0] == "SPY"] == ["reg", "post"]
    assert meta == ["#IWM,ok,2026-11-25T12:00:00Z,2026-11-25T16:05:00Z,3",
                    "#SPY,ok,2026-11-24T20:59:00Z,2026-11-24T21:00:00Z,2", "#done"]
    assert len(provider.calls) == 2      # one 1m window covers two days


@pytest.mark.asyncio
async def test_duplicates_across_windows_written_once():
    day = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)

    class Overlap(FakeBars):
        async def get_bars(self, symbol, frequency, start, end, extended=True):
            self.calls.append(symbol)
            return [bar(day)]            # every window answers the same bar

    provider = Overlap({})
    text = await collect(stream_bars(provider, ["QQQ"], "1m", date(2026, 11, 1), date(2026, 11, 25),
                                     True, frozenset(), 100000, now_fn=lambda: NOW))
    rows, meta = parse(text)
    assert len(provider.calls) == 3 and len(rows) == 2
    assert meta == ["#QQQ,ok,2026-11-10T15:00:00Z,2026-11-10T15:00:00Z,1", "#done"]


@pytest.mark.asyncio
async def test_failing_symbol_is_error_and_the_next_still_streams():
    provider = FakeBars({"GLD": RuntimeError("boom"), "SPY": [bar(datetime(2026, 11, 24, 15, 0, tzinfo=UTC))]})
    text = await collect(stream_bars(provider, ["GLD", "SPY", "TLT"], "5m", date(2026, 11, 24), date(2026, 11, 24),
                                     True, frozenset(), 100000, now_fn=lambda: NOW))
    _, meta = parse(text)
    assert meta[0] == "#GLD,error,,,0"
    assert meta[1].startswith("#SPY,ok,") and meta[2] == "#TLT,empty,,,0" and meta[-1] == "#done"


@pytest.mark.asyncio
async def test_auth_error_ends_with_error_and_no_done():
    provider = FakeBars({
        "IWM": [bar(datetime(2026, 11, 24, 15, 0, tzinfo=UTC))],
        "SPY": Exception("Schwab refresh token expired (7-day limit). Please reconnect your Schwab account."),
    })
    text = await collect(stream_bars(provider, ["IWM", "SPY", "QQQ"], "1d", date(2026, 11, 1), date(2026, 11, 24),
                                     True, frozenset(), 100000, now_fn=lambda: NOW))
    _, meta = parse(text)
    assert meta[0].startswith("#IWM,ok,")
    assert meta[-1].startswith("#error,SPY,Schwab refresh token expired")
    assert "#done" not in meta and all(not m.startswith("#QQQ") for m in meta)


@pytest.mark.asyncio
async def test_daily_bars_are_reg_and_today_is_left_out_until_the_close():
    provider = FakeBars({"IWM": [bar(datetime(2026, 11, 24, 6, 0, tzinfo=UTC)), bar(datetime(2026, 11, 25, 6, 0, tzinfo=UTC))]})
    text = await collect(stream_bars(provider, ["IWM"], "1d", date(2026, 11, 20), date(2026, 11, 25),
                                     True, frozenset(), 100000, now_fn=lambda: NOW))
    rows, meta = parse(text)
    assert [(r[3], r[4]) for r in rows[1:]] == [("2026-11-24", "reg")]
    assert meta[-1] == "#done"


# ── The route ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_ready():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _sessions() as db:
        db.add_all([
            User(id=USER_A, username="a", email="a@example.com", role="admin", is_active=True),
            User(id=USER_B, username="b", email="b@example.com", role="admin", is_active=True),
        ])
        stamp = datetime(2026, 11, 20, 15, 0)
        for i, (user, sym) in enumerate([(USER_A, "NVDA"), (USER_A, "AMD"), (USER_A, "spy"), (USER_A, None), (USER_B, "ZZZ")]):
            db.add(BrokerTransaction(user_id=user, account_id=1, activity_id=1000 + i, transaction_type="TRADE",
                                     time=stamp, trade_date=stamp.date(), underlying_symbol=sym, raw_json="{}"))
        await db.commit()
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def build_app(provider, monkeypatch, user_id=USER_A):
    from app.auth.dependencies import require_write
    from app.models.session import get_db

    async def _user():
        return {"sub": user_id, "username": "test", "role": "admin", "mfa": True}

    async def _db():
        async with _sessions() as session:
            yield session

    app = FastAPI()
    app.include_router(price_bar_router, prefix="/api/v1")
    app.dependency_overrides[require_write] = _user
    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(market_routes, "_provider_registry", StubRegistry(provider))
    monkeypatch.setattr("app.api.price_bar_routes.settings.price_bars_calls_per_minute", 100000)
    monkeypatch.setattr("app.api.price_bar_routes.settings.price_bars_symbols", "IWM,SPY")
    return app


async def get(app, url):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(url)


@pytest.mark.asyncio
async def test_route_streams_csv_with_explicit_symbols(db_ready, monkeypatch):
    provider = FakeBars({"IWM": [bar(datetime(2026, 11, 24, 15, 0, tzinfo=UTC))]})
    resp = await get(build_app(provider, monkeypatch), "/api/v1/market/bars/pull?frequency=5m&start=2026-11-24&end=2026-11-24&symbols=iwm&extended=false")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    assert 'filename="bars_5m_2026-11-24_2026-11-24.csv"' in resp.headers["content-disposition"]
    rows, meta = parse(resp.text)
    assert rows[1][:5] == ["IWM", "5m", "2026-11-24T15:00:00Z", "2026-11-24", "reg"]
    assert meta == ["#IWM,ok,2026-11-24T15:00:00Z,2026-11-24T15:00:00Z,1", "#done"]
    assert provider.calls[0][4] is False


@pytest.mark.asyncio
async def test_route_default_symbols_are_settings_plus_own_underlyings(db_ready, monkeypatch):
    provider = FakeBars({})
    resp = await get(build_app(provider, monkeypatch), "/api/v1/market/bars/pull?frequency=1d&start=2026-11-01&end=2026-11-24")
    _, meta = parse(resp.text)
    assert [m.split(",")[0] for m in meta[:-1]] == ["#IWM", "#SPY", "#AMD", "#NVDA"]
    assert [c[0] for c in provider.calls] == ["IWM", "SPY", "AMD", "NVDA"]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "frequency=15m&start=2026-11-24",
    "frequency=1m&start=2026-11-25&end=2026-11-24",
])
async def test_route_rejects_bad_input(db_ready, monkeypatch, query):
    resp = await get(build_app(FakeBars({}), monkeypatch), f"/api/v1/market/bars/pull?{query}")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_route_501_without_get_bars(db_ready, monkeypatch):
    resp = await get(build_app(NoBars(), monkeypatch), "/api/v1/market/bars/pull?frequency=1d&start=2026-11-24&symbols=IWM")
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_429_is_retried_once(monkeypatch):
    import httpx

    monkeypatch.setattr("app.api.price_bar_routes._RATE_LIMIT_PAUSE_SECONDS", 0)
    request = httpx.Request("GET", "https://api.schwabapi.com/marketdata/v1/pricehistory")

    class Throttled(FakeBars):
        def __init__(self, failures):
            super().__init__({})
            self.failures = failures

        async def get_bars(self, symbol, frequency, start, end, extended=True):
            self.calls.append(symbol)
            if len(self.calls) <= self.failures:
                raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))
            return [bar(datetime(2026, 11, 24, 15, 0, tzinfo=UTC))]

    once = Throttled(1)
    _, meta = parse(await collect(stream_bars(once, ["IWM"], "1d", date(2026, 11, 24), date(2026, 11, 24),
                                              True, frozenset(), 100000, now_fn=lambda: NOW)))
    assert len(once.calls) == 2 and meta[0].startswith("#IWM,ok,")

    twice = Throttled(2)
    _, meta = parse(await collect(stream_bars(twice, ["IWM"], "1d", date(2026, 11, 24), date(2026, 11, 24),
                                              True, frozenset(), 100000, now_fn=lambda: NOW)))
    assert len(twice.calls) == 2 and meta == ["#IWM,error,,,0", "#done"]


@pytest.mark.asyncio
async def test_calls_are_paced():
    import time as _time

    provider = FakeBars({})
    started = _time.monotonic()
    await collect(stream_bars(provider, ["A", "B", "C"], "1d", date(2026, 11, 24), date(2026, 11, 24),
                              True, frozenset(), 600, now_fn=lambda: NOW))      # 0.1 s apart
    assert len(provider.calls) == 3 and _time.monotonic() - started >= 0.19
