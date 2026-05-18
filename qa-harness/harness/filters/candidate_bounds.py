"""
Candidate bound filters applied before capture.

Filters:
  - Vertical spread width must be in ALLOWED_WIDTHS
  - All candidates: |strike - underlying| / underlying <= STRIKE_WINDOW_PCT
"""

from typing import List, Dict, Any
from harness.config import ALLOWED_WIDTHS, STRIKE_WINDOW_PCT


def filter_verticals(spreads: List[Dict[str, Any]], underlying_price: float) -> List[Dict[str, Any]]:
    """Filter vertical spreads by width and strike window."""
    if underlying_price <= 0:
        return spreads

    result = []
    for s in spreads:
        width = abs(s.get("long_strike", 0) - s.get("short_strike", 0))
        if width not in ALLOWED_WIDTHS:
            continue

        # Anchor strike: short leg for credit, long leg for debit
        spread_type = s.get("spread_type", "")
        if spread_type in ("bull_put", "bear_call"):
            anchor = s.get("short_strike", 0)
        else:
            anchor = s.get("long_strike", 0)

        if underlying_price > 0 and abs(anchor - underlying_price) / underlying_price > STRIKE_WINDOW_PCT:
            continue

        result.append(s)
    return result


def filter_long_options(options: List[Dict[str, Any]], underlying_price: float) -> List[Dict[str, Any]]:
    """Filter long options by strike window."""
    if underlying_price <= 0:
        return options

    result = []
    for o in options:
        strike = o.get("strike", 0)
        if underlying_price > 0 and abs(strike - underlying_price) / underlying_price > STRIKE_WINDOW_PCT:
            continue
        result.append(o)
    return result
