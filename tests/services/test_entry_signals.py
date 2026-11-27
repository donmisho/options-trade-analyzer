"""Entry signal rules: VWAP, 15-minute trend, 5-minute push, volume, ATR room, contract pick."""

from datetime import datetime, timedelta, timezone

from app.services.entry_signals import (
    EntryRules, evaluate_underlying, pick_contract, session_vwap, spread_pct, trend_15m,
)

UTC = timezone.utc
OPEN = datetime(2026, 11, 24, 14, 30, tzinfo=UTC)   # 09:30 New York
ATR = 4.0
PREV_CLOSE = 100.0


def minute(i, open_, close, volume=100):
    return {"datetime": int((OPEN + timedelta(minutes=i)).timestamp() * 1000), "open": open_,
            "high": max(open_, close) + 0.01, "low": min(open_, close) - 0.01, "close": close, "volume": volume}


def session(push=0.5, push_volume=300, drift=0.01, minutes=40):
    """A slow drift from 100.00, then the 10:05 to 10:10 five-minute bar moves `push` on `push_volume` a minute."""
    bars, price = [], 100.0
    for i in range(minutes - 5):
        bars.append(minute(i, price, price + drift))
        price += drift
    for i in range(minutes - 5, minutes):
        bars.append(minute(i, price, price + push / 5, push_volume))
        price += push / 5
    return bars


NOW = OPEN + timedelta(minutes=40, seconds=10)   # 10:10:10, the push bar has just completed


def test_vwap_weights_by_volume():
    bars = [minute(0, 10, 10, 100), minute(1, 20, 20, 300)]
    assert round(session_vwap(bars), 4) == 17.5
    assert session_vwap([minute(0, 10, 10, 0)]) is None


def test_trend_needs_two_bars_and_agreement():
    up = {"open": 1, "close": 2}
    assert trend_15m([up]) is None
    assert trend_15m([{"open": 1, "close": 1.5}, up]) == "up"
    assert trend_15m([{"open": 3, "close": 2.5}, {"open": 2.4, "close": 2.0}]) == "down"
    assert trend_15m([{"open": 3, "close": 2.5}, up]) == "flat"      # closed up but under the prior close


def test_ready_call_when_every_gate_passes():
    out = evaluate_underlying(session(), ATR, PREV_CLOSE, NOW)
    assert out["status"] == "ready" and out["direction"] == "call"
    assert out["push"] == 0.5 and out["push_pct_atr"] == 12.5 and out["push_strong"] is False
    assert out["volume_ratio"] == 3.0
    assert out["push_bar_utc"] == OPEN + timedelta(minutes=35)
    assert out["price"] > out["vwap"] and out["trend_15m"] == "up"
    assert out["atr_used_pct"] < 70
    assert (out["gate_trend"], out["gate_push"], out["gate_volume"], out["gate_room"]) == (True, True, True, True)


def test_ready_put_on_a_down_session():
    out = evaluate_underlying(session(push=-0.7, drift=-0.01), ATR, PREV_CLOSE, NOW)
    assert out["status"] == "ready" and out["direction"] == "put"
    assert out["push_strong"] is True and out["trend_15m"] == "down"


def test_watch_when_trend_and_room_pass_without_a_push():
    out = evaluate_underlying(session(push=0.1, push_volume=100), ATR, PREV_CLOSE, NOW)
    assert out["status"] == "watch" and out["direction"] == "call"
    assert out["gate_push"] is False and out["gate_trend"] is True


def test_push_without_volume_is_not_ready():
    out = evaluate_underlying(session(push_volume=120), ATR, PREV_CLOSE, NOW)
    assert out["gate_push"] is True and out["gate_volume"] is False and out["status"] == "watch"


def test_push_against_the_trend_fails_the_trend_gate():
    out = evaluate_underlying(session(push=-0.5), ATR, PREV_CLOSE, NOW)   # up drift, down push
    assert out["direction"] == "put" and out["gate_push"] is True
    assert out["gate_trend"] is False and out["status"] == "idle"


def test_no_room_once_the_day_has_used_the_atr():
    out = evaluate_underlying(session(), ATR, PREV_CLOSE - 3.0, NOW)       # already up over 3 of a 4 ATR
    assert out["gate_room"] is False and out["atr_used_pct"] > 70 and out["status"] == "idle"


def test_the_forming_five_minute_bar_is_not_the_push_bar():
    out = evaluate_underlying(session(), ATR, PREV_CLOSE, OPEN + timedelta(minutes=39, seconds=10))
    assert out["push_bar_utc"] == OPEN + timedelta(minutes=30)
    assert out["gate_push"] is False


def test_no_data_cases():
    assert evaluate_underlying([], ATR, PREV_CLOSE, NOW)["status"] == "no_data"
    assert evaluate_underlying(session(), None, PREV_CLOSE, NOW)["message"] == "no daily ATR"
    early = evaluate_underlying(session(minutes=20), ATR, PREV_CLOSE, OPEN + timedelta(minutes=20, seconds=10))
    assert early["status"] == "no_data" and early["message"] == "waiting for two completed 15-minute bars"


def contract(dte, delta, bid, ask, option_type="call", strike=100):
    return {"symbol": f"X{dte}{option_type[0]}{strike}", "expiration": "2026-12-01", "dte": dte, "strike": strike,
            "option_type": option_type, "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "delta": delta}


def test_spread_pct():
    assert round(spread_pct({"bid": 1.98, "ask": 2.02}), 2) == 2.0
    assert spread_pct({"bid": 0, "ask": 2.0}) is None


def test_pick_prefers_the_preferred_dte_band_then_delta():
    chain = [
        contract(3, 0.55, 1.99, 2.01),            # fits, outside the preferred band
        contract(7, 0.62, 2.99, 3.01),            # preferred band, delta further from 0.55
        contract(8, 0.56, 3.49, 3.51),            # preferred band, delta nearest
        contract(7, 0.55, 2.00, 2.30),            # spread too wide
        contract(7, -0.55, 2.99, 3.01, "put"),    # wrong side
        contract(20, 0.55, 4.99, 5.01),           # too far out
    ]
    picked, why = pick_contract(chain, "call")
    assert why == "" and picked["dte"] == 8 and picked["spread_pct"] == 0.57
    put, _ = pick_contract(chain, "put")
    assert put["option_type"] == "put"


def test_pick_says_why_nothing_fits():
    assert pick_contract([contract(20, 0.55, 1.99, 2.01)], "call")[1] == "no call between 2 and 14 DTE"
    assert pick_contract([contract(7, 0.30, 1.99, 2.01)], "call")[1] == "no call with delta 0.45 to 0.65"
    assert pick_contract([contract(7, 0.55, 2.00, 2.30)], "call")[1] == "no call with a spread within 3% of the mid"
    assert pick_contract([contract(7, 0.55, 2.00, 2.30)], "call", EntryRules(spread_max_pct=20))[0] is not None
