# business-rules.md

**Last Updated:** 2026-05-31 00:00 UTC
**Instigating Ticket:** OTA-495 (v1 Create — Extract business rules from architecture-plan.md and CLAUDE.md)
**Restructured under:** OTA-807 (reshape into the Insight Engine rule-catalog form per `insight_engine.md` §9)

---

This document is the human-readable **rule catalog and input definitions for the options consumer** of the Insight Engine. It records *what the rules are and why they exist*, the named values the options adapter produces, and the trading-philosophy decisions that don't reduce to a single rule.

It is **not** a second source of rule *values*. Thresholds, weights, gate behaviour, ordering, and verdict bands live in the runtime rules / strategies / junction tables (`insight_engine.md` §2.1, §6). `Scoring Parameters.xlsx` is a build-time seed only. Where a numeric value appears below it is shown for orientation and reflects the **seeded junction/config** — the authoritative value is the table row, not this document. Code-level `params.get(..., default)` fallbacks are noted as defaults, never as the source of truth.

**Strategies are not documented here.** A strategy is self-documenting in the Strategies table (its description, verdict bands, scan parameters) and the junction (its per-rule rationale, parameters, and weights). Where a strategy needs long-form or visual explanation, this document carries a *pointer*, never the strategy content inline (`insight_engine.md` §9.2).

The hand-off between this document and `insight_engine.md` is the input-adapter contract (§5) and the table schema (§6.1). For engine mechanics, read `insight_engine.md`. For architectural placement, read `architecture-plan.md`. For workflow, read `CLAUDE.md`. For UI presentation, read `UI-GUIDANCE.md`. When any other document and this one disagree on a business rule, this document wins.

---

## Table of Contents

**Part A — Options Engine Rule Catalog (the three sections)**
1. [Input Definitions](#1-input-definitions)
2. [Rule Catalog](#2-rule-catalog)
3. [Domain Semantics](#3-domain-semantics)

**Part B — Market Context Interpretations** (deterministic market-context, not per-candidate engine rules)
- [Regime Classification](#regime-classification)
- [SMA-Alignment Narrative & Technical Labels](#sma-alignment-narrative--technical-labels)

**Part C — Appendix: Non-Engine Business Rules** (canonical rules that are not engine input/rule/semantics)
- [Cost Guardrails](#cost-guardrails)
- [Display Formatting Rules](#display-formatting-rules)
- [Position Lifecycle](#position-lifecycle)
- [Signal Freshness / TTL Windows](#signal-freshness--ttl-windows)
- [Health Grade Computation](#health-grade-computation)
- [Validation Baseline](#validation-baseline)

---

# Part A — Options Engine Rule Catalog

## 1. Input Definitions

Every named value the options adapter (`app/ota_adapters/options_chain/adapter.py`, `_CATALOG`) produces, with its tier, type, and null semantics. This is the prose companion to the §5.1 input catalog in `insight_engine.md`; the catalog declaration in code is the authoritative source — this table must stay in sync with it.

**How to read this section.**

- **Tier** — `RAW` (produced directly by the adapter from market data), `DERIVED` (computed deterministically from RAW values, no external call), `COMPUTED` (heavier math, populated on demand via the adapter callback for surviving candidates only). The tier system is a performance contract; see `insight_engine.md` §3.5.
- **Null semantics** —
  - `FAIL_CLOSED` — required. A data-completeness gate fails the candidate if the value is absent.
  - `FAIL_OPEN` — optional. Rules degrade gracefully (fail-soft / pass) when the value is absent.
  - `SKIP` — optional. Rules that reference the value skip it or substitute a neutral default when it is absent.
- **Aliases** — several values are alternate names for the same underlying quantity, retained so rules can reference either spelling. They are marked *alias of X* and carry the same source.

### 1.1 RAW inputs (36)

| Named value | Type | Null | Definition / source |
|---|---|---|---|
| `underlying_price` | number | FAIL_CLOSED | Current spot price of the underlying, from the market-data chain API. |
| `option_type` | enum | FAIL_CLOSED | `call` or `put`. |
| `expiration` | date | FAIL_CLOSED | Contract expiration date (ISO 8601). |
| `spread_type` | enum | FAIL_CLOSED | Structure family: `bull_call`, `bear_put`, `bull_put`, `bear_call`, `long_call`, `long_put`. |
| `long_strike` | number | FAIL_CLOSED | Strike of the long leg (spreads). |
| `short_strike` | number | FAIL_CLOSED | Strike of the short leg (spreads). |
| `long_bid` | number | SKIP | Bid of the long leg (spreads). |
| `long_ask` | number | SKIP | Ask of the long leg (spreads). |
| `short_bid` | number | SKIP | Bid of the short leg (spreads). |
| `short_ask` | number | SKIP | Ask of the short leg (spreads). |
| `long_delta` | number | SKIP | Delta of the long leg; null when the chain omits it (B-S fallback may supply `bs_delta`). |
| `short_delta` | number | SKIP | Delta of the short leg; null when the chain omits it. |
| `long_theta` | number | FAIL_OPEN | Per-day theta of the long leg. |
| `short_theta` | number | FAIL_OPEN | Per-day theta of the short leg. |
| `long_gamma` | number | FAIL_OPEN | Gamma of the long leg. |
| `short_gamma` | number | FAIL_OPEN | Gamma of the short leg. |
| `long_vega` | number | FAIL_OPEN | Vega of the long leg. |
| `short_vega` | number | FAIL_OPEN | Vega of the short leg. |
| `long_volume` | number | FAIL_OPEN | Daily volume of the long leg. |
| `short_volume` | number | FAIL_OPEN | Daily volume of the short leg. |
| `long_oi` | number | FAIL_OPEN | Open interest of the long leg. |
| `short_oi` | number | FAIL_OPEN | Open interest of the short leg. |
| `long_iv` | number | FAIL_OPEN | Implied volatility of the long leg (normalized). |
| `short_iv` | number | FAIL_OPEN | Implied volatility of the short leg (normalized). |
| `spread_width` | number | FAIL_CLOSED | Absolute difference between the long and short strikes. |
| `strike` | number | FAIL_CLOSED | Strike (naked single-leg options). |
| `bid` | number | SKIP | Bid (naked options). |
| `ask` | number | SKIP | Ask (naked options). |
| `delta` | number | SKIP | Delta (naked options); null when the chain omits it. |
| `theta` | number | FAIL_OPEN | Per-day theta (naked options). |
| `gamma` | number | FAIL_OPEN | Gamma (naked options). |
| `vega` | number | FAIL_OPEN | Vega (naked options). |
| `iv` | number | FAIL_OPEN | Implied volatility (naked options, normalized). |
| `volume` | number | FAIL_OPEN | Daily volume (naked options). |
| `open_interest` | number | FAIL_OPEN | Open interest (naked options). |
| `next_earnings_date` | date | SKIP | Next earnings date. Null until the earnings data source is wired (external provider). |

### 1.2 DERIVED inputs (41)

| Named value | Type | Null | Definition / source |
|---|---|---|---|
| `dte` | number | FAIL_CLOSED | Days to expiration (`expiration` − `entry_date`). |
| `net_debit` | number | SKIP | Net cash of the spread; positive = debit paid, negative = credit received. Null off-structure. |
| `net_credit` | number | SKIP | Net credit received (credit spreads); null for debit structures. |
| `max_profit` | number | FAIL_CLOSED | Maximum profit at expiration. |
| `max_loss` | number | FAIL_CLOSED | Maximum loss at expiration. |
| `breakeven` | number | FAIL_CLOSED | Underlying price at breakeven at expiration. |
| `prob_of_profit` | number | FAIL_OPEN | Probability of profit, 0–100, from long-leg delta (see §3.2). |
| `ev_raw` | number | FAIL_OPEN | Expected value (spreads). |
| `reward_risk_ratio` | number | FAIL_OPEN | `max_profit / max_loss`. |
| `cushion_pct` | number | SKIP | Cushion as a percentage of spot. |
| `bid_ask_spread_pct` | number | SKIP | Bid-ask spread as a percentage (naked options). |
| `premium_dollars` | number | FAIL_OPEN | Option premium in dollars (naked: mid × 100). |
| `theta_runway_days` | number | SKIP | Days of premium the position sustains at the current daily theta decay. |
| `credit_pct_of_width` | number | SKIP | Net credit ÷ spread width (credit spreads). |
| `debit_pct_of_width` | number | SKIP | Net debit ÷ spread width (debit spreads). |
| `breakeven_distance_pct` | number | SKIP | Distance from spot to breakeven as a percentage (naked options). |
| `net_theta` | number | FAIL_OPEN | Sum of leg thetas (spreads & naked). |
| `trade_direction` | enum `bullish\|bearish` | SKIP | Inferred from the structure type. |
| `stock_price` | number | FAIL_CLOSED | *Alias of* `underlying_price`. |
| `mid_price` | number | SKIP | `(bid + ask) / 2` (naked options). |
| `min_leg_open_interest` | number | FAIL_OPEN | Minimum open interest across both legs. |
| `min_leg_volume` | number | FAIL_OPEN | Minimum volume across both legs. |
| `entry_date` | date | FAIL_OPEN | Date the candidate was produced (today). |
| `expiry_date` | date | FAIL_CLOSED | *Alias of* `expiration`. |
| `sma_alignment_classification` | enum `BULLISH\|BEARISH\|MIXED\|NEUTRAL` | SKIP | *Alias of* `sma_alignment`. |
| `credit_width_pct` | number | SKIP | *Alias of* `credit_pct_of_width`. |
| `debit_width_pct` | number | SKIP | *Alias of* `debit_pct_of_width`. |
| `bid_ask_spread` | number | SKIP | Bid-ask spread in dollars (max across legs). |
| `sma_8` | number | SKIP | 8-day simple moving average of daily closes. |
| `sma_21` | number | SKIP | 21-day simple moving average of daily closes. |
| `sma_50` | number | SKIP | 50-day simple moving average of daily closes. |
| `sma_alignment` | enum `BULLISH\|BEARISH\|MIXED\|NEUTRAL` | SKIP | SMA stack classification (see Part B → SMA-Alignment Narrative). |
| `atr_14` | number | SKIP | 14-period Wilder-smoothed Average True Range. |
| `iv_percentile` | number | SKIP | IV percentile vs. trailing realized volatility. Proxy until a historical-IV producer exists. |
| `atm_iv` | number | SKIP | At-the-money implied volatility. |
| `iv_rank` | number | SKIP | *Alias of* `iv_percentile`. |
| `chart_state` | enum `Bullish\|Bearish\|Mixed\|Neutral` | SKIP | Title-cased mapping of `sma_alignment`. **Planned engine gate input** — see Part B cross-reference. |
| `is_etf` | boolean | FAIL_OPEN | True if the symbol is an ETF; false for equity/ADR; null if unknown. |
| `cushion_vs_atr` | number | SKIP | Cushion expressed as a multiple of an ATR-based move. |
| `dte_before_earnings` | number | SKIP | Days from entry to earnings; null when no earnings fall in the trade window. |
| `dte_after_earnings` | number | SKIP | Days from earnings to expiration; null when no earnings fall in the trade window. |

### 1.3 COMPUTED inputs (5)

Populated on demand by the adapter `populate_computed()` callback, only for candidates that survive the DERIVED gates (`insight_engine.md` §5.2). All carry `SKIP` null semantics — a referencing rule skips the value if it is absent.

| Named value | Type | Null | Definition / source |
|---|---|---|---|
| `probability_matrix` | matrix | SKIP | Black-Scholes probability-of-profit matrix (price levels × time horizons). |
| `total_ev` | number | SKIP | Expected value for naked long options (Black-Scholes). |
| `p_max_loss` | number | SKIP | Probability of maximum loss at expiration (B-S CDF). |
| `p_max_profit` | number | SKIP | Probability of maximum profit at expiration (B-S CDF). |
| `bs_delta` | number | SKIP | Black-Scholes delta estimate, fallback when the chain omits API delta. |

---

## 2. Rule Catalog

The options consumer's rules, grouped by common rule type. Each rule states its **intent** (plain-language why), **logical evaluation formula**, **required inputs**, and **expected output** (gate pass/fail, score contribution, or adjustment).

**Reading conventions.**

- Numeric thresholds, weights, and scales shown are **seeded-junction values for orientation**; the authoritative value is the junction row. Code defaults (`params.get(..., default)`) are labelled *default*.
- Gate formulas return `True` = pass (continue) / `False` = fail. What a failure *does* — halt vs. record-and-continue, any `score_penalty`, any `terminal_verdict` — is junction-driven, not in the formula (`insight_engine.md` §3.6). Most gates are **fail-soft on missing inputs** (return pass) so absent data never silently kills a candidate at the wrong tier.
- **Which strategy uses which rule, with what parameters and weight, lives in the junction** and is not restated here. A strategy's active scoring weights sum to 1.0 (engine startup validation, `insight_engine.md` §6.6).
- Source: gate formulas `app/options_rules/screening/gate_formulas.py`; scoring formulas `app/options_rules/screening/scoring_formulas.py`.

### 2.1 Structure-compatibility (scan-entry gate)

| Field | Value |
|---|---|
| **Intent** | A candidate is evaluated against a strategy only if the strategy's mechanism fits the candidate's structure. Premium-collection and directional-payoff structures must not be scored against each other (see §3.1). |
| **Formula** | `spread_type ∈ strategy.compatible_structures` |
| **Inputs** | `spread_type` |
| **Output** | Scan-entry gate. Incompatible pairs return null and are never scored against that strategy. The per-strategy `compatible_structures` lists live in the Strategies table (seeded from `Scoring Parameters.xlsx`); they are **not** restated here. |

### 2.2 Earnings rules (gates)

The adapter supplies `dte_before_earnings` / `dte_after_earnings` (DERIVED from `next_earnings_date`, `entry_date`, `expiry_date`). When no earnings fall in the trade window both are null and **every route returns pass** (fail-soft). The four routes are mutually exclusive; the junction `evaluation_order` places the three stopping routes ahead of the non-stopping penalty route. Gate semantics: a matched condition returns `False` (fail), and the junction decides the consequence.

| Rule key | Intent | Formula (defaults; junction is authoritative) | Inputs | Expected output |
|---|---|---|---|---|
| `earnings_route1_no_viable_window` | Neither pre- nor post-earnings window is workable; the trade is definitively unworkable. | `dte_before ≤ 7 AND dte_after < 14` | `dte_before_earnings`, `dte_after_earnings` | Gate fail → junction halts, `terminal_verdict = PASS`. |
| `earnings_route2_wait_post_window` | Pre-earnings window too short, but the post-earnings window is viable — re-evaluate after the event. | `dte_before ≤ 7 AND dte_after ≥ 14` | same | Gate fail → junction halts, `terminal_verdict = WAIT_FOR_EARNINGS`. |
| `earnings_route3_post_entry_better` | Both windows viable, but post-earnings entry is likely better — delay entry. | `dte_before ≥ 8 AND dte_after ≥ 21` | same | Gate fail → junction halts, `terminal_verdict = WAIT_FOR_EARNINGS`. |
| `earnings_route4_pre_momentum_play` | A pre-earnings momentum play is viable; score it but discount for event risk. | `dte_before ≥ 8 AND dte_after < 21` | same | Gate fail, **non-stopping** → junction applies `score_penalty` (seeded −15); candidate continues to scoring. |

**Strategy bindings (junction, summarized — not restated as strategy docs):** the SP/WG/TR strategies bind all four routes with the verdicts above; the LT strategy binds all four as `stop_if_fail = true` with `terminal_verdict = NULL` (a silent halt — known gap flagged under OTA-680).

### 2.3 DTE rules (gates)

| Rule key | Intent | Formula (defaults) | Inputs | Expected output |
|---|---|---|---|---|
| `dte_hard_filter` | Block trades too close to expiration to manage. | pass when `dte > 7` | `dte` | Gate. Fail (`dte ≤ 7`) → junction halts. Fail-soft when `dte` absent. |
| `dte_warning_penalty` | Flag the short-DTE warning band without killing the trade. | fail when `8 ≤ dte ≤ 13` | `dte` | Gate, **non-stopping** → junction `score_penalty` applied. Fail-soft when `dte` absent. |

### 2.4 Credit / debit-width rules (gates)

| Rule key | Intent | Formula (defaults) | Inputs | Expected output |
|---|---|---|---|---|
| `credit_pct_of_width_floor` | Reject credit spreads that don't collect enough premium relative to risk width. | for credit spreads (`net_debit < 0`): pass when `abs(net_debit) / spread_width ≥ 0.30` | `net_debit`, `spread_width` | Gate → junction halts on fail. Fail-soft / pass when not a credit spread or inputs absent. |
| `debit_pct_of_width_ceiling` | Reject debit spreads that overpay relative to width. | for debit spreads (`net_debit > 0`): pass when `net_debit / spread_width ≤ 0.40` | `net_debit`, `spread_width` | Gate → junction halts on fail. Fail-soft / pass when not a debit spread or inputs absent. |

### 2.5 Expected-value rule (gate)

| Rule key | Intent | Formula (defaults) | Inputs | Expected output |
|---|---|---|---|---|
| `negative_ev_gate` | Never pass a trade whose expected value is negative. | pass when `ev_raw ≥ 0.0` | `ev_raw` | Gate → junction halts on fail. Fail-soft when `ev_raw` absent (missing EV ≠ negative EV). |

### 2.6 Scoring criteria

Each criterion is a pure function `(named_values, params) → float` in `[0, 100]`, multiplied by its junction weight; the weighted sum across a strategy's active criteria is the raw score. Grouped by type below. Parameters (`scale`, `divisor`, `center`, etc.) are junction-supplied; values shown are code defaults.

**Theta / decay**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `theta_margin_ratio` | Reward daily theta earned per unit of capital at risk. | `min(100, abs(net_theta) / max_loss × scale)` | `net_theta`, `max_loss` |
| `theta_gamma_ratio` | Reward theta relative to gamma risk. Proxy = `theta_margin_ratio` until per-leg gamma propagation lands. | `min(100, abs(net_theta) / max_loss × scale)` | `net_theta`, `max_loss` |
| `runway_score` | Reward trades whose premium sustains more days of decay. | `min(100, theta_runway_days / scale × 100)` | `theta_runway_days` |

**Probability / expected value / reward**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `probability_of_profit` | Reward higher probability of profit (long-leg delta — see §3.2). | `clamp(prob_of_profit, 0, 100)` | `prob_of_profit` |
| `expected_value` | Reward positive expected value. | credit path: `clamp(ev_raw × scale, 0, 100)`; long path: `clamp((delta × underlying_price × move_pct − mid_price) × scale, 0, 100)` | `ev_raw` *or* (`delta`, `underlying_price`, `mid_price`) |
| `reward_risk` | Reward favorable payoff-to-risk. | `min(100, reward_risk_ratio × scale)` (or `max_profit / max_loss`) | `reward_risk_ratio` (or `max_profit`, `max_loss`) |

**Credit width**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `credit_width` | Reward richer credit relative to spread width. | `min(100, abs(net_debit) / spread_width × 100)` | `net_debit`, `spread_width` |

**Implied volatility**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `iv_rank` | Reward selling into elevated IV. True IV rank when available; else proxy `min(1, atm_iv / divisor) × 100`. | true: `clamp(iv_rank, 0, 100)`; proxy divisor default `0.60`; neutral `50` when absent | `iv_rank` *or* `atm_iv` |
| `iv_percentile_cost` | Reward buying into cheaper IV (lower IV → higher score). | `max(0, 1 − iv_decimal / max_iv) × 100` | `iv` |

**Liquidity**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `liquidity` | Reward combined two-leg liquidity. | `min(100, (long_volume + short_volume + long_oi + short_oi) / scale × 100)` | `long_volume`, `short_volume`, `long_oi`, `short_oi` |
| `open_interest` | Reward open interest as a depth signal. | `min(100, open_interest / scale × 100)` | `open_interest` |
| `bid_ask_tightness` | Reward tighter quoted markets. | `max(0, 1 − bid_ask_spread_pct / max_spread_pct) × 100` | `bid_ask_spread_pct` |

**Delta shape**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `delta_quality` | Reward deltas near a target band (peak around `center`). | `max(0, 1 − abs(delta − center) / (half_range + smoothing)) × 100` | `delta` |
| `delta_otm_score` | Reward further-OTM strikes (lower delta → higher score). | `max(0, 1 − delta / max_delta) × 100` | `delta` |

**Payout**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `payout_ratio` | Reward asymmetric payout on a configured underlying move. | `clamp((delta × underlying_price × move_pct × multiplier) / premium_dollars / scale × 100, 0, 100)` | `delta`, `underlying_price`, `premium_dollars` |

**Technical alignment**

| Rule key | Intent | Formula | Inputs |
|---|---|---|---|
| `sma_alignment_score` | Reward trend agreement with the SMA stack. | maps `sma_alignment_classification` → `{BULLISH:100, BEARISH:0, NEUTRAL:50, MIXED:25}` (junction params); `default_score` 50 when absent | `sma_alignment_classification` |

> **Cross-reference.** The classification consumed by `sma_alignment_score` is the same SMA stack interpretation documented in Part B → SMA-Alignment Narrative, surfaced to the engine as the `sma_alignment` / `chart_state` named values (§1.2). When `chart_state` is promoted to a gate input, its values come from that same classification — do not duplicate the thresholds here.

### 2.7 Halt verdicts and verdict-domain registration

A **halt verdict** is a `terminal_verdict` string set on a junction row where `stop_if_fail = true`. When the engine halts a candidate at that gate, the verdict is taken directly from the junction row, bypassing the Phase-7 band lookup (`insight_engine.md` §3.8). A row with `stop_if_fail = true` and `terminal_verdict = NULL` halts with no surfaced verdict.

**`WAIT` and `WAIT_FOR_EARNINGS` are distinct strings.** `WAIT` is the Phase-7 band verdict for scores 50–69.99. `WAIT_FOR_EARNINGS` is emitted by the earnings gate's `terminal_verdict` and never passes through band lookup. They must not be conflated in UI rendering, filtering, or analytics.

Every non-null `terminal_verdict` must exist in the `engine_lookups` verdict-domain set for the strategy's `consumer_surface`. For the SCREENING surface:

| lookup_key | kind | Registered by |
|---|---|---|
| `EXECUTE` | BAND_VERDICT | OTA-682 (seed) |
| `WAIT` | BAND_VERDICT | OTA-682 (seed) |
| `PASS` | BAND_VERDICT | OTA-682 (seed) |
| `WAIT_FOR_EARNINGS` | HALT_VERDICT | OTA-711 |

All other `stop_if_fail = true` rows (structure-compatibility, DTE, credit/debit width, EV, liquidity, data-completeness) carry `terminal_verdict = NULL`. Their halts are recorded in the per-rule trace but surface no special verdict — these are structural disqualifications, not actionable user signals.

---

## 3. Domain Semantics

Trading-philosophy decisions that don't reduce to a single rule.

### 3.1 Strategy is a mechanism, not a metrics bucket

Each strategy gates on the candidate's trade structure (§2.1) because **strategy is a mechanism, not a metrics bucket.** A bull put credit and a bear put debit may share calendar metrics (DTE, probability of profit) but they have opposite relationships with time (theta tailwind vs. theta headwind), opposite cash-flow shapes (premium received vs. premium paid), and require different management (exit at a fraction of credit captured vs. exit at a fixed R:R multiple of debit paid). Scoring both under one strategy because they share calendar metrics is a category error. The structure-compatibility gate enforces this at the scoring boundary rather than relying on a downstream narrative to catch it.

The **per-strategy `compatible_structures` lists, scoring weights, and verdict bands are strategy configuration** and live in the Strategies table and junction (seeded from `Scoring Parameters.xlsx`), not in this document. The four current strategies (the SP / WG / TR / LT taxonomy) are self-documenting there; a redesign to mechanics-based names is on the future backlog. For any strategy's definition, read the Strategies table — this catalog documents only the rules a strategy may bind, not the strategies themselves.

### 3.2 Probability of profit uses long-leg delta

PoP (`prob_of_profit`, the `probability_of_profit` criterion) is derived from the **long-leg delta**, not `1 − short_delta`. Long-leg delta is the directly observable market estimate of the probability the long strike finishes in the money, which is the quantity these structures are scored on; deriving it from the short leg's delta would introduce the short strike's skew and a second source of estimation error. This is the canonical PoP basis across the screening criteria.

### 3.3 Tier discipline is a cost contract

RAW and DERIVED gates eliminate candidates before any COMPUTED (Black-Scholes) value is produced; the adapter populates COMPUTED values only for survivors (`insight_engine.md` §3.5, §5.2). This is why the expensive probability matrix is never computed for a candidate already killed by a cheap earnings or DTE gate. The engine honors the tier order; this document does not restate the mechanism.

---

# Part B — Market Context Interpretations

These are deterministic market-context classifications used in the export/market-context surface. They are **not** per-candidate engine gate or scoring rules, and (for regime) do not correspond to a named value in the options adapter catalog. They are computed with no Claude API call (cost guardrail). They are documented here because they encode trading-meaning judgments, but they sit alongside — not inside — the engine rule catalog.

## Regime Classification

Deterministic one-liner for the Market context section of export MD v2. No Claude API call. Computed by `regime_note(vix_value, underlying_ivr_pct)` in `app/services/market_context.py`.

### VIX × IVR Grid

| VIX | Underlying IVR | Regime note |
|---|---|---|
| VIX < 15 | IVR < 30 | "Low-vol, range-bound. Premium selling favorable; long premium expensive." |
| VIX < 15 | IVR 30–60 | "Low-vol broad market with elevated single-name IV. Mixed signal." |
| VIX < 15 | IVR > 60 | "Low-vol broad market, single-name IV elevated. Skew favors premium sellers on this name." |
| VIX 15–20 | IVR < 30 | "Low-vol, mildly choppy. VIX below 20 makes long premium expensive relative to expected move." |
| VIX 15–20 | IVR 30–60 | "Moderate-vol. Standard premium pricing." |
| VIX 15–20 | IVR > 60 | "Moderate-vol broad market with elevated single-name IV." |
| VIX 20–25 | any | "Elevated vol regime. Watch for IV crush on event-driven positions." |
| VIX 25–30 | any | "High-vol regime. Premium selling rich; debit spreads compressed." |
| VIX > 30 | any | "Crisis vol regime. Sizing and stops both warrant tightening." |

**Boundaries:** Half-open intervals `[lo, hi)`. VIX exactly 15 → 15–20 bucket. IVR exactly 30 → 30–60 bucket. IVR exactly 60 → >60 bucket.

### 5-Day Trend Classification

```
five_day_pct = (spot_today − spot_5d_ago) / spot_5d_ago × 100
if abs(five_day_pct) <= 0.5: label = "flat"
elif five_day_pct > 0:       label = "up"
else:                        label = "down"
```

Rendered as `<label> (<signed_pct>%)` with one decimal.

### VIX 52-Week Percentile

Percentile = (# of observations < current VIX close) / series length × 100, clamped to integer 0–100. Computed over the rolling 252-trading-day VIX series fetched on-demand from the market data provider. If series < 252 days, rendered with a windowed note: `(52w percentile: <pct>% based on <n> days)`.

### Distance from 50-Day SMA (SPY/QQQ)

```
dist_pct = (spot − sma_50) / sma_50 × 100
direction = "above" if dist_pct >= 0 else "below"
```

Rendered as `<signed_pct>% (<direction>)` with one decimal.

## SMA-Alignment Narrative & Technical Labels

The per-candidate SMA stack classification surfaces to the engine as the `sma_alignment` / `sma_alignment_classification` named values (Part A §1.2) and drives the `sma_alignment_score` scoring criterion (§2.6). The **narrative rendering** of that classification — and the related technical labels below — are interpretation, documented here.

> **Cross-reference to `chart_state`.** `chart_state` (§1.2) is the title-cased mapping of `sma_alignment` and is a **planned engine gate input**. When it is promoted to a gate, its values are produced by this same classification — the thresholds live here only, and the engine consumes the named value. Do not duplicate these thresholds into the rule catalog.

### SMA Alignment Narrative

Computed deterministically from the spot price and three simple moving averages (8, 21, 50). Four mutually exclusive cases, evaluated in priority order:

1. **Bullish stack** — `sma8 > sma21 > sma50` AND `spot > sma8`:
   → `"bullish stack — price above 8 > 21 > 50 SMA."`

2. **Bearish stack** — `sma8 < sma21 < sma50` AND `spot < sma8`:
   → `"bearish stack — price below 8 < 21 < 50 SMA."`

3. **Clustered** — `max_spread_pct < 0.5` where `max_spread_pct = (max(sma8, sma21, sma50) − min(sma8, sma21, sma50)) / spot × 100`:
   → `"clustered — all three SMAs within {max_spread_pct:.1f}% of spot. Trend undefined."`

4. **Mixed** (default) — describe where price sits relative to each SMA:
   → `"mixed — price below {below_list}, above {above_list}. Not a clean bullish or bearish stack."`

The mixed case renders exactly as: `mixed — price below 8 and 50, above 21. Not a clean bullish or bearish stack.` (for the QQQ sample inputs: spot=715.0, sma8=717.32, sma21=713.85, sma50=720.71).

### Distance from 50-Day SMA (per-symbol label)

| Absolute distance | Label |
|---|---|
| < 2.0% | `within range, not extended` |
| 2.0% – 4.99% | `somewhat extended` |
| ≥ 5.0% | `extended` |

Rendered as `<signed_pct>% (<label>)`. Negative distances use the Unicode minus sign (−).

### Computation Inputs

- **SMA(n):** Simple average of the last `n` daily closing prices from the market data provider via `_get_provider()`. Surfaced as `sma_8` / `sma_21` / `sma_50` (§1.2).
- **ATR(14):** Wilder-smoothed Average True Range from 14-period OHLC daily bars. Surfaced as `atr_14` (§1.2).
- **Source:** Schwab daily bars, fetched at export time. No cached or stale values.

---

# Part C — Appendix: Non-Engine Business Rules

Canonical business rules that are not part of the engine's input/rule/semantics catalog. They remain here because this document is their established home; they are kept separate from Parts A–B so the three-section engine catalog stays clean.

## Cost Guardrails

These rules constrain Claude API call volume. They apply to every UI action and background job that may invoke a Claude API call.

- **Multi-call refresh confirmation.** Any refresh action that would trigger more than one Claude API call must show a confirmation dialog before firing. The dialog must state the number of calls about to be made and require explicit user confirmation.
- **Single-call refreshes.** Run without confirmation.
- **Daily auto-refresh.** One auto-refresh per position per day, fired after market close. No other timer-driven Claude calls are permitted.
- **No page-load Claude calls.** Visiting a page must never trigger a Claude API call. Calls are only triggered by explicit user action or the post-market-close batch.
- **Rationale.** Cost containment and explicit user awareness of paid-API consumption. The user-facing confirmation dialog is the enforcement point that prevents accidental fan-out.

The UI implementation pattern that enforces the confirmation requirement (`RefreshConfirmDialog.jsx`) is documented in `UI-GUIDANCE.md`. This document specifies *what* the rule is; `UI-GUIDANCE.md` specifies *how* it is rendered.

## Display Formatting Rules

*Content pending — extract from `CLAUDE.md` House Style Rules. These are presentation rules that derive from business meaning (e.g., score precision, monetary precision, percentage precision), distinct from pure UI rules in `UI-GUIDANCE.md`.*

*Rules to document:*

- *Date format: `mm-dd-yyyy`; with time: `mm-dd-yyyy hh:mm`*
- *Monetary display: `##.00` via `.toFixed(2)`; no `$` prefix*
- *Probabilities: `##.00%`*
- *IV rank: `##.00%`*
- *Config percentages: `##%` (no decimals)*
- *Scores (0–100 scale): `##.00` everywhere*
- *Health grades: letter (A/B/C/D/F) with color mapping (cross-reference Health Grade Computation section)*
- *Position source labels: "Paper" / "Live" (title case in UI)*
- *Trade type display names: title case, no underscores*

## Position Lifecycle

*Content pending — extract from `architecture-plan.md` "Position Lifecycle" section. Document the state machine:*

- *Source: PAPER | LIVE*
- *Status: FOLLOWING | LIVE | CLOSED*
- *Transitions: when each transition is allowed, who triggers it, what side effects occur*
- *Cross-reference to Pattern 4 (Unified Position Model) in `architecture-plan.md`*

## Signal Freshness / TTL Windows

*Content pending — document the TTL per signal type. Each `ContextSource` adapter declares `ttl_seconds()`. Catalog them here:*

- *Schwab quotes: TTL window TBD*
- *Finnhub earnings: TTL window TBD*
- *Future signal sources: list as added*

*Document staleness rules: when a signal exceeds its TTL, what behavior is correct (refetch on demand, mark stale in UI, drop from scoring, etc.).*

## Health Grade Computation

> **Separate consumer surface.** Health grading is a distinct Insight Engine consumer (position health), not the trade-screening surface catalogued in Part A. Its named values and rules belong in their own input-definition / rule-catalog pass under a dedicated ticket; they are intentionally not folded into the screening catalog above. The placeholder below is retained until that pass lands.

*Content pending — extract from `architecture-plan.md` "Health Grade Computation" section. Document:*

- *Letter grade scale: A (on track) → F (thesis invalid)*
- *Color mapping: A=green, B=teal, C=yellow, D=orange, F=red*
- *Inputs: Claude's exit levels stored at position entry; current price; time elapsed; P&L vs target*
- *Update cadence: daily after market close, plus on-demand*
- *Computed by Position Monitor Agent against deterministic math, not by Claude*

## Validation Baseline

*Content pending — document the regression suite expectations:*

- *AMZN regression suite: location, scope, what it validates*
- *Hard gate ordering test: what it asserts*
- *Strategy scoring regressions: per-strategy expected outputs against fixed inputs*
- *When the baseline can be updated: only after a Level 2 QA run with all tests passing (see CLAUDE.md Post-Build QA Gate)*
- *Where snapshots live: `agents/qa-context/baseline-ux.json`, `baseline-data.json`*

### QA Harness Assertions

**D6 — Narrative drift (advisory).** Compares the `claude_read` text between two runs of the same trade using `SequenceMatcher.ratio()`. Threshold: ≥ 0.85. Pairs where either side is the fallback placeholder text `"Narrative unavailable this cycle"` are skipped and logged, not warned. Per OTA-656, the fallback-text filter prevents narrative-availability nondeterminism (a separate concern, tracked under OTA-507) from polluting the drift signal. The character-level metric remains a known limitation and is tracked separately for upgrade.

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-05-31 00:00 UTC | OTA-807 | Restructured into the Insight Engine rule-catalog form per `insight_engine.md` §9. **Part A — Options Engine Rule Catalog** now holds the three target sections: (1) Input Definitions documenting all 82 adapter-produced named values (36 RAW / 41 DERIVED / 5 COMPUTED) with tier, type, and null semantics; (2) Rule Catalog grouping the 9 screening gates and 16 scoring criteria by rule type, each with intent / formula / required inputs / expected output, with all quoted thresholds marked as seeded-junction values rather than authority; (3) Domain Semantics (strategy-is-a-mechanism, PoP long-leg delta, tier discipline). The inline per-strategy Strategy-Structure Compatibility table was replaced with a structure-compatibility *rule* plus a pointer to the Strategies table (no strategy documented inline, per `insight_engine.md` §9.2). **Part B — Market Context Interpretations** holds Regime Classification and the SMA-Alignment Narrative/technical labels as siblings to the engine catalog, with a cross-reference noting the SMA classification feeds the planned `chart_state` engine gate input (no threshold duplication). **Part C — Appendix** retains the non-engine canonical rules (Cost Guardrails, Display Formatting, Position Lifecycle, Health Grade, Validation Baseline); Health Grade annotated as a separate consumer surface pending its own catalog pass. The former Halt Verdicts section folded into Rule Catalog §2.7. Substance preserved throughout; no rule values invented. |
| 2026-05-28 UTC | OTA-711 | Halt Verdicts section added. Documents terminal_verdict per (strategy, rule) binding for the earnings-gate 4-route tree: Route 1 → PASS, Routes 2–3 → WAIT_FOR_EARNINGS, Route 4 → NULL (non-stopping). WAIT vs WAIT_FOR_EARNINGS distinction documented. Halt-verdict domain registration table added. LT silent-halt gap flagged. |
| 2026-05-18 UTC | OTA-656 | Validation Baseline: added D6 narrative drift assertion documentation with fallback-text filter rule. Pairs where either narrative matches the placeholder "Narrative unavailable this cycle" are skipped rather than warned. Threshold (0.85) unchanged. |
| 2026-05-12 UTC | OTA-640 | Regime Classification subsection added: VIX x IVR 9-cell grid, 5-day trend classification rule, VIX 52w percentile computation, distance-from-50d SMA for SPY/QQQ. All rules deterministic (no Claude call). |
| 2026-05-11 UTC | OTA-641 | Technicals Classification subsection added under Strategy Scoring: SMA alignment narrative rules (bullish/bearish/clustered/mixed), distance-from-50d label thresholds, computation inputs (SMA, ATR, source). |
| 2026-05-11 UTC | OTA-635 | Strategy Scoring section: Strategy-Structure Compatibility subsection populated. Canonical compatibility map established: SP/WG → credit structures only (BULL_PUT_CREDIT, BEAR_CALL_CREDIT); TR → debit structures only (BULL_CALL_DEBIT, BEAR_PUT_DEBIT); LT → single-leg long options (SINGLE_LONG_CALL, SINGLE_LONG_PUT). Rationale documented: strategy is a mechanism (premium collection vs directional payoff), not a metrics bucket. Resolves the production contradiction where bear_put debit spreads were scored against SP and produced verdicts contradicting their own narrative. `best_fit` semantics under compatibility documented. Scoring formula and weights subsection remains a placeholder under OTA-495. |
| 2026-04-30 22:05 UTC | OTA-495 | Cost Guardrails section populated as the first extraction. Rule moved from CLAUDE.md House Style section to here. CLAUDE.md now references this file for the canonical rule. |
| 2026-04-30 21:33 UTC | OTA-495 | Initial shell created. Sections and TOC defined per OTA-495 scope (Strategy Scoring, Hard Gates, PoP Computation, Health Grade, Position Lifecycle, Signal Freshness, Display Formatting, Cost Guardrails, Validation Baseline). Each section contains a placeholder describing the source material to extract from and the rules to document. Full content extraction is the body of OTA-495 implementation work. |
</content>
</invoke>
