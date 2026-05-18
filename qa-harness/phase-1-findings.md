# QA Harness — Phase 1 Discovery Findings

**Date:** 2026-05-15
**Status:** Awaiting Don's approval before Phase 2 implementation begins

---

## 1. Endpoint Inventory (Section 10, Item 1)

### Stage 1 — Security Strategies Card Scan

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/analyze/scorecard` |
| **File** | `app/api/analysis_routes.py` (lines 838-933) |
| **Auth** | Tier 1 (require_read) |
| **Request** | `{ symbol: str, user_config?: { [strategy_key]: { dte_min, dte_max } } }` |
| **Response** | `ScorecardResponse` — see below |

**Response shape:**
```json
{
  "symbol": "VOO",
  "underlying_price": 512.30,
  "quote": { "price", "change", "change_pct", "volume", "rel_volume", "description" },
  "sma_signal": { "sma_8", "sma_21", "sma_50", "alignment" },
  "strategies": [
    {
      "strategy_key": "steady-paycheck",
      "label": "Steady Paycheck",
      "score": 85,
      "best_trade": { ... },
      "signal_summary": { ... },
      "metric_scores": { ... },
      "reason": null
    }
  ]
}
```

- `score` is 0-100 or `null` when no eligible candidates exist.
- `reason` is populated when `score` is null (e.g., "No compatible structures in DTE window").
- `best_trade` contains the top candidate for that strategy (the `argmax_spread_ref` equivalent).

**Harness implication:** This is the sole Stage 1 endpoint. One call per symbol returns all four strategy scores. The `sma_signal` block provides the SMA alignment needed for assertion A8. The `quote` block provides spot price and IV context. Missing from the response: IV rank, ATR-14, VIX, SPY 5d trend, QQQ 5d trend, regime note. These will need to be captured from either market data endpoints or computed/hardcoded for the harness context.

---

### Stage 2 — Trades Page Candidate List

There is **no single "Trades page" endpoint**. The frontend calls two separate scan endpoints:

#### 2a. Vertical Spreads

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/analyze/verticals` |
| **File** | `app/api/analysis_routes.py` (lines 493-667) |
| **Auth** | Tier 1 |
| **Request** | `{ symbol, spread_types?, max_results?, enabled_strategies?, user_config?, ...filter_overrides }` |

**Response per spread:**
```
spread_type, long_strike, short_strike, option_type, expiration, dte,
net_debit, max_profit, breakeven, reward_risk_ratio, prob_of_profit,
ev_raw, composite_score, fitting_strategies[], trade_key,
long_volume, short_volume, long_oi, short_oi,
ev_score, rr_score, prob_score, liquidity_score, theta_score
```

Key fields for harness:
- `fitting_strategies[]` — the strategy pills (A3 assertion source)
- `composite_score` — the row-level score
- `spread_type` — classification check (A7); values are engine-level: `"bull_call"`, `"bear_put"`, `"bull_put"`, `"bear_call"`
- `trade_key` — UUID for cross-stage linking

#### 2b. Long Options (Calls/Puts)

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/analyze/long-calls` |
| **File** | `app/api/analysis_routes.py` (lines 669-795) |
| **Auth** | Tier 1 |
| **Request** | `{ symbol, option_types?, max_results?, ...filter_overrides }` |

**Response per option:**
```
strike, option_type, expiration, days_to_exp, bid, ask, mid_price,
delta, theta_per_day_dollars, iv, volume, open_interest, breakeven,
composite_score, delta_score, theta_score, iv_score, rr_score,
liquidity_score, trade_key
```

**Harness implication:** The harness must call both endpoints to cover all four strategies:
- Steady Paycheck + Weekly Grind use verticals (credit spreads)
- Trend Rider uses verticals (debit spreads)
- Lottery Ticket uses long-calls/long-puts

The "section grouping" the spec describes is a frontend concern — the backend returns `fitting_strategies[]` per row, and the frontend groups rows by best-fit strategy. The harness will need to replicate this grouping logic (or capture it from the frontend's perspective).

**Footer:** The "No compatible setups today for: X, Y" footer is **frontend-generated** from the scorecard response (strategies where `score` is null). Not an API field.

---

### Stage 3 — Trade Detail Expansion

**There is NO separate detail endpoint.** The scan responses (verticals + long-calls) already contain full trade detail inline. Each spread/option object in the Stage 2 response IS the detail.

**Exit Scenario Calculation** (supplemental):

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/evaluate/exit-scenario` |
| **File** | `app/api/evaluation_routes.py` |
| **Request** | Spread economics (entry price, max profit, max loss, etc.) |
| **Response** | `{ rows[], breakeven, max_profit_price, max_loss_price, total_ev, dte, time_exit_date }` |

**Harness implication:** Stage 3 in the spec (trade detail expansion) maps to two data sources:
1. The inline fields from Stage 2 scan response (strikes, greeks, scores)
2. The exit-scenario endpoint for the outcome table (probabilities, EV, exit signals)

The `best_fit_strategy` and `best_fit_score` mentioned in the spec are **not direct API fields** — they are derived by the frontend from the `fitting_strategies[]` array and the scorecard scores. The harness will need to replicate this derivation.

---

### Stage 4 — Claude Evaluation (Foundry)

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/evaluate/structured` |
| **File** | `app/api/evaluation_routes.py` (lines 499-1040) |
| **Auth** | Tier 1 |

**Request:**
```json
{
  "symbol": "VOO",
  "current_price": 512.30,
  "iv": 0.18,
  "sma_alignment": { "sma_8": 510, "sma_21": 505, "sma_50": 498, "alignment": "bullish" },
  "strategy_keys": ["steady-paycheck", "trend-rider"],
  "scores": { "steady-paycheck": 85, "trend-rider": 72 },
  "trade": { ... },
  "trade_key": "uuid-from-stage-2"
}
```

**Response — per TradeEvaluationCard:**
```
strategy_key, strategy_label, trade_structure,
entry_price, max_profit, max_loss,
exit_warning_price, exit_warning_pnl, exit_target_debit, exit_stop_debit,
probability_matrix (embedded B-S matrix),
score (0-100), verdict ("EXECUTE"|"WAIT"|"PASS"),
claude_read (narrative text),
key_risks[], thesis_invalidators[],
auto_pass_reason (if hard-gated),
dte_warning (if 8-13 DTE),
asymmetry_penalty,
effective_dte, credit_pct_of_width, debit_pct_of_width
```

**Hard gate pipeline (pre-Claude):**
1. Earnings date within window -> auto-PASS (no Claude call)
2. DTE < 8 -> auto-PASS
3. Credit < 30% of width -> auto-PASS
4. Debit > 40% of width -> auto-PASS
5. DTE 8-13 -> 20-point penalty (Claude still called)
6. Negative EV -> gate behavior TBD (need to verify)

**Post-Claude processing:**
- Verdict band enforcement: score >= 70 -> EXECUTE, 50-69 -> WAIT, < 50 -> PASS
- Asymmetry penalty if prob_max_loss > prob_max_profit
- Narrative grounding retry (OTA-504)
- Strategy classifier ranking (OTA-506)

**Harness implication:** This is the richest capture point. The `auto_pass_reason` field directly tells us which hard gate fired (A5 assertion). The `verdict` + `claude_read` pair is the A6 assertion target. The `score` breakdown components are the A10 reconciliation target. The `trade_key` links back to Stage 2.

---

### Stage 5 — Order Generation

**No dedicated order generation endpoint was found.** The TOS order block is likely frontend-only rendering based on trade detail data. The harness spec already marks Stage 5 as observational with no assertions — this finding confirms there's nothing to capture from the backend for v1.0.

---

## 2. Strategy Config Endpoint (Section 10, Item 2)

**There is no dedicated "get effective config" endpoint.** The strategy configuration is:

- **Backend source of truth:** `app/analysis/strategy_definitions.py` — `STRATEGIES` dict containing `StrategyDefinition` dataclasses with `dte_min`, `dte_max`, `scoring_weights`, `compatible_structures`, delta/IV thresholds, exit parameters.
- **User overrides:** Passed per-request via `user_config` parameter on scorecard and verticals endpoints.
- **Effective config:** The backend merges `STRATEGIES[key]` defaults with `user_config` overrides at call time. There is no endpoint that returns the merged result.

**Harness implication:** To capture the effective config, the harness should:
1. Read `STRATEGIES` from `strategy_definitions.py` (import directly since the harness runs in the same Python env)
2. Record whatever `user_config` overrides it passes (if any — for determinism, the harness should pass NO overrides and use defaults)
3. Log both in the capture JSON for auditability

---

## 3. Canonical Compatibility Map (Section 10, Item 3)

**Found.** Single source of truth in `app/analysis/strategy_definitions.py`:

| Strategy Key | Compatible Structures |
|---|---|
| `steady-paycheck` | `bull_put_credit`, `bear_call_credit` |
| `weekly-grind` | `bull_put_credit`, `bear_call_credit` |
| `trend-rider` | `bull_call_debit`, `bear_put_debit` |
| `lottery-ticket` | `long_call`, `long_put` |

**Routing functions** in `app/analysis/strategy_routing.py`:
- `is_compatible(strategy_key, structure)` — single check
- `get_compatible_strategies(structure)` — inverse lookup
- `normalize_to_structure(spread_type, option_type)` — converts engine-level types to structure names

**Engine-level to structure mapping:**
```
bull_call -> bull_call_debit
bear_put  -> bear_put_debit
bull_put  -> bull_put_credit
bear_call -> bear_call_credit
call      -> long_call
put       -> long_put
```

**Harness implication:** The harness can import `strategy_routing.py` directly for A3 assertions. No need to duplicate the compatibility map — just import `is_compatible()` and `get_compatible_strategies()`.

**Spread type classification** happens deterministically in the engine builders (`vertical_engine.py` lines 289-369). Spreads are never classified as `UNKNOWN` — they're built with explicit types. If an UNKNOWN appears, it's a bug upstream of the engine (e.g., structure derivation in evaluation_routes.py).

---

## 4. Trade Key Stability (Section 10, Item 4)

**Trade keys are NOT deterministic.** They are `uuid.uuid4()` — random UUIDs generated fresh on every scan call.

- Generated in `_build_vertical_candidate()` and `_build_long_option_candidate()` in `analysis_routes.py`
- Persisted to `TradeCandidate` table as primary key
- Each scan run produces entirely new UUIDs even for identical (symbol, strikes, expiration) combinations

**Harness implication — CRITICAL for cross-run assertions (D3, D4, D5):**

The harness CANNOT match trades across runs by `trade_key`. Cross-run matching must use a **natural key** composed of:
```
(symbol, spread_type, long_strike, short_strike, expiration)  — for verticals
(symbol, option_type, strike, expiration)                      — for long options
```

The harness should:
1. Compute this natural key for each trade in every run
2. Use the natural key for D3/D4/D5 cross-run comparisons
3. Store the actual `trade_key` UUID in captures for Stage 4 linking within a single run

---

## 5. Authentication (Section 10, Item 5)

**Three-tier auth model:**
- **Tier 1 (READ):** JWT Bearer token. All analysis/scoring endpoints require this.
- **Tier 2 (WRITE):** JWT + MFA. Positions endpoints require this.
- **Tier 3 (TRADE):** Per-trade challenge. Not needed for harness.

**Dev bypass:** When `settings.skip_auth=True` in `.env`, all auth is bypassed with a fake admin UUID.

**Harness auth strategy:**
- **Option A (recommended for dev):** Set `skip_auth=True` in the dev environment. The harness runs against dev only, and auth bypass simplifies the capture pipeline.
- **Option B (production-safe):** The harness authenticates via JWT. It would need a service account or Don's credentials to obtain a token. Since the harness only needs Tier 1 (READ) access for Stages 1-4, and Tier 2 for Stage 5 position follow (which is observational-only in v1.0), JWT is sufficient.

**Recommendation:** Option A for Phase 2-4 development. Option B when the harness runs in CI.

---

## 6. Backend Cache Behavior (Section 10, Item 6)

**No scoring/analysis caching exists.** Every call to `/analyze/scorecard`, `/analyze/verticals`, `/analyze/long-calls`, and `/evaluate/structured` triggers:
1. Fresh options chain fetch from Schwab provider
2. Fresh scoring computation
3. Fresh TradeCandidate persistence

**The only cache in the system:** `@lru_cache(maxsize=16)` on `SkillLoader.get_skill()` — caches SKILL.md file reads. This affects Claude evaluation prompts but not scoring math.

**Harness implication:**
- **Good news:** No cache means each harness run exercises the full pipeline. No risk of masked bugs from stale cache hits.
- **Bad news:** No cache means each run triggers a Schwab API call for chain data. During market-closed hours, chain data is static, so results SHOULD be identical — but the provider call itself could theoretically return slightly different timestamps or metadata.
- **Risk:** If Schwab's closed-market chain response includes any non-deterministic fields (e.g., `lastTradeTimestamp` that updates on each API call), those could propagate into scoring inputs and cause spurious D1 failures. The harness should capture raw chain data and compare at the scoring-input level, not the raw-provider level.

---

## 7. Harness Design Implications — Summary

### Endpoint call sequence per symbol per run:

```
1. POST /api/v1/analyze/scorecard          -> Stage 1 capture
2. POST /api/v1/analyze/verticals          -> Stage 2a capture (SP, WG, TR candidates)
3. POST /api/v1/analyze/long-calls         -> Stage 2b capture (LT candidates)
4. POST /api/v1/evaluate/exit-scenario     -> Stage 3 supplement (per top candidate)
5. POST /api/v1/evaluate/structured        -> Stage 4 capture (per top candidate)
```

### Key design decisions needed for Phase 2:

| Decision | Options | Recommendation |
|---|---|---|
| **Natural key for cross-run matching** | (symbol, type, strikes, expiry) | Use this composite; document in harness config |
| **Auth model** | skip_auth=True vs JWT | skip_auth for dev; JWT for CI |
| **Which candidates get Stage 4 evaluation?** | All candidates vs top-N per strategy | Top 1 per strategy (matches scorecard `best_trade`) to limit Claude calls |
| **Market hours detection** | Build new utility vs simple time check | Simple check: `datetime.now(ET).hour` + weekday. No holiday calendar in v1.0 |
| **Footer "no compatible setups" assertion** | Capture from API vs derive from scorecard | Derive: strategy with `score=null` in scorecard = "no compatible setups" |
| **best_fit derivation** | Capture from frontend vs replicate in harness | Replicate: use `fitting_strategies[0]` + scorecard scores to determine best_fit |
| **user_config overrides** | Pass custom vs use defaults | Use defaults only (no `user_config` parameter) for determinism |

### Missing from current API (gaps the harness must work around):

1. **No IV rank in scorecard response** — needed for input capture. May need a separate market data call or derive from chain data.
2. **No ATR-14, VIX, SPY/QQQ 5d trend in scorecard** — these are market context fields. The harness may need to call a market data endpoint or accept that these are not captured at Stage 1.
3. **No "section grouping" from API** — the Trades page grouping is frontend logic. The harness must replicate it from `fitting_strategies[]` + scorecard scores.
4. **No score component breakdown in Stage 4 response** — need to verify whether `TradeEvaluationCard` includes a component-level breakdown for A10 reconciliation, or if only the total score is returned.

---

## 8. Open Questions for Don

1. **Stage 4 scope:** Should the harness evaluate ALL candidates per strategy, or only the `best_trade` from the scorecard? Evaluating all would be thorough but expensive (one Claude call per candidate). Evaluating only the best trade per strategy = 4 Claude calls per symbol max.

2. **Market context fields:** The spec calls for capturing VIX, SPY 5d trend, QQQ 5d trend, and regime note. These aren't in the scorecard response. Should we add a market context capture step (calling the quote endpoint for $VIX, SPY, QQQ), or accept that these are out of scope for v1.0?

3. **Dev environment target:** Should the harness run against `oa-dev.tmtctech.ai` or `localhost:8000`? Running against dev means Schwab OAuth must be active; running locally means the backend must be started manually.

4. **Claude cost per full run:** 5 symbols x 4 strategies x 5 runs = up to 100 Claude calls per full harness execution. At ~$0.10-0.30 per structured evaluation call, that's $10-30 per full run. Is this acceptable, or should we cap evaluations?
