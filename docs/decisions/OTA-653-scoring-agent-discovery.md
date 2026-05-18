# Scoring Agent Architecture: Discovery Document

**Story:** OTA-653
**Date:** 2026-05-18 UTC
**Author:** Claude Code (Opus 4.6)
**Status:** Discovery complete — awaiting Don's decision

---

## Phase 1 — Codebase Mapping

### Summary

The scoring pipeline spans 19 distinct sites across 15 backend files and 14 frontend files. Each site is cataloged below with its file path, line range, what it produces, what it consumes, call sites, and Bright-line / Judgment / Unclear classification.

### Backend Scoring Sites

#### Site B1: Strategy Scorer — `score_all_strategies()`
- **File:** `app/analysis/strategy_scorer.py` lines 539–625
- **Produces:** `List[StrategyScore]` — score 0–100 per strategy, best_trade, signal_summary, metric_scores
- **Consumes:** symbol, provider (market data), user_config overrides
- **Call sites:** `POST /api/v1/analyze/scorecard` (analysis_routes.py:838–932)
- **Classification: Bright-line.** Orchestrator that delegates to deterministic engines (B2, B3). No judgment of its own — runs each engine, collects results, returns them.

#### Site B2: Vertical Spread Engine — `VerticalSpreadEngine.analyze()` / `_score_all()`
- **File:** `app/analysis/vertical_engine.py` lines 212–285 (analyze), 645–769 (_score_all)
- **Produces:** `ScoredSpread` objects with composite_score (0–100) and 5 component scores (0–1 normalized via min-max)
- **Consumes:** option chain contracts, underlying_price, ScoringWeights (per-strategy from STRATEGIES dict), SpreadFilters
- **Call sites:** `_score_credit_spread_strategy()` in strategy_scorer.py:408; `_score_debit_spread_strategy()` (TR)
- **Classification: Bright-line.** Min-max normalization across candidate set, weighted average with fixed weights from `strategy_definitions.py`. Fully deterministic given the same inputs and candidate set.

#### Site B3: Long Option Engine — `NakedOptionEngine.analyze()` / `_score_all()`
- **File:** `app/analysis/long_call_engine.py` lines 148–200 (analyze), 300–374 (_score_all)
- **Produces:** `ScoredNakedOption` objects with composite_score (0–100) and 5 component scores (0–1 normalized)
- **Consumes:** option chain contracts, underlying_price, NakedOptionWeights, NakedOptionFilters
- **Call sites:** `_score_long_option_strategy()` in strategy_scorer.py:510
- **Classification: Bright-line.** Same min-max + weighted average pattern as B2. Delta sweet-spot uses Gaussian distance metric centered at 0.45 — still deterministic.

#### Site B4: Strategy Routing — Compatibility Predicates
- **File:** `app/analysis/strategy_routing.py` lines 42–104
- **Produces:** Boolean compatibility (`is_compatible()`), strategy key lists (`get_compatible_strategies()`), engine parameter mappings
- **Consumes:** strategy_key and structure string; reads `STRATEGIES` dict from strategy_definitions.py
- **Call sites:** strategy_classifier.py:129, strategy_scorer.py (implicit), evaluation_routes.py (normalize_to_structure), qa-harness assertions
- **Classification: Bright-line.** Pure lookup against the STRATEGIES dict. No judgment, no weighing.

#### Site B5: Strategy Classifier — `classify_best_strategy()`
- **File:** `app/analysis/strategy_classifier.py` lines 104–157
- **Produces:** `StrategyClassification` — best_fit strategy key, score, reason
- **Consumes:** pre-scored StrategyScore list, effective_dte, trade_structure
- **Call sites:** evaluation_routes.py (structured eval), position_routes.py (follow/take)
- **Classification: Bright-line.** Filters by DTE eligibility and structural compatibility, then selects argmax score. No judgment — deterministic selection from already-scored candidates.

#### Site B6: Hard Gates Framework — `evaluate_hard_gates()`
- **File:** `app/analysis/hard_gates/__init__.py` lines 130–169
- **Produces:** `Optional[GateResult]` — triggered/not, verdict (PASS/WAIT_FOR_EARNINGS), penalty_points, effective_dte_override
- **Consumes:** `GateTradeContext` (symbol, entry_date, expiry_date, dte, trade dict, db session, expected_value)
- **Call sites:** evaluation_routes.py:574 (single call site)
- **Classification: Bright-line.** Registry evaluator — runs registered gates in order, returns first triggered. Framework itself is deterministic; individual gates may differ (see B7, B8).

#### Site B7: Earnings Gate — `EarningsInWindowGate.evaluate()`
- **File:** `app/analysis/hard_gates/earnings_gate.py` lines 115–246
- **Produces:** `GateResult` — one of four routes per OTA-515 decision tree (hard block PASS, WAIT_FOR_EARNINGS, or penalty+dte_override)
- **Consumes:** symbol, dte, expiry, earnings date from ContextStore (Finnhub), trading day counts
- **Call sites:** Gate registry (invoked by B6)
- **Classification: Bright-line.** Decision tree based on concrete calendar arithmetic (business days between dates). No judgment.

#### Site B8: Negative EV Gate — `NegativeEVGate.evaluate()`
- **File:** `app/analysis/hard_gates/negative_ev_gate.py` lines 30–89
- **Produces:** `GateResult` — triggered (PASS) when EV < 0, not triggered when EV ≥ 0 or null
- **Consumes:** `GateTradeContext.expected_value`
- **Call sites:** Gate registry (invoked by B6)
- **Classification: Bright-line.** Single comparison: `EV < 0`.

#### Site B9: Asymmetry Penalty — `asymmetry_penalty()`
- **File:** `app/analysis/scoring_factors/asymmetry.py` lines 16–41
- **Produces:** Penalty points (0, 8, 15, or 25) deducted from score
- **Consumes:** p_max_loss, p_max_profit (probabilities from exit scenario)
- **Call sites:** strategy_scorer.py:497, strategy_scorer.py:535, evaluation_routes.py:854
- **Classification: Bright-line.** Graduated threshold lookup: ratio < 1.25 → 0, ≥ 1.25 → 8, ≥ 1.5 → 15, ≥ 2.0 → 25.

#### Site B10: Verdict Banding — `_assign_verdict()`
- **File:** `app/api/evaluation_routes.py` lines 174–181
- **Produces:** Verdict string: "EXECUTE" (≥70), "WAIT" (50–69), "PASS" (<50)
- **Consumes:** Final score (float, 0–100)
- **Call sites:** evaluation_routes.py:860, evaluation_routes.py:936 (called for every card after all penalties applied)
- **Classification: Bright-line.** Three-threshold lookup. Comment in code: "This is the ONLY place verdicts are assigned from scores."

#### Site B11: DTE Inline Gate
- **File:** `app/api/evaluation_routes.py` lines 594–604
- **Produces:** auto_pass_reason (DTE ≤ 7) or dte_warning_msg + 20-point penalty (DTE 8–13)
- **Consumes:** Computed DTE from expiration string
- **Call sites:** Inline in evaluate_structured endpoint (single site)
- **Classification: Bright-line.** `if dte <= 7: auto_pass` / `elif dte <= 13: -20 points`. Pure threshold.

#### Site B12: Credit/Debit Width Gate
- **File:** `app/api/evaluation_routes.py` lines 607–629
- **Produces:** auto_pass_reason when credit < 30% of width or debit > 40% of width
- **Consumes:** net_debit, spread_width from trade dict
- **Call sites:** Inline in evaluate_structured endpoint (single site)
- **Classification: Bright-line.** `credit_pct < 0.30 → auto_pass` / `debit_pct > 0.40 → auto_pass`. Fixed thresholds.

#### Site B13: Claude Deep Dive Evaluation — Foundry/Anthropic API call
- **File:** `app/api/evaluation_routes.py` lines ~700–850 (prompt construction + API call)
- **Produces:** `TradeEvaluationCard` JSON array: score (0–100), verdict (overridden by B10), claude_read (2–3 sentence narrative), key_risks[], thesis_invalidators[], exit_plan
- **Consumes:** Market context (price, SMAs, alignment), trade data (strikes, expiration, greeks), computed metrics (EV, debit_pct, cushion_pct, p_max_loss, p_max_profit), strategy_spec (from STRATEGIES dict), DEEP_DIVE_SYSTEM prompt from SKILL.md
- **Call sites:** evaluation_routes.py:~740 (single call site within evaluate_structured)
- **Classification: Judgment.** This is the LLM call. Claude assigns a score, writes the narrative (claude_read), identifies key_risks and thesis_invalidators, and proposes exit_plan levels. The score is subsequently overridden by B10's verdict banding, but the narrative, risks, invalidators, and exit levels are wholly Claude's judgment.

#### Site B14: Narrative Grounding Validator — `validate_narrative()`
- **File:** `app/validators/narrative_grounding.py` lines 149–157
- **Produces:** `List[ValidationError]` — catches EV contradictions, SMA positional contradictions, SMA hallucinations
- **Consumes:** narrative text (from Claude), computed fields (price, SMAs, expected_value)
- **Call sites:** evaluation_routes.py:~510–540 (post-Claude validation)
- **Classification: Bright-line.** Pattern matching (regex) against known contradiction signatures. No judgment — either the narrative contradicts the data or it doesn't.

#### Site B15: Health Grade — `compute_health_grade()`
- **File:** `app/analysis/health_grade.py` lines 23–89
- **Produces:** Letter grade A–F based on P&L percentage or proximity to Claude exit levels
- **Consumes:** entry_price, current_price, optional claude_exit_levels_json
- **Call sites:** position_monitor.py, position_routes.py
- **Classification: Bright-line.** Fixed P&L brackets: ≥0% → A, 0 to −10% → B, −10 to −25% → C, −25 to −50% → D, < −50% → F.

#### Site B16: Position Monitor Agent
- **File:** `app/agents/position_monitor.py` lines 87–219
- **Produces:** PositionHealthUpdate (health_grade, current_pnl, needs_insight flag); writes position table updates
- **Consumes:** All open positions, symbol context from ContextSource adapters, SKILL.md prompt
- **Call sites:** `/agents/position-monitor/run` endpoint, APScheduler
- **Classification: Judgment.** Makes a Claude API call to assess all open positions, parse health updates, and flag positions needing insights. The grade itself uses B15 (bright-line), but the overall assessment and "needs_insight" flag involve Claude judgment.

#### Site B17: Insight Engine — `InsightEngine.generate()`
- **File:** `app/agents/insight_engine.py` lines 68–220
- **Produces:** Insight row: title, body, severity, recommended_actions, deviation_score
- **Consumes:** deviation result, context signals, domain SKILL.md
- **Call sites:** position_monitor.py:179 (triggered by B16)
- **Classification: Judgment.** Claude generates the insight narrative, title, severity, and recommendations from deviation context.

#### Site B18: Black-Scholes Probability Matrix — `compute_probability_matrix()`
- **File:** `app/analysis/black_scholes.py` lines 16–95
- **Produces:** 2D probability matrix (price levels × dates)
- **Consumes:** underlying_price, iv, dte, risk_free_rate
- **Call sites:** analysis_routes.py (probability-matrix endpoint), evaluation_routes.py (embedded in cards)
- **Classification: Bright-line.** Lognormal distribution math. Fully deterministic.

#### Site B19: Strategy Definitions (Data)
- **File:** `app/analysis/strategy_definitions.py` lines 38–127
- **Produces:** `STRATEGIES` dict with per-strategy: compatible_structures, DTE windows, scoring_weights, delta/IV thresholds, exit parameters
- **Consumes:** Nothing (static data)
- **Call sites:** strategy_routing.py, strategy_scorer.py, strategy_classifier.py, evaluation_routes.py
- **Classification: Bright-line.** Static configuration data. No computation.

### Frontend Consumer Sites

#### Site F1: TradeEvaluationCard.jsx (710 lines)
- **Consumes:** card prop with score, verdict, claude_read, key_risks, thesis_invalidators, exit_levels, probability_matrix, auto_pass_reason
- **Source:** `POST /evaluate/structured` response
- **Transformation:** None (raw display)
- **Classification:** Consumer only — no scoring logic

#### Site F2: StrategyScorecard.jsx (280 lines)
- **Consumes:** scores array with key, label, score, best_trade, signal_summary
- **Source:** `POST /analyze/scorecard` response
- **Transformation:** Score color mapping (green ≥70, amber 40–69, red <40); formatBestTrade() for display
- **Classification:** Consumer only — color thresholds mirror B10 bands

#### Site F3: ScanCard.jsx (270 lines)
- **Consumes:** strategies array with key, label, score, reason
- **Source:** `POST /analyze/scorecard` response
- **Transformation:** Score color (same thresholds as F2), N/A handling
- **Classification:** Consumer only

#### Site F4: ScoreBar.jsx (31 lines)
- **Consumes:** score (0–100)
- **Transformation:** Color: green ≥75, cyan 55–74, yellow 40–54, orange <40
- **Note:** Different color thresholds from F2/F3 (75 vs 70 for green). Minor inconsistency.
- **Classification:** Consumer only

#### Site F5: ScoreCell.jsx (50 lines)
- **Consumes:** score (0–100)
- **Transformation:** Color: green ≥70, amber 40–69, red <40
- **Classification:** Consumer only

#### Site F6: PositionDetailPanel.jsx (286 lines)
- **Consumes:** pos with claude_verdict, claude_score, claude_read, claude_exit_levels, claude_probability_matrix, trade_structure
- **Source:** `GET /positions` response
- **Transformation:** Text truncation (200 chars); delta calculation to exit levels
- **Classification:** Consumer only

#### Site F7: ClaudesRead.jsx (221 lines)
- **Consumes:** result with verdict, ev_commentary, key_level, iv_context, verdict_rationale
- **Source:** `/evaluate/trade-verdict` response (legacy path)
- **Transformation:** None
- **Classification:** Consumer only (legacy)

#### Site F8: PositionsPage.jsx (964 lines)
- **Consumes:** All position fields, assessment versions, best_fit, is_orphaned
- **Source:** `GET /positions`, `GET /positions/{id}/assessments`, `POST /positions/{id}/refresh`
- **Transformation:** normalizePosition() flattens API response; scoreColor() function
- **Classification:** Consumer — normalizePosition() is a shape transform, not a scoring transform

#### Site F9: SecurityStrategiesPage.jsx (606 lines)
- **Consumes:** Strategy scores per symbol
- **Source:** `POST /analyze/scorecard`
- **Transformation:** buildScanResult() transforms API shape to ScanCard props; client-side sort by score
- **Classification:** Consumer only

#### Site F10: TradesPage.jsx
- **Consumes:** Vertical/long-call scan results, evaluation cards
- **Source:** `POST /analyze/verticals`, `POST /analyze/long-calls`, `POST /evaluate/structured`
- **Transformation:** buildExitScenarios() computes P&L across price range (this is bright-line math on the client)
- **Classification:** Consumer with local computation (exit scenarios). The exit scenario math is bright-line (P&L at each price point).

#### Site F11: StrategyPage.jsx
- **Consumes:** Positions filtered by strategy_key
- **Source:** `GET /positions`
- **Transformation:** normalizePos() shape transform
- **Classification:** Consumer only

#### Site F12: strategy-configs/ (6 config files + index.js)
- **Produces:** Strategy metadata (key, label, compatible_structures, DTE windows, color_text)
- **Consumes:** Nothing (static config, mirrors B19)
- **Note:** This is a frontend mirror of the backend STRATEGIES dict. Compatibility-filtering logic in TradesPage uses `getStrategiesForStructure()` from this registry.
- **Classification:** Consumer with duplicated routing data. A wiring concern — this is a copy of B4/B19 on the frontend side.

#### Site F13: positions-columns.jsx (204 lines)
- **Consumes:** score, health_grade, pnl_amount
- **Transformation:** Health sort weight mapping (A=5..F=1)
- **Classification:** Consumer only

#### Site F14: FormulaBreakdown.jsx / FormulaBreakdownPanel.jsx
- **Consumes:** Score component breakdown from evaluation
- **Source:** Card score_breakdown field
- **Transformation:** Display rendering of weighted components
- **Classification:** Consumer only

---

## Phase 2 — Categorization Tally

### Summary

| Category | Count | Percentage |
|---|---|---|
| Bright-line | 15 | 79% |
| Judgment | 3 | 16% |
| Unclear | 1 | 5% |

### Bright-line Sites (15)

| ID | Site | Location |
|---|---|---|
| B1 | Strategy Scorer orchestrator | strategy_scorer.py:539–625 |
| B2 | Vertical Spread Engine | vertical_engine.py:212–769 |
| B3 | Long Option Engine | long_call_engine.py:148–374 |
| B4 | Strategy Routing predicates | strategy_routing.py:42–104 |
| B5 | Strategy Classifier | strategy_classifier.py:104–157 |
| B6 | Hard Gates Framework | hard_gates/__init__.py:130–169 |
| B7 | Earnings Gate | hard_gates/earnings_gate.py:115–246 |
| B8 | Negative EV Gate | hard_gates/negative_ev_gate.py:30–89 |
| B9 | Asymmetry Penalty | scoring_factors/asymmetry.py:16–41 |
| B10 | Verdict Banding | evaluation_routes.py:174–181 |
| B11 | DTE Inline Gate | evaluation_routes.py:594–604 |
| B12 | Credit/Debit Width Gate | evaluation_routes.py:607–629 |
| B14 | Narrative Grounding Validator | narrative_grounding.py:149–157 |
| B15 | Health Grade | health_grade.py:23–89 |
| B18 | Black-Scholes Matrix | black_scholes.py:16–95 |

### Judgment Sites (3)

| ID | Site | Location |
|---|---|---|
| B13 | Claude Deep Dive Evaluation | evaluation_routes.py:~700–850 |
| B16 | Position Monitor Agent | position_monitor.py:87–219 |
| B17 | Insight Engine | insight_engine.py:68–220 |

### Unclear Sites (1)

| ID | Site | Ambiguity |
|---|---|---|
| B19/F12 | Strategy Definitions / Frontend strategy-configs | The STRATEGIES dict is bright-line data, but it is duplicated between backend (B19) and frontend (F12). The duplication is a wiring problem — changes to strategy compatibility in B19 must be manually mirrored in F12 or the frontend will route incorrectly. This is neither bright-line nor judgment; it's a data synchronization concern that exists independent of the agent question. |

### Current Bright-Line Gate Values

| Gate | Threshold | Code Location |
|---|---|---|
| DTE hard floor | ≤ 7 → auto PASS | evaluation_routes.py:596 |
| DTE warning penalty | 8–13 → −20 points | evaluation_routes.py:601–603 |
| Credit % minimum | < 30% of width → auto PASS | evaluation_routes.py:616 |
| Debit % maximum | > 40% of width → auto PASS | evaluation_routes.py:624 |
| Negative EV | EV < 0 → auto PASS | negative_ev_gate.py:66 |
| Earnings in window | Decision tree (4 routes) | earnings_gate.py:115–246 |
| Asymmetry penalty | ratio ≥ 1.25 → 8pt, ≥ 1.5 → 15pt, ≥ 2.0 → 25pt | asymmetry.py:35–41 |
| Verdict: EXECUTE | score ≥ 70 | evaluation_routes.py:176 |
| Verdict: WAIT | score 50–69 | evaluation_routes.py:178 |
| Verdict: PASS | score < 50 | evaluation_routes.py:180 |

### Per-Strategy DTE Windows

| Strategy | DTE Min | DTE Max |
|---|---|---|
| Steady Paycheck | 14 | 45 |
| Weekly Grind | 14 | 21 |
| Trend Rider | 14 | 60 |
| Lottery Ticket | 7 | 60 |

### Per-Strategy Scoring Weights

**Steady Paycheck:** theta_margin_ratio (0.30), probability_of_profit (0.25), expected_value (0.20), reward_risk (0.15), iv_rank (0.10)

**Weekly Grind:** theta_gamma_ratio (0.35), probability_of_profit (0.25), credit_width_pct (0.20), expected_value (0.15), liquidity (0.05)

**Trend Rider:** sma_alignment_score (0.30), delta_quality (0.25), expected_value (0.20), iv_percentile_cost (0.15), runway_score (0.10)

**Lottery Ticket:** payout_ratio (0.45), delta_otm_score (0.25), bid_ask_tightness (0.20), open_interest (0.10)

---

## Phase 3 — Latency Analysis

### Assumptions

- Current Foundry Sonnet round-trip: 1.5–3.0s per call (based on typical Azure-hosted Claude Sonnet 4.6 response times for structured output with 1200 max_tokens)
- Backend scoring computation (B1–B12): <200ms total (chain fetch + scoring math)
- Schwab chain fetch: 300–800ms depending on symbol and chain depth

### Surface Analysis

| Surface | Current Call Shape | Current Latency | Agent Call Shape | Projected Agent Latency | Tolerable? |
|---|---|---|---|---|---|
| Security Strategies scan (20 symbols × 4 strategies) | 20 × `POST /analyze/scorecard` (each hits Schwab + scoring math) | ~15–20s total (parallel, bottlenecked by Schwab rate limits) | 20 × agent call per symbol | 20 × 2s = 40s minimum (serial); 10–15s with concurrency=4 | **No.** 40s serial breaks the progressive-render UX. Even at concurrency=4, 15s for a full scan is marginal. The current code-based path at 15–20s is already at the edge. |
| Trades page initial render (1 symbol, all scanners) | 1 × `POST /analyze/verticals` + 1 × `POST /analyze/long-calls` | ~1–2s (single Schwab fetch shared, scoring math) | 1 × agent call | 2–3s | **Yes**, but barely. Currently sub-2s; agent adds 1–2s. |
| Trade detail expansion | No separate call (data inline from Trades scan) | ~0ms (already loaded) | N/A — detail is inline | N/A | N/A |
| Evaluate button (single trade) | 1 × `POST /evaluate/structured` (Foundry call) | 2–4s (chain fetch + hard gates + Claude call + validation) | Already an agent call (B13) | Same: 2–4s | **Yes.** Intentional user action; 3s is well within tolerance. |

### Key Finding

The only surface where an agent call could replace code-based scoring is the scorecard scan (Security Strategies). This is also the surface least tolerant of latency. The trades page scan and evaluation are already fast enough or already use Claude. Replacing the code-based scoring engines (B1–B3) with agent calls would degrade the scan experience from ~15s to ~40s (serial) or ~15s (highly concurrent), with no quality improvement — the scoring math is deterministic and already correct.

---

## Phase 4 — Cost Projection

### Assumptions

| Parameter | Value | Source |
|---|---|---|
| Daily active users | 1 (Don) | Current state |
| Sessions per day | 3 | Estimated |
| Symbols scanned per session | 10 | Typical watchlist subset |
| Candidates evaluated per session | 4 (1 per strategy top-pick) | Evaluate button clicks |
| Token cost (Sonnet 4.6) | $3.00 / 1M input, $15.00 / 1M output | Current Anthropic pricing |
| Avg input tokens per scorecard call | ~2,000 (market context + 4 strategy specs) | Estimated from SKILL.md |
| Avg output tokens per scorecard call | ~800 (4 strategy cards) | Estimated from current eval output |
| Avg input tokens per evaluation | ~3,000 (full trade context + metrics) | Measured from agent_run_log |
| Avg output tokens per evaluation | ~600 (single card) | Measured from agent_run_log |

### Scenario A: Agent replaces code-based scoring (all strategies scored by Claude)

| Metric | Single User | 10× Scale |
|---|---|---|
| Scorecard calls per day | 30 (10 symbols × 3 sessions) | 300 |
| Evaluate calls per day | 12 (4 per session × 3 sessions) | 120 |
| Daily input tokens | 96,000 | 960,000 |
| Daily output tokens | 31,200 | 312,000 |
| Daily cost | $0.76 | $7.56 |
| **Monthly cost** | **$22.73** | **$226.80** |

### Scenario B: Status quo (Claude only for evaluation, scoring stays code)

| Metric | Single User | 10× Scale |
|---|---|---|
| Evaluate calls per day | 12 | 120 |
| Position refresh calls per day | 5 (estimated open positions) | 50 |
| Daily input tokens | 51,000 | 510,000 |
| Daily output tokens | 10,200 | 102,000 |
| Daily cost | $0.31 | $3.06 |
| **Monthly cost** | **$9.18** | **$91.80** |

### Delta

Moving scorecard scoring to an agent adds ~$13.55/month at single-user scale and ~$135/month at 10×. This is the cost of replacing deterministic scoring math that is already correct with an LLM call that introduces nondeterminism and latency.

### Break-even against engineering time

The cross-surface drift bugs (OTA-646 family) consumed approximately 15–20 hours of engineering time across 6 tickets. At a conservative $100/hour, that is $1,500–2,000 in remediation cost. At the $13.55/month incremental agent cost, the break-even point is ~110–150 months (9–12 years). This is not a favorable trade-off.

The engineering cost of drift was real but has already been spent. The QA harness (OTA-652) now catches future drift automatically. The recurring monthly cost of agent scoring does not offset the one-time remediation cost.

---

## Phase 5 — Determinism Analysis

### D-class Assertions vs. LLM Scoring Path

| Assertion | What It Tests | Survives LLM at temp=0? | Required Softening | Diagnostic Power Impact |
|---|---|---|---|---|
| **D1: Identical inputs** | Stage 1 input fields match across runs | **Yes** — inputs are market data, not LLM outputs | None | None |
| **D2: Identical card scores** | Scorecard strategy scores match across runs | **No** — LLM scoring is inherently nondeterministic even at temp=0 (quantization, batching, API routing variability) | Relax to ±3 points tolerance (0–100 scale) | **Severe.** The VOO 80→92 swing (12 points) that the harness was built to catch would fall within a widened tolerance. A ±3pt window catches ≥4pt swings but misses the subtle 2–3pt drifts that compound across surfaces. |
| **D3: Identical candidate set** | Trade keys, pills, scores match across runs | **No** — if scores come from LLM, candidate ordering and pill assignment drift | Relax to: same candidate set (by natural key), scores within ±3pt, pills identical (pills are routing, not scoring) | **Moderate.** Candidate set equality is still bright-line (chain data is frozen). Score tolerance weakens the row-level signal. |
| **D4: Identical evaluation outputs** | Verdict, score, key_risks, thesis_invalidators match | **No** — verdict depends on score (which now drifts), and key_risks/thesis_invalidators are free-text | Relax verdict to "same after re-banding post-tolerance"; relax key_risks to semantic similarity ≥ 0.8 | **Severe.** The entire point of D4 is that the pipeline produces the same decision for the same trade. An LLM path makes this assertion statistical, not deterministic. |
| **D5: Identical hard-gate outcomes** | auto_pass_reason matches across runs | **Yes** — hard gates are code-based (B6–B8, B11, B12) and remain bright-line | None (assuming gates stay code) | None |
| **D6: Narrative drift (advisory)** | claude_read similarity ≥ 0.85 | **Already softened** — D6 uses SequenceMatcher ratio with 0.85 threshold and is advisory, not blocking | No change needed | None — already designed for LLM nondeterminism |

### Net Assessment

Moving scorecard scoring to an LLM path would break D2 (identical card scores) and D3 (identical candidate scores), and weaken D4 (identical evaluation outputs). The required softening to accommodate LLM nondeterminism would reduce the harness's ability to catch the class of bugs it was specifically built to detect (VOO-style cross-surface drift where scores swing 10+ points between identical runs).

D5 (hard-gate outcomes) and D1 (identical inputs) survive because hard gates and market data remain code-based. D6 already accommodates narrative variance.

The fundamental tension: determinism assertions are valuable precisely because the scoring pipeline IS deterministic. Making it nondeterministic turns the harness from a regression detector into a statistical monitor, which is a categorically weaker tool.

---

## Phase 6 — Reproducibility for Backtesting

### Proposed Versioning Model: Content Hash + Git Commit SHA

**Skill version identifier:** SHA-256 hash of the SKILL.md file contents at invocation time.

**Storage:**
- `agent_run_log.prompt_version` — already exists, currently stores the SKILL.md frontmatter `version` field. Change to store `{semver}:{content_hash_first_8}` (e.g., `1.2.0:a3f7c2d1`).
- `positions.claude_verdict` — already stores the full evaluation JSON. Add a `skill_version` field to the stored JSON.
- `trade_recommendations.prompt_version` — already exists, same format change.

**Rerun mechanism:**
1. Every SKILL.md is version-controlled in git. The content hash maps to one or more git commits.
2. To rerun a score against a historical skill version: check out the commit where the content hash matches, load the SKILL.md, replay the evaluation with the same inputs (from agent_run_log.market_snapshot + trade_snapshot).
3. Git history is sufficient — no separate skill registry needed. The content hash provides a fast lookup; `git log -p --all -- app/skills/claude-trade-agent/SKILL.md` finds the commit.

**What happens to historical scores when a skill is edited:**
- Historical scores are immutable. They were produced by the skill version recorded in their `skill_version` field.
- A new skill version produces new scores. The two are comparable only by running both versions against the same inputs and diffing.
- The QA harness should include a "skill version" field in capture JSON so that cross-version regressions are distinguishable from cross-run nondeterminism.

---

## Phase 7 — Governance Model

### Editorial Authority

- **Don** is the sole editorial authority for SKILL.md files. Claude Web may draft edits, but Don approves and merges.
- Claude Code never modifies SKILL.md without explicit prompt instruction (consistent with SoT doc governance in CLAUDE.md).

### Review Process

1. Skill edit is drafted (by Don or Claude Web) as a git branch.
2. Before merging, the edit must pass the QA harness against the full 5-symbol universe with the modified skill in place.
3. Don reviews the harness report and the diff. If the harness shows regression (assertions that passed before now fail), the edit does not merge.
4. If the harness is green and Don approves, the branch merges to main. Normal deploy workflow follows.

### Test Bed

- Run the OTA-652 QA harness with `--skill-override path/to/modified/SKILL.md` (new flag to add if agent scoring is adopted).
- Compare assertion results against the most recent green baseline (`last_green.json`).
- Additionally, run against 3 historical captures (replay mode) to verify consistency with known-good evaluations.

### Rollback

1. Identify the last-known-good skill version from `last_green.json` (which records the skill content hash).
2. `git revert` the skill edit commit. This restores the prior SKILL.md.
3. Deploy. New evaluations use the reverted skill. Historical scores remain immutable.
4. If the revert itself causes issues, pin the prior version by tagging it and pointing the skill loader at the tagged path (requires a one-line code change in `skill_loader.py` to accept an override path).

### Conflict Resolution

- Skill edits are serialized through the git branch + merge workflow. Two concurrent edits create a merge conflict in the SKILL.md file, resolved by the normal git conflict resolution process.
- Don arbitrates any semantic conflict (two edits that don't conflict textually but conflict in intent).

---

## Phase 8 — Hybrid Scope Proposal

### Challenge to the Default Working Proposal

The default proposal states: "Bright-line stays code; judgment moves to agent; consumer-wiring problem remains its own concern."

**I confirm the default with one modification:** judgment already IS agent-driven. The three judgment sites (B13, B16, B17) are already Claude API calls mediated by SKILL.md prompts. There is nothing to "move to agent" — the judgment path is already there.

The proposal to consolidate scoring into an agent (Hypothesis 1) is refuted by the evidence:

1. **The 15 bright-line sites are correct and deterministic.** The cross-surface drift disease (OTA-646) was not caused by the scoring math being wrong. It was caused by consumers wiring to different sources (card vs trades vs detail) that computed independently and disagreed. This is Hypothesis 2 in action.

2. **The QA harness now catches wiring drift automatically.** The A1–A10 within-run assertions and D1–D6 cross-run assertions detect exactly this class of bug. The harness is the permanent fix for the wiring discipline problem.

3. **Agent scoring would degrade D2, D3, D4 assertions.** The harness's diagnostic power depends on deterministic scoring. Replacing deterministic math with LLM calls turns regression detection into statistical monitoring.

4. **Cost and latency trade-offs are unfavorable.** +$13.55/month and +25s scan latency for no quality improvement.

5. **The narrative (B13) is already the most reliable component.** As the OTA-653 description notes, "Claude's Read" correctly identifies structural mismatches and qualitative weaknesses. The problem was never the narrative — it was the code-based pipeline disagreeing with the narrative. The fix was to make the code-based pipeline correct (OTA-636 compatibility gating, OTA-637 frontend pills, OTA-645 verdict-narrative consistency). That fix shipped.

### What Stays Code (Bright-line — by name)

All 15 bright-line sites remain code:

B1 (strategy_scorer.py), B2 (vertical_engine.py), B3 (long_call_engine.py), B4 (strategy_routing.py), B5 (strategy_classifier.py), B6 (hard_gates/__init__.py), B7 (earnings_gate.py), B8 (negative_ev_gate.py), B9 (asymmetry.py), B10 (_assign_verdict), B11 (DTE gate), B12 (credit/debit gate), B14 (narrative_grounding.py), B15 (health_grade.py), B18 (black_scholes.py).

### What Stays Agent (Judgment — already agent-driven, by name)

B13 (Claude Deep Dive Evaluation), B16 (Position Monitor Agent), B17 (Insight Engine).

These are already mediated by SKILL.md prompts. No change needed.

### What Stays a Wiring Problem (Consumer concerns, by name)

- **F12 (strategy-configs/):** Frontend mirror of STRATEGIES dict. Should be generated from the backend or fetched via API endpoint, not manually synchronized. This is the highest-priority wiring fix remaining.
- **F4 (ScoreBar.jsx):** Uses green ≥75 threshold instead of ≥70. Should match B10's verdict bands. Minor fix.
- **F2/F3/F5:** Score color thresholds. Should use a shared constant derived from B10's bands.
- **Scorecard → Trades page consistency (A1 assertion):** Already validated by QA harness. The fix shipped in OTA-646.
- **Pills → Compatibility (A3 assertion):** Already validated by QA harness. The fix shipped in OTA-637.

### Migration Order

No migration needed for the scoring engine. The recommended follow-up work is:

1. **F12 deduplication:** Create a `GET /api/v1/config/strategies` endpoint that returns the STRATEGIES dict; frontend fetches it at app init instead of maintaining a static copy. This eliminates the single remaining structural source of strategy metadata drift.
2. **Score color constant unification:** Extract the 70/50 thresholds from B10 into a shared constant; frontend score-color functions reference the API-served thresholds.
3. **QA harness integration into CI:** Run the harness automatically on dev deploy (already scoped under OTA-652).

---

## Phase 9 — Recommendation

**Proceed with explicit hybrid at the current scope: bright-line stays code, judgment stays in the existing agent paths (SKILL.md-mediated Claude calls), and the wiring problem is addressed by deduplicating strategy config data (F12) and unifying score color thresholds.**

There is no scoring work to move to an agent. The three judgment sites are already agent-driven. The 15 bright-line sites are deterministic, correct, and harness-validated. Consolidating them into an LLM path would degrade determinism, increase cost, increase latency, and weaken the QA harness — with no compensating quality benefit.

The cross-surface drift disease was a wiring bug, not a scoring-logic bug. The fix was wiring discipline (OTA-636 through OTA-651) plus automated regression detection (OTA-652 QA harness). That fix has shipped. The remaining work is housekeeping: F12 deduplication, score color unification, and CI integration of the harness.
