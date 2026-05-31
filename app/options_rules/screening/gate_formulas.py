"""
Screening gate formulas — registered pre-scoring gates.

OTA-730: Earnings gate — four atomic route formulas.
OTA-731: Negative EV gate — single consolidated formula.

Gate formulas return bool:
  True  = gate passed, candidate continues
  False = gate failed, engine checks stop_if_fail / terminal_verdict

Gate behavior (stop/penalty/terminal_verdict) is entirely junction-driven.
The formulas only evaluate conditions — they never set verdicts.

Legacy code superseded:
- app/analysis/hard_gates/earnings_gate.py (EarningsInWindowGate)
- app/analysis/hard_gates/negative_ev_gate.py (NegativeEVGate)
- app/analysis/vertical_engine.py:265 (duplicate EV filter)

OTA-730, OTA-731
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


# ── OTA-731: Negative EV gate ────────────────────────────────────────────
#
# Consolidates:
# 1. NegativeEVGate (hard_gates/negative_ev_gate.py) — class-based gate
# 2. vertical_engine.py:265 — inline filter: ev_raw >= min_ev_threshold
#
# Both enforce the same rule: negative EV trades must not pass.
# The engine rule replaces both with a single registered formula.
#
# Semantics:
#   ev_raw < 0 (or < threshold) → False (gate fails → junction halts)
#   ev_raw >= 0 (or None)       → True (gate passes — fail-soft)


# ── OTA-780: DTE gates ──────────────────────────────────────────────────


@gate_formula("dte_hard_filter")
def dte_hard_filter(named_values: dict, params: dict) -> bool:
    """Block trades with DTE at or below the hard threshold.

    Returns True (pass) when DTE is above threshold.
    Returns False (fail) when DTE <= threshold.

    Params (from junction):
      threshold: int (default 7)
    """
    dte = named_values.get("dte")
    if dte is None:
        return True  # fail-soft: missing DTE data

    threshold = params.get("threshold", 7)
    return dte > threshold


@gate_formula("dte_warning_penalty")
def dte_warning_penalty(named_values: dict, params: dict) -> bool:
    """Flag trades in the DTE warning band (8-13 DTE).

    Returns True (pass) when DTE is outside the warning band.
    Returns False (fail) when DTE is in [dte_low, dte_high].

    When failed with stop_if_fail=false, junction's score_penalty is applied.

    Params (from junction):
      dte_low: int (default 8)
      dte_high: int (default 13)
    """
    dte = named_values.get("dte")
    if dte is None:
        return True

    dte_low = params.get("dte_low", 8)
    dte_high = params.get("dte_high", 13)
    condition_met = dte_low <= dte <= dte_high
    return not condition_met  # False when in warning band → gate fails


# ── OTA-780: Credit/debit quality gates ────────────────────────────────


@gate_formula("credit_pct_of_width_floor")
def credit_pct_of_width_floor(named_values: dict, params: dict) -> bool:
    """Block credit spreads where credit is below minimum % of spread width.

    Returns True (pass) when credit_pct >= threshold or not a credit spread.
    Returns False (fail) when credit_pct < threshold.

    Params (from junction):
      threshold: float (default 0.30)
    """
    net_debit = named_values.get("net_debit")
    spread_width = named_values.get("spread_width")
    if net_debit is None or spread_width is None or spread_width <= 0:
        return True  # fail-soft
    if net_debit >= 0:
        return True  # not a credit spread

    credit_pct = abs(net_debit) / spread_width
    threshold = params.get("threshold", 0.30)
    return credit_pct >= threshold


@gate_formula("debit_pct_of_width_ceiling")
def debit_pct_of_width_ceiling(named_values: dict, params: dict) -> bool:
    """Block debit spreads where debit exceeds maximum % of spread width.

    Returns True (pass) when debit_pct <= threshold or not a debit spread.
    Returns False (fail) when debit_pct > threshold.

    Params (from junction):
      threshold: float (default 0.40)
    """
    net_debit = named_values.get("net_debit")
    spread_width = named_values.get("spread_width")
    if net_debit is None or spread_width is None or spread_width <= 0:
        return True  # fail-soft
    if net_debit <= 0:
        return True  # not a debit spread

    debit_pct = net_debit / spread_width
    threshold = params.get("threshold", 0.40)
    return debit_pct <= threshold


@gate_formula("negative_ev_gate")
def negative_ev_gate(named_values: dict, params: dict) -> bool:
    """Block trades with negative expected value.

    Returns True (pass) when EV is non-negative or absent.
    Returns False (fail) when EV is below threshold.

    Params (from junction):
      threshold: float (default 0.0) — EV must be >= this value
    """
    ev_raw = named_values.get("ev_raw")
    if ev_raw is None:
        return True  # fail-soft: missing EV ≠ negative EV

    threshold = params.get("threshold", 0.0)
    return ev_raw >= threshold
