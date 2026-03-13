"""
Health Grade Computation (Phase 2.10)

Pure math — no Claude call. Computes an A-F grade for a position based on
current P&L versus entry price, or versus Claude's stored exit levels when
available (Phase 2.11+).

Grade scale:
  A — P&L positive, all clear
  B — slightly negative OR approaching warning, not breached
  C — within 20% of exit warning level (or -10% to -25% P&L fallback)
  D — exit warning level breached (or -25% to -50% P&L fallback)
  F — hard stop hit or max loss (or > -50% P&L fallback)
"""

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


def compute_health_grade(
    entry_price: float,
    current_price: Optional[float],
    claude_exit_levels_json: Optional[str] = None,
) -> str:
    """
    Compute A-F health grade for a position.

    Args:
        entry_price: Price at which the position was entered (net credit/debit per contract).
        current_price: Current mark price of the position.
        claude_exit_levels_json: JSON string of Claude's exit levels dict, if available.
            Expected shape: {"warning": float, "scale_out": float, "stop": float}
            Values are underlying price levels. When present, grade is based on
            proximity to these levels rather than raw P&L percentage.

    Returns:
        Single letter grade string: "A", "B", "C", "D", or "F"
    """
    if current_price is None or entry_price == 0:
        return None  # Cannot grade without both prices

    # ── Try Claude exit-level grading first ─────────────────────────────────
    if claude_exit_levels_json:
        try:
            levels = json.loads(claude_exit_levels_json)
            warning = levels.get("warning")
            stop = levels.get("stop")

            if warning is not None and stop is not None:
                # For a credit spread, current_price here is the underlying.
                # If underlying has moved past stop → F
                # If past warning → D
                # Within 20% of warning → C
                # Otherwise positive / minimal negative → A or B

                # Determine direction: if stop < warning, we're in a bull put spread
                # (underlying fell through). If stop > warning, bear call spread
                # (underlying rose through). Handle both.
                if stop < warning:
                    # Bull put spread / bearish scenario
                    if current_price <= stop:
                        return "F"
                    if current_price <= warning:
                        return "D"
                    buffer = warning - stop
                    if buffer > 0 and current_price <= warning + 0.20 * buffer:
                        return "C"
                else:
                    # Bear call spread / bullish scenario
                    if current_price >= stop:
                        return "F"
                    if current_price >= warning:
                        return "D"
                    buffer = stop - warning
                    if buffer > 0 and current_price >= warning - 0.20 * buffer:
                        return "C"

                pnl_pct = _pnl_pct(entry_price, current_price)
                return "A" if pnl_pct >= 0 else "B"
        except (json.JSONDecodeError, KeyError, TypeError):
            log.debug("health_grade: could not parse claude_exit_levels, falling back to P&L")

    # ── P&L percentage fallback ──────────────────────────────────────────────
    pnl_pct = _pnl_pct(entry_price, current_price)
    return _grade_from_pnl_pct(pnl_pct)


def _pnl_pct(entry_price: float, current_price: float) -> float:
    """
    Return P&L as a fraction of entry price.

    Uses abs(entry_price) so credit spreads (negative entry_price) grade
    correctly: a position moving toward zero from a credit entry is a win.
    Callers must ensure entry_price != 0.
    """
    return (current_price - entry_price) / abs(entry_price)


def _grade_from_pnl_pct(pnl_pct: float) -> str:
    """Map P&L percentage to letter grade."""
    if pnl_pct >= 0:
        return "A"
    if pnl_pct >= -0.10:
        return "B"
    if pnl_pct >= -0.25:
        return "C"
    if pnl_pct >= -0.50:
        return "D"
    return "F"
