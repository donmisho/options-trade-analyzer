"""
DTEGate — OTA-780.

Hard gate that evaluates DTE (days to expiration) thresholds.

Two behaviors in one gate:
  DTE <= dte_block_threshold (default 7):
      action=BLOCK — insufficient time for active management.
  DTE in [dte_warning_min, dte_warning_max] (default 8-13):
      triggered=False, penalty_points=20, action=MODIFY —
      near-expiry warning band; penalty applied post-scoring.

Reads `dte` from candidate.named_values (set by evaluation_routes.py,
may be overridden by EarningsInWindowGate's effective_dte_override).

Thresholds are constructor params (will come from junction rows when
the engine tables are the live source).
"""

import logging

from app.analysis.hard_gates import (
    ACTION_BLOCK,
    ACTION_MODIFY,
    GateResult,
    GateTradeContext,
    HardGate,
)

logger = logging.getLogger(__name__)


class DTEGate(HardGate):
    """Pre-scoring gate: block or penalise trades near expiration."""

    gate_id = "dte_filter"

    def __init__(
        self,
        *,
        dte_block_threshold: int = 7,
        dte_warning_min: int = 8,
        dte_warning_max: int = 13,
        warning_penalty: int = 20,
    ):
        self._block = dte_block_threshold
        self._warn_min = dte_warning_min
        self._warn_max = dte_warning_max
        self._penalty = warning_penalty

    async def evaluate(self, ctx: GateTradeContext) -> GateResult:
        try:
            return self._evaluate(ctx)
        except Exception as exc:
            logger.error(
                f"DTEGate: unexpected error for {ctx.symbol}: {exc}. "
                "Returning triggered=False (fail-soft).",
                exc_info=True,
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

    def _evaluate(self, ctx: GateTradeContext) -> GateResult:
        dte = ctx.candidate.named_values.get("dte") if ctx.candidate else None

        if dte is None:
            return GateResult(triggered=False, gate_id=self.gate_id)

        if dte <= self._block:
            return GateResult(
                triggered=True,
                action=ACTION_BLOCK,
                reason=(
                    f"Insufficient time remaining for active management. "
                    f"This trade expires in {dte} day(s). "
                    f"Minimum {self._block + 1} DTE required to enter any position."
                ),
                gate_id=self.gate_id,
            )

        if self._warn_min <= dte <= self._warn_max:
            warning_msg = (
                f"{dte} DTE — Below recommended minimum. "
                f"{self._penalty}-point penalty applied. "
                "Exit management time is limited."
            )
            return GateResult(
                triggered=False,
                action=ACTION_MODIFY,
                penalty_points=self._penalty,
                reason=warning_msg,
                gate_id=self.gate_id,
                metadata={"dte_warning": warning_msg},
            )

        return GateResult(triggered=False, gate_id=self.gate_id)
