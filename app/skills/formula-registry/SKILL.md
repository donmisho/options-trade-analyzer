---
name: formula-registry
version: 1.0.0
description: >
  Options consumer formula registry — the human-readable companion to the live
  rule library registered by app/options_rules/screening. Documents every
  formula:<name> the OTA (options) consumer registers, grouped by family
  (gate / scoring / adjustment), each with its true return type, parameter
  schema, and required named-value inputs.
---

# Options Formula Registry — formula-registry/SKILL.md (Updated 2026-06-01 00:00 UTC)

This file documents the **options consumer's** registered formula rule library — the
set returned by `get_registry().registered_names()` in
`app/options_rules/screening/__init__.py`. It is the human-readable companion to the
live registry; the live `DictFormulaRegistry` is the runtime contract.

This is the **options/`OTA`** consumer library only. It is **not** the cross-app
`('SHARED','formula_registry')` lookup union, and it is not a multi-consumer registry.
Other consumers (directional, position-health) register their own libraries and are
documented elsewhere (see `insight_engine.md` §7.3).

---

### Overview (`OVERVIEW`)

```
The Insight Engine resolves a rule's condition expression of the form
`formula:<name>` by looking <name> up in the registered rule library for the
consumer being loaded, then calling the implementation with the candidate's
named values and the rule's junction-bound parameters
(insight_engine.md §6.3). At startup the loader rejects the configuration if a
condition expression references a named formula not in that registered rule
library (insight_engine.md §6.6). The comparison target for the options
consumer is the OPTIONS library enumerated here — never the SHARED cross-app
union.

Every options formula is a pure function with the call shape
`(named_values, params) -> result`, where:
  - `named_values` is the candidate's input catalog (Greeks, prices, DTE, etc.),
    produced by the options input adapter — never computed by the engine.
  - `params` is the rule's junction-bound parameter set (thresholds, scales,
    bands). Formulas read configurable values from `params`, never from literals.

There are three formula families, each with a distinct return type. The single
signature `(named_values, params) -> float in [0, 100]` describes only the
scoring family; gate and adjustment families return other types:

  - Gate formulas        -> bool
        Registered via @gate_formula. True = gate passed (candidate continues);
        False = gate condition matched (engine then applies the junction's
        stop_if_fail / score_penalty / terminal_verdict). Gates are fail-soft on
        missing inputs (return True). The formula evaluates the condition only;
        verdict/halt behavior is entirely junction-driven.

  - Scoring formulas     -> float, clamped to [0, 100]
        Registered via @screening_formula. The decorator validates the return
        value is a number in [0, 100] on every invocation and raises
        FormulaReturnValueError otherwise.

  - Adjustment formulas  -> bool | signed float
        Registered via @adjustment_formula. A bool result of False triggers the
        junction's score_penalty; a numeric result (which may be negative) is
        added directly to the score. No [0, 100] clamping is applied at the
        formula; the engine clamps after applying the delta.

Counts: 9 gate, 16 scoring, 2 adjustment = 27 formulas.
```

---

### Gate formulas (`GATE_FORMULAS`)

```
Return type: bool. Params show their in-code default; the runtime value comes
from the junction row. Inputs are the named values the implementation reads.

credit_pct_of_width_floor       -> bool
  Intent : Block credit spreads whose credit is below the minimum % of spread
           width. Pass when not a credit spread or credit_pct >= threshold.
  Params : threshold (default 0.30)
  Inputs : net_debit, spread_width

debit_pct_of_width_ceiling      -> bool
  Intent : Block debit spreads whose debit exceeds the maximum % of spread
           width. Pass when not a debit spread or debit_pct <= threshold.
  Params : threshold (default 0.40)
  Inputs : net_debit, spread_width

dte_hard_filter                 -> bool
  Intent : Block trades at or below the hard DTE threshold. Pass when
           dte > threshold.
  Params : threshold (default 7)
  Inputs : dte

dte_warning_penalty             -> bool
  Intent : Flag trades in the DTE warning band. Fail (False) when
           dte_low <= dte <= dte_high; with stop_if_fail=false the junction's
           score_penalty applies.
  Params : dte_low (default 8), dte_high (default 13)
  Inputs : dte

earnings_route1_no_viable_window    -> bool
  Intent : Earnings Route 1 — no viable window: dte_before <= threshold and
           dte_after < threshold. Matched → junction halts (terminal_verdict
           PASS). Fail-soft (True) when earnings not in window.
  Params : dte_before_threshold (default 7), dte_after_threshold (default 14)
  Inputs : dte_before_earnings, dte_after_earnings

earnings_route2_wait_post_window    -> bool
  Intent : Earnings Route 2 — pre-earnings window too short, post-earnings
           window viable: dte_before <= threshold and dte_after >= threshold.
           Matched → junction halts (terminal_verdict WAIT_FOR_EARNINGS).
  Params : dte_before_threshold (default 7), dte_after_threshold (default 14)
  Inputs : dte_before_earnings, dte_after_earnings

earnings_route3_post_entry_better   -> bool
  Intent : Earnings Route 3 — post-earnings entry likely better: dte_before >=
           threshold and dte_after >= threshold. Matched → junction halts
           (terminal_verdict WAIT_FOR_EARNINGS).
  Params : dte_before_threshold (default 8), dte_after_threshold (default 21)
  Inputs : dte_before_earnings, dte_after_earnings

earnings_route4_pre_momentum_play   -> bool
  Intent : Earnings Route 4 — pre-earnings momentum play: dte_before >=
           threshold and dte_after < threshold. Matched → non-stopping; junction
           applies score_penalty (-15).
  Params : dte_before_threshold (default 8), dte_after_threshold (default 21)
  Inputs : dte_before_earnings, dte_after_earnings

negative_ev_gate                -> bool
  Intent : Block trades with negative expected value. Pass when ev_raw is absent
           (fail-soft) or ev_raw >= threshold.
  Params : threshold (default 0.0)
  Inputs : ev_raw
```

---

### Scoring formulas (`SCORING_FORMULAS`)

```
Return type: float, clamped to [0, 100] by the @screening_formula decorator.
Params show their in-code default; the runtime value comes from the junction
row. Inputs are the named values the implementation reads.

bid_ask_tightness               -> float [0, 100]
  Intent : Inverse of bid-ask spread percentage. Tighter spreads score higher.
  Params : max_spread_pct (default 100.0)
  Inputs : bid_ask_spread_pct

credit_width                    -> float [0, 100]
  Intent : Net credit received as a percentage of spread width.
  Params : (none)
  Inputs : net_debit, spread_width

delta_otm_score                 -> float [0, 100]
  Intent : How far out-of-the-money. Lower delta = more OTM = higher score.
  Params : max_delta (default 0.25)
  Inputs : delta

delta_quality                   -> float [0, 100]
  Intent : Gaussian-like peak around a target delta range.
  Params : delta_center (default 0.35), delta_half_range (default 0.15),
           smoothing (default 0.05)
  Inputs : delta

expected_value                  -> float [0, 100]
  Intent : Expected value of the trade. Credit-spread path uses precomputed
           ev_raw; long-option path uses delta/underlying/mid as an EV proxy.
  Params : scale (default 1.0), move_pct (default 0.05, long path)
  Inputs : ev_raw (credit path); otherwise delta, underlying_price, mid_price

iv_percentile_cost              -> float [0, 100]
  Intent : Linear inversion of raw IV. Lower IV scores higher.
  Params : max_iv (default 1.0)
  Inputs : iv

iv_rank                         -> float [0, 100]
  Intent : IV rank score. True path uses iv_rank; proxy path uses ATM IV /
           divisor.
  Params : divisor (default 0.60)
  Inputs : iv_rank (true path); otherwise atm_iv

liquidity                       -> float [0, 100]
  Intent : Combined liquidity from both legs' volume and open interest.
  Params : scale (default 10000.0)
  Inputs : long_volume, short_volume, long_oi, short_oi

open_interest                   -> float [0, 100]
  Intent : Open interest as a scoring signal.
  Params : scale (default 10000.0)
  Inputs : open_interest

payout_ratio                    -> float [0, 100]
  Intent : Expected payout multiple on a configured underlying move, relative to
           premium paid.
  Params : move_pct (default 0.10), multiplier (default 100.0), scale (default 10.0)
  Inputs : delta, underlying_price, premium_dollars

probability_of_profit           -> float [0, 100]
  Intent : Probability of profit, derived from option delta (already 0-100 scale
           from the engine).
  Params : (none)
  Inputs : prob_of_profit

reward_risk                     -> float [0, 100]
  Intent : Ratio of max profit to max loss.
  Params : scale (default 100.0)
  Inputs : reward_risk_ratio; otherwise max_profit, max_loss

runway_score                    -> float [0, 100]
  Intent : How many days of theta the premium can sustain.
  Params : scale (default 100.0)
  Inputs : theta_runway_days

sma_alignment_score             -> float [0, 100]
  Intent : Score from SMA alignment classification
           (BULLISH/BEARISH/NEUTRAL/MIXED), with a fallback default.
  Params : bullish_score (default 100.0), bearish_score (default 0.0),
           neutral_score (default 50.0), mixed_score (default 25.0),
           default_score (default 50.0)
  Inputs : sma_alignment_classification

theta_gamma_ratio               -> float [0, 100]
  Intent : Ratio of theta decay to gamma risk (proxy: abs(net_theta) / max_loss).
  Params : scale (default 100.0)
  Inputs : net_theta, max_loss

theta_margin_ratio              -> float [0, 100]
  Intent : Daily theta decay as a fraction of max loss (margin at risk).
  Params : scale (default 100.0)
  Inputs : net_theta, max_loss
```

---

### Adjustment formulas (`ADJUSTMENT_FORMULAS`)

```
Return type: bool or signed float. A bool False triggers the junction's
score_penalty; a numeric result is added directly to the score (may be
negative). No [0, 100] clamping is applied by the formula. Params show their
in-code default where one exists; cushion_penalty_moderate's thresholds are
required (supplied by the junction). Inputs are the named values the
implementation reads.

cushion_penalty_moderate        -> bool
  Intent : Moderate cushion-proximity check. Returns False (triggers the
           junction's score_penalty, -10) when cushion_pct is in the moderate
           band [lower_threshold, upper_threshold); True otherwise. Missing data
           → True (no penalty).
  Params : lower_threshold (required), upper_threshold (required)
  Inputs : cushion_pct

probability_asymmetry_penalty   -> signed float
  Intent : Graduated penalty based on loss/profit probability ratio. ratio >=
           band_severe → penalty_severe; >= band_high → penalty_high; >=
           band_moderate → penalty_moderate; otherwise 0.0. Missing data → 0.0.
           The formula supplies the penalty amount directly (junction
           score_penalty is None).
  Params : band_severe (default 2.0), band_high (default 1.5),
           band_moderate (default 1.25), penalty_severe (default -25),
           penalty_high (default -15), penalty_moderate (default -8)
  Inputs : p_max_loss, p_max_profit
```

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-06-01 00:00 UTC | OTA-810 | Initial authoring. Documents the live options consumer formula registry (`app/options_rules/screening`): 9 gate, 16 scoring, 2 adjustment = 27 formulas. Each formula lists its true return type by family (gate `bool` / scoring `float [0,100]` / adjustment `bool \| signed float`), parameter schema, and required named-value inputs. |
