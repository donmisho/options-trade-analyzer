"""
Unit tests for EarningsInWindowGate (OTA-502).

All tests mock _fetch_earnings_date so no DB or Finnhub calls are made.

Business-day calendar used by the tests (entry = April 22, 2026, Wednesday):
  Day 1 = Apr 23 (Thu)   Day 6 = Apr 30 (Thu)
  Day 2 = Apr 24 (Fri)   Day 7 = May  1 (Fri)  ← 7-day hard boundary
  Day 3 = Apr 27 (Mon)   Day 8 = May  4 (Mon)  ← warning band starts
  Day 4 = Apr 28 (Tue)   Day 9 = May  5 (Tue)
  Day 5 = Apr 29 (Wed)   Day 10= May  6 (Wed)
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.analysis.hard_gates import GateTradeContext, _clear_gates
from app.analysis.hard_gates.earnings_gate import (
    EarningsInWindowGate,
    _business_days_between,
)

ENTRY   = date(2026, 4, 22)   # Wednesday
EXPIRY  = date(2026, 5, 15)   # Friday


def _ctx(entry=ENTRY, expiry=EXPIRY, symbol="TEST", **kwargs) -> GateTradeContext:
    dte = (expiry - entry).days if expiry is not None else 0
    return GateTradeContext(
        symbol=symbol,
        entry_date=entry,
        expiry_date=expiry,
        dte=dte,
        trade=None,
        db=None,
        **kwargs,
    )


def _gate(earnings_date) -> EarningsInWindowGate:
    """Create a gate whose _fetch_earnings_date is patched to return earnings_date."""
    gate = EarningsInWindowGate(source=object())  # source unused — patched below
    gate._fetch_earnings_date = AsyncMock(return_value=earnings_date)
    return gate


# ─── Business-day helper ──────────────────────────────────────────────────────


def test_business_days_same_day():
    assert _business_days_between(ENTRY, ENTRY) == 0


def test_business_days_apr22_to_apr29():
    # Wed Apr 22 → Wed Apr 29: Thu, Fri, Mon, Tue, Wed = 5 business days
    assert _business_days_between(date(2026, 4, 22), date(2026, 4, 29)) == 5


def test_business_days_apr22_to_may1():
    # 7 business days (boundary)
    assert _business_days_between(date(2026, 4, 22), date(2026, 5, 1)) == 7


def test_business_days_apr22_to_may4():
    # 8 business days (first day of warning band)
    assert _business_days_between(date(2026, 4, 22), date(2026, 5, 4)) == 8


def test_business_days_end_before_start():
    assert _business_days_between(date(2026, 4, 29), date(2026, 4, 22)) == 0


def test_business_days_skips_weekend():
    # Fri Apr 24 → Mon Apr 27: only Monday counts (Sat+Sun skipped)
    assert _business_days_between(date(2026, 4, 24), date(2026, 4, 27)) == 1


# ─── Gate: AMZN regression ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_amzn_regression_triggered():
    """AMZN 260/270 May 15: earnings Apr 29 (5 biz days from entry) → PASS."""
    gate = _gate(date(2026, 4, 29))
    result = await gate.evaluate(_ctx())

    assert result.triggered is True
    assert result.verdict == "PASS"
    assert result.gate_id == "earnings_in_window"
    assert "2026-04-29" in result.reason
    assert "5 trading days" in result.reason


# ─── Gate: hard-block boundary tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_boundary_exactly_7_business_days_triggers():
    """Earnings exactly 7 biz days from entry → inclusive boundary → PASS."""
    gate = _gate(date(2026, 5, 1))   # 7 business days from Apr 22
    result = await gate.evaluate(_ctx())

    assert result.triggered is True
    assert result.verdict == "PASS"
    assert "7 trading days" in result.reason


@pytest.mark.asyncio
async def test_boundary_exactly_8_business_days_warning_band():
    """Earnings exactly 8 biz days from entry → warning band, no hard block."""
    gate = _gate(date(2026, 5, 4))   # 8 business days from Apr 22
    result = await gate.evaluate(_ctx())

    assert result.triggered is False
    assert result.verdict is None
    assert result.penalty_points == 15
    assert result.effective_dte_override == 7   # 8 - 1


# ─── Gate: warning band ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warning_band_10_business_days():
    """Earnings 10 biz days from entry → triggered=False, effective_dte=9, penalty=15."""
    gate = _gate(date(2026, 5, 6))   # 10 business days from Apr 22
    result = await gate.evaluate(_ctx())

    assert result.triggered is False
    assert result.penalty_points == 15
    assert result.effective_dte_override == 9   # 10 - 1


# ─── Gate: out of window ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_earnings_after_expiry_not_gated():
    """Earnings 2 days after expiry → outside window → no action."""
    gate = _gate(date(2026, 5, 17))   # 2 days after May 15 expiry
    result = await gate.evaluate(_ctx())

    assert result.triggered is False
    assert result.penalty_points == 0
    assert result.effective_dte_override is None


@pytest.mark.asyncio
async def test_earnings_before_entry_not_gated():
    """Earnings before entry → outside window → no action."""
    gate = _gate(date(2026, 4, 20))   # before Apr 22 entry
    result = await gate.evaluate(_ctx())

    assert result.triggered is False
    assert result.penalty_points == 0


# ─── Gate: missing / null earnings ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_earnings_not_triggered():
    """No earnings data → gate does not trigger, no error raised."""
    gate = _gate(None)
    result = await gate.evaluate(_ctx())

    assert result.triggered is False
    assert result.penalty_points == 0
    assert result.effective_dte_override is None


@pytest.mark.asyncio
async def test_fetch_raises_not_triggered():
    """If DB lookup raises unexpectedly, gate fails soft."""
    gate = EarningsInWindowGate(source=object())
    gate._fetch_earnings_date = AsyncMock(side_effect=RuntimeError("DB is down"))
    result = await gate.evaluate(_ctx())

    assert result.triggered is False


# ─── Gate: expiry_date=None ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_expiry_date_not_triggered():
    """If expiry_date cannot be parsed, gate cannot determine window — no trigger."""
    gate = _gate(date(2026, 4, 29))
    ctx = _ctx(expiry=None)
    result = await gate.evaluate(ctx)

    assert result.triggered is False


# ─── Golden path: no earnings in window ───────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_path_no_earnings_gate_does_not_fire():
    """Symbol with null earnings → gate does not fire, pipeline continues normally."""
    gate = _gate(None)
    result = await gate.evaluate(_ctx(symbol="GOOGL"))  # noqa: E501

    assert result is not None
    assert result.triggered is False
    assert result.penalty_points == 0
    assert result.effective_dte_override is None
