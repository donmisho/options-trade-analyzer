"""
Market context helpers for export MD v2.

Provides VIX percentile, index trend/SMA helpers, and the deterministic
regime-note grid.  All quote reads go through the provider passed by the
caller — never import a concrete provider here.

VIX history: fetched on-demand via provider.get_price_history("$VIX", 12)
which returns ~252 daily candles (one trading year).  No persistence table
is needed; the provider API is the source of truth.

Schwab apiSymbol mapping:
  VIX -> "$VIX"   (index)
  SPY -> "SPY"    (ETF, no prefix)
  QQQ -> "QQQ"    (ETF, no prefix)
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Schwab apiSymbol for the VIX index
VIX_API_SYMBOL = "$VIX"


# ---------------------------------------------------------------------------
# VIX 52-week percentile
# ---------------------------------------------------------------------------

async def get_vix_series(provider, months: int = 12) -> list[float]:
    """Fetch daily VIX closes for *months* months via the provider.

    Returns a list of close prices ordered oldest-to-newest.
    Empty list on provider error (caller decides how to degrade).
    """
    candles = await provider.get_price_history(VIX_API_SYMBOL, num_periods=months)
    return [c["close"] for c in candles if "close" in c]


def vix_percentile_52w(current_close: float, series: list[float]) -> int:
    """Compute the percentile rank of *current_close* within *series*.

    Percentile = (# of observations < current_close) / len(series) * 100,
    clamped to 0–100 integer.

    If *series* is empty, returns 50 as a neutral fallback.
    """
    if not series:
        return 50
    below = sum(1 for v in series if v < current_close)
    pct = below / len(series) * 100
    return max(0, min(100, round(pct)))


# ---------------------------------------------------------------------------
# 5-day trend
# ---------------------------------------------------------------------------

def five_day_trend(candles: list[dict]) -> tuple[str, float]:
    """Classify the 5-trading-day trend from a candle series.

    *candles* must be ordered oldest-to-newest and contain at least 6 entries
    (today + 5 prior days).  Each entry must have a ``"close"`` key.

    Returns ``(label, signed_pct)`` where label is "flat", "up", or "down"
    and signed_pct has one-decimal precision.

    Rule (OTA-640):
        pct = (spot_today - spot_5d_ago) / spot_5d_ago * 100
        |pct| <= 0.5  -> "flat"
        pct > 0       -> "up"
        pct < 0       -> "down"
    """
    if len(candles) < 6:
        return ("flat", 0.0)
    spot_today = candles[-1]["close"]
    spot_5d = candles[-6]["close"]
    if spot_5d == 0:
        return ("flat", 0.0)
    pct = (spot_today - spot_5d) / spot_5d * 100
    pct = round(pct, 1)
    if abs(pct) <= 0.5:
        label = "flat"
    elif pct > 0:
        label = "up"
    else:
        label = "down"
    return (label, pct)


# ---------------------------------------------------------------------------
# Distance from 50-day SMA
# ---------------------------------------------------------------------------

def distance_from_50d(spot: float, candles: list[dict]) -> tuple[float, str]:
    """Compute distance of *spot* from the 50-day SMA.

    *candles* ordered oldest-to-newest, each with a ``"close"`` key.
    Uses the last 50 entries to compute SMA-50.

    Returns ``(signed_pct, direction)`` where direction is "above" or "below"
    and signed_pct has one-decimal precision.

    Rule (OTA-640):
        dist_pct = (spot - sma_50) / sma_50 * 100
        direction = "above" if dist_pct >= 0 else "below"
    """
    if len(candles) < 50:
        sma = sum(c["close"] for c in candles) / len(candles) if candles else spot
    else:
        sma = sum(c["close"] for c in candles[-50:]) / 50
    if sma == 0:
        return (0.0, "above")
    dist = (spot - sma) / sma * 100
    dist = round(dist, 1)
    direction = "above" if dist >= 0 else "below"
    return (dist, direction)


# ---------------------------------------------------------------------------
# Regime note — deterministic 9-cell grid (no Claude call)
# ---------------------------------------------------------------------------

# OTA-640 rule grid.  See business-rules.md "Regime Classification".
_REGIME_GRID: list[tuple] = [
    # (vix_lo, vix_hi, ivr_lo, ivr_hi, note)
    (0,  15, 0,   30, "Low-vol, range-bound. Premium selling favorable; long premium expensive."),
    (0,  15, 30,  60, "Low-vol broad market with elevated single-name IV. Mixed signal."),
    (0,  15, 60, 101, "Low-vol broad market, single-name IV elevated. Skew favors premium sellers on this name."),
    (15, 20, 0,   30, "Low-vol, mildly choppy. VIX below 20 makes long premium expensive relative to expected move."),
    (15, 20, 30,  60, "Moderate-vol. Standard premium pricing."),
    (15, 20, 60, 101, "Moderate-vol broad market with elevated single-name IV."),
    (20, 25, 0,  101, "Elevated vol regime. Watch for IV crush on event-driven positions."),
    (25, 30, 0,  101, "High-vol regime. Premium selling rich; debit spreads compressed."),
    (30, 999, 0, 101, "Crisis vol regime. Sizing and stops both warrant tightening."),
]


def regime_note(vix_value: float, underlying_ivr_pct: float) -> str:
    """Return a deterministic one-liner for the current regime.

    *vix_value*: current VIX level (e.g. 18.40).
    *underlying_ivr_pct*: underlying's IV Rank as a percentage 0–100
                          (e.g. 22.7 means 22.7%).

    Grid boundaries are half-open: [lo, hi).  VIX >= 30 catches crisis.
    IVR > 60 catches the "elevated" bucket; 101 upper bound is a sentinel.
    """
    for vix_lo, vix_hi, ivr_lo, ivr_hi, note in _REGIME_GRID:
        if vix_lo <= vix_value < vix_hi and ivr_lo <= underlying_ivr_pct < ivr_hi:
            return note
    return "Regime undetermined."
