"""Price bar helpers (OTA-859): windows, session tags, the forming-bar rule, aggregation."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.price_bars import (
    aggregate, bar_session, bar_windows, complete, early_close_dates, iso_utc, symbol_list, to_utc,
)

UTC = timezone.utc
EARLY = frozenset({date(2026, 11, 27), date(2026, 12, 24)})


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def ms(moment):
    return int(moment.timestamp() * 1000)


class TestWindows:
    def test_one_minute_windows_are_ten_days_and_contiguous(self):
        windows = bar_windows("1m", date(2026, 10, 6), date(2026, 11, 25))
        assert len(windows) == 6
        assert windows[0][0] == utc(2026, 10, 6, 4, 0)                      # New York midnight, EDT
        assert windows[-1][1] == utc(2026, 11, 26, 4, 59, 59, 999000)       # 23:59:59.999 EST on 11/25
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
            assert next_start - prev_end == timedelta(milliseconds=1)

    def test_five_minute_and_daily(self):
        assert len(bar_windows("5m", date(2026, 2, 18), date(2026, 11, 25))) == 4
        daily = bar_windows("1d", date(2024, 10, 26), date(2026, 11, 25))
        assert len(daily) == 1 and daily[0][0] == utc(2024, 10, 26, 4, 0)

    def test_single_day(self):
        windows = bar_windows("1m", date(2026, 11, 25), date(2026, 11, 25))
        assert windows == [(utc(2026, 11, 25, 5, 0), utc(2026, 11, 26, 4, 59, 59, 999000))]

    def test_bad_input(self):
        with pytest.raises(ValueError):
            bar_windows("15m", date(2026, 11, 1), date(2026, 11, 2))
        with pytest.raises(ValueError):
            bar_windows("1m", date(2026, 11, 3), date(2026, 11, 2))


class TestSession:
    def test_across_the_november_change(self):
        assert bar_session(utc(2026, 10, 30, 13, 30)) == (date(2026, 10, 30), "reg")   # 09:30 EDT
        assert bar_session(utc(2026, 10, 30, 13, 29)) == (date(2026, 10, 30), "pre")
        assert bar_session(utc(2026, 11, 2, 13, 30)) == (date(2026, 11, 2), "pre")     # 08:30 EST
        assert bar_session(utc(2026, 11, 2, 14, 30)) == (date(2026, 11, 2), "reg")     # 09:30 EST
        assert bar_session(utc(2026, 11, 2, 20, 59)) == (date(2026, 11, 2), "reg")     # 15:59 EST
        assert bar_session(utc(2026, 11, 2, 21, 0)) == (date(2026, 11, 2), "post")     # 16:00 EST

    def test_across_the_march_change(self):
        assert bar_session(utc(2026, 3, 6, 14, 30)) == (date(2026, 3, 6), "reg")       # 09:30 EST
        assert bar_session(utc(2026, 3, 9, 13, 30)) == (date(2026, 3, 9), "reg")       # 09:30 EDT

    def test_early_close(self):
        assert bar_session(utc(2026, 11, 27, 17, 59), EARLY) == (date(2026, 11, 27), "reg")   # 12:59 EST
        assert bar_session(utc(2026, 11, 27, 18, 0), EARLY) == (date(2026, 11, 27), "post")   # 13:00 EST
        assert bar_session(utc(2026, 11, 27, 18, 0)) == (date(2026, 11, 27), "reg")          # not listed

    def test_evening_bar_keeps_its_new_york_date(self):
        assert bar_session(utc(2026, 11, 25, 0, 30)) == (date(2026, 11, 24), "post")    # 19:30 EST on 11/24


class TestComplete:
    def test_intraday(self):
        start = utc(2026, 11, 25, 15, 0)
        assert not complete(start, "1m", start + timedelta(seconds=59))
        assert complete(start, "1m", start + timedelta(seconds=60))
        assert not complete(start, "5m", start + timedelta(minutes=4, seconds=59))
        assert complete(start, "5m", start + timedelta(minutes=5))

    def test_daily(self):
        today_bar = utc(2026, 11, 25, 6, 0)   # Schwab stamps daily bars near midnight Central
        assert not complete(today_bar, "1d", utc(2026, 11, 25, 20, 59))
        assert complete(today_bar, "1d", utc(2026, 11, 25, 21, 0))
        assert complete(utc(2026, 11, 24, 6, 0), "1d", utc(2026, 11, 25, 15, 0))
        half_day = utc(2026, 11, 27, 6, 0)
        assert not complete(half_day, "1d", utc(2026, 11, 27, 17, 59), EARLY)
        assert complete(half_day, "1d", utc(2026, 11, 27, 18, 0), EARLY)

    def test_bad_frequency(self):
        with pytest.raises(ValueError):
            complete(utc(2026, 11, 25, 15, 0), "15m", utc(2026, 11, 25, 16, 0))


def one_minute(start, n, base=100.0):
    out = []
    for i in range(n):
        t = start + timedelta(minutes=i)
        o = base + i
        out.append({"datetime": ms(t), "open": o, "high": o + 2, "low": o - 1, "close": o + 1, "volume": 10 + i})
    return out


class TestAggregate:
    def test_ten_minutes_make_two_bars(self):
        bars = aggregate(one_minute(utc(2026, 11, 24, 14, 30), 10))   # 09:30 EST
        assert len(bars) == 2
        first, second = bars
        assert first == {"datetime": ms(utc(2026, 11, 24, 14, 30)), "open": 100.0, "high": 106.0,
                         "low": 99.0, "close": 105.0, "volume": 10 + 11 + 12 + 13 + 14}
        assert second["datetime"] == ms(utc(2026, 11, 24, 14, 35))
        assert second["open"] == 105.0 and second["close"] == 110.0 and second["volume"] == 15 + 16 + 17 + 18 + 19

    def test_bucket_edges_and_dates(self):
        bars = one_minute(utc(2026, 11, 24, 14, 34), 2) + one_minute(utc(2026, 11, 25, 14, 34), 1)
        out = aggregate(bars)
        assert [b["datetime"] for b in out] == [
            ms(utc(2026, 11, 24, 14, 30)), ms(utc(2026, 11, 24, 14, 35)), ms(utc(2026, 11, 25, 14, 30)),
        ]

    def test_unsorted_input(self):
        bars = one_minute(utc(2026, 11, 24, 14, 30), 5)
        assert aggregate(list(reversed(bars))) == aggregate(bars)


class TestParsers:
    def test_symbol_list(self):
        assert symbol_list(" iwm, SPY,,qqq ,IWM ") == ["IWM", "SPY", "QQQ"]
        assert symbol_list(None) == []

    def test_early_close_dates(self):
        assert early_close_dates("2026-11-27, 2026-12-24,bad,") == EARLY

    def test_time_helpers(self):
        moment = utc(2026, 11, 25, 14, 30)
        assert to_utc(ms(moment)) == moment
        assert iso_utc(moment) == "2026-11-25T14:30:00Z"
