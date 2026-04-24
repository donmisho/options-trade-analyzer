"""
NegativeEVGate — OTA-503.

Hard gate that fires when a trade's expected value is negative.

Per user framework: EV is the primary quality gate. A negative EV trade
must never reach EXECUTE or WAIT.

Rules:
  EV < 0     → triggered=True, verdict=PASS
  EV == 0    → triggered=False (strict <, not <=; zero-EV trades are poor
                setups but do not violate the framework rule)
  EV is None → triggered=False (fail-soft; "not yet computed" ≠ negative)
  EV > 0     → triggered=False

EV is in dollars as passed by the scoring pipeline's total_ev field.

Defense-in-depth with EarningsInWindowGate (OTA-502):
  - Earnings gate catches catalyst risk.
  - This gate catches the math.
  - Either alone would have flipped the AMZN 260/270 May 15 verdict.
  - Registration order: EarningsInWindowGate first, NegativeEVGate second.
    When both fire, earnings reason surfaces (first-match-wins, Option A
    approved by Don in OTA-503 Phase 1).
"""

import logging

from app.analysis.hard_gates import GateResult, GateTradeContext, HardGate

logger = logging.getLogger(__name__)


class NegativeEVGate(HardGate):
    """
    Pre-scoring gate: block trades whose expected value is negative.

    Stateless — no I/O, no injected dependencies. Reads only from
    GateTradeContext.expected_value, which is populated by the scoring
    pipeline from the trade's computed total_ev.
    """

    gate_id = "negative_ev"

    async def evaluate(self, ctx: GateTradeContext) -> GateResult:
        """
        Evaluate the negative-EV condition for the given trade context.

        Never raises — returns GateResult(triggered=False) on any unexpected
        error so the gate is always fail-soft.
        """
        try:
            return self._evaluate(ctx)
        except Exception as exc:
            logger.error(
                f"NegativeEVGate: unexpected error for {ctx.symbol}: {exc}. "
                "Returning triggered=False (fail-soft).",
                exc_info=True,
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

    def _evaluate(self, ctx: GateTradeContext) -> GateResult:
        ev = ctx.expected_value

        if ev is None:
            logger.debug(
                f"NegativeEVGate: expected_value is None for {ctx.symbol} "
                "— not gating (EV not yet computed)"
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

        if ev < 0:
            logger.info(
                f"NegativeEVGate: triggered for {ctx.symbol} EV={ev:.2f}"
            )
            return GateResult(
                triggered=True,
                verdict="PASS",
                reason=(
                    f"Negative expected value ({ev:.2f}). "
                    f"Trade fails primary quality gate."
                ),
                gate_id=self.gate_id,
            )

        logger.debug(
            f"NegativeEVGate: EV={ev:.2f} for {ctx.symbol} — not gating"
        )
        return GateResult(triggered=False, gate_id=self.gate_id)
