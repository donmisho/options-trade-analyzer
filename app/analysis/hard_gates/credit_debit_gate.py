"""
CreditDebitQualityGate — OTA-780.

Hard gate that evaluates credit/debit spread quality.

Rules:
  Credit spread (net_debit < 0):
      credit_pct = |net_debit| / spread_width
      credit_pct < credit_min_pct → BLOCK
  Debit spread (net_debit > 0):
      debit_pct = net_debit / spread_width
      debit_pct > debit_max_pct → BLOCK

Reads trade data from ctx.trade (raw trade dict).

Thresholds are constructor params (will come from junction rows when
the engine tables are the live source).
"""

import logging

from app.analysis.hard_gates import (
    ACTION_BLOCK,
    GateResult,
    GateTradeContext,
    HardGate,
)

logger = logging.getLogger(__name__)


class CreditDebitQualityGate(HardGate):
    """Pre-scoring gate: block trades with poor credit/debit quality."""

    gate_id = "credit_debit_quality"

    def __init__(
        self,
        *,
        credit_min_pct: float = 0.30,
        debit_max_pct: float = 0.40,
    ):
        self._credit_min = credit_min_pct
        self._debit_max = debit_max_pct

    async def evaluate(self, ctx: GateTradeContext) -> GateResult:
        try:
            return self._evaluate(ctx)
        except Exception as exc:
            logger.error(
                f"CreditDebitQualityGate: unexpected error for {ctx.symbol}: {exc}. "
                "Returning triggered=False (fail-soft).",
                exc_info=True,
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

    def _evaluate(self, ctx: GateTradeContext) -> GateResult:
        if not ctx.trade:
            return GateResult(triggered=False, gate_id=self.gate_id)

        net_debit = float(ctx.trade.get("net_debit") or 0)
        spread_width = float(ctx.trade.get("spread_width") or 0)

        if spread_width <= 0:
            return GateResult(triggered=False, gate_id=self.gate_id)

        if net_debit < 0:
            # Credit spread
            net_credit = abs(net_debit)
            credit_pct = round(net_credit / spread_width, 4)
            if credit_pct < self._credit_min:
                return GateResult(
                    triggered=True,
                    action=ACTION_BLOCK,
                    reason=(
                        f"Credit of {net_credit:.2f} represents "
                        f"{credit_pct * 100:.1f}% of the "
                        f"{spread_width:.0f} spread width. "
                        f"Minimum {self._credit_min * 100:.0f}% required "
                        f"({spread_width * self._credit_min:.2f} minimum credit)."
                    ),
                    gate_id=self.gate_id,
                    metadata={"credit_pct_of_width": credit_pct},
                )
            return GateResult(
                triggered=False,
                gate_id=self.gate_id,
                metadata={"credit_pct_of_width": credit_pct},
            )

        if net_debit > 0:
            # Debit spread
            debit_pct = round(net_debit / spread_width, 4)
            if debit_pct > self._debit_max:
                return GateResult(
                    triggered=True,
                    action=ACTION_BLOCK,
                    reason=(
                        f"Debit of {net_debit:.2f} represents "
                        f"{debit_pct * 100:.1f}% of the "
                        f"{spread_width:.0f} spread width. "
                        f"Maximum {self._debit_max * 100:.0f}% permitted "
                        f"({spread_width * self._debit_max:.2f} maximum debit)."
                    ),
                    gate_id=self.gate_id,
                    metadata={"debit_pct_of_width": debit_pct},
                )
            return GateResult(
                triggered=False,
                gate_id=self.gate_id,
                metadata={"debit_pct_of_width": debit_pct},
            )

        return GateResult(triggered=False, gate_id=self.gate_id)
