"""
Shared Black-Scholes probability computation for OTA adapters.

This module is the designated shared home for the canonical B-S
implementation. The actual computation body is moved here in OTA-716;
until then this is an interface placeholder that establishes the import
path Wave-3.2 adapters depend on.

OTA-713 (placeholder), OTA-716 (body)
"""

from __future__ import annotations

from typing import Any


def compute_probability_matrix(
    *,
    current_price: float,
    strike: float,
    iv: float,
    dte: int,
    risk_free_rate: float = 0.05,
) -> dict[str, Any]:
    """Compute the Black-Scholes probability matrix for a trade.

    Returns a dict with probability data. Body deferred to OTA-716 —
    this stub raises so callers know the implementation isn't wired yet.
    """
    raise NotImplementedError(
        "Black-Scholes body deferred to OTA-716. "
        "Do not call until that story ships."
    )
