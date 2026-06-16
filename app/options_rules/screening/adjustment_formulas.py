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


# ── OTA-836: extension-matches-direction (contract-only impl) ─────────────
#
# Contract-only formula given a live implementation. The rule
# `adj_stock_extended_direction_match` carries
# formula_ref="formula:extension_matches_trade_direction" and binds to all four
# screening strategies. Before OTA-836 it was in the contract with no live impl
# (FORMULA_REGISTRY_DRIFT / FORMULA_MISSING_FROM_LIVE_REGISTRY at startup).
#
# Behavior is implemented to the formula contract intent: returns True when the
# stock's extension direction matches the trade direction (price above SMA-50
# for a bull trade, below for a bear trade). The engine's adjustment runner
# (pipeline._run_adjustments) maps True → no penalty, False → junction penalty;
# the penalty-direction *semantics* of this adjustment are a rule-correctness
# question deferred to backtesting (OTA-836 hard constraint: no rule tuning),
# since this formula has never executed at runtime before.


@adjustment_formula("extension_matches_trade_direction")
def extension_matches_trade_direction(named_values: dict, params: dict) -> bool:
    """Does the stock's extension direction match the trade direction?

    Returns True when price is above SMA-50 for a bull trade (or below SMA-50
    for a bear trade), or when any input is missing (fail-soft — no penalty).

    Reads: stock_price, sma_50, trade_direction.
    """
    stock_price = named_values.get("stock_price")
    sma_50 = named_values.get("sma_50")
    trade_direction = named_values.get("trade_direction")
    if stock_price is None or sma_50 is None or trade_direction is None:
        return True  # missing data → no penalty

    td = str(trade_direction).lower()
    if "bull" in td:
        return stock_price > sma_50
    if "bear" in td:
        return stock_price < sma_50
    return True  # unknown direction → no penalty


# ── OTA-836: DTE 8-13 penalty (new formula) ──────────────────────────────
#
# Replaces the non-§6.3 condition_expression "dte >= 8 AND dte <= 13" on the
# code-only rule `adj_dte_8_13_penalty` (bound to all four screening
# strategies), which the §6.3 loader rejected and blocked load_config.
# Replicates the confirmed behavior exactly: -20 when 8 <= dte <= 13, else 0.
# Returns the amount directly (like probability_asymmetry_penalty) so the
# junction's score_penalty does not double the effect.


@adjustment_formula("adj_dte_8_13_penalty")
def adj_dte_8_13_penalty(named_values: dict, params: dict) -> float:
    """Near-expiry penalty: -20 points when 8 <= dte <= 13, else 0.

    Reads: dte. Params (from junction): dte_low (8), dte_high (13),
    penalty (-20).
    """
    dte = named_values.get("dte")
    if dte is None:
        return 0.0  # missing data → no penalty

    dte_low = params.get("dte_low", 8)
    dte_high = params.get("dte_high", 13)
    penalty = params.get("penalty", -20)
    return float(penalty) if dte_low <= dte <= dte_high else 0.0


# ── OTA-836: SMA-alignment-against-trade penalty (new formula) ────────────
#
# Replaces the non-§6.3 workbook condition "REDUCE SCORE BY 15 IF price is
# positioned against the trade direction across all 3 SMAs" on the rule
# `adj_sma_alignment_against_trade` (bound to steady-paycheck + weekly-grind),
# which blocked load_config. Cross-field (price vs sma_8/21/50 vs
# trade_direction) → cannot be a §6.3 atom, so it is a formula. Replicates the
# captured penalty: -15 when price is on the wrong side of all three SMAs for
# the trade direction, else 0.


@adjustment_formula("adj_sma_alignment_against_trade")
def adj_sma_alignment_against_trade(named_values: dict, params: dict) -> float:
    """-15 when price is positioned against the trade direction across all 3 SMAs.

    "Against" = price below all of SMA-8/21/50 for a bull trade, or above all
    three for a bear trade. Returns 0 otherwise or when any input is missing.

    Reads: stock_price, sma_8, sma_21, sma_50, trade_direction.
    Params (from junction): penalty (-15).
    """
    price = named_values.get("stock_price")
    sma_8 = named_values.get("sma_8")
    sma_21 = named_values.get("sma_21")
    sma_50 = named_values.get("sma_50")
    trade_direction = named_values.get("trade_direction")
    if None in (price, sma_8, sma_21, sma_50, trade_direction):
        return 0.0  # missing data → no penalty

    penalty = params.get("penalty", -15)
    td = str(trade_direction).lower()
    below_all = price < sma_8 and price < sma_21 and price < sma_50
    above_all = price > sma_8 and price > sma_21 and price > sma_50
    if "bull" in td and below_all:
        return float(penalty)
    if "bear" in td and above_all:
        return float(penalty)
    return 0.0
