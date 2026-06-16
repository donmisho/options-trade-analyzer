"""
Screening gate formulas — registered pre-scoring gates.

OTA-730: Earnings gate — four atomic route formulas.
OTA-836: chart_state_matches_direction — contract-only impl wired live.

Gate formulas return bool:
  True  = gate passed, candidate continues
  False = gate failed, engine checks stop_if_fail / terminal_verdict

Gate behavior (stop/penalty/terminal_verdict) is entirely junction-driven.
The formulas only evaluate conditions — they never set verdicts.

Legacy code superseded:
- app/analysis/hard_gates/earnings_gate.py (EarningsInWindowGate)

OTA-836 note: the five EV-gate formulas (dte_hard_filter, dte_warning_penalty,
credit_pct_of_width_floor, debit_pct_of_width_ceiling, negative_ev_gate) were
DEREGISTERED. They were live in this registry but absent from the formula
contract and referenced by no live formula_ref (the engine's real EV gate is
the total_expected_value BETWEEN rule), so they fired FORMULA_REGISTRY_DRIFT at
startup validation. The app-layer NegativeEVGate HardGate class
(app/analysis/hard_gates/negative_ev_gate.py, registered in main.py) is a
SEPARATE legacy mechanism and is untouched by this removal.

OTA-730, OTA-836
"""

from __future__ import annotations

from app.options_rules.screening import gate_formula


# ── OTA-730: Earnings gate (4 atomic routes) ─────────────────────────────
#
# The adapter provides dte_before_earnings and dte_after_earnings as
# named values (DERIVED from next_earnings_date, entry_date, expiry_date).
# If earnings are not in the trade window, these values are absent/None,
# and all route formulas return True (pass — fail-soft).
#
# Routes are mutually exclusive. Evaluation_order in junctions ensures
# stopping routes (1-3) are checked before the penalty route (4).
#
# Gate semantics: False = gate FAILS = condition matched.
# Route 1 matching means "no viable window" → gate fails → junction halts.


def _earnings_in_window(named_values: dict) -> bool:
    """Check if earnings data is present (earnings in trade window)."""
    return (
        named_values.get("dte_before_earnings") is not None
        and named_values.get("dte_after_earnings") is not None
    )


@gate_formula("earnings_route1_no_viable_window")
def earnings_route1_no_viable_window(named_values: dict, params: dict) -> bool:
    """Route 1: No viable window on either side of earnings.

    Condition: dte_before <= 7 AND dte_after < 14.
    When matched: gate fails → junction halts with terminal_verdict=PASS.

    Params (from junction):
      dte_before_threshold: int (default 7)
      dte_after_threshold: int (default 14)
    """
    if not _earnings_in_window(named_values):
        return True  # no earnings data → pass

    dte_before = named_values["dte_before_earnings"]
    dte_after = named_values["dte_after_earnings"]
    threshold_before = params.get("dte_before_threshold", 7)
    threshold_after = params.get("dte_after_threshold", 14)

    condition_met = dte_before <= threshold_before and dte_after < threshold_after
    return not condition_met  # False when condition matches → gate fails


@gate_formula("earnings_route2_wait_post_window")
def earnings_route2_wait_post_window(named_values: dict, params: dict) -> bool:
    """Route 2: Pre-earnings window too short, strong post-earnings window.

    Condition: dte_before <= 7 AND dte_after >= 14.
    When matched: gate fails → junction halts with terminal_verdict=WAIT_FOR_EARNINGS.

    Params (from junction):
      dte_before_threshold: int (default 7)
      dte_after_threshold: int (default 14)
    """
    if not _earnings_in_window(named_values):
        return True

    dte_before = named_values["dte_before_earnings"]
    dte_after = named_values["dte_after_earnings"]
    threshold_before = params.get("dte_before_threshold", 7)
    threshold_after = params.get("dte_after_threshold", 14)

    condition_met = dte_before <= threshold_before and dte_after >= threshold_after
    return not condition_met


@gate_formula("earnings_route3_post_entry_better")
def earnings_route3_post_entry_better(named_values: dict, params: dict) -> bool:
    """Route 3: Post-earnings entry likely better.

    Condition: dte_before >= 8 AND dte_after >= 21.
    When matched: gate fails → junction halts with terminal_verdict=WAIT_FOR_EARNINGS.

    Params (from junction):
      dte_before_threshold: int (default 8)
      dte_after_threshold: int (default 21)
    """
    if not _earnings_in_window(named_values):
        return True

    dte_before = named_values["dte_before_earnings"]
    dte_after = named_values["dte_after_earnings"]
    threshold_before = params.get("dte_before_threshold", 8)
    threshold_after = params.get("dte_after_threshold", 21)

    condition_met = dte_before >= threshold_before and dte_after >= threshold_after
    return not condition_met


@gate_formula("earnings_route4_pre_momentum_play")
def earnings_route4_pre_momentum_play(named_values: dict, params: dict) -> bool:
    """Route 4: Pre-earnings momentum play.

    Condition: dte_before >= 8 AND dte_after < 21.
    When matched: gate fails → junction applies score_penalty=-15 (non-stopping).

    Params (from junction):
      dte_before_threshold: int (default 8)
      dte_after_threshold: int (default 21)
    """
    if not _earnings_in_window(named_values):
        return True

    dte_before = named_values["dte_before_earnings"]
    dte_after = named_values["dte_after_earnings"]
    threshold_before = params.get("dte_before_threshold", 8)
    threshold_after = params.get("dte_after_threshold", 21)

    condition_met = dte_before >= threshold_before and dte_after < threshold_after
    return not condition_met


# ── OTA-836: Chart-state direction confirmation gate ─────────────────────
#
# Contract-only formula given a live implementation. The rule
# `chart_state_matches_trade_direction` (engine_rules) carries
# formula_ref="formula:chart_state_matches_direction" and binds to the
# directional screening strategies (trend-rider, lottery-ticket) as a
# stop_if_fail gate. Before OTA-836 the formula was in the contract but had no
# live impl, firing FORMULA_REGISTRY_DRIFT / FORMULA_MISSING_FROM_LIVE_REGISTRY.
#
# Behavior (per the formula contract intent): pass when the chart-state
# alignment confirms the trade direction — bullish alignment for a bull trade,
# bearish for a bear trade. Domain-agnostic substring match on "bull"/"bear" so
# it holds regardless of the chart_state value-domain reconciliation tracked by
# OTA-839 (this formula does NOT read/modify chart_state_valid_alignment).


@gate_formula("chart_state_matches_direction")
def chart_state_matches_direction(named_values: dict, params: dict) -> bool:
    """Chart-state alignment must confirm the trade direction.

    Returns True (pass) when the chart state aligns with the trade direction
    (bullish chart for a bull trade, bearish chart for a bear trade), or when
    either input is missing (fail-soft — a missing signal does not gate).
    Returns False (fail) for a directional trade whose chart state does not
    confirm it (e.g. Mixed/Neutral, or alignment opposite the trade).

    Reads: chart_state, trade_direction.
    """
    chart_state = named_values.get("chart_state")
    trade_direction = named_values.get("trade_direction")
    if chart_state is None or trade_direction is None:
        return True  # fail-soft: missing signal does not gate

    cs = str(chart_state).lower()
    td = str(trade_direction).lower()
    if "bull" in td:
        return "bull" in cs
    if "bear" in td:
        return "bear" in cs
    return True  # unknown/neutral direction → do not gate
