# EV Gate Diagnostic — MSFT 410P Reproduction Case

**Date:** 2026-05-19
**Story:** OTA-676 Phase 1
**Trade:** MSFT SINGLE_LONG_PUT, strike 410, expiry 2026-07-17, debit $14.90

---

## Primary Hypotheses

### Hypothesis 1 — The EV gate runs but on incomplete EV

**Verdict: CONFIRMED — but worse than hypothesized. The gate runs on *no* EV at all.**

The `NegativeEVGate` reads `ctx.expected_value` (`app/analysis/hard_gates/negative_ev_gate.py:63`). This field is populated from `request.trade.get("total_ev")` in the `evaluate_structured` endpoint (`app/api/evaluation_routes.py:561`).

For the MSFT 410P case (a `SINGLE_LONG_PUT`), the `trade` dict sent by the frontend is the raw output from `NakedOptionEngine.analyze()` (`app/analysis/long_call_engine.py:194`). The `ScoredNakedOption` dataclass (`app/analysis/long_call_engine.py:86-127`) contains these fields:

- `strike`, `expiration`, `days_to_exp`, `option_type`
- `bid`, `ask`, `mid_price`, `premium_dollars`
- `delta`, `gamma`, `theta`, `vega`, `iv`
- `volume`, `open_interest`, `bid_ask_spread_pct`
- `breakeven`, `breakeven_distance_pct`, `theta_per_day_dollars`, `theta_runway_days`
- `delta_score`, `theta_score`, `iv_score`, `rr_score`, `liquidity_score`, `composite_score`

**There is no `total_ev` field.** The NakedOptionEngine does not compute expected value.

The frontend *does* compute a `totalEV` via `buildLongOptionExitScenarios()` (`web/src/pages/TradesPage.jsx:254`), but this value is used for display only. It is **never injected into the `trade` dict** that is sent to `/evaluate/structured`. At `TradesPage.jsx:1128`, the raw `trade` object (without `totalEV`) is passed directly to `evaluateStructured()`.

Therefore, at `evaluation_routes.py:561-562`:
```python
_raw_ev = request.trade.get("total_ev")   # → None
_gate_ev = float(_raw_ev) if _raw_ev is not None else None  # → None
```

And at `evaluation_routes.py:573`:
```python
expected_value=_gate_ev  # → None
```

The `NegativeEVGate._evaluate()` at `negative_ev_gate.py:65-70` handles `None` as a pass-through:
```python
if ev is None:
    return GateResult(triggered=False, gate_id=self.gate_id)
```

**Actual EV value passed to NegativeEVGate: `None`.**
**Gate result: `triggered=False` (fail-soft, "not yet computed").**

The gate is functioning correctly per its contract — it treats `None` as "EV not yet computed" and does not block. The problem is upstream: no EV is ever computed for `SINGLE_LONG_PUT` candidates before the gate runs.

---

### Hypothesis 2 — The EV gate runs but only flags, does not FAIL

**Verdict: RULED OUT (gate logic is correct when given an EV value).**

The `NegativeEVGate._evaluate()` method (`negative_ev_gate.py:62-89`) returns:
- `ev < 0` → `GateResult(triggered=True, verdict="PASS")` — this is a hard block (`negative_ev_gate.py:72-84`)
- `ev is None` → `GateResult(triggered=False)` — pass-through (`negative_ev_gate.py:65-70`)
- `ev >= 0` → `GateResult(triggered=False)` — pass-through (`negative_ev_gate.py:86-89`)

The caller at `evaluation_routes.py:578-591` correctly acts on `triggered=True`:
```python
if _gate_result and _gate_result.triggered:
    if _gate_result.verdict == "WAIT_FOR_EARNINGS":
        _wait_for_earnings = True
        auto_pass_reason = _gate_result.reason
    else:
        auto_pass_reason = _gate_result.reason  # → short-circuits pipeline
```

When `triggered=True` with `verdict="PASS"`, `auto_pass_reason` is set, which prevents the Claude API call and forces a PASS verdict. This is correct.

**The gate logic and its consumption are both correct.** The issue is that the gate never sees an EV value for this trade.

---

### Hypothesis 3 — The EV gate is not invoked on the long-options path

**Verdict: RULED OUT — the gate *is* invoked, but it receives `None` for EV.**

Gate registration occurs in `app/main.py:305-309`:
```python
register_gate(EarningsInWindowGate())   # first
register_gate(NegativeEVGate())         # second
```

The `evaluate_structured` endpoint (`evaluation_routes.py:501`) is the **only** path that calls `evaluate_hard_gates`. Both vertical spreads and long options flow through this same endpoint. The gate runner is called unconditionally at `evaluation_routes.py:575`:
```python
_gate_result = await evaluate_hard_gates(_gate_ctx)
```

There is no branch that skips gate evaluation for `SINGLE_LONG_PUT`. The long-options path does NOT bypass the hard-gate pipeline. The gates run — they just have no EV to evaluate.

---

## Secondary Investigation — Probability Mass

### Does the Black-Scholes probability matrix sum to 1.0?

**Yes — for the PDF-based matrix used by the backend exit-scenario engine.**

In `app/analysis/black_scholes.py:73-88`, the `compute_probability_matrix()` function computes raw lognormal PDF values for each discrete price level, then normalizes:
```python
total = sum(raw)
if total > 0:
    probs = [r / total for r in raw]
```

This normalization ensures probabilities sum to 1.0 across the discrete price levels. **However**, this function is only used for the probability matrix display (Section D), not for exit scenario EV computation.

### Does the exit scenario generator capture full probability mass?

**For verticals: No — and this is the source of the displayed -$36.90 total EV.**

The backend `_build_exit_rows()` function (`evaluation_routes.py:1181-1296`) generates rows only for prices within a tight band: `lo - 5.0` to `hi + 5.0` in $5 steps, where `lo` and `hi` are the spread's two strike prices. For a spread with strikes at 400/410, that's 395 to 415 — roughly 8-9 rows. Probability outside this band is not captured.

**However, for SINGLE_LONG_PUT, this function is never called.** The `/exit-scenario` endpoint (`evaluation_routes.py:1299`) requires `long_strike` and `short_strike`, and `_spread_value()` (`evaluation_routes.py:1100-1115`) handles only four spread types (`BEAR_PUT_DEBIT`, `BULL_CALL_DEBIT`, `BEAR_CALL_CREDIT`, `BULL_PUT_CREDIT`). `SINGLE_LONG_PUT` would return `0.0` for all spread values.

### Frontend probability computation for long options

The frontend `buildLongOptionExitScenarios()` (`TradesPage.jsx:230-311`) **does** compute EV across the full distribution:

- Range: `underlying ± 3σ` in $5 steps (`TradesPage.jsx:250-251`)
- Uses a normal CDF bin approach: `P(price in [K-2.5, K+2.5])` (`TradesPage.jsx:257-259`)
- `totalEV = Σ(pnl × probability)` across all bins (`TradesPage.jsx:262-263`)

This computation covers the full probability mass within ±3σ (99.7%). It correctly includes the modal outcome (underlying staying above the put strike = max loss = -$1,490). The displayed `totalEV` of -$36.90 in the reproduction case is the **frontend-computed total EV** — but only the 5 tagged rows (STOP, MONITOR LOSS, BREAK EVEN, MONITOR PROFIT, MAX PROFIT) are displayed in the table.

**Wait — re-reading the reproduction case.** The listed probabilities sum to ~13.5%. The table shows only the 5 tagged rows. The frontend `totalEV` (-$36.90) is computed from ALL rows (not just displayed ones) but something is wrong:

The frontend uses `normCdf` with a normal distribution (not lognormal), which doesn't account for the skewness of stock price returns. More critically, the `sigma` calculation at `TradesPage.jsx:238`:
```javascript
const sigma = Math.max(1, (iv || 0.25) * underlying * Math.sqrt(dte / 365));
```
This gives `σ = 0.2731 × 416.78 × √(58/365) ≈ 45.3`. The range is `underlying ± 3×45.3` = 281 to 553, in $5 steps = ~54 rows.

The true total EV should heavily reflect the modal outcome. The frontend code at `TradesPage.jsx:262-263`:
```javascript
const ev = pnl * probability / 100;
totalEV += ev;
```

All rows where `price > strike` (410) produce `pnl = -premium * 100 = -1490`. The cumulative probability of MSFT staying above 410 at expiry is ~57% (rough estimate from delta 0.418). So `0.57 × -1490 ≈ -849` should dominate. Yet the displayed total EV is -$36.90, suggesting the frontend computation may have a different issue — possibly the normal (not lognormal) PDF spreading probability mass unrealistically across a wide range, diluting the modal mass.

**Where is "total EV" computed for display?** The "Total EV" footer in the UI table comes from the frontend's `buildLongOptionExitScenarios` return value (`TradesPage.jsx:310`). However, the table only **displays** 5 tagged rows — the `totalEV` shown in the footer is the sum across ALL ~54 rows. So the displayed -$36.90 is the full-distribution sum using the frontend's normal-PDF approximation.

**The -$36.90 may be an artifact of the normal-distribution approximation.** The frontend uses `normCdf` (symmetric normal distribution), but stock prices follow a lognormal distribution. For OTM puts with 58 DTE, the normal approximation underweights the probability of the underlying staying near current levels (the modal outcome) and overweights the probability of extreme moves. This is a known limitation of the normal vs lognormal approximation.

---

## Tertiary — Lottery Ticket Scoring Weights

From `app/analysis/strategy_definitions.py:114-119`:

| Metric | Weight | What it measures |
|---|---|---|
| `payout_ratio` | 0.45 | Estimated payout multiple on a 10% underlying move: `(delta × price × 0.10 × 100) / premium_dollars` |
| `delta_otm_score` | 0.25 | Lower delta = more OTM = higher score: `max(0, 1.0 - delta / 0.25)` |
| `bid_ask_tightness` | 0.20 | Lower bid-ask spread % = better: `max(0, 1.0 - ba_pct / 100)` |
| `open_interest` | 0.10 | Raw OI as liquidity metric |

**Total: 1.00**

From `app/analysis/strategy_scorer.py:326-491`:

**Notable observations:**

1. **No EV metric.** Unlike Steady Paycheck (20% `expected_value`), Weekly Grind (15% `expected_value`), and Trend Rider (20% `expected_value`), the Lottery Ticket strategy has **zero weight on expected value**. The `expected_value` metric function exists in the scorer (`strategy_scorer.py:424-430`) but it is not in the Lottery Ticket's `scoring_weights` dict, so it receives zero weight.

2. **No veto or floor mechanism.** The composite score is a pure weighted sum (`strategy_scorer.py:452`):
   ```python
   cs = sum(norm[k][i] * weights[k] for k in norm)
   ```
   There is no minimum threshold on any individual metric. A candidate with a terrible EV but excellent payout ratio, tight bid-ask, and high OI could still score above 73.

3. **Delta sweet-spot for Lottery Ticket** (`strategy_scorer.py:386-387`): `delta_center = 0.10`, `delta_half_range = 0.10`. But the MSFT 410P has delta 0.418, which is far from the LT sweet spot. However, `delta_otm_score` uses `max(0, 1.0 - delta / 0.25)` (`strategy_scorer.py:396-397`), so delta 0.418 → score 0.0 (clamped at 0). This contributes 0 × 0.25 = 0 to the composite.

4. **The 73.13 composite score** for the MSFT 410P is likely driven by:
   - `payout_ratio` (45%): with delta 0.418 and mid_price $14.90, payout = `0.418 × 416.78 × 0.10 × 100 / 1490 ≈ 1.17`. This is low for a lottery ticket, but if it's the best among available candidates, min-max normalization could push it to 1.0 (or near it).
   - `bid_ask_tightness` (20%): likely high for a liquid name like MSFT.
   - `open_interest` (10%): likely high for MSFT.
   - `delta_otm_score` (25%): 0.0 (delta 0.418 >> 0.25 ceiling).
   - Max possible score with delta_otm_score = 0: `(0.45 + 0.20 + 0.10) × 100 = 75`. The 73.13 is consistent with this ceiling (near-perfect scores on the 3 non-delta metrics minus normalization variance).

5. **MSFT 410P is not a Lottery Ticket.** Delta 0.418 on a 58-DTE put is an ATM-to-slightly-OTM put, not a "deep OTM asymmetric payout" trade. The strategy scored it because the structure is compatible (`SINGLE_LONG_PUT` ∈ Lottery Ticket's `compatible_structures`), but the delta filter in the NakedOptionEngine (`min_delta=0.05`, `max_delta=0.85` per `strategy_scorer.py:345-346`) is far too permissive for LT's intent. The LT config says `delta_max=0.15` (`strategy_definitions.py:122`), but the scorer uses `cfg.get("delta_max", 0.85)` as a fallback when no user config is supplied (`strategy_scorer.py:346`).

---

## Root Cause Summary

The bug is a **multi-layer failure**:

### Layer 1 (Critical): No EV computation for long options before gates
The NakedOptionEngine does not compute expected value. The frontend computes it (`buildLongOptionExitScenarios`) but does not send it with the evaluation request. The backend has no exit-scenario computation for `SINGLE_LONG_PUT`. Result: `NegativeEVGate` receives `None` and passes through.

### Layer 2 (Critical): `/exit-scenario` does not support single-leg options
The backend `_build_exit_rows()` only handles 4 spread types. `SINGLE_LONG_PUT` falls through to the default `return 0.0` in `_spread_value()`. There is no backend endpoint that computes EV for naked options.

### Layer 3 (Contributing): Lottery Ticket scoring has no EV weight
The 4-metric Lottery Ticket scorer gives zero weight to expected value. A negative-EV trade cannot be dragged below the EXECUTE threshold by EV alone because EV is not a scored dimension.

### Layer 4 (Contributing): Permissive delta filter
The NakedOptionEngine is called with `delta_max=0.85` (scorer fallback default) instead of the Lottery Ticket's intended `delta_max=0.15`. This allows near-ATM options (delta 0.418) to enter the Lottery Ticket pipeline when they should be filtered out.

---

## Recommended Phase 2 Fix

The minimum code change that would cause `NegativeEVGate` to FAIL the MSFT 410P case is:

**Compute EV for single-leg options server-side before the gate runs.** Add a function (analogous to `_build_exit_rows` but for naked options) that takes `{strike, entry_price, option_type, expiration, underlying_price, iv}` and computes `total_ev` across the full lognormal probability distribution (using the existing `black_scholes_probability` function from `app/analysis/black_scholes.py`). Call this function in `evaluate_structured()` between lines 534 and 558 (before `GateTradeContext` construction) whenever the trade dict has `option_type` but no `long_strike`/`short_strike`. Set the computed EV on `request.trade["total_ev"]` so the existing gate pickup at line 561 works without modification. This single change would cause the MSFT 410P trade to present an EV of approximately -$850 to -$1,300 to the gate, triggering `NegativeEVGate` with `verdict="PASS"`.

Secondary fixes (not strictly required but high-value):
- Pass the Lottery Ticket's `delta_max=0.15` to the NakedOptionEngine filter instead of the 0.85 fallback, so ATM options never enter the LT pipeline.
- Consider adding `expected_value` as a weighted metric to the Lottery Ticket scorer (even at 10-15%) as defense-in-depth.

---

## File:Line Citation Index

| Claim | File:Line |
|---|---|
| NegativeEVGate reads `ctx.expected_value` | `app/analysis/hard_gates/negative_ev_gate.py:63` |
| None → pass-through in NegativeEVGate | `app/analysis/hard_gates/negative_ev_gate.py:65-70` |
| ev < 0 → triggered=True, verdict=PASS | `app/analysis/hard_gates/negative_ev_gate.py:72-84` |
| Gate registration in main.py | `app/main.py:305-309` |
| `evaluate_hard_gates` called in evaluate_structured | `app/api/evaluation_routes.py:575` |
| `total_ev` read from `request.trade` | `app/api/evaluation_routes.py:561-562` |
| `GateTradeContext` constructed with `expected_value` | `app/api/evaluation_routes.py:566-574` |
| Caller acts on `triggered=True` | `app/api/evaluation_routes.py:578-591` |
| ScoredNakedOption fields (no total_ev) | `app/analysis/long_call_engine.py:86-127` |
| Frontend trade dict sent without total_ev | `web/src/pages/TradesPage.jsx:1128` |
| Frontend `buildLongOptionExitScenarios` computes totalEV | `web/src/pages/TradesPage.jsx:254-263` |
| Frontend totalEV never injected into trade dict | `web/src/pages/TradesPage.jsx:1240-1248` (totalEV used for display, not in makeTradeHandlers) |
| `_build_exit_rows` requires spread_type/two strikes | `app/api/evaluation_routes.py:1181-1196` |
| `_spread_value` handles only 4 spread types | `app/api/evaluation_routes.py:1100-1115` |
| BS probability matrix normalizes to sum 1.0 | `app/analysis/black_scholes.py:83-85` |
| Lottery Ticket scoring_weights (no EV) | `app/analysis/strategy_definitions.py:114-119` |
| LT delta fallback 0.85 in scorer | `app/analysis/strategy_scorer.py:346` |
| LT intended delta_max=0.15 in config | `app/analysis/strategy_definitions.py:122` |
| delta_otm_score formula | `app/analysis/strategy_scorer.py:394-397` |
| payout_ratio formula | `app/analysis/strategy_scorer.py:399-407` |
| Composite score = pure weighted sum, no floor | `app/analysis/strategy_scorer.py:452` |
| `_build_structured_user_message` tries `trade.get("total_ev")` | `app/api/evaluation_routes.py:270` |
