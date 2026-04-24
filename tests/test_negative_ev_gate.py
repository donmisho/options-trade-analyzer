"""Unit tests for NegativeEVGate (OTA-503)."""

import pytest
from datetime import date
from unittest.mock import AsyncMock

from app.analysis.hard_gates import GateTradeContext
from app.analysis.hard_gates.negative_ev_gate import NegativeEVGate

ENTRY  = date(2026, 4, 22)
EXPIRY = date(2026, 5, 15)


def _ctx(ev=None, symbol="TEST") -> GateTradeContext:
    return GateTradeContext(
        symbol=symbol,
        entry_date=ENTRY,
        expiry_date=EXPIRY,
        dte=(EXPIRY - ENTRY).days,
        trade=None,
        db=None,
        expected_value=ev,
    )


# ─── AMZN regression ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_amzn_regression_negative_ev_triggers():
    """AMZN EV = -5.86 → triggered=True, verdict=PASS."""
    gate = NegativeEVGate()
    result = await gate.evaluate(_ctx(ev=-5.86, symbol="AMZN"))

    assert result.triggered is True
    assert result.verdict == "PASS"
    assert result.gate_id == "negative_ev"
    assert "-5.86" in result.reason


# ─── Positive EV ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_positive_ev_not_triggered():
    """EV = 12.50 → triggered=False."""
    gate = NegativeEVGate()
    result = await gate.evaluate(_ctx(ev=12.50))

    assert result.triggered is False
    assert result.verdict is None
    assert result.penalty_points == 0


# ─── Zero EV (strict < boundary) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zero_ev_not_triggered():
    """EV exactly 0.0 → triggered=False (strict <, not <=)."""
    gate = NegativeEVGate()
    result = await gate.evaluate(_ctx(ev=0.0))

    assert result.triggered is False


# ─── Null EV (fail-soft) ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_null_ev_not_triggered():
    """EV = None → triggered=False, no error raised."""
    gate = NegativeEVGate()
    result = await gate.evaluate(_ctx(ev=None))

    assert result.triggered is False
    assert result.penalty_points == 0
    assert result.effective_dte_override is None


# ─── Tiny negative (no tolerance) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tiny_negative_ev_triggers():
    """EV = -0.01 → triggered=True (no tolerance — negative is negative)."""
    gate = NegativeEVGate()
    result = await gate.evaluate(_ctx(ev=-0.01))

    assert result.triggered is True
    assert result.verdict == "PASS"


# ─── Reason string content ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reason_contains_ev_value_and_message():
    """Reason must surface the EV value and 'primary quality gate' text."""
    gate = NegativeEVGate()
    result = await gate.evaluate(_ctx(ev=-3.14))

    assert "-3.14" in result.reason
    assert "primary quality gate" in result.reason


# ─── Unexpected error is fail-soft ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_unexpected_exception_returns_not_triggered(monkeypatch):
    """If _evaluate raises unexpectedly, gate returns triggered=False."""
    gate = NegativeEVGate()

    def _boom(ctx):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(gate, "_evaluate", _boom)
    result = await gate.evaluate(_ctx(ev=-5.0))

    assert result.triggered is False
