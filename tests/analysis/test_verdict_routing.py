"""
OTA-515: Earnings gate verdict routing tests.

Verifies the 4-route decision tree in EarningsInWindowGate produces the correct
verdict, dte_after_earnings, and reevaluate_on for all edge cases.

Test matrix (from OTA-515 prompt):
  1. dte_before=5, dte_after=10  → Route 1: PASS
  2. dte_before=7, dte_after=13  → Route 1: PASS (boundary)
  3. dte_before=5, dte_after=14  → Route 2: WAIT_FOR_EARNINGS
  4. dte_before=7, dte_after=20  → Route 2: WAIT_FOR_EARNINGS (boundary)
  5. dte_before=10, dte_after=21 → Route 3: WAIT_FOR_EARNINGS
  6. dte_before=15, dte_after=30 → Route 3: WAIT_FOR_EARNINGS
  7. dte_before=10, dte_after=15 → Route 4: modifier (no trigger)
  8. dte_before=8, dte_after=20  → Route 4: modifier (boundary)
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.analysis.hard_gates import ACTION_BLOCK, ACTION_DEFER, GateTradeContext
from app.analysis.hard_gates.earnings_gate import (
    EarningsInWindowGate,
    _business_days_between,
    _next_business_day,
)
from app.insight_engine.models import Candidate


# ─── Helper to build context with a controlled earnings date ──────────────────


def _make_context(entry: date, expiry: date) -> GateTradeContext:
    dte = _business_days_between(entry, expiry)
    candidate = Candidate(
        candidate_id="test",
        candidate_type="options_trade",
        named_values={"expiry_date": expiry, "dte": dte},
        symbol="TEST",
    )
    return GateTradeContext(
        symbol="TEST",
        entry_date=entry,
        candidate=candidate,
        trade={"spread_label": "Test Spread"},
        db=None,
    )


def _date_plus_bdays(start: date, bdays: int) -> date:
    """Advance `start` by `bdays` business days."""
    current = start
    added = 0
    while added < bdays:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


# ─── Parametrized test cases ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "dte_before,dte_after,expected_triggered,expected_action,route_label",
    [
        # Route 1: dte_before <= 7 AND dte_after < 14 → BLOCK
        (5, 10, True, ACTION_BLOCK, "Route 1: typical"),
        (7, 13, True, ACTION_BLOCK, "Route 1: boundary"),
        # Route 2: dte_before <= 7 AND dte_after >= 14 → DEFER
        (5, 14, True, ACTION_DEFER, "Route 2: typical"),
        (7, 20, True, ACTION_DEFER, "Route 2: boundary"),
        # Route 3: dte_before >= 8 AND dte_after >= 21 → DEFER
        (10, 21, True, ACTION_DEFER, "Route 3: boundary"),
        (15, 30, True, ACTION_DEFER, "Route 3: typical"),
        # Route 4: dte_before >= 8 AND dte_after < 21 → modifier (not triggered)
        (10, 15, False, None, "Route 4: typical"),
        (8, 20, False, None, "Route 4: boundary"),
    ],
)
@pytest.mark.asyncio
async def test_earnings_gate_routing(
    dte_before, dte_after, expected_triggered, expected_action, route_label
):
    """Verify each route in the earnings decision tree."""
    # Build dates: entry=Monday 2026-06-01, earnings after dte_before bdays,
    # expiry after dte_before + dte_after bdays from entry
    entry = date(2026, 6, 1)  # Monday
    earnings = _date_plus_bdays(entry, dte_before)
    expiry = _date_plus_bdays(earnings, dte_after)

    ctx = _make_context(entry, expiry)

    gate = EarningsInWindowGate(source=None)

    # Mock _fetch_earnings_date to return our controlled date
    with patch.object(gate, "_fetch_earnings_date", new=AsyncMock(return_value=earnings)):
        result = await gate.evaluate(ctx)

    assert result.triggered == expected_triggered, f"{route_label}: triggered mismatch"

    if expected_triggered:
        assert result.action == expected_action, f"{route_label}: action mismatch"
        if expected_action == ACTION_DEFER:
            assert result.metadata.get("dte_after_earnings") == dte_after, f"{route_label}: dte_after mismatch"
            assert result.metadata.get("reevaluate_on") is not None, f"{route_label}: reevaluate_on should be set"
    else:
        # Route 4: modifier
        assert result.penalty_points == 15, f"{route_label}: expected 15-point penalty"
        assert result.effective_dte_override == dte_before - 1, f"{route_label}: effective_dte mismatch"


# ─── Edge case: no earnings date ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_earnings_date_does_not_trigger():
    """When no earnings date is available, gate should not fire."""
    entry = date(2026, 6, 1)
    expiry = date(2026, 7, 18)
    ctx = _make_context(entry, expiry)

    gate = EarningsInWindowGate(source=None)
    with patch.object(gate, "_fetch_earnings_date", new=AsyncMock(return_value=None)):
        result = await gate.evaluate(ctx)

    assert result.triggered is False
    assert result.penalty_points == 0


# ─── Edge case: earnings outside window ──────────────────────────────────────


@pytest.mark.asyncio
async def test_earnings_outside_window_does_not_trigger():
    """When earnings are after expiry, gate should not fire."""
    entry = date(2026, 6, 1)
    expiry = date(2026, 6, 20)
    earnings_after_expiry = date(2026, 7, 10)

    ctx = _make_context(entry, expiry)

    gate = EarningsInWindowGate(source=None)
    with patch.object(gate, "_fetch_earnings_date", new=AsyncMock(return_value=earnings_after_expiry)):
        result = await gate.evaluate(ctx)

    assert result.triggered is False
    assert result.penalty_points == 0


# ─── Helper unit tests ───────────────────────────────────────────────────────


def test_business_days_between():
    """Verify weekends are skipped."""
    # Monday to Friday same week = 4 business days
    mon = date(2026, 6, 1)  # Monday
    fri = date(2026, 6, 5)  # Friday
    assert _business_days_between(mon, fri) == 4

    # Friday to next Monday = 1 business day
    assert _business_days_between(fri, date(2026, 6, 8)) == 1

    # Same day = 0
    assert _business_days_between(mon, mon) == 0


def test_next_business_day():
    """Friday → Monday, weekday → next day."""
    fri = date(2026, 6, 5)
    assert _next_business_day(fri) == date(2026, 6, 8)  # Monday

    wed = date(2026, 6, 3)
    assert _next_business_day(wed) == date(2026, 6, 4)  # Thursday
