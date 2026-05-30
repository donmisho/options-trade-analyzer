"""
Shared SMA signal computation for OTA adapters.

Canonical home for SMA-8/21/50 calculation and alignment classification.
Moved here in OTA-717 from ``app/analysis/strategy_scorer.py``.

OTA-717
"""

from __future__ import annotations


def compute_sma_signal(candles: list, current_price: float) -> dict:
    """
    Compute SMA-8, SMA-21, SMA-50 from daily close candles and derive alignment.

    candles: list of dicts with at least {"close": float}, ordered oldest -> newest.
    Returns: {"alignment": str, "summary": str, "sma_8": float, "sma_21": float, "sma_50": float}

    Alignment rules:
      BULLISH  -- price > SMA8 > SMA21 > SMA50  (full bull stack)
      BEARISH  -- price < SMA8 < SMA21 < SMA50  (full bear stack)
      MIXED    -- partial alignment (some SMAs bullish, some bearish)
      NEUTRAL  -- insufficient data to compute
    """
    closes = [c["close"] for c in candles if isinstance(c.get("close"), (int, float))]

    def sma(n):
        if len(closes) < n:
            return None
        return sum(closes[-n:]) / n

    s8 = sma(8)
    s21 = sma(21)
    s50 = sma(50)

    if s8 is None or s21 is None or s50 is None or current_price <= 0:
        return {"alignment": "NEUTRAL", "summary": "Insufficient price history for SMA"}

    p = current_price
    if p > s8 > s21 > s50:
        alignment = "BULLISH"
        summary = f"Full bull stack: price {p:.0f} > SMA8 {s8:.0f} > SMA21 {s21:.0f} > SMA50 {s50:.0f}"
    elif p < s8 < s21 < s50:
        alignment = "BEARISH"
        summary = f"Full bear stack: price {p:.0f} < SMA8 {s8:.0f} < SMA21 {s21:.0f} < SMA50 {s50:.0f}"
    else:
        bull_count = sum([p > s8, s8 > s21, s21 > s50])
        alignment = "MIXED"
        summary = f"Mixed ({bull_count}/3 bullish): SMA8 {s8:.0f} | SMA21 {s21:.0f} | SMA50 {s50:.0f}"

    return {"alignment": alignment, "summary": summary, "sma_8": round(s8, 2), "sma_21": round(s21, 2), "sma_50": round(s50, 2)}
