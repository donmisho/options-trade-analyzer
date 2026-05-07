"""
EarningsInWindowGate — OTA-502 + OTA-515.

Hard gate that fires when an earnings event falls inside a trade's hold window.

User framework rule: never hold through earnings.

OTA-515 Decision Tree (4 routes):
  Route 1 — dte_before ≤ 7 AND dte_after < 14:
      verdict=PASS — no viable window on either side
  Route 2 — dte_before ≤ 7 AND dte_after >= 14:
      verdict=WAIT_FOR_EARNINGS — can't enter pre-earnings, strong post window
  Route 3 — dte_before >= 8 AND dte_after >= 21:
      verdict=WAIT_FOR_EARNINGS — post-earnings entry likely better
  Route 4 — dte_before >= 8 AND dte_after < 21:
      score normally using effective_DTE = dte_before_earnings
      (pre-earnings momentum play)

Legacy (OTA-502) warning band (8-13 DTE to earnings with no post-window routing):
  Superseded by routes 3/4. The 15-point penalty in Route 4 is preserved.

"Trading days" = business days; weekends are not counted.

Data source: symbol_context table via ContextStore.refresh_if_stale().
If no earnings date is recorded (Finnhub returned null) the gate does NOT fire.
Unknown earnings ≠ no earnings — fail-soft.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from app.analysis.hard_gates import GateResult, GateTradeContext, HardGate

logger = logging.getLogger(__name__)


# ─── Business-day helper ─────────────────────────────────────────────────────


def _business_days_between(start: date, end: date) -> int:
    """
    Count business days strictly between start (exclusive) and end (inclusive).

    Weekdays 0-4 (Mon-Fri) are counted; Sat (5) and Sun (6) are skipped.
    Returns 0 when end <= start.
    """
    if end <= start:
        return 0
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # Mon=0 … Fri=4
            count += 1
        current += timedelta(days=1)
    return count


def _next_business_day(d: date) -> date:
    """Return the next weekday after the given date."""
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # skip Sat/Sun
        nxt += timedelta(days=1)
    return nxt


# ─── Gate implementation ──────────────────────────────────────────────────────


class EarningsInWindowGate(HardGate):
    """
    Pre-scoring gate: block or penalise trades where earnings fall inside the
    hold window.

    Injected with a FinnhubEarningsSource instance so the gate can refresh
    symbol_context via ContextStore without owning a DB session directly.
    The session is received per-call via GateTradeContext.db.
    """

    gate_id = "earnings_in_window"

    def __init__(self, source=None):
        """
        Args:
            source: A ContextSource instance used to refresh earnings data.
                    Defaults to a new FinnhubEarningsSource() if not provided.
        """
        if source is None:
            from app.providers.finnhub_earnings import FinnhubEarningsSource
            source = FinnhubEarningsSource()
        self._source = source

    # ── Public interface ──────────────────────────────────────────────────────

    async def evaluate(self, ctx: GateTradeContext) -> GateResult:
        """
        Evaluate the earnings-in-window condition for the given trade context.

        Never raises — returns GateResult(triggered=False) on any unexpected
        error so the gate is always fail-soft.
        """
        try:
            return await self._evaluate(ctx)
        except Exception as exc:
            logger.error(
                f"EarningsInWindowGate: unexpected error for {ctx.symbol}: {exc}. "
                "Returning triggered=False (fail-soft).",
                exc_info=True,
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _evaluate(self, ctx: GateTradeContext) -> GateResult:
        earnings_date = await self._fetch_earnings_date(ctx.symbol, ctx.db)

        if earnings_date is None:
            logger.debug(
                f"EarningsInWindowGate: no earnings date for {ctx.symbol} — not gating"
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

        # Gate only fires when earnings fall inside [entry_date, expiry_date]
        if ctx.expiry_date is None or not (ctx.entry_date <= earnings_date <= ctx.expiry_date):
            logger.debug(
                f"EarningsInWindowGate: {ctx.symbol} earnings {earnings_date} "
                f"outside window [{ctx.entry_date}, {ctx.expiry_date}] — not gating"
            )
            return GateResult(triggered=False, gate_id=self.gate_id)

        # OTA-515: Compute both windows
        dte_before = _business_days_between(ctx.entry_date, earnings_date)
        dte_after = _business_days_between(earnings_date, ctx.expiry_date) if ctx.expiry_date else 0
        earnings_str = earnings_date.isoformat()

        # Compute reevaluate_on: next business day after earnings
        reeval_date = _next_business_day(earnings_date)
        reeval_str = reeval_date.strftime("%m-%d-%Y")

        # Route 1 — no viable window on either side
        if dte_before <= 7 and dte_after < 14:
            return GateResult(
                triggered=True,
                verdict="PASS",
                reason=(
                    f"Earnings {earnings_str} — insufficient time both before "
                    f"({dte_before} trading days) and after ({dte_after} trading days) catalyst."
                ),
                gate_id=self.gate_id,
            )

        # Route 2 — can't enter pre-earnings, but strong post-earnings window
        if dte_before <= 7 and dte_after >= 14:
            return GateResult(
                triggered=True,
                verdict="WAIT_FOR_EARNINGS",
                reason=(
                    f"Re-evaluate {reeval_str}. {dte_after} DTE remaining post-IV crush."
                ),
                gate_id=self.gate_id,
                # Stash routing metadata for the response builder
                _dte_after_earnings=dte_after,
                _reevaluate_on=reeval_str,
            )

        # Route 3 — pre-earnings window viable, but post-earnings entry likely better
        if dte_after >= 21:
            return GateResult(
                triggered=True,
                verdict="WAIT_FOR_EARNINGS",
                reason=(
                    "Post-earnings entry likely better. Waiting preserves most of "
                    f"window ({dte_after} trading days post-earnings)."
                ),
                gate_id=self.gate_id,
                _dte_after_earnings=dte_after,
                _reevaluate_on=reeval_str,
            )

        # Route 4 — pre-earnings window is the only viable one
        # Score normally with effective_DTE = dte_before, 15-point penalty
        return GateResult(
            triggered=False,
            effective_dte_override=dte_before - 1,
            penalty_points=15,
            reason=(
                f"Earnings {earnings_str} in window. Pre-earnings momentum play: "
                f"effective DTE={dte_before - 1}, 15-point penalty. "
                f"Post-earnings window too short ({dte_after} days)."
            ),
            gate_id=self.gate_id,
        )

    async def _fetch_earnings_date(
        self, symbol: str, db=None
    ) -> Optional[date]:
        """
        Return next_earnings_date from symbol_context, or None if unavailable.

        Uses ContextStore.refresh_if_stale() so a fresh Finnhub fetch only
        happens when the cached TTL has expired (typically 24 h).
        If db is None (e.g. in unit tests), falls back to a standalone session.
        """
        try:
            signal_value = await self._load_signal(symbol, db)
        except Exception as exc:
            logger.error(
                f"EarningsInWindowGate: DB lookup failed for {symbol}: {exc}"
            )
            return None

        if not signal_value:
            return None

        ned_str = signal_value.get("next_earnings_date")
        if not ned_str:
            logger.debug(
                f"EarningsInWindowGate: next_earnings_date is null for {symbol} "
                "(Finnhub returned no data) — not gating"
            )
            return None

        try:
            return date.fromisoformat(ned_str)
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"EarningsInWindowGate: could not parse next_earnings_date "
                f"{ned_str!r} for {symbol}: {exc}"
            )
            return None

    async def _load_signal(self, symbol: str, db=None) -> dict:
        """Load from ContextStore using the provided session or a standalone one."""
        from app.agents.context_store import ContextStore

        if db is not None:
            store = ContextStore(db)
            return await store.refresh_if_stale(symbol, self._source)

        # Fallback: open a short-lived standalone session (e.g. if called outside
        # a request context or in background tasks)
        from app.models.session import async_session
        async with async_session() as standalone_db:
            store = ContextStore(standalone_db)
            return await store.refresh_if_stale(symbol, self._source)
