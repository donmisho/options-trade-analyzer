# OTA QA Harness — Strategy Routing & Scoring Pipeline

**Version:** 1.0 (draft, market-closed mode)
**Owner:** Don Mishory
**Status:** Specification — to be implemented via Claude Code per project two-Claude workflow
**Document scope:** Defines what the harness IS and DOES. Prescriptive only. No alternatives-considered content.

---

## 1. Purpose & Trigger

A repeatable test harness that validates the end-to-end scoring pipeline of the Options Analyzer after every dev deploy. Three QA pastes — ASML BULL_CALL_DEBIT 1630/1640, TSM SINGLE_LONG_PUT 390, VOO grouped Trades view — reproduced the canonical OTA-646 "five surfaces disagree on the same trade" disease in dev *after* the six-ticket Epic shipped. Ad-hoc QA caught the failures; ad-hoc QA does not scale, does not run consistently, and does not produce a comparable artifact across deploys. This harness does.

### When to run

- **Mandatory:** after every dev deploy that touches `strategy_definitions.py`, `strategy_scorer.py`, scanner modules, `analysis_routes.py`, frontend scoring rendering, or any SKILL.md consumed by the Foundry evaluation path.
- **Mandatory:** as the validation gate before any of the six OTA-646 child tickets (OTA-636 / 637 / 645 / 649 / 650 / 651) advances from Code & Test Complete to Production Deployed.
- **Mandatory operating condition:** market closed. Inputs must be frozen for determinism to be meaningfully testable. Running during market hours invalidates the cross-run equality assertions. A 24/5 lockout in the harness itself blocks accidental market-hours runs unless explicitly overridden with `--allow-market-hours` (which then disables determinism assertions and only runs intra-snapshot coherence).

### Gating authority

Don holds the gate. A green run is **necessary but not sufficient** for promoting to PD; a red run **blocks** promotion until investigation completes and a re-run is green.

---

## 2. Scope

### In scope

1. End-to-end pipeline for a given symbol: card cell scoring → Trades page candidate list → trade-detail expansion → Claude's Read evaluation → trade detail's downstream payload (order generation if applicable).
2. **Strict determinism** across N sequential captures while market is closed. Scores, verdicts, and structured outputs must match across runs.
3. **Cross-surface coherence** within a single capture: card ↔ Trades page ↔ trade detail ↔ narrative ↔ best_fit ↔ pills ↔ section grouping ↔ footer.
4. **Hard-gate enforcement** at the right pipeline stage: debit % cap (OTA-141), negative EV (OTA-503), structural compatibility (OTA-636), earnings-in-window (OTA-502).
5. **Spread type classification** — UNKNOWN detection at every capture point where it appears.
6. **Directional sign** of technical alignment scoring — bullish stack on bearish trade should drag, not lift.

### Out of scope

1. Positions surface (OTA-650). Different data path (entered trades, not scanned candidates). Separate harness when scoped.
2. Visual rendering — pill colors, badge styles, section dividers, CSS variable application. The harness validates structural data; visual QA stays manual.
3. Foundry endpoint reliability. API 502s and similar are surfaced as **warnings** but do not fail the harness — they're tracked separately (OTA-611 / OTA-507).
4. Historical accuracy / predictive quality. This is current-state validation. The follow-on historical-replay harness (Section 12) answers that question.

---

## 3. Symbol Universe

The harness runs against 5 symbols, configured in `regression-symbols.yaml` so the universe can evolve without code changes. The rationale below is the contract — symbol selections can change as long as each role is covered.

| Slot | Suggested symbol | Coverage role |
|---|---|---|
| 1 | **VOO** | Full bullish SMA stack, low IV, broad-market ETF. Tests: SP credit + LT long-call + Bull Call debit should score; WG/TR/credit-bear should be N/A. Reproduces VOO regression evidence (Image 1 / Image 5). |
| 2 | **MMM** | Bearish SMA stack per OTA-646 problem statement. Tests: TR / Bear Put debit / WG credit should score; SP / bull-side credit should be N/A. Reproduces canonical OTA-646 case. |
| 3 | **AAPL** | Mid-volatility mega-cap, often mixed signals. Tests: scoring resolution under ambiguous conditions; multiple strategies competing legitimately. |
| 4 | **TSM** | Stretched-uptrend, +9% extended condition. Tests: directional alignment on long-put trades; extended-move flag enforcement. Reproduces TSM regression evidence. |
| 5 | **\[rotating\]** | Symbol with earnings in next 7 trading days. Tests: OTA-502 earnings-in-window hard gate. Manual selection at run time, captured in the report. |

Initial recommendation for Slot 5 today: rotate based on the upcoming earnings calendar. Capture the chosen symbol in the run report so the test record reflects what was tested.

---

## 4. Pipeline Stages

The harness captures data at **five stages**. Stages 1–4 are validation core. Stage 5 is observational only (no assertions, surfaces drift in the post-evaluation order generation path).

### Stage 1 — Security Strategies card scan

- **Surface:** Security Strategies grid card (Image 1 / Image 5).
- **Endpoint (Phase 1 confirm):** likely `/api/v1/analysis/scorecard?symbol=X`.
- **Input capture:** symbol, capture timestamp (UTC), underlying spot price, IV rank, SMA-8 / SMA-21 / SMA-50, ATR-14, VIX, SPY 5d trend, QQQ 5d trend, regime note.
- **Output capture:** for each strategy in {SP, WG, TR, LT}: `score` (numeric 0–100 or `null` for N/A), `argmax_spread_ref` if populated (the spread that produced the cell's max score).

### Stage 2 — Trades page candidate list

- **Surface:** Trades page grouped sections (Image 2).
- **Endpoint (Phase 1 confirm):** Trades scan endpoint — `/api/v1/trades/scan?symbol=X` or scorecard-with-candidates variant.
- **Input capture:** Stage 1 inputs PLUS the active strategy config snapshot (DTE windows per strategy, IV thresholds, debit/credit % caps, any other scoring config the user can adjust). Capture the **effective** config used, not just stored defaults.
- **Output capture per section:** strategy name, `Recommended` badge presence, candidate count, ordered list of rows.
- **Output capture per row:** `trade_key`, `score`, `strategy_pills[]`, `spread_strikes`, `spread_type` (verbatim — UNKNOWN detected here), `expiration`, `dte`, `delta`, `iv`, `theta`, `net_debit_or_credit`, `r_r`, `probability`, `best_fit_strategy` (if surfaced at row level).
- **Footer capture:** the literal "No compatible setups today for: X, Y" string verbatim.

### Stage 3 — Trade detail expansion (per row)

- **Surface:** expanded row view (Image 3).
- **Endpoint (Phase 1 confirm):** likely embedded in Stage 2 response, possibly a `/api/v1/trades/{trade_key}/detail` endpoint.
- **Input capture:** `trade_key`, full leg array: for each leg, `side`, `type`, `strike`, `expiration`, `qty`, `bid`, `ask`, `mid`, `delta`, `iv`, `volume`, `oi`.
- **Output capture:** `entry_price`, `max_profit`, `max_loss`, `breakeven`, `best_fit_strategy_name`, **`best_fit_score`** (the `0.00` red value in Image 3 is the key signal), `profit_trigger`, `stop_trigger`, `time_exit`, exit scenario analysis table (per-band: underlying_price, option_value, p_l_per_contract, p_l_pct, probability, expected_value, exit_signal), outcome summary (`p_max_profit`, `p_breakeven_or_better`, `p_partial_profit`, `p_max_loss`, `expected_value`, `ev_pct_of_risk`, `negative_ev_badge_present`).

### Stage 4 — Claude's Read evaluation

- **Surface:** the "Claude's Read" panel inside trade detail.
- **Endpoint (Phase 1 confirm):** Foundry evaluation endpoint behind the Evaluate button — `/api/v1/evaluate` or similar.
- **Input capture:** the **structured evaluation payload** sent to Foundry. This is critical — many cross-surface bugs trace to what the evaluation step actually receives vs. what other surfaces compute. Capture the payload verbatim (redacted if it contains secrets).
- **Output capture:** verdict (`PASS` / `WAIT` / `EXECUTE` / `WAIT_FOR_EARNINGS`), narrative text verbatim, `invalidation_conditions[]`, `key_risks[]`, computed score breakdown by component, the `best_fit` echo from the evaluation, any structured EV / probability / asymmetry diagnostic fields.
- **Failure capture:** if the endpoint returns non-200 (Image 4 showed a 502 on LT evaluation), record status code + response body in `evaluation_errors[]`. This produces a warning, not a failure of the harness — but it's logged.

### Stage 5 — Order generation echo (observational, no assertions)

- **Surface:** TOS order block + OCO bracket that the Trade Detail produces (per `tos-order-types` skill).
- **Capture only.** No assertions in v1.0 of the harness — order generation has its own correctness criteria that haven't been formalized as assertions yet. Captured so that when v2.0 of the harness adds order-shape assertions, the historical data exists.

---

## 5. Per-Stage Capture Contract

All captures serialize to JSON. One file per symbol per run: `captures/{symbol}/{run_id}.json`. Schema:

```json
{
  "symbol": "VOO",
  "run_id": "2026-05-14T23:30:12Z_run1",
  "run_index": 1,
  "of_runs": 5,
  "market_status": "closed",
  "captured_at_utc": "2026-05-14T23:30:12Z",
  "stages": {
    "stage_1_card": { ... },
    "stage_2_trades": { ... },
    "stage_3_detail": { "per_trade_key": { ... } },
    "stage_4_evaluation": { "per_trade_key": { ... } },
    "stage_5_order": { "per_trade_key": { ... } }
  },
  "warnings": [],
  "errors": []
}
```

Each stage's structure matches the field list in Section 4. Numeric scores stored as floats; null/N/A stored as JSON `null` (never as the string "N/A" or zero).

**Critical: do not normalize, round, or transform values during capture.** Capture verbatim from the API. Normalization happens later, in the assertion layer, where it's auditable.

---

## 6. Consistency Assertions

Two assertion classes. Both must pass for a green run.

### 6a. Within-run assertions (intra-snapshot coherence)

Run once per captured run. These assertions test that one snapshot is internally consistent across surfaces.

**A1. Card score ↔ Trades page reality.**
For each strategy `S` in {SP, WG, TR, LT}:
- If `stage_1.cell[S].score` is non-null, **then** at least one row in `stage_2.section[S]` must exist (or `stage_2.footer` must not list S as "no compatible setups").
- If `stage_1.cell[S].score` is null/N/A, **then** `stage_2.section[S]` must be absent or empty AND `stage_2.footer` must list S as "no compatible setups."
- The `argmax_spread_ref` from Stage 1 must correspond to a row present in Stage 2 (or in expected eligible candidates).

*Reproduces VOO failure: WG cell scored 100 / 90 with footer claiming no WG setups.*

**A2. Section grouping ↔ best_fit.**
For each row in Stage 2:
- The section under which the row appears must equal the row's `best_fit_strategy` (from Stage 3 detail, or from row-level `best_fit_strategy` if Stage 2 surfaces it).
- "Mixed grid" — a row appearing in section X with `best_fit = Y` where Y ≠ X — is a hard fail.

*Reproduces VOO failure: Bull Call rows in Steady Paycheck section with best_fit displayed as Steady Paycheck at score 0.00.*

**A3. Strategy pills ↔ compatibility.**
For each row in Stage 2:
- Every strategy in `strategy_pills[]` must be in the row's `eligible_strategies(spread)` set per the canonical compatibility map (Phase 1 imports the same map the backend uses, or asserts against an inline copy).
- A pill for a strategy not in `eligible_strategies` is a hard fail.

*Reproduces VOO failure: WG pill shown on Bull Call rows grouped under SP.*

**A4. best_fit null state rendering.**
For any row where `stage_3.best_fit_score == 0.00` or `stage_3.best_fit_strategy_name == null`:
- The rendered "Best fit" display in Stage 3 must read `none` or equivalent — not a strategy name with a zero score.

*Reproduces VOO failure: "Best fit: Steady Paycheck 0.00" appearing in red instead of "Best fit: none."*

**A5. Hard-gate enforcement at candidate surfacing.**
For each row in Stage 2:
- If `stage_3.entry_price / stage_3.spread_width > 0.40` (debit % cap, OTA-141), the row should not be in the candidate list at all — OR the row's verdict from Stage 4 must be PASS. The harness flags either presence-without-PASS or absence-with-violation as a finding.
- If `stage_3.expected_value < 0` (negative EV, OTA-503), same logic: row should not surface as a candidate OR verdict must be PASS.
- If `stage_3.earnings_in_window && days_to_earnings <= 7` (OTA-502), same.

*Reproduces VOO failure: 690/700 Bull Call surfaced at score 59.63 with 41.5% debit ratio AND -16.85% EV, both violations.*

**A6. Verdict ↔ narrative consistency (two patterns).**
For each row's Stage 4 evaluation:
- **Pattern 1 — explicit:** if `narrative` opens with or contains "PASS — structural mismatch" or equivalent reject keywords, `verdict` must be PASS. (OTA-645 case.)
- **Pattern 2 — qualitative:** if `narrative` contains phrases that indicate the trade is structurally wrong ("structurally fighting the tape," "directional conviction the dominant weakness," "wrong tool for this job," etc. — a configurable keyword set), the verdict must not be EXECUTE. WAIT or PASS only.

*Reproduces TSM failure: EXECUTE verdict with "structurally fighting the tape" in narrative.*

**A7. Spread type classification.**
For each row in Stage 2 and each detail in Stage 3:
- `spread_type` must not be `UNKNOWN` for any spread whose legs are well-formed (two-leg same-expiry vertical, or single-leg long option). The classifier should produce a concrete enum: `BULL_CALL_DEBIT`, `BEAR_PUT_DEBIT`, `BULL_PUT_CREDIT`, `BEAR_CALL_CREDIT`, `SINGLE_LONG_CALL`, `SINGLE_LONG_PUT`, etc.

*Reproduces ASML + TSM failures: spread_type: UNKNOWN with cleanly classifiable legs.*

**A8. Technical alignment directional sign.**
For each row:
- Derive `trade_direction` from `spread_type` (BULL_*, *_LONG_CALL → bullish; BEAR_*, *_LONG_PUT → bearish).
- Derive `stack_direction` from `stage_1.sma_alignment` (price > SMA8 > SMA21 > SMA50 → bullish; price < SMA8 < SMA21 < SMA50 → bearish).
- If `trade_direction != stack_direction`, the `technical_alignment_score_component` in Stage 4 must be **≤ 0.3**, not 1.0. (Threshold tunable; the principle is "opposing stack drags, doesn't lift.")

*Reproduces TSM failure: bullish stack + long put scored technical alignment 1.0/1.0.*

**A9. Net delta sign vs trade direction.**
For each row in Stage 3:
- Compute expected net delta sign from spread type and legs.
- `stage_3.net_delta` sign must match expectation. (For ASML: Bull Call Debit should have positive net delta; observed +0.00 was a finding.)

*Reproduces ASML failure: net delta +0.00 on a Bull Call Debit that should have been clearly positive.*

**A10. Score arithmetic reconciliation.**
For each row in Stage 4 with a score breakdown:
- `sum(component_score * weight for component) == displayed_total`, within rounding tolerance of ±0.01.

*Reproduces TSM finding: components 0.2 + 0.0 + 0.2 + 0.1 + 0.1 = 0.6, displayed total = 71. Arithmetic doesn't reconcile.*

### 6b. Cross-run assertions (determinism, market-closed only)

Run after all N captures complete. Compare runs pairwise; report on any diff.

**D1. Identical inputs.**
For each symbol, across the N runs, the Stage 1 input fields (price, IV rank, SMAs, ATR, VIX, market context) must be **identical** (string-level equality on the JSON-serialized values). If they're not, the test environment isn't actually frozen and the rest of the determinism assertions are invalid — abort the run with a configuration error.

**D2. Identical card scores.**
Across N runs, for each symbol and each strategy, `stage_1.cell[S].score` must be byte-identical. No tolerance window. Any diff is a finding.

*The VOO 80→92 / 100→90 / 10→20 swing happened during a closed-market session — this assertion would have caught it.*

**D3. Identical Trades page candidate set.**
Across N runs, for each symbol, the **set of `trade_key`s** in `stage_2` must be identical, the **section grouping** must be identical, the **pills per row** must be identical, the **score per row** must be byte-identical.

**D4. Identical evaluation outputs.**
Across N runs, for each `trade_key`, `stage_4.verdict` must be identical. The narrative text MAY differ in wording (LLM nondeterminism is real even at temperature=0 across runs), but the **structured fields** (`verdict`, `invalidation_conditions[]`, `key_risks[]`, component scores) must be identical.

**D5. Identical hard-gate outcomes.**
Across N runs, the result of each hard-gate assertion (A5 cases) must be identical. A row passing A5 in run 1 and failing A5 in run 2 indicates a non-deterministic gate.

**D6. Narrative drift bound (advisory, not blocking).**
If `stage_4.narrative` text differs across runs, compute a similarity score (e.g., embedding cosine or token overlap). If similarity < 0.85, flag as a warning. Verdict still passes if D4 passed — narrative wording variance is allowed; semantic drift is observed.

---

## 7. Determinism Protocol

Concrete: N=5 sequential runs per symbol, no delay between runs (or 5-second minimum to avoid hammering the backend). All five complete in under 5 minutes per symbol; full universe of 5 symbols completes in under 30 minutes.

Each run captures all 5 stages independently. After all 5 runs complete:
1. Run all 6a assertions per-run, per-symbol. Aggregate: a symbol passes 6a if **every run** passes every assertion.
2. Run all 6b assertions across the 5 runs per symbol. A symbol passes 6b if every cross-run assertion passes.
3. Symbol passes overall if it passes both 6a (every run) and 6b (across runs).
4. Universe passes if every symbol passes.

Failure mode definitions:
- **Hard fail:** any 6a assertion failing in any run, or any 6b assertion failing across runs.
- **Warning:** infrastructure errors (502s), narrative drift below threshold, missing optional fields.
- **Config error:** D1 fails (inputs not stable) — the test environment isn't usable; run aborts.

---

## 8. Output Format

Per run, the harness produces:

1. **Raw captures**: `captures/{symbol}/run-{1..5}.json` — one per run per symbol, schema per Section 5.
2. **Assertion report (machine-readable)**: `reports/{run_timestamp}/assertions.json` — every assertion, every run, every symbol, with pass/fail and evidence references.
3. **Human-readable summary**: `reports/{run_timestamp}/summary.md` — high-level pass/fail, top findings, regression vs last green run.
4. **Last-green baseline pointer**: `reports/last_green.json` — symlink or pointer to the most recent fully-green run, used for regression diffs.

The summary.md uses this structure:

```
# QA Harness Run — 2026-05-14T23:30Z

## Status: ❌ FAIL (3 symbols failed, 2 passed)

## Failures
### VOO — 4 assertion failures across 5 runs
- A1 (card↔Trades): WG cell scored 100, footer "no WG setups." Runs 1, 2, 3, 4, 5.
- A2 (section↔best_fit): Bull Call in SP section with best_fit=SP at score 0.00. Runs 1, 2, 3, 4, 5.
- A3 (pills↔compat): WG pill on Bull Call row. Runs 1, 2, 3, 4, 5.
- D2 (determinism): SP score 80→92 between run 1 and run 2. Run 1: 80.00. Run 2: 92.00. Diff: +12.

### TSM — 3 assertion failures
...

## Passes
- AAPL — 0 findings, deterministic
- ...

## Regression vs last green (2026-05-12T19:00Z)
- 3 new failures introduced
- 0 previously-failing assertions now passing
- 0 unchanged

## Warnings (non-blocking)
- LT evaluation on VOO returned 502 in run 3. (1 occurrence.)
```

---

## 9. Pass/Fail Criteria

A run is **green** if:
- All 5 symbols pass all 6a assertions in all 5 runs.
- All 5 symbols pass all 6b assertions across runs.
- D1 confirmed inputs were stable (the test environment was actually frozen).

A run is **red** if any of the above fails.

Warnings (502s, narrative drift below threshold, optional field missing) do not change the pass/fail signal but appear in the report.

**A red run blocks promotion** of any in-flight ticket from Code & Test Complete to Production Deployed in the pipeline area the harness covers. Specifically the six OTA-646 child tickets and any future scoring-pipeline work under OTA-507.

---

## 10. Phase 1 Discovery (unknowns for Claude Code to resolve)

Before implementation, Claude Code runs a read-only discovery phase to confirm these specifics. The output of Phase 1 is a `phase-1-findings.md` document; Phase 2 (implementation) only begins after Don approves Phase 1 findings.

1. **Endpoint inventory.** Confirm the actual URLs and request/response shapes for:
   - Security Strategies scorecard
   - Trades page scan / candidate list
   - Trade detail expansion (separate endpoint or embedded?)
   - Foundry evaluation (Evaluate button)
   - Order generation echo (if exposed)

2. **Strategy config endpoint.** Confirm how to capture the *effective* per-strategy config used during scoring (the per-strategy DTE windows, thresholds, etc. — what OTA-516 plumbed through). Required to ensure Stage 2 inputs are fully captured.

3. **Canonical compatibility map.** Locate the shared `compatible_structures` definition from OTA-636. The harness imports or replicates it for A3 assertions.

4. **Trade key stability.** Confirm `trade_key` is deterministic for the same (symbol, spread, legs, expiration) across runs while market is closed. If trade_keys are session-scoped or randomly generated per scan, the cross-run assertions need to match on (symbol, strikes, expiration, spread_type) instead.

5. **Authentication.** Harness needs to authenticate against dev. Confirm: API key in Key Vault? Bearer token from Entra? Session cookie from BFF? The auth model determines how the harness runs.

6. **Backend cache behavior.** Does the scoring pipeline cache between sequential calls? If so, what's the TTL, and does each run hit a fresh path or a cached path? Caching could *mask* determinism bugs (or *cause* them depending on cache key correctness).

---

## 11. Implementation Sketch

### File layout

```
qa-harness/
├── README.md
├── regression-symbols.yaml
├── compatibility-map.yaml          # canonical eligible_strategies, mirrored from backend
├── narrative-keywords.yaml         # for A6 Pattern 2 — qualitative reject phrases
├── harness/
│   ├── __init__.py
│   ├── runner.py                   # orchestrates N runs per symbol
│   ├── capture/
│   │   ├── stage_1_card.py
│   │   ├── stage_2_trades.py
│   │   ├── stage_3_detail.py
│   │   ├── stage_4_evaluate.py
│   │   └── stage_5_order.py
│   ├── assertions/
│   │   ├── within_run.py           # A1–A10
│   │   └── cross_run.py            # D1–D6
│   ├── report/
│   │   ├── json_report.py
│   │   └── markdown_summary.py
│   └── auth.py
├── captures/                       # gitignored — raw captures
├── reports/                        # gitignored except last_green.json
└── tests/                          # pytest tests of the harness itself
```

### Run command

PowerShell, from project root:

```powershell
cd $PROJECT_ROOT
.\venv\Scripts\Activate.ps1
python -m qa_harness.runner --env dev --symbols all --runs 5
```

Outputs land in `qa-harness/captures/` and `qa-harness/reports/`. Exit code 0 if green, non-zero if red.

### Schedule

- Manual invocation after every dev deploy (not auto-triggered yet — explicit human gate).
- Future: GitHub Actions workflow that runs the harness against dev on every push to a release branch, blocking the merge gate on red.

### Implementation phasing for the build prompt

Per project memory's prompt-style convention:

1. **Phase 1 — Discovery** (read-only). Resolve all Section 10 unknowns. Write `phase-1-findings.md`. Stop and report.
2. **Phase 2 — Capture stages.** Implement Stage 1–4 capture against confirmed endpoints. Run once against VOO and dump raw JSON. Stop and report a sample capture.
3. **Phase 3 — Assertions.** Implement A1–A10 and D1–D6. Run against the Phase 2 sample capture. Confirm the harness catches the VOO failures (A1, A2, A3 should all fail per known evidence). Stop and report.
4. **Phase 4 — Full universe.** Run all 5 symbols × 5 runs. Generate the full report. Stop and report — Don reviews before declaring the harness production-ready.

Each phase ends with a stop-and-report gate. Phase 1 likely fits in one Claude Code session; Phase 2 and 3 may want separate sessions to keep context tight.

---

## 12. Future Direction — Historical Backtest Harness

The current harness validates that the pipeline is **internally coherent and deterministic** on live data. It does not answer whether the pipeline produces **good trades**. That's a different question and requires different infrastructure: historical chain snapshots, replay machinery, and outcome attribution.

A future harness — call it `qa-harness-historical` — would:

1. **Acquire historical chain snapshots** for a wider symbol universe (10–50 symbols) over a meaningful window (3–12 months). Likely OpenBB-backed via the existing `obb_*` Azure SQL tables, or a Polygon historical pull when Phase 3.3 backtesting lands.
2. **Replay each historical snapshot** through the current scoring pipeline. The capture/assertion infrastructure built in this spec is directly reusable — only the data source changes.
3. **Compare verdicts against actual outcomes** at the trade's expiration. A trade verdicted EXECUTE that ended at max loss is data. A trade verdicted PASS that would have hit max profit is also data. Aggregate over hundreds or thousands of trades produces a calibration signal — does the pipeline systematically over- or under-rate certain structures, IV environments, technical setups?
4. **Surface systematic biases** to feed back into scoring weights, gate thresholds, or strategy compatibility rules.

This belongs after the current harness lands and produces consecutive green runs. Replaying a non-deterministic pipeline against historical data produces non-deterministic backtest results; you can't tell whether a verdict was "wrong" or "noisy." Determinism first, predictive quality second.

When ready, the historical harness becomes a new Story under **OTA-13 (Intelligence Expansion)** or a new Epic under OTAR-19 (Data Sources & Market Intelligence). Not in current scope.

---

## Document maintenance

Updates to this spec accompany changes to the harness itself. Anything that changes what's tested, how it's tested, or the pass/fail criteria is a Story under OTA-507 with a documentation update as part of acceptance. No silent drift between spec and implementation.
