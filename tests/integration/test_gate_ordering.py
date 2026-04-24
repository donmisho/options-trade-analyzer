"""
Integration test for hard-gate registration order (OTA-503 Phase 3).

Verifies Option A ordering: EarningsInWindowGate wins on double-trigger.
  - Trade triggers BOTH earnings-in-window AND negative EV
    → earnings reason surfaces; negative-EV reason does NOT appear
  - Trade triggers ONLY negative EV (earnings out of window)
    → negative-EV gate wins standalone
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock

from app.analysis.hard_gates import (
    GateTradeContext,
    _clear_gates,
    evaluate_hard_gates,
    register_gate,
)
from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
from app.analysis.hard_gates.negative_ev_gate import NegativeEVGate

ENTRY  = date(2026, 4, 22)   # Wednesday
EXPIRY = date(2026, 5, 15)   # Friday


@pytest.fixture(autouse=True)
def isolated_registry():
    """Each test gets a clean gate registry."""
    _clear_gates()
    yield
    _clear_gates()


def _register_option_a():
    """Register gates in Option A order: earnings first, negative-EV second."""
    earnings_gate = EarningsInWindowGate(source=object())
    # Patch DB lookup so no real Finnhub / DB calls happen in tests
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 4, 29))  # 5 biz days in

    neg_ev_gate = NegativeEVGate()

    register_gate(earnings_gate)
    register_gate(neg_ev_gate)
    return earnings_gate, neg_ev_gate


def _ctx(ev, earnings_in_window: bool) -> GateTradeContext:
    """
    Build a context where:
      - earnings_in_window=True  → earnings patched to Apr 29 (5 biz days from entry, inside window)
      - earnings_in_window=False → earnings patched to May 17 (after expiry, outside window)
    """
    # Note: earnings date is controlled via the gate mock, not the ctx.
    # The ctx just needs valid entry/expiry so the window check can fire.
    return GateTradeContext(
        symbol="AMZN",
        entry_date=ENTRY,
        expiry_date=EXPIRY,
        dte=(EXPIRY - ENTRY).days,
        trade={"total_ev": ev},
        db=None,
        expected_value=ev,
    )


# ─── Double-trigger: earnings wins (Option A) ─────────────────────────────────


@pytest.mark.asyncio
async def test_double_trigger_earnings_gate_wins():
    """
    Trade triggers both gates: earnings ≤7 days AND EV < 0.
    EarningsInWindowGate is registered first → it wins.
    Returned reason contains 'Earnings', not 'Negative expected value'.
    """
    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 4, 29))  # 5 biz days
    neg_ev_gate = NegativeEVGate()

    register_gate(earnings_gate)    # first
    register_gate(neg_ev_gate)      # second

    ctx = _ctx(ev=-5.86, earnings_in_window=True)
    result = await evaluate_hard_gates(ctx)

    assert result is not None
    assert result.triggered is True
    assert result.gate_id == "earnings_in_window", (
        f"Expected earnings gate to win; got gate_id={result.gate_id!r}"
    )
    assert "Earnings" in result.reason, f"Expected 'Earnings' in reason: {result.reason!r}"
    assert "Negative expected value" not in result.reason, (
        f"Negative-EV reason should NOT appear: {result.reason!r}"
    )


@pytest.mark.asyncio
async def test_double_trigger_reason_contains_earnings_date():
    """Winning reason from earnings gate must include the specific date."""
    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 4, 29))
    register_gate(earnings_gate)
    register_gate(NegativeEVGate())

    result = await evaluate_hard_gates(_ctx(ev=-5.86, earnings_in_window=True))

    assert result is not None
    assert "2026-04-29" in result.reason


# ─── Single-trigger: negative EV wins standalone ─────────────────────────────


@pytest.mark.asyncio
async def test_negative_ev_wins_when_earnings_out_of_window():
    """
    Earnings after expiry (outside window) AND EV < 0.
    EarningsInWindowGate does NOT fire; NegativeEVGate fires standalone.
    """
    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 5, 17))  # after expiry
    neg_ev_gate = NegativeEVGate()

    register_gate(earnings_gate)    # first but won't trigger
    register_gate(neg_ev_gate)      # second — triggers

    ctx = _ctx(ev=-5.86, earnings_in_window=False)
    result = await evaluate_hard_gates(ctx)

    assert result is not None
    assert result.triggered is True
    assert result.gate_id == "negative_ev", (
        f"Expected negative_ev gate to fire; got gate_id={result.gate_id!r}"
    )
    assert "Negative expected value" in result.reason
    assert "-5.86" in result.reason


@pytest.mark.asyncio
async def test_negative_ev_standalone_verdict_is_pass():
    """NegativeEVGate standalone → verdict must be PASS."""
    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 5, 17))
    register_gate(earnings_gate)
    register_gate(NegativeEVGate())

    result = await evaluate_hard_gates(_ctx(ev=-5.86, earnings_in_window=False))

    assert result is not None
    assert result.verdict == "PASS"


# ─── Neither gate fires (positive EV, earnings out of window) ─────────────────


@pytest.mark.asyncio
async def test_no_gates_fire_on_positive_ev_no_earnings():
    """
    EV positive, earnings out of window → neither gate fires.
    evaluate_hard_gates returns None → pipeline continues normally.
    """
    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=None)  # no earnings
    register_gate(earnings_gate)
    register_gate(NegativeEVGate())

    result = await evaluate_hard_gates(_ctx(ev=12.50, earnings_in_window=False))

    assert result is None
