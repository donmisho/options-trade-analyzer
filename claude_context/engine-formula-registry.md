# Engine Formula Registry

> **Status:** 36 formulas registered (26 screening + 10 directional) · 2026-06-10
> **Scope:** Complete, deduplicated list of every `formula:<name>` reference in `engine_rules.formula_ref`, plus formulas registered in a live surface registry. Each entry is the implementation contract for the rule library. The engine's startup validation (OTA-699, `insight_engine.md` §6.6) checks that every reference resolves to both a registered lookup row and a live implementation.
>
> **Dual-validation contract:** This doc and the SHARED `engine_lookups.formula_registry` set must agree row-for-row. The lookup payloads carry the same intent/signature/notes as this doc. Drift between them is a defect class OTA-699 will catch.
>
> **Combined registry (OTA-840):** there is one SHARED contract validated against the **union** of every surface's live registry (screening ∪ directional). The drift check is global; the per-surface formula-in-live check resolves each surface's formulas through the union. So both screening and directional formulas live in this single contract.
>
> **Change Log**
> | Date | Change |
> |---|---|
> | 2026-05-28 | Initial registry: 24 formulas (5 gate, 16 scoring, 3 adjustment). OTA-689 re-open. |
> | 2026-06-10 | OTA-836: 24 → 26. Added two adjustment formulas (`adj_dte_8_13_penalty`, `adj_sma_alignment_against_trade`) given live implementations to unblock SCREENING startup hydration. The five EV-gate formulas (`dte_hard_filter`, `dte_warning_penalty`, `credit_pct_of_width_floor`, `debit_pct_of_width_ceiling`, `negative_ev_gate`) were deregistered from the live screening registry — they were never in this contract and were referenced by no live `formula_ref`, so their removal changes no rows here (it clears a FORMULA_REGISTRY_DRIFT). Directional `dir_*` formulas remain out of this SHARED contract (directional surface parked; returns under the deferred surface-scoped-validation story). |
> | 2026-06-10 | OTA-840: 26 → 36. Directional surface re-enabled with surface-scoped validation (mechanism a). Added the 10 `dir_*` directional formulas to the SHARED contract — 8 **bound** (`dir_probability`, `dir_buffer`, `dir_expected_value`, `dir_max_loss_pct`, `dir_reward_risk`, `dir_payoff_multiple` scoring; `dir_earnings`, `dir_negative_ev` gate) and 2 **reserved/unbound** (`dir_budget_fit`, `dir_defined_risk` — registered in the live directional registry, bound by no strategy; carried in the contract so the global drift check balances against the union registry). Validation now injects the combined screening ∪ directional registry. |

---

## Gate Formulas (5)

Gate formulas evaluate a pass/fail condition against the candidate's named values. Output type is always `bool`.

| Name | Intent | Inputs | Notes |
|---|---|---|---|
| `chart_state_matches_direction` | Chart state alignment must match trade direction (bullish for bull, bearish for bear). | `chart_state`, `trade_direction` | — |
| `earnings_route1_no_viable_window` | Earnings Route 1: no viable window — dte_before ≤ 7 and dte_after < 14. Halt verdict: PASS. | `next_earnings_date`, `entry_date`, `expiry_date`, `dte_before_earnings`, `dte_after_earnings` | — |
| `earnings_route2_wait_post_window` | Earnings Route 2: pre-earnings window too short, post-earnings window viable — dte_before ≤ 7 and dte_after ≥ 14. Halt verdict: WAIT_FOR_EARNINGS. | `next_earnings_date`, `entry_date`, `expiry_date`, `dte_before_earnings`, `dte_after_earnings` | — |
| `earnings_route3_post_entry_better` | Earnings Route 3: post-earnings entry likely better — dte_before ≥ 8 and dte_after ≥ 21. Halt verdict: WAIT_FOR_EARNINGS. | `next_earnings_date`, `entry_date`, `expiry_date`, `dte_before_earnings`, `dte_after_earnings` | — |
| `earnings_route4_pre_momentum_play` | Earnings Route 4: pre-earnings momentum play — dte_before ≥ 8 and dte_after < 21. Score with −15 penalty, effective DTE = dte_before − 1. | `next_earnings_date`, `entry_date`, `expiry_date`, `dte_before_earnings`, `dte_after_earnings` | Non-stopping gate (stop_if_fail=false). |

---

## Scoring Formulas (16)

Scoring formulas produce a value that contributes to the candidate's weighted score. Output types vary.

| Name | Intent | Inputs | Output | Notes |
|---|---|---|---|---|
| `bid_ask_tightness` | Inverse of bid-ask spread percentage. Tighter spreads score higher. | `bid_ask_spread_pct` | score 0–1 | Normalization owed: multiply by 100 for [0,100]. |
| `credit_width` | Net credit received as percentage of spread width. | `net_debit`, `spread_width` | score 0–100 | — |
| `delta_otm_score` | How far out-of-the-money the option is. 0.25 delta → 0; 0 delta → 1. | `delta` | score 0–1 | Normalization owed: multiply by 100 for [0,100]. |
| `delta_quality` | Gaussian-like peak around a target delta range. | `delta` | score 0–1 | Junction params: `delta_center`, `delta_half_range`. |
| `expected_value` | Expected value: (P(profit) × max gain) − (P(loss) × max loss). | `p_max_profit`, `max_profit`, `p_max_loss`, `max_loss` | decimal | COMPUTED tier — requires Black-Scholes probability matrix. |
| `iv_percentile_cost` | Linear inversion of raw IV. Penalises high IV. | `iv` | score 0–100 | PROXY: true IV percentile requires historical-IV producer (adapter feature, later). |
| `iv_rank` | IV rank as a percentile of historical IV range. | `iv_rank` | score 0–100 | PROXY: code uses ATM IV / 0.60 as proxy. True IV rank is percentile-based. |
| `liquidity` | Combined liquidity from both legs' volume and open interest. | `long_volume`, `short_volume`, `long_oi`, `short_oi` | decimal | Normalization owed: raw sum, not yet on [0,100] scale. |
| `open_interest` | Raw open interest value as a scoring signal. | `open_interest` | decimal | PROXY: normalization to [0,100] to be defined during tuning. |
| `payout_ratio` | Expected 10% move payout relative to premium paid. | `delta`, `underlying_price`, `premium_dollars` | decimal | Normalization owed: raw ratio, not yet on [0,100] scale. |
| `probability_of_profit` | Probability that the trade expires profitable, derived from option delta. | `long_delta`, `short_delta` | score 0–100 | COMPUTED tier. Uses long-leg delta (not 1 − short_delta). See `business-rules.md`. |
| `reward_risk` | Ratio of maximum reward to maximum risk. | `max_profit`, `max_loss` | decimal | — |
| `runway_score` | How many days of theta the premium can sustain (premium / daily_theta). | `theta_runway_days` | decimal | PROXY: normalization to [0,100] to be defined during tuning. |
| `sma_alignment_score` | Score from SMA alignment classification (BULLISH/BEARISH/MIXED/NEUTRAL). | `sma_8`, `sma_21`, `sma_50`, `sma_alignment_classification` | score 0–1 | PROXY: 0.5 passthrough. Planned: classification-to-score via `compute_sma_signal()`. |
| `theta_gamma_ratio` | Ratio of theta decay to gamma risk. | `net_theta`, `max_loss` | decimal | PROXY: currently identical to theta_margin_ratio (abs(net_theta) / max_loss). True theta/gamma requires per-leg gamma. |
| `theta_margin_ratio` | Daily theta decay as a fraction of maximum loss (margin at risk). | `net_theta`, `max_loss` | decimal | — |

---

## Adjustment Formulas (5)

Adjustment formulas apply post-scoring penalties or bonuses based on conditions.

| Name | Intent | Inputs | Output | Notes |
|---|---|---|---|---|
| `cushion_penalty_moderate` | Moderate proximity penalty: cushion ≥ 1.0% and < 2.0% of underlying price → −10 points. | `stock_price`, `short_strike` | decimal | — |
| `extension_matches_trade_direction` | Check if stock extension direction matches trade direction (above SMA for bull, below for bear). | `stock_price`, `sma_50`, `trade_direction` | bool | OTA-836: live impl added. Penalty-direction semantics deferred to backtesting. |
| `probability_asymmetry_penalty` | Graduated penalty based on loss/profit probability ratio. ≥ 2.0 → −25; ≥ 1.5 → −15; ≥ 1.25 → −8; < 1.25 → 0. | `p_max_loss`, `p_max_profit` | decimal | Junction params: `band_severe` (2.0), `band_high` (1.5), `band_moderate` (1.25), `penalty_severe` (−25), `penalty_high` (−15), `penalty_moderate` (−8). |
| `adj_dte_8_13_penalty` | Near-expiry penalty: −20 points when 8 ≤ dte ≤ 13, else 0. | `dte` | decimal | OTA-836. Returns the penalty amount directly (junction does not double it). Junction params: `dte_low` (8), `dte_high` (13), `penalty` (−20). Replaces the non-§6.3 `dte >= 8 AND dte <= 13` condition that blocked the loader. |
| `adj_sma_alignment_against_trade` | −15 points when price is positioned against the trade direction across all three SMAs (below all of SMA-8/21/50 for a bull trade, above all for a bear trade), else 0. | `stock_price`, `sma_8`, `sma_21`, `sma_50`, `trade_direction` | decimal | OTA-836. Cross-field → cannot be a §6.3 atom. Junction param: `penalty` (−15). |

---

## Proxy Status Summary

Seven formulas are currently proxies or carry normalization debt:

| Formula | Status | Planned Resolution |
|---|---|---|
| `iv_percentile_cost` | PROXY | True IV percentile from historical-IV adapter |
| `iv_rank` | PROXY | True IV rank (percentile-based) from historical-IV adapter |
| `open_interest` | PROXY | Normalization TBD during tuning |
| `runway_score` | PROXY | Normalization TBD during tuning |
| `sma_alignment_score` | PROXY | Classification-to-score via `compute_sma_signal()` |
| `theta_gamma_ratio` | PROXY | True theta/gamma requires per-leg gamma propagation |
| `bid_ask_tightness`, `delta_otm_score`, `liquidity`, `payout_ratio` | NORMALIZATION OWED | Multiply by 100 or define [0,100] mapping |

---

## Directional Formulas (10) — DIRECTIONAL surface

Live implementations in `app/options_rules/directional/`. Validated against the combined registry (OTA-840). Eight are bound to the three directional strategies (`directional_income`/`growth`/`longshot`); two are reserved (registered, no junction binding).

### Bound — scoring (6)

| Name | Intent | Inputs | Output |
|---|---|---|---|
| `dir_probability` | Probability of profit scaled to [0,100]. | `prob_of_profit` | score 0–100 |
| `dir_buffer` | Breakeven-vs-target buffer, capped and scaled. | `buffer_pct` | score 0–100 |
| `dir_expected_value` | EV unified across spreads (`ev_raw`) and naked longs (`total_ev`), tanh-scaled to [0,100]. | `ev_raw`, `total_ev` | score 0–100 |
| `dir_max_loss_pct` | Budget consumption: `max_loss / thesis_risk_budget`, lower is better. | `max_loss`, `thesis_risk_budget` | score 0–100 |
| `dir_reward_risk` | Reward-to-risk ratio scaled to [0,100]; null (naked, unlimited) scores full. | `reward_risk_ratio` | score 0–100 |
| `dir_payoff_multiple` | Target-based payoff multiple scaled to [0,100]. | `structure_type`, `cost`, `strike`, `thesis_target_price`, `option_type`, `reward_risk_ratio` | score 0–100 |

### Bound — gate (2)

| Name | Intent | Inputs | Output |
|---|---|---|---|
| `dir_earnings` | Fail when `next_earnings_date <= expiration + buffer_days`; unknown earnings fail-open. | `next_earnings_date`, `expiration` | bool |
| `dir_negative_ev` | Fail when resolved EV (`ev_raw` else `total_ev`) < threshold; both null defers to data-completeness. | `ev_raw`, `total_ev` | bool |

### Reserved / unbound (2)

| Name | Intent | Inputs | Output | Notes |
|---|---|---|---|---|
| `dir_budget_fit` | Binary budget-fit score. | `fits_budget` | score 0–100 | Registered live; bound by no strategy. Carried in the SHARED contract so the global drift check balances against the union registry. Do not deregister. |
| `dir_defined_risk` | Defined-risk-structure preference. | `structure_type` | score 0–100 | Registered live; bound by no strategy. Same contract rationale as `dir_budget_fit`. |
