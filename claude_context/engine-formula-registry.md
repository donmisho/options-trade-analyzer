# Engine Formula Registry

> **Status:** 24 formulas registered · 2026-05-28
> **Scope:** Complete, deduplicated list of every `formula:<name>` reference in `engine_rules.formula_ref`. Each entry is the implementation contract for the rule library. The engine's startup validation (OTA-699, `insight_engine.md` §6.6) checks that every reference resolves to both a registered lookup row and a live implementation.
>
> **Dual-validation contract:** This doc and the SHARED `engine_lookups.formula_registry` set must agree row-for-row. The lookup payloads carry the same intent/signature/notes as this doc. Drift between them is a defect class OTA-699 will catch.
>
> **Change Log**
> | Date | Change |
> |---|---|
> | 2026-05-28 | Initial registry: 24 formulas (5 gate, 16 scoring, 3 adjustment). OTA-689 re-open. |

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

## Adjustment Formulas (3)

Adjustment formulas apply post-scoring penalties or bonuses based on conditions.

| Name | Intent | Inputs | Output | Notes |
|---|---|---|---|---|
| `cushion_penalty_moderate` | Moderate proximity penalty: cushion ≥ 1.0% and < 2.0% of underlying price → −10 points. | `stock_price`, `short_strike` | decimal | — |
| `extension_matches_trade_direction` | Check if stock extension direction matches trade direction (above SMA for bull, below for bear). | `stock_price`, `sma_50`, `trade_direction` | bool | — |
| `probability_asymmetry_penalty` | Graduated penalty based on loss/profit probability ratio. ≥ 2.0 → −25; ≥ 1.5 → −15; ≥ 1.25 → −8; < 1.25 → 0. | `p_max_loss`, `p_max_profit` | decimal | Junction params: `band_severe` (2.0), `band_high` (1.5), `band_moderate` (1.25), `penalty_severe` (−25), `penalty_high` (−15), `penalty_moderate` (−8). |

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
