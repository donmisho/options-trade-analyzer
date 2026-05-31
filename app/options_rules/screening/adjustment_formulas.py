"""
Screening post-scoring adjustment formulas.

OTA-728: Cushion penalty — moderate band check (bool-returning).
OTA-729: Probability asymmetry penalty — graduated penalty by ratio bands.

Adjustment formulas use @adjustment_formula, NOT @screening_formula,
because they return bool or negative floats — not [0, 100] scores.

The engine's _run_adjustments (pipeline.py:378-418) handles:
  - bool result: True → no penalty, False → apply -(junction.score_penalty)
  - numeric result: added directly to score (can be negative)

Thresholds and penalties come from params (junction rows), not literals.

Legacy code superseded:
- app/analysis/strategy_scorer.py:114-142 (cushion_penalty)
- app/analysis/scoring_factors/asymmetry.py (asymmetry_penalty)

OTA-728, OTA-729
"""

from __future__ import annotations

from app.options_rules.screening import adjustment_formula


# ── OTA-728: Cushion penalty (moderate band) ─────────────────────────────
#
# The cushion penalty is decomposed into two atomic adjustment rules
# (seeded under OTA-680 / OTA-683):
#
#   adj_cushion_penalty_severe:
#     condition_expression: "cushion_pct < 1.0"
#     score_penalty: -20 (from junction)
#     → Pure comparison rule — engine evaluates directly. No formula needed.
#
#   adj_cushion_penalty_moderate:
#     formula_ref: "formula:cushion_penalty_moderate"
#     score_penalty: -10 (from junction)
#     → This formula. Returns False when cushion_pct is in [lower, upper),
#       which triggers the junction's score_penalty.


@adjustment_formula("cushion_penalty_moderate")
def cushion_penalty_moderate(named_values: dict, params: dict) -> bool:
    """Moderate cushion proximity check.

    Returns True (pass, no penalty) when cushion_pct is NOT in the
    moderate band. Returns False (triggers junction score_penalty)
    when cushion_pct IS in [lower_threshold, upper_threshold).

    The severe band (cushion_pct < severe_threshold) is handled by
    the adj_cushion_penalty_severe condition_expression rule.

    Params (required, from junction — OTA-770):
      lower_threshold: float — inclusive lower bound of moderate band
      upper_threshold: float — exclusive upper bound of moderate band
    """
    cushion_pct = named_values.get("cushion_pct")
    if cushion_pct is None:
        return True  # missing data → no penalty

    lower = params["lower_threshold"]
    upper = params["upper_threshold"]

    in_moderate_band = lower <= cushion_pct < upper
    return not in_moderate_band  # False when in band → triggers penalty


# ── OTA-729: Probability asymmetry penalty ───────────────────────────────
#
# Graduated penalty based on loss/profit probability ratio.
# Returns the penalty amount as a negative float (added directly to score).
# Junction score_penalty is None — the formula provides the amount.
#
# Legacy from scoring_factors/asymmetry.py:16-41:
#   ratio >= 2.0  → -25
#   ratio >= 1.5  → -15
#   ratio >= 1.25 → -8
#   ratio <  1.25 → 0


@adjustment_formula("probability_asymmetry_penalty")
def probability_asymmetry_penalty(named_values: dict, params: dict) -> float:
    """Graduated penalty based on loss/profit probability ratio.

    Returns a negative penalty amount (or 0.0 for no penalty).
    The engine adds this value directly to the score.

    Params (from junction):
      band_severe: float (default 2.0) — ratio threshold for severe penalty
      band_high: float (default 1.5) — ratio threshold for high penalty
      band_moderate: float (default 1.25) — ratio threshold for moderate penalty
      penalty_severe: float (default -25) — penalty for severe band
      penalty_high: float (default -15) — penalty for high band
      penalty_moderate: float (default -8) — penalty for moderate band
    """
    p_max_loss = named_values.get("p_max_loss")
    p_max_profit = named_values.get("p_max_profit")

    if p_max_loss is None or p_max_profit is None:
        return 0.0  # missing data → no penalty

    if p_max_profit == 0:
        return float(params.get("penalty_severe", -25))

    ratio = p_max_loss / p_max_profit

    band_severe = params.get("band_severe", 2.0)
    band_high = params.get("band_high", 1.5)
    band_moderate = params.get("band_moderate", 1.25)

    if ratio >= band_severe:
        return float(params.get("penalty_severe", -25))
    elif ratio >= band_high:
        return float(params.get("penalty_high", -15))
    elif ratio >= band_moderate:
        return float(params.get("penalty_moderate", -8))

    return 0.0
