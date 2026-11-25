"""simple_atr (OTA-858): D ATR = simple average of the last 14 completed daily true ranges."""

import csv
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.broker_activity import simple_atr, wilder_atr


def stamp(day):
    return int(datetime(day.year, day.month, day.day, 6, tzinfo=timezone.utc).timestamp() * 1000)


def weekdays(start, n):
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def flat(days, rng=2.0, start=date(2026, 9, 1), base=100.0):
    """Each day opens at the prior close, trades base..base+rng, closes mid-range: true range = rng."""
    out, close = [], base
    for day in weekdays(start, days):
        out.append({"open": close, "high": close + rng, "low": close, "close": close + rng / 2, "volume": 1, "datetime": stamp(day)})
        close += rng / 2
    return out


def test_constant_true_range_matches_wilder():
    candles = flat(40)
    last = weekdays(date(2026, 9, 1), 40)[-1]
    atr, as_of = simple_atr(candles, before=last + timedelta(days=1))
    assert atr == 2.0 and as_of == last
    assert wilder_atr(candles, before=last + timedelta(days=1))[0] == 2.0


def test_only_the_last_14_true_ranges_count():
    candles = flat(30, rng=1.0) + flat(15, rng=3.0, start=date(2026, 11, 1), base=200.0)
    # The first of the late candles gaps from the early run's close, so its true range is large;
    # the 14 after it are exactly 3.0.
    atr, as_of = simple_atr(candles, before=date(2026, 12, 1))
    assert atr == 3.0 and as_of == weekdays(date(2026, 11, 1), 15)[-1]
    wilder, _ = wilder_atr(candles, before=date(2026, 12, 1))
    assert wilder != 3.0          # Wilder still carries the older, smaller ranges


def test_gap_counts_in_the_true_range():
    days = weekdays(date(2026, 11, 2), 15)
    candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "datetime": stamp(d)} for d in days[:-1]]
    candles.append({"open": 105, "high": 107, "low": 105, "close": 106, "datetime": stamp(days[-1])})   # gap up from 100
    atr, _ = simple_atr(candles, before=days[-1] + timedelta(days=1))
    assert atr == round((13 * 2 + 7) / 14, 4)     # 13 days of 2.0, then max(107, 100) - min(105, 100) = 7


def test_trade_day_excluded_and_enough_candles_needed():
    candles = flat(20)
    days = weekdays(date(2026, 9, 1), 20)
    atr, as_of = simple_atr(candles, before=days[15])          # 15 candles before: exactly enough
    assert atr == 2.0 and as_of == days[14]
    assert simple_atr(candles, before=days[14]) == (None, None)   # 14 candles: not enough
    assert simple_atr([], before=days[0]) == (None, None)


BARS_1D = os.environ.get("OTA_BARS_1D")


@pytest.mark.skipif(not BARS_1D, reason="set OTA_BARS_1D to the OTA-859 daily bar file to run")
def test_iwm_pair_on_11_24():
    candles = []
    with open(BARS_1D, newline="") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].startswith("#")]
    header, body = rows[0], rows[1:]
    for r in (dict(zip(header, row)) for row in body):
        if r["symbol"] != "IWM":
            continue
        t = datetime.strptime(r["bar_start_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        candles.append({"datetime": int(t.timestamp() * 1000), "high": r["high"], "low": r["low"], "close": r["close"],
                        "session_date": date.fromisoformat(r["session_date"])})
    trade_day = date(2026, 11, 25)
    simple, as_of = simple_atr(candles, before=trade_day)
    assert as_of == date(2026, 11, 24) and round(simple, 2) == 6.61
    three_months = [c for c in candles if c["session_date"] >= date(2026, 8, 25)]
    assert round(wilder_atr(three_months, before=trade_day)[0], 2) == 5.63
