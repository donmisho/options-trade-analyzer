"""
Entry signals for short-dated long options — pure rules, no I/O.

Reads one underlying's 1-minute regular-session bars for today, its daily ATR and
prior close, and says whether the entry conditions hold right now:

  trend   price on the right side of the session VWAP and the 15-minute trend agrees
  push    the last completed 5-minute bar moved at least push_min_pct_atr of the daily ATR
  volume  that bar traded at least volume_ratio_min times the average of the bars before it
  room    the day's net move has used less than atr_used_max_pct of the daily ATR

and, given an option chain, which contract fits (DTE, delta, spread). The signal
monitor (app/agents/signal_monitor.py) feeds it and stores the answer; the
dashboard only displays it.

Bars are in the provider's shape: {"datetime": epoch ms (bar start), "open",
"high", "low", "close", "volume"}.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from app.services.price_bars import aggregate, to_utc


@dataclass(frozen=True)
class EntryRules:
    # 5-minute push as a percent of the daily ATR: the gate, and the level called strong.
    push_min_pct_atr: float = 10.0
    push_strong_pct_atr: float = 15.0
    # Push bar volume against the average of the completed 5-minute bars before it today.
    volume_ratio_min: float = 1.5
    volume_lookback_bars: int = 20
    volume_min_bars: int = 3
    # |price - prior close| as a percent of the daily ATR must stay under this.
    atr_used_max_pct: float = 70.0
    # Contract: days to expiry, the preferred band inside it, delta and spread.
    dte_min: int = 2
    dte_max: int = 14
    dte_pref_min: int = 5
    dte_pref_max: int = 10
    delta_min: float = 0.45
    delta_max: float = 0.65
    spread_max_pct: float = 3.0

    def as_dict(self) -> dict:
        return asdict(self)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _round(value: Optional[float], places: int = 2) -> Optional[float]:
    return None if value is None else round(value, places)


def session_vwap(bars_1m: Iterable[dict]) -> Optional[float]:
    """Volume-weighted average of the typical price (high + low + close) / 3 over the bars."""
    money = volume = 0.0
    for b in bars_1m:
        v = float(b.get("volume") or 0)
        money += (b["high"] + b["low"] + b["close"]) / 3.0 * v
        volume += v
    return money / volume if volume > 0 else None


def completed(bars: list[dict], minutes: int, now: datetime) -> list[dict]:
    """The bars whose full length has passed at `now`."""
    length = timedelta(minutes=minutes)
    return [b for b in bars if to_utc(b["datetime"]) + length <= now]


def trend_15m(bars_15m: list[dict]) -> Optional[str]:
    """
    'up' when the last completed 15-minute bar closed above its open and above the
    close of the bar before it, 'down' for the mirror, otherwise 'flat'. None with
    fewer than two completed bars (before 10:00 New York).
    """
    if len(bars_15m) < 2:
        return None
    prev, last = bars_15m[-2], bars_15m[-1]
    if last["close"] > last["open"] and last["close"] > prev["close"]:
        return "up"
    if last["close"] < last["open"] and last["close"] < prev["close"]:
        return "down"
    return "flat"


def evaluate_underlying(bars_1m: list[dict], atr: Optional[float], prev_close: Optional[float],
                        now: datetime, rules: EntryRules = EntryRules()) -> dict:
    """
    The underlying's side of the entry: measures, the four gates and a status.

    status: 'ready' (all four gates pass), 'watch' (trend and room pass, no push
    yet), 'idle', or 'no_data' when something needed is missing (see message).
    direction is 'call' or 'put': the push bar's side once it qualifies, otherwise
    the side the trend points to. A gate is None when it cannot be judged.
    """
    now = _aware(now)
    bars = sorted(completed(bars_1m, 1, now), key=lambda b: int(b["datetime"]))
    out = {
        "status": "no_data", "direction": None, "message": None,
        "price": None, "last_bar_utc": None, "vwap": None, "trend_15m": None,
        "push_bar_utc": None, "push": None, "push_pct_atr": None, "push_strong": None, "volume_ratio": None,
        "atr": _round(atr, 4), "prev_close": prev_close, "net_change": None,
        "atr_used_pct": None, "range_used_pct": None,
        "gate_trend": None, "gate_push": None, "gate_volume": None, "gate_room": None,
    }
    if not bars:
        out["message"] = "no completed 1-minute bars today"
        return out
    if not atr or atr <= 0:
        out["message"] = "no daily ATR"
        return out

    price = bars[-1]["close"]
    vwap = session_vwap(bars)
    fives = completed(aggregate(bars, 5), 5, now)
    trend = trend_15m(completed(aggregate(bars, 15), 15, now))
    out.update({
        "price": price, "last_bar_utc": to_utc(bars[-1]["datetime"]), "vwap": _round(vwap, 4), "trend_15m": trend,
        "range_used_pct": _round((max(b["high"] for b in bars) - min(b["low"] for b in bars)) / atr * 100, 1),
    })
    if prev_close:
        out["net_change"] = _round(price - prev_close, 4)
        out["atr_used_pct"] = _round(abs(price - prev_close) / atr * 100, 1)
        out["gate_room"] = out["atr_used_pct"] < rules.atr_used_max_pct

    push_side = None
    if fives:
        bar = fives[-1]
        push = bar["close"] - bar["open"]
        pct = abs(push) / atr * 100
        out.update({
            "push_bar_utc": to_utc(bar["datetime"]), "push": _round(push, 4), "push_pct_atr": _round(pct, 1),
            "push_strong": pct >= rules.push_strong_pct_atr, "gate_push": pct >= rules.push_min_pct_atr,
        })
        if out["gate_push"]:
            push_side = "call" if push > 0 else "put"
        before = fives[:-1][-rules.volume_lookback_bars:]
        if len(before) >= rules.volume_min_bars:
            average = sum(b["volume"] for b in before) / len(before)
            if average > 0:
                out["volume_ratio"] = _round(bar["volume"] / average, 2)
                out["gate_volume"] = out["volume_ratio"] >= rules.volume_ratio_min

    trend_side = None
    if vwap is not None and trend in ("up", "down"):
        if trend == "up" and price > vwap:
            trend_side = "call"
        elif trend == "down" and price < vwap:
            trend_side = "put"
    direction = push_side or trend_side
    out["direction"] = direction
    if vwap is not None and trend is not None:
        out["gate_trend"] = direction is not None and trend_side == direction

    gates = (out["gate_trend"], out["gate_push"], out["gate_volume"], out["gate_room"])
    if all(g is True for g in gates):
        out["status"] = "ready"
    elif out["gate_trend"] is None or out["gate_room"] is None:
        out["message"] = ("waiting for two completed 15-minute bars" if trend is None
                          else "no prior close" if out["gate_room"] is None else "no volume for VWAP")
    elif out["gate_trend"] and out["gate_room"]:
        out["status"] = "watch"
    else:
        out["status"] = "idle"
    return out


def spread_pct(contract: dict) -> Optional[float]:
    """Bid-ask width as a percent of the mid; None without a two-sided quote."""
    bid, ask = contract.get("bid") or 0, contract.get("ask") or 0
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (ask - bid) / ((ask + bid) / 2) * 100


def pick_contract(contracts: Iterable[dict], direction: str, rules: EntryRules = EntryRules()) -> tuple[Optional[dict], str]:
    """
    The contract to buy for `direction` ('call' or 'put') from provider chain rows
    ({symbol, expiration, dte, strike, option_type, bid, ask, mid, delta}).

    Keeps contracts inside the DTE band, the delta band and the spread gate, then
    prefers the preferred DTE band, the delta nearest the middle of its band, and
    the tighter spread. Returns (contract with spread_pct added, '') or
    (None, why nothing fit).
    """
    target = (rules.delta_min + rules.delta_max) / 2
    in_dte = in_delta = 0
    fits = []
    for c in contracts:
        if c.get("option_type") != direction:
            continue
        dte, delta = c.get("dte"), c.get("delta")
        if dte is None or not (rules.dte_min <= dte <= rules.dte_max):
            continue
        in_dte += 1
        if delta is None or not (rules.delta_min <= abs(delta) <= rules.delta_max):
            continue
        in_delta += 1
        width = spread_pct(c)
        if width is None or width > rules.spread_max_pct:
            continue
        preferred = rules.dte_pref_min <= dte <= rules.dte_pref_max
        fits.append(((0 if preferred else 1, round(abs(abs(delta) - target), 4), width), {**c, "spread_pct": round(width, 2)}))
    if fits:
        fits.sort(key=lambda f: f[0])
        return fits[0][1], ""
    if not in_dte:
        return None, f"no {direction} between {rules.dte_min} and {rules.dte_max} DTE"
    if not in_delta:
        return None, f"no {direction} with delta {rules.delta_min} to {rules.delta_max}"
    return None, f"no {direction} with a spread within {rules.spread_max_pct:g}% of the mid"
