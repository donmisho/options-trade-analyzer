"""Tests for the hard-gate scaffolding (OTA-502)."""

import pytest
from datetime import date

from app.analysis.hard_gates import (
    GateResult,
    GateTradeContext,
    HardGate,
    _clear_gates,
    evaluate_hard_gates,
    register_gate,
)


def _ctx(**kwargs) -> GateTradeContext:
    defaults = dict(
        symbol="TEST",
        entry_date=date(2026, 4, 22),
        expiry_date=date(2026, 5, 15),
        dte=23,
        trade=None,
    )
    defaults.update(kwargs)
    return GateTradeContext(**defaults)


@pytest.fixture(autouse=True)
def clear_registry():
    """Isolate each test — reset the global gate registry."""
    _clear_gates()
    yield
    _clear_gates()


# ─── Scaffolding behaviour ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_registered_gates_returns_none():
    result = await evaluate_hard_gates(_ctx())
    assert result is None


@pytest.mark.asyncio
async def test_non_triggering_gate_returns_none_when_no_modifiers():
    class PassGate(HardGate):
        gate_id = "always_pass"

        async def evaluate(self, ctx):
            return GateResult(triggered=False, gate_id=self.gate_id)

    register_gate(PassGate())
    result = await evaluate_hard_gates(_ctx())
    assert result is None


@pytest.mark.asyncio
async def test_triggered_gate_short_circuits():
    call_log = []

    class BlockGate(HardGate):
        gate_id = "block"

        async def evaluate(self, ctx):
            call_log.append("block")
            return GateResult(triggered=True, verdict="PASS", reason="blocked", gate_id=self.gate_id)

    class ShouldNotRunGate(HardGate):
        gate_id = "second"

        async def evaluate(self, ctx):
            call_log.append("second")
            return GateResult(triggered=False, gate_id=self.gate_id)

    register_gate(BlockGate())
    register_gate(ShouldNotRunGate())

    result = await evaluate_hard_gates(_ctx())

    assert result is not None
    assert result.triggered is True
    assert result.verdict == "PASS"
    assert "second" not in call_log


@pytest.mark.asyncio
async def test_modifier_gate_returns_result():
    class PenaltyGate(HardGate):
        gate_id = "penalty"

        async def evaluate(self, ctx):
            return GateResult(
                triggered=False,
                penalty_points=15,
                effective_dte_override=9,
                gate_id=self.gate_id,
            )

    register_gate(PenaltyGate())
    result = await evaluate_hard_gates(_ctx())

    assert result is not None
    assert result.triggered is False
    assert result.penalty_points == 15
    assert result.effective_dte_override == 9


@pytest.mark.asyncio
async def test_failing_gate_is_skipped_fail_soft():
    class BrokenGate(HardGate):
        gate_id = "broken"

        async def evaluate(self, ctx):
            raise RuntimeError("unexpected error")

    class GoodGate(HardGate):
        gate_id = "good"

        async def evaluate(self, ctx):
            return GateResult(triggered=True, verdict="PASS", reason="good gate fired", gate_id=self.gate_id)

    register_gate(BrokenGate())
    register_gate(GoodGate())

    result = await evaluate_hard_gates(_ctx())

    # BrokenGate is skipped; GoodGate still fires
    assert result is not None
    assert result.triggered is True
    assert result.gate_id == "good"
