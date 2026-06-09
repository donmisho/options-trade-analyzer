"""
Directional comparison scoring criteria — 8 registered formula implementations.

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

OTA-834 adds four criteria for the three-objective directional model
(expected value, budget consumption, reward-to-risk, target payoff),
unified across debit spreads and naked longs:
    dir_expected_value   reads ev_raw (spreads) else total_ev (naked longs)
    dir_max_loss_pct     max_loss / thesis_risk_budget — budget consumption
    dir_reward_risk      reward_risk_ratio; null (naked, unlimited) -> 100
    dir_payoff_multiple  payoff at thesis_target_price (naked) / RR (spreads)

OTA-755, OTA-834
"""

from __future__ import annotations

import math

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


# ── OTA-834 — three-objective directional criteria ─────────────────────


@directional_formula("dir_expected_value")
def dir_expected_value(named_values: dict, params: dict) -> float:
    """Expected value scaled to [0, 100], unified across structures.

    Reads ``ev_raw`` (DERIVED — populated for debit spreads) when present,
    else ``total_ev`` (COMPUTED — populated for naked longs via Black-Scholes).
    A break-even EV (0) scores ``neutral_score`` (default 50); positive EV
    scales toward 100 and negative toward 0 via a tanh curve whose width is
    ``ev_scale`` dollars (default 100).

    When neither EV value is available, returns ``null_score`` (default 50)
    so a missing EV neither rewards nor punishes the candidate.
    """
    ev = named_values.get("ev_raw")
    if ev is None:
        ev = named_values.get("total_ev")
    if ev is None:
        return float(params.get("null_score", 50.0))
    mid = float(params.get("neutral_score", 50.0))
    scale = float(params.get("ev_scale", 100.0)) or 1.0
    score = mid + 50.0 * math.tanh(float(ev) / scale)
    return min(100.0, max(0.0, score))


@directional_formula("dir_max_loss_pct")
def dir_max_loss_pct(named_values: dict, params: dict) -> float:
    """Budget consumption: max_loss as a fraction of the thesis risk budget.

    ``consumption = max_loss / thesis_risk_budget``. Lower consumption scores
    higher: ``score = 100 * (1 - min(consumption / full_consumption, 1))``.
    ``full_consumption`` (default 1.0) is the fraction at which the score
    reaches 0 — a trade that risks the entire budget scores 0, one that risks
    nothing scores 100.

    Returns ``null_score`` (default 0) when the budget is missing/non-positive
    or max_loss is absent — an undefinable budget fit is treated as no fit.
    """
    max_loss = named_values.get("max_loss")
    budget = named_values.get("thesis_risk_budget")
    if max_loss is None or budget is None or budget <= 0:
        return float(params.get("null_score", 0.0))
    full = float(params.get("full_consumption", 1.0)) or 1.0
    consumption = float(max_loss) / float(budget)
    score = 100.0 * (1.0 - min(consumption / full, 1.0))
    return min(100.0, max(0.0, score))


@directional_formula("dir_reward_risk")
def dir_reward_risk(named_values: dict, params: dict) -> float:
    """Reward-to-risk ratio scaled to [0, 100].

    Reads ``reward_risk_ratio`` (DERIVED). A null ratio means a naked long
    (unlimited upside, undefined ratio) → returns ``null_score`` (default 100).
    For defined-risk structures the score scales linearly:
    ``score = min(100, rr / full_score_ratio * 100)`` so a ratio of
    ``full_score_ratio`` (default 2.0) or better maxes the criterion.
    """
    rr = named_values.get("reward_risk_ratio")
    if rr is None:
        return float(params.get("null_score", 100.0))
    full = float(params.get("full_score_ratio", 2.0)) or 1.0
    score = float(rr) / full * 100.0
    return min(100.0, max(0.0, score))


@directional_formula("dir_payoff_multiple")
def dir_payoff_multiple(named_values: dict, params: dict) -> float:
    """Target-based payoff multiple scaled to [0, 100].

    Naked longs: the multiple is the contract payoff at the thesis target
    price over its cost — intrinsic value at ``thesis_target_price`` (call:
    ``target - strike``; put: ``strike - target``) times 100, divided by
    ``cost``. Spreads: the multiple is ``reward_risk_ratio``
    (max_profit / max_loss).

    ``score = min(100, multiple / full_multiple * 100)``; a multiple of
    ``full_multiple`` (default 2.0) or better maxes the criterion. Returns
    ``null_score`` (default 0) when the multiple cannot be computed.
    """
    null_score = float(params.get("null_score", 0.0))
    full = float(params.get("full_multiple", 2.0)) or 1.0
    structure = named_values.get("structure_type", "")

    if structure == "long_option":
        cost = named_values.get("cost")
        strike = named_values.get("strike")
        target = named_values.get("thesis_target_price")
        option_type = named_values.get("option_type", "call")
        if not cost or cost <= 0 or strike is None or not target or target <= 0:
            return null_score
        if option_type == "put":
            intrinsic = max(0.0, float(strike) - float(target))
        else:
            intrinsic = max(0.0, float(target) - float(strike))
        multiple = (intrinsic * 100.0) / float(cost)
    else:
        rr = named_values.get("reward_risk_ratio")
        if rr is None:
            return null_score
        multiple = float(rr)

    score = multiple / full * 100.0
    return min(100.0, max(0.0, score))
