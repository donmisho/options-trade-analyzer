"""
Underlying price bars — pure helpers (OTA-859).

Request windows, New York session tagging, the forming-bar rule and 1-minute to
N-minute aggregation for Schwab /pricehistory bars. No I/O and no settings here:
the pull route and, later, the bar sync job (slice 2) pass everything in.

Bars are in the provider's shape: {"datetime": epoch ms (bar start), "open",
"high", "low", "close", "volume"}.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional

from app.services.broker_activity import MARKET_TZ, zone

FREQUENCIES = ("1m", "5m", "1d")

# Calendar days per /pricehistory request. Schwab does not document a per-call cap,
# so the windows are deliberately small.
_WINDOW_DAYS = {"1m": 10, "5m": 90}

_OPEN = time(9, 30)
_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)
_BAR_LENGTH = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5)}


def _ny():
    return zone(MARKET_TZ)


def _localize(day: date, at: time) -> datetime:
    """A New York wall-clock time on `day` as an aware datetime (pytz-safe)."""
    tz = _ny()
    naive = datetime.combine(day, at)
    if hasattr(tz, "localize"):  # pytz fallback on a Windows box without tzdata
        return tz.localize(naive)
    return naive.replace(tzinfo=tz)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def symbol_list(text: Optional[str]) -> list[str]:
    """Comma list → upper-case symbols, blanks dropped, first occurrence kept, order kept."""
    out: list[str] = []
    for part in (text or "").split(","):
        sym = part.strip().upper()
        if sym and sym not in out:
            out.append(sym)
    return out


def early_close_dates(text: Optional[str]) -> frozenset:
    """Comma list of ISO dates → frozenset of dates. Bad entries are ignored."""
    days = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            days.add(date.fromisoformat(part))
        except ValueError:
            continue
    return frozenset(days)


def to_utc(epoch_ms) -> datetime:
    return datetime.fromtimestamp(int(epoch_ms) / 1000.0, tz=timezone.utc)


def iso_utc(moment: datetime) -> str:
    return _aware(moment).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny_date(moment: datetime) -> date:
    return _aware(moment).astimezone(_ny()).date()


def session_close(day: date, early_closes: frozenset = frozenset()) -> time:
    return _EARLY_CLOSE if day in early_closes else _CLOSE


def bar_windows(frequency: str, start: date, end: date) -> list[tuple[datetime, datetime]]:
    """
    Request windows covering New York dates start..end inclusive, as UTC datetimes.
    Each runs from 00:00:00 New York on its first date to 23:59:59.999 New York on
    its last. 10 calendar days per window for 1m, 90 for 5m, one window for 1d.
    """
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {FREQUENCIES}")
    if start > end:
        raise ValueError("start is after end")
    span = _WINDOW_DAYS.get(frequency, (end - start).days + 1)
    windows = []
    first = start
    while first <= end:
        last = min(first + timedelta(days=span - 1), end)
        w_start = _localize(first, time(0, 0)).astimezone(timezone.utc)
        w_end = (_localize(last + timedelta(days=1), time(0, 0)) - timedelta(milliseconds=1)).astimezone(timezone.utc)
        windows.append((w_start, w_end))
        first = last + timedelta(days=1)
    return windows


def bar_session(bar_start_utc: datetime, early_closes: frozenset = frozenset()) -> tuple[date, str]:
    """New York date and 'pre', 'reg' or 'post' for an intraday bar start."""
    local = _aware(bar_start_utc).astimezone(_ny())
    day = local.date()
    clock = local.time().replace(tzinfo=None)
    if clock < _OPEN:
        return day, "pre"
    if clock < session_close(day, early_closes):
        return day, "reg"
    return day, "post"


def complete(bar_start_utc: datetime, frequency: str, now: datetime, early_closes: frozenset = frozenset()) -> bool:
    """False for the bar still forming."""
    bar_start_utc = _aware(bar_start_utc)
    now = _aware(now)
    if frequency in _BAR_LENGTH:
        return bar_start_utc + _BAR_LENGTH[frequency] <= now
    if frequency == "1d":
        day = ny_date(bar_start_utc)
        today = ny_date(now)
        if day < today:
            return True
        if day > today:
            return False
        return now >= _localize(day, session_close(day, early_closes))
    raise ValueError(f"frequency must be one of {FREQUENCIES}")


def aggregate(bars_1m: Iterable[dict], minutes: int = 5) -> list[dict]:
    """
    N-minute bars from 1-minute bars. Buckets are New York date plus
    floor(minute_of_day / N) * N, so 5-minute buckets align to 09:30. Bars from
    different dates never merge. Output oldest first.
    """
    buckets: dict = {}
    for bar in sorted(bars_1m, key=lambda b: int(b["datetime"])):
        local = to_utc(bar["datetime"]).astimezone(_ny())
        minute_of_day = local.hour * 60 + local.minute
        start_minute = (minute_of_day // minutes) * minutes
        key = (local.date(), start_minute)
        if key not in buckets:
            bucket_start = _localize(local.date(), time(start_minute // 60, start_minute % 60))
            buckets[key] = {
                "datetime": int(bucket_start.astimezone(timezone.utc).timestamp() * 1000),
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": int(bar.get("volume") or 0),
            }
        else:
            agg = buckets[key]
            agg["high"] = max(agg["high"], bar["high"])
            agg["low"] = min(agg["low"], bar["low"])
            agg["close"] = bar["close"]
            agg["volume"] += int(bar.get("volume") or 0)
    return [buckets[k] for k in sorted(buckets)]
