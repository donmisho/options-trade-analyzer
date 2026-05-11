"""
Tests for app.services.market_context helpers.

Covers:
  - vix_percentile_52w  (edge cases + typical)
  - five_day_trend      (flat / up / down / short series)
  - distance_from_50d   (above / below / short series)
  - regime_note         (all 9 cells of the VIX x IVR grid)
"""

import pytest
from app.services.market_context import (
    vix_percentile_52w,
    five_day_trend,
    distance_from_50d,
    regime_note,
)


# ---------------------------------------------------------------------------
# vix_percentile_52w
# ---------------------------------------------------------------------------

class TestVixPercentile:
    def test_middle_of_range(self):
        series = list(range(10, 40))  # 10..39
        # 20 is above 10 values (10..19) out of 30 -> 33%
        assert vix_percentile_52w(20, series) == 33

    def test_at_minimum(self):
        series = [15.0, 18.0, 20.0, 25.0, 30.0]
        # 15.0: nothing below -> 0%
        assert vix_percentile_52w(15.0, series) == 0

    def test_at_maximum(self):
        series = [15.0, 18.0, 20.0, 25.0, 30.0]
        # 30.0: 4 below -> 4/5*100 = 80%
        assert vix_percentile_52w(30.0, series) == 80

    def test_above_all(self):
        series = [10.0, 12.0, 14.0]
        # 50.0: all 3 below -> 100%
        assert vix_percentile_52w(50.0, series) == 100

    def test_empty_series_returns_50(self):
        assert vix_percentile_52w(18.0, []) == 50

    def test_single_element(self):
        assert vix_percentile_52w(20.0, [15.0]) == 100
        assert vix_percentile_52w(10.0, [15.0]) == 0


# ---------------------------------------------------------------------------
# five_day_trend
# ---------------------------------------------------------------------------

class TestFiveDayTrend:
    def _candles(self, closes: list[float]) -> list[dict]:
        return [{"close": c} for c in closes]

    def test_flat_within_half_pct(self):
        # 100 -> 100.4 = +0.4% -> flat
        candles = self._candles([100, 101, 102, 101, 100, 100.4])
        label, pct = five_day_trend(candles)
        assert label == "flat"
        assert pct == 0.4

    def test_up_trend(self):
        # 100 -> 102 = +2%
        candles = self._candles([100, 100.5, 101, 101.5, 101.8, 102])
        label, pct = five_day_trend(candles)
        assert label == "up"
        assert pct == 2.0

    def test_down_trend(self):
        # 100 -> 97 = -3%
        candles = self._candles([100, 99, 98.5, 98, 97.5, 97])
        label, pct = five_day_trend(candles)
        assert label == "down"
        assert pct == -3.0

    def test_exactly_minus_half_pct_is_flat(self):
        # 100 -> 99.5 = -0.5% -> flat (abs <= 0.5)
        candles = self._candles([100, 100, 100, 100, 100, 99.5])
        label, pct = five_day_trend(candles)
        assert label == "flat"
        assert pct == -0.5

    def test_short_series_returns_flat(self):
        candles = self._candles([100, 101, 102])
        label, pct = five_day_trend(candles)
        assert label == "flat"
        assert pct == 0.0

    def test_longer_series_uses_last_six(self):
        # 20 candles; last 6: 50, 51, 52, 53, 54, 55 -> (55-50)/50*100 = 10%
        candles = self._candles([10] * 14 + [50, 51, 52, 53, 54, 55])
        label, pct = five_day_trend(candles)
        assert label == "up"
        assert pct == 10.0


# ---------------------------------------------------------------------------
# distance_from_50d
# ---------------------------------------------------------------------------

class TestDistanceFrom50d:
    def _candles(self, closes: list[float]) -> list[dict]:
        return [{"close": c} for c in closes]

    def test_above_sma(self):
        # 50 candles all at 100, spot = 105 -> +5%
        candles = self._candles([100.0] * 50)
        dist, direction = distance_from_50d(105.0, candles)
        assert direction == "above"
        assert dist == 5.0

    def test_below_sma(self):
        # 50 candles all at 100, spot = 95 -> -5%
        candles = self._candles([100.0] * 50)
        dist, direction = distance_from_50d(95.0, candles)
        assert direction == "below"
        assert dist == -5.0

    def test_at_sma_is_above(self):
        candles = self._candles([100.0] * 50)
        dist, direction = distance_from_50d(100.0, candles)
        assert direction == "above"
        assert dist == 0.0

    def test_short_series_uses_available(self):
        # Only 10 candles at 200, spot = 210 -> +5%
        candles = self._candles([200.0] * 10)
        dist, direction = distance_from_50d(210.0, candles)
        assert direction == "above"
        assert dist == 5.0

    def test_uses_last_50_of_long_series(self):
        # 100 candles: first 50 at 50, last 50 at 100. SMA-50 = 100.
        candles = self._candles([50.0] * 50 + [100.0] * 50)
        dist, direction = distance_from_50d(102.0, candles)
        assert direction == "above"
        assert dist == 2.0


# ---------------------------------------------------------------------------
# regime_note — all 9 cells
# ---------------------------------------------------------------------------

class TestRegimeNote:
    """Cover all 9 cells of the VIX x IVR grid."""

    def test_low_vix_low_ivr(self):
        note = regime_note(12.0, 20.0)
        assert "Low-vol, range-bound" in note

    def test_low_vix_mid_ivr(self):
        note = regime_note(12.0, 45.0)
        assert "Mixed signal" in note

    def test_low_vix_high_ivr(self):
        note = regime_note(12.0, 75.0)
        assert "Skew favors premium sellers" in note

    def test_mid_vix_low_ivr(self):
        note = regime_note(18.0, 22.7)
        assert "mildly choppy" in note
        assert "VIX below 20" in note

    def test_mid_vix_mid_ivr(self):
        note = regime_note(17.0, 50.0)
        assert "Moderate-vol" in note
        assert "Standard premium pricing" in note

    def test_mid_vix_high_ivr(self):
        note = regime_note(19.0, 80.0)
        assert "Moderate-vol" in note
        assert "elevated single-name IV" in note

    def test_elevated_vix(self):
        note = regime_note(22.0, 50.0)
        assert "Elevated vol regime" in note

    def test_high_vix(self):
        note = regime_note(27.0, 10.0)
        assert "High-vol regime" in note

    def test_crisis_vix(self):
        note = regime_note(35.0, 50.0)
        assert "Crisis vol regime" in note

    def test_boundary_vix_15_is_mid(self):
        """VIX exactly 15 should fall into the 15-20 bucket (half-open)."""
        note = regime_note(15.0, 10.0)
        assert "mildly choppy" in note

    def test_boundary_vix_30_is_crisis(self):
        """VIX exactly 30 should fall into the >= 30 bucket."""
        note = regime_note(30.0, 50.0)
        assert "Crisis vol regime" in note

    def test_ivr_exactly_30_is_mid(self):
        """IVR exactly 30 should fall into the 30-60 bucket."""
        note = regime_note(10.0, 30.0)
        assert "Mixed signal" in note

    def test_ivr_exactly_60_is_high(self):
        """IVR exactly 60 should fall into the > 60 bucket."""
        note = regime_note(10.0, 60.0)
        assert "Skew favors premium sellers" in note
