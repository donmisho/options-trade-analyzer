"""
OTA-855: account activity poller — normalization, fill-context math, market-hours
gating, and the sync service against an in-memory SQLite database with a fake provider.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.account_activity_sync import AccountActivitySync, account_labels, resolve_owner_user_id
from app.models.database import (
    Base, BrokerAccount, BrokerFillContext, BrokerOrder, BrokerSyncRun, BrokerTransaction, User,
)
from app.providers.schwab_account import iso_utc, option_symbol
from app.services.broker_activity import (
    FILL_COLUMNS, daily_context_from_candles, fill_context_values, fill_row, in_market_hours,
    normalize_order, normalize_transaction, parse_option_symbol, parse_time, wilder_atr,
)
from app.services.trade_fills import list_fill_rows

NY = timezone(timedelta(hours=-4))  # EDT, the zone of the sample timestamps below

# ── Sample payloads in the Trader API's shape ────────────────────────────────

CURRENCY = {"assetType": "CURRENCY", "status": "ACTIVE", "symbol": "CURRENCY_USD", "description": "US Dollar", "instrumentId": 1}


def option_instrument(root, exp, pc, strike, underlying=None):
    return {
        "assetType": "OPTION", "status": "ACTIVE", "symbol": option_symbol(root, exp, pc, strike),
        "description": f"{root} {exp:%m/%d/%Y} {strike:.2f} {pc[0]}", "instrumentId": 123,
        "expirationDate": f"{exp.isoformat()}T20:00:00+0000", "optionPremiumMultiplier": 100,
        "putCall": pc, "strikePrice": strike, "type": "VANILLA", "underlyingSymbol": underlying or root,
    }


def single_buy(activity_id=1001, order_id=5001, when="2026-10-23T14:31:05+0000"):
    return {
        "activityId": activity_id, "time": when, "type": "TRADE", "status": "VALID", "subAccount": "CASH",
        "tradeDate": when, "settlementDate": "2026-10-24T04:00:00+0000", "positionId": 777, "orderId": order_id,
        "netAmount": -1234.69, "activityType": "EXECUTION", "accountNumber": "24427892",
        "transferItems": [
            {"instrument": option_instrument("SPY", date(2026, 10, 24), "CALL", 580.0), "amount": 1, "cost": -1234.0, "price": 12.34, "positionEffect": "OPENING"},
            {"instrument": CURRENCY, "amount": -0.65, "cost": -0.65, "feeType": "COMMISSION"},
            {"instrument": CURRENCY, "amount": -0.04, "cost": -0.04, "feeType": "OPT_REG_FEE"},
        ],
    }


def vertical_sell(activity_id=1002, order_id=5002, when="2026-10-23T15:02:10+0000"):
    exp = date(2026, 10, 24)
    return {
        "activityId": activity_id, "time": when, "type": "TRADE", "status": "VALID", "subAccount": "CASH",
        "tradeDate": when, "positionId": 778, "orderId": order_id, "netAmount": 238.70, "activityType": "EXECUTION",
        "transferItems": [
            {"instrument": option_instrument("QQQ", exp, "PUT", 500.0), "amount": -2, "cost": 640.0, "price": 3.20, "positionEffect": "OPENING"},
            {"instrument": option_instrument("QQQ", exp, "PUT", 495.0), "amount": 2, "cost": -400.0, "price": 2.00, "positionEffect": "OPENING"},
            {"instrument": CURRENCY, "amount": -1.30, "cost": -1.30, "feeType": "COMMISSION"},
        ],
    }


def oco_order(order_id=5001):
    leg = {"instrument": option_instrument("SPY", date(2026, 10, 24), "CALL", 580.0), "instruction": "SELL_TO_CLOSE", "positionEffect": "CLOSING", "quantity": 1}
    return {
        "orderId": order_id, "orderType": "LIMIT", "orderStrategyType": "TRIGGER", "status": "FILLED", "session": "NORMAL",
        "duration": "DAY", "price": 12.34, "quantity": 1, "filledQuantity": 1, "remainingQuantity": 0,
        "enteredTime": "2026-10-23T14:30:50+0000", "closeTime": "2026-10-23T14:31:05+0000",
        "orderLegCollection": [{**leg, "instruction": "BUY_TO_OPEN", "positionEffect": "OPENING"}],
        "childOrderStrategies": [{
            "orderStrategyType": "OCO",
            "childOrderStrategies": [
                {"orderId": order_id + 1, "orderType": "LIMIT", "orderStrategyType": "SINGLE", "status": "WORKING", "price": 16.00,
                 "quantity": 1, "filledQuantity": 0, "enteredTime": "2026-10-23T14:30:50+0000", "orderLegCollection": [leg]},
                {"orderId": order_id + 2, "orderType": "STOP", "orderStrategyType": "SINGLE", "status": "WORKING", "stopPrice": 9.50,
                 "quantity": 1, "filledQuantity": 0, "enteredTime": "2026-10-23T14:30:50+0000", "orderLegCollection": [leg]},
            ],
        }],
    }


def candles(days=40, start=date(2026, 9, 1), base=100.0, rng=2.0):
    """Daily candles, weekdays only, each with a true range of exactly `rng`."""
    out, day, close = [], start, base
    while len(out) < days:
        if day.weekday() < 5:
            stamp = int(datetime(day.year, day.month, day.day, 5, tzinfo=timezone.utc).timestamp() * 1000)
            out.append({"open": close, "high": close + rng, "low": close, "close": close + rng / 2, "volume": 1000, "datetime": stamp})
            close = close + rng / 2
        day += timedelta(days=1)
    return out


# ── Normalization ────────────────────────────────────────────────────────────


class TestOptionSymbols:
    def test_build_and_parse(self):
        sym = option_symbol("SPY", date(2026, 10, 24), "CALL", 580)
        assert sym == "SPY   261024C00580000"
        parsed = parse_option_symbol(sym)
        assert parsed == {"root": "SPY", "expiration": date(2026, 10, 24), "put_call": "CALL", "strike": 580.0}

    def test_half_strike_and_long_root(self):
        sym = option_symbol("SPXW", date(2026, 10, 24), "PUT", 5042.5)
        assert sym == "SPXW  261024P05042500"
        assert parse_option_symbol(sym)["strike"] == 5042.5

    def test_times(self):
        assert parse_time("2026-10-23T14:31:05+0000") == datetime(2026, 10, 23, 14, 31, 5, tzinfo=timezone.utc)
        assert parse_time("2026-10-23T14:31:05.250Z").microsecond == 250000
        assert parse_time(None) is None
        assert iso_utc(datetime(2026, 10, 23, 14, 31, 5, tzinfo=timezone.utc)) == "2026-10-23T14:31:05.000Z"


class TestNormalizeTransaction:
    def test_single_buy(self):
        row = normalize_transaction(single_buy())
        assert row["activity_id"] == 1001 and row["order_id"] == 5001
        assert row["side"] == "Buy" and row["structure"] == "Single" and row["asset_type"] == "OPTION"
        assert row["quantity"] == 1 and row["price"] == 12.34
        assert row["leg_cost"] == -1234.0 and row["commissions"] == -0.65 and row["fees"] == -0.04
        assert row["underlying_symbol"] == "SPY" and row["put_call"] == "CALL" and row["strike_price"] == 580.0
        assert row["strikes_text"] == "580" and row["expiration_date"] == date(2026, 10, 24)
        assert row["trade_date"] == date(2026, 10, 23) and row["position_effect"] == "OPENING"
        assert row["leg_count"] == 1 and len(json.loads(row["legs_json"])) == 1
        assert json.loads(row["raw_json"])["activityId"] == 1001

    def test_vertical_sell_prices_the_spread(self):
        row = normalize_transaction(vertical_sell())
        assert row["structure"] == "Vertical" and row["side"] == "Sell"
        assert row["strikes_text"] == "495/500"          # long leg first, as the statement writes it
        assert row["quantity"] == 2 and row["price"] == 1.2  # (640 - 400) / (2 × 100)
        assert row["leg_cost"] == 240.0 and row["commissions"] == -1.3
        assert row["put_call"] == "PUT" and row["strike_price"] == 495.0
        assert row["description"].startswith("SOLD -2 VERTICAL QQQ 100 24 OCT 26 495/500 PUT @1.2")

    def test_index_root_maps_to_underlying(self):
        raw = single_buy()
        raw["transferItems"][0]["instrument"] = option_instrument("SPXW", date(2026, 10, 24), "PUT", 5040.0, underlying="$SPX")
        row = normalize_transaction(raw)
        assert row["underlying_symbol"] == "SPX" and row["option_symbol"].startswith("SPXW  ")


class TestNormalizeOrder:
    def test_flattens_bracket_children(self):
        rows = normalize_order(oco_order())
        by_id = {r["order_id"]: r for r in rows if r["order_id"] is not None}
        assert set(by_id) == {5001, 5002, 5003}
        assert by_id[5001]["parent_order_id"] is None and by_id[5001]["instruction"] == "BUY_TO_OPEN"
        assert by_id[5002]["parent_order_id"] == 5001 and by_id[5002]["order_type"] == "LIMIT" and by_id[5002]["price"] == 16.0
        assert by_id[5003]["order_type"] == "STOP" and by_id[5003]["stop_price"] == 9.5 and by_id[5003]["status"] == "WORKING"
        assert by_id[5003]["strikes_text"] == "580" and by_id[5003]["expiration_date"] == date(2026, 10, 24)
        assert by_id[5001]["entered_time"] == datetime(2026, 10, 23, 14, 30, 50, tzinfo=timezone.utc)


# ── Fill context math ────────────────────────────────────────────────────────


class TestAtr:
    def test_constant_true_range(self):
        atr, as_of = wilder_atr(candles(40), before=date(2026, 10, 23))
        assert atr == 2.0 and as_of == date(2026, 10, 22)

    def test_excludes_the_trade_day_and_needs_enough_candles(self):
        atr, as_of = wilder_atr(candles(40), before=date(2026, 9, 10))
        assert atr is None and as_of is None
        atr, as_of = wilder_atr(candles(40), before=date(2026, 9, 23))
        assert atr == 2.0 and as_of == date(2026, 9, 22)

    def test_context_values(self):
        fill = datetime(2026, 10, 23, 14, 31, 5, tzinfo=timezone.utc)
        captured = fill + timedelta(minutes=9)
        values = fill_context_values(fill, captured, "SPY", "SPY   261024C00580000",
                                     {"lastPrice": 583.1, "netChange": -1.5, "closePrice": 584.6},
                                     {"bidPrice": 12.2, "askPrice": 12.5, "mark": 12.35, "lastPrice": 12.34, "openInterest": 4100, "totalVolume": 950},
                                     2.0, date(2026, 10, 22))
        assert values["atr_used"] == 0.75 and values["lag_seconds"] == 540
        assert values["spread"] == 0.3 and values["spread_pct_mid"] == round(0.3 / 12.35, 4)
        assert values["open_interest"] == 4100 and values["option_volume"] == 950 and values["kind"] == "live"

    def test_daily_context(self):
        quote, atr, as_of = daily_context_from_candles(candles(40), date(2026, 10, 23))
        assert atr == 2.0 and as_of == date(2026, 10, 22)
        assert quote["lastPrice"] - quote["closePrice"] == pytest.approx(1.0)


class TestMarketHours:
    def test_boundaries(self):
        assert in_market_hours(datetime(2026, 10, 23, 9, 30, tzinfo=NY))
        assert in_market_hours(datetime(2026, 10, 23, 16, 45, tzinfo=NY))
        assert not in_market_hours(datetime(2026, 10, 23, 9, 15, tzinfo=NY))
        assert not in_market_hours(datetime(2026, 10, 23, 17, 0, tzinfo=NY))
        assert not in_market_hours(datetime(2026, 10, 24, 12, 0, tzinfo=NY))  # Saturday

    def test_labels(self, monkeypatch):
        monkeypatch.setattr("app.agents.account_activity_sync.settings.broker_account_labels", "7892=Options, 1234=IRA")
        assert account_labels() == {"7892": "Options", "1234": "IRA"}


# ── Sync against SQLite with a fake provider ─────────────────────────────────

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_sessions = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


class FakeProvider:
    def __init__(self):
        self.transactions = [single_buy(), vertical_sell()]
        self.orders = [oco_order()]
        self.quotes = {
            "SPY": {"quote": {"lastPrice": 583.1, "netChange": -1.5, "closePrice": 584.6}},
            "QQQ": {"quote": {"lastPrice": 498.0, "netChange": 3.0, "closePrice": 495.0}},
            "SPY   261024C00580000": {"quote": {"bidPrice": 12.2, "askPrice": 12.5, "mark": 12.35, "lastPrice": 12.34, "openInterest": 4100, "totalVolume": 950}},
            "QQQ   261024P00495000": {"quote": {"bidPrice": 1.9, "askPrice": 2.1, "mark": 2.0}},
        }
        self.calls = []

    async def get_account_numbers(self):
        self.calls.append("numbers")
        return [{"accountNumber": "24427892", "hashValue": "HASH-OPTIONS"}, {"accountNumber": "99991234", "hashValue": "HASH-IRA"}]

    async def get_transactions(self, account_hash, start, end, types="TRADE", symbol=None):
        self.calls.append(("transactions", account_hash, start, end))
        return self.transactions if account_hash == "HASH-OPTIONS" else []

    async def get_orders(self, account_hash, start, end, max_results=3000, status=None):
        self.calls.append(("orders", account_hash))
        return self.orders if account_hash == "HASH-OPTIONS" else []

    async def get_quotes(self, symbols):
        self.calls.append(("quotes", tuple(symbols)))
        return {s: self.quotes[s] for s in symbols if s in self.quotes}

    async def get_daily_candles(self, symbol, months=3):
        self.calls.append(("candles", symbol))
        return candles(40)

    async def health_check(self):
        return True


@pytest_asyncio.fixture(autouse=True)
async def _db_setup(monkeypatch):
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr("app.agents.account_activity_sync.settings.broker_account_labels", "7892=Options,1234=IRA")
    monkeypatch.setattr("app.agents.account_activity_sync.settings.broker_activity_user_id", None)
    monkeypatch.setattr("app.services.trade_fills.settings.broker_activity_display_tz", "America/Chicago")
    async with _sessions() as db:
        db.add(User(id="user-don", username="don", email="don@example.com", role="admin", is_active=True))
        await db.commit()
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


NOW = datetime(2026, 10, 23, 15, 10, tzinfo=timezone.utc)  # 11:10 ET, nine minutes after the vertical filled


@pytest.mark.asyncio
async def test_first_run_pulls_accounts_fills_orders_and_context():
    provider = FakeProvider()
    sync = AccountActivitySync(provider, now=lambda: NOW)
    async with _sessions() as db:
        result = await sync.run(db)
        assert result.status == "ok", result.message
        assert (result.accounts, result.transactions_new, result.orders_upserted, result.contexts_captured) == (2, 2, 3, 2)

        accounts = {a.label: a for a in (await db.execute(select(BrokerAccount))).scalars().all()}
        assert set(accounts) == {"Options", "IRA"} and accounts["Options"].account_last4 == "7892"
        assert accounts["Options"].user_id == "user-don"

        txns = (await db.execute(select(BrokerTransaction).order_by(BrokerTransaction.time))).scalars().all()
        assert [t.activity_id for t in txns] == [1001, 1002]
        assert txns[0].account_id == accounts["Options"].id and txns[0].time == datetime(2026, 10, 23, 14, 31, 5)

        orders = {o.order_id: o for o in (await db.execute(select(BrokerOrder))).scalars().all()}
        assert orders[5003].parent_order_id == 5001 and float(orders[5003].stop_price) == 9.5

        contexts = {c.transaction_id: c for c in (await db.execute(select(BrokerFillContext))).scalars().all()}
        spy = contexts[txns[0].id]
        assert spy.kind == "live" and float(spy.atr14) == 2.0 and spy.atr_used == 0.75 and float(spy.spread) == 0.3
        qqq = contexts[txns[1].id]
        assert qqq.option_symbol == "QQQ   261024P00495000" and qqq.atr_used == 1.5

        # first run reaches back 59 days, the Trader API's limit
        first_window = next(c for c in provider.calls if isinstance(c, tuple) and c[0] == "transactions")
        assert (NOW - first_window[2]).days == 59

        runs = (await db.execute(select(BrokerSyncRun))).scalars().all()
        assert len(runs) == 1 and runs[0].status == "ok" and runs[0].transactions_new == 2 and runs[0].trigger == "schedule"


@pytest.mark.asyncio
async def test_second_run_adds_nothing_and_updates_order_state():
    provider = FakeProvider()
    sync = AccountActivitySync(provider, now=lambda: NOW)
    async with _sessions() as db:
        await sync.run(db)
    # the target fills, the stop is cancelled, a new fill arrives
    provider.orders[0]["childOrderStrategies"][0]["childOrderStrategies"][0]["status"] = "FILLED"
    provider.orders[0]["childOrderStrategies"][0]["childOrderStrategies"][1]["status"] = "CANCELED"
    provider.transactions.append(single_buy(activity_id=1003, order_id=5002, when="2026-10-23T15:05:00+0000"))
    later = NOW + timedelta(minutes=15)
    sync2 = AccountActivitySync(provider, now=lambda: later)
    async with _sessions() as db:
        result = await sync2.run(db)
        assert result.status == "ok"
        assert result.transactions_new == 1 and result.orders_upserted == 2 and result.contexts_captured == 1
        assert len((await db.execute(select(BrokerTransaction))).scalars().all()) == 3
        orders = {o.order_id: o for o in (await db.execute(select(BrokerOrder))).scalars().all()}
        assert orders[5002].status == "FILLED" and orders[5003].status == "CANCELED"
        # the window starts 3 days before the latest stored fill, not 59 days back
        window = [c for c in provider.calls if isinstance(c, tuple) and c[0] == "transactions"][-2]
        assert window[2] == datetime(2026, 10, 23, 15, 2, 10, tzinfo=timezone.utc) - timedelta(days=3)


@pytest.mark.asyncio
async def test_scheduled_run_stands_down_outside_market_hours():
    provider = FakeProvider()
    evening = datetime(2026, 10, 23, 23, 0, tzinfo=timezone.utc)
    sync = AccountActivitySync(provider, now=lambda: evening)
    async with _sessions() as db:
        assert (await sync.run(db)).status == "skipped"
        assert provider.calls == []
        assert (await sync.run(db, trigger="manual", force=True)).status == "ok"


@pytest.mark.asyncio
async def test_old_fills_get_a_daily_context():
    provider = FakeProvider()
    provider.transactions = [single_buy(activity_id=1010, when="2026-10-15T14:31:05+0000")]
    sync = AccountActivitySync(provider, now=lambda: NOW)
    async with _sessions() as db:
        result = await sync.run(db)
        assert result.contexts_captured == 1
        ctx = (await db.execute(select(BrokerFillContext))).scalars().one()
        assert ctx.kind == "daily" and float(ctx.atr14) == 2.0 and ctx.atr_used == 0.5 and ctx.option_bid is None
        assert not any(c[0] == "quotes" for c in provider.calls if isinstance(c, tuple))


@pytest.mark.asyncio
async def test_no_owner_user_records_an_error_run():
    async with _sessions() as db:
        db.add(User(id="user-two", username="two", email="two@example.com", role="admin", is_active=True))
        await db.commit()
    sync = AccountActivitySync(FakeProvider(), now=lambda: NOW)
    async with _sessions() as db:
        assert await resolve_owner_user_id(db) is None
        result = await sync.run(db)
        assert result.status == "error" and "owner user" in result.message
        run = (await db.execute(select(BrokerSyncRun))).scalars().one()
        assert run.status == "error"


@pytest.mark.asyncio
async def test_fill_rows_match_the_dashboard_shape_and_are_user_scoped():
    sync = AccountActivitySync(FakeProvider(), now=lambda: NOW)
    async with _sessions() as db:
        await sync.run(db)
        result = await list_fill_rows(db, "user-don")
        assert result["count"] == 2 and result["columns"] == FILL_COLUMNS
        first, second = result["rows"]
        assert set(FILL_COLUMNS) <= set(first)
        assert first["row"] == "1" and first["trade_datetime"] == "2026-10-23 09:31:05"   # Chicago wall clock
        assert first["type"] == "Buy" and first["contract_count"] == 1 and first["contract_price"] == 12.34
        assert first["contract_amount"] == -1234.0 and first["total_fees"] == 0.69 and first["net_profit_loss"] == -1234.69
        assert first["account"] == "Options" and first["symbol"] == "SPY" and first["strike"] == "580"
        assert first["trade_hour"] == "09:00" and first["trade_weekday"] == "Friday" and first["day_of_week"] == "5-Fri"
        assert first["trade_week_start"] == "2026-10-19" and first["atr_used"] == 0.75 and first["spread_pct_mid"] == round(0.3 / 12.35, 4)
        assert second["type"] == "Sell" and second["contract_count"] == -2 and second["structure"] == "Vertical"
        assert second["long_strike"] == 495.0 and second["short_strike"] == 500.0 and second["net_profit_loss"] == 238.7
        assert (await list_fill_rows(db, "someone-else"))["count"] == 0
        assert (await list_fill_rows(db, "user-don", start=date(2026, 10, 24)))["count"] == 0
        assert (await list_fill_rows(db, "user-don", account="IRA"))["count"] == 0


def test_fill_row_handles_missing_context():
    txn = BrokerTransaction(id=9, activity_id=1, order_id=None, time=datetime(2026, 10, 23, 14, 31, 5), trade_date=date(2026, 10, 23),
                            side="Sell", quantity=3, price=0.5, leg_cost=150.0, commissions=-1.95, fees=-0.1, put_call="PUT",
                            strikes_text="500", underlying_symbol="QQQ", structure="Single", expiration_date=date(2026, 10, 24))
    row = fill_row(txn, None, "IRA", "America/Chicago")
    assert row["reference_number"] == "" and row["atr_used"] is None and row["context_kind"] == ""
    assert row["contract_count"] == -3 and row["net_profit_loss"] == 147.95 and row["sell_amount"] == 150.0
