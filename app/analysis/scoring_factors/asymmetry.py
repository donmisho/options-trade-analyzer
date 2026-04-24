"""
Probability Asymmetry Scoring Factor (OTA-505)

Graduated score penalty applied when the loss/profit probability ratio is
unfavorable. This is a SCORING FACTOR, not a hard gate:
  - Hard gate (OTA-503): binary block when EV is negative.
  - This factor: continuous penalty when probability skew is present but EV
    is still positive. Reduces the final score before band assignment.

Applied post-scoring, pre-band-assignment in evaluation_routes.py.
"""

from typing import Optional


def asymmetry_penalty(p_max_loss: Optional[float], p_max_profit: Optional[float]) -> int:
    """
    Return penalty points (0-25) based on the loss/profit probability ratio.

    Null inputs return 0 — missing probability data should not punish a trade.
    p_max_profit == 0 returns max penalty (25) via explicit early return;
    never divides by zero.

    Boundary thresholds use >= (inclusive):
      ratio >= 2.0  → 25 points
      ratio >= 1.5  → 15 points
      ratio >= 1.25 →  8 points
      ratio <  1.25 →  0 points
    """
    if p_max_loss is None or p_max_profit is None:
        return 0
    if p_max_profit == 0:
        return 25
    ratio = p_max_loss / p_max_profit
    if ratio >= 2.0:
        return 25
    elif ratio >= 1.5:
        return 15
    elif ratio >= 1.25:
        return 8
    return 0


def asymmetry_ratio(p_max_loss: Optional[float], p_max_profit: Optional[float]) -> Optional[float]:
    """
    Diagnostic helper. Returns p_max_loss / p_max_profit, or None when undefined.

    Returns None if either input is None or if p_max_profit is 0 (undefined ratio).
    """
    if p_max_loss is None or p_max_profit is None or p_max_profit == 0:
        return None
    return p_max_loss / p_max_profit
