"""
Directional comparison scoring criteria — 4 registered formula implementations.

Each formula is pure: (named_values, params) -> float in [0, 100].
Thresholds and configurable values come from params (junction rows),
never from literals.

These formulas decompose the legacy fitness_score from
app/analysis/directional_engine.py:458-469 into atomic scoring criteria
registered under formula:<name> references.

Legacy fitness_score (max 85 raw points):
    +20  if fits_budget                          -> dir_budget_fit
    +prob_of_profit * 30                         -> dir_probability
    +min(buffer_pct, 10) * 3                     -> dir_buffer
    +5   if strategy_type == "vertical_spread"   -> dir_defined_risk

Junction weights normalise these to sum=1.0:
    budget_fit=0.235, probability=0.353, buffer=0.353, defined_risk=0.059

KNOWN DIVERGENCE from legacy:
    The legacy fitness_score allows negative buffer_pct to produce negative
    contributions (e.g. buffer=-5 -> -15 points), which can pull the total
    score below zero. The engine's formula contract requires [0, 100], so
    dir_buffer clamps at 0. Negative buffer candidates score 0 on the
    buffer criterion rather than dragging down the total. This is an
    intentional improvement: the engine's per-criterion [0, 100] contract
    prevents one criterion from offsetting another's contribution.

OTA-755
"""

from __future__ import annotations

from app.options_rules.directional import directional_formula


@directional_formula("dir_budget_fit")
def dir_budget_fit(named_values: dict, params: dict) -> float:
    """Binary: does the trade cost fit within the thesis risk budget?

    Returns fit_score (default 100) if fits_budget is truthy,
    no_fit_score (default 0) otherwise.

    Legacy: +20 if candidate.fits_budget else 0
    """
    fits = named_values.get("fits_budget", False)
    if fits:
        return float(params.get("fit_score", 100))
    return float(params.get("no_fit_score", 0))


@directional_formula("dir_probability")
def dir_probability(named_values: dict, params: dict) -> float:
    """Probability of profit scaled to [0, 100].

    prob_of_profit is 0.0-1.0 from delta. Multiplied by scale (default 100).

    Legacy: prob_of_profit * 30 (max 30 points out of 85)
    """
    pop = named_values.get("prob_of_profit", 0)
    scale = params.get("scale", 100)
    return min(100.0, max(0.0, float(pop) * scale))


@directional_formula("dir_buffer")
def dir_buffer(named_values: dict, params: dict) -> float:
    """Buffer between breakeven and thesis target, capped and scaled.

    buffer_pct = abs(target_move) - abs(required_move). More buffer = more
    room for thesis imprecision. Capped at `cap` (default 10) to prevent
    diminishing returns from dominating the score.

    Formula: max(0, min(buffer_pct, cap)) / cap * scale

    Legacy: min(buffer_pct, 10) * 3 (max 30 points out of 85)
    Divergence: legacy allows negative contributions; engine clamps at 0.
    """
    buffer_pct = named_values.get("buffer_pct")
    if buffer_pct is None:
        return 0.0
    cap = params.get("cap", 10)
    scale = params.get("scale", 100)
    if cap <= 0:
        return 0.0
    clamped = max(0.0, min(float(buffer_pct), cap))
    return min(100.0, clamped / cap * scale)


@directional_formula("dir_defined_risk")
def dir_defined_risk(named_values: dict, params: dict) -> float:
    """Preference for defined-risk structures (vertical spreads).

    Returns spread_score (default 100) for vertical spreads,
    naked_score (default 0) for naked options.

    Legacy: +5 if strategy_type == "vertical_spread" else 0
    """
    structure = named_values.get("structure_type", "")
    if structure == "vertical_spread":
        return float(params.get("spread_score", 100))
    return float(params.get("naked_score", 0))
