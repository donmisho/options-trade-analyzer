"""
EarningsInWindowGate — OTA-502.

Hard gate that fires when an earnings event falls inside a trade's hold window.

User framework rule: never hold through earnings.

Two modes:
  ≤ 7 trading days to earnings  → triggered=True, verdict=PASS
                                   (no time to enter and exit before catalyst)
  8-13 trading days to earnings → triggered=False, penalty_points=15,
                                   effective_dte_override = days_to_earnings - 1
                                   (warning band: reduce effective window, penalise)
  > 13 trading days or out of   → GateResult(triggered=False) — no action
  window or earnings unknown

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

        days_to_earnings = _business_days_between(ctx.entry_date, earnings_date)
        earnings_str = earnings_date.isoformat()

        if days_to_earnings <= 7:
            return GateResult(
                triggered=True,
                verdict="PASS",
                reason=(
                    f"Earnings {earnings_str} falls {days_to_earnings} trading "
                    f"days into trade window. Insufficient time to enter and exit "
                    f"before catalyst."
                ),
                gate_id=self.gate_id,
            )
        else:
            # 8-13 trading days: warning band — does not force verdict
            return GateResult(
                triggered=False,
                effective_dte_override=days_to_earnings - 1,
                penalty_points=15,
                reason=(
                    f"Earnings {earnings_str} in window at {days_to_earnings} "
                    f"trading days. Effective DTE reduced to {days_to_earnings - 1}, "
                    f"15-point scoring penalty applied."
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
