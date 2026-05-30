# Insight Engine — Migration Plan

> **Status:** Plan only — no tickets created. Administer via Atlassian MCP after review.
> **Version:** v3 — runtime tables as source of truth (sheet = build-time seed); gate mechanics (`stop_if_fail` / `evaluation_order` / `score_penalty`); LLM-precedence; engine-owned bronze contract + injected sink with `source_app_id`.
> **Companion docs:** `insight_engine.md` (v3, this session) · `rules-engine-audit-2026-05-20.md` · `Scoring Parameters.xlsx` (seed) · `app/analysis/health_grade.py`
> **Labels to apply:** `framework-portable` on F1, F2, F9. `options-domain` on F3, F4, F6, F7, F10, F11, F12. Mixed/both on F5, F8.

> **Governing principle:** Every rule-based evaluation surface in OTA runs through the engine. Screening, position health grading, and directional thesis comparison are three consumers of one engine — three input adapters, three rule libraries, three rule-set configurations, one set of pipeline code. There is no second evaluation path under any circumstance.

> **Naming convention:**
> - **Insight Engine** = the new generic evaluation framework. Package: `app/insight_engine/`. Output: `ResultRecord`.
> - **Insight Communicator** = the renamed existing `app/agents/insight_engine.py`. Claude-based component that turns detected anomalies into human-readable insights stored in the `insights` table. Output: `Insight` records.
> - The `insights` table name stays — it stores Communicator output (rightfully called insights).

---

## The four buckets

Every piece of code touched by this extraction lands in exactly one of:

1. **Engine core** — new `app/insight_engine/` package. Generic, domain-agnostic. No imports from `app/analysis/`, no domain terms. This is what becomes the cross-app framework component.
2. **Input adapters** — one per evaluation surface. New packages under `app/ota_adapters/`:
   - `app/ota_adapters/options_chain/` — produces trade candidates for screening (SP/WG/TR/LT and any future screening strategy)
   - `app/ota_adapters/position_health/` — produces position candidates for health grading
   - `app/ota_adapters/directional/` — produces directional comparison candidates (resolves the DirectionalEngine question)
   Each implements the §5 contract from `insight_engine.md`. All adapters can share lower-level providers (Schwab client, Black-Scholes implementation, etc.) but each is its own boundary.
3. **Rule libraries** — registered formula implementations the engine looks up via `formula:<name>` references. Organised by evaluation surface:
   - `app/options_rules/screening/` — formulas used by trade-screening strategies
   - `app/options_rules/position_health/` — formulas used by health-grading
   - `app/options_rules/directional/` — formulas for directional comparison
   All register into the same engine formula registry. The split is for human organisation; the engine sees one registry.
4. **App-side residual** — stays under `app/api/`, `app/agents/`, `app/models/`, `web/src/`. Orchestration, persistence, routes, scheduled-job triggers, UI. Calls the engine; doesn't contain rule logic.

## Bucket assignment for each audit-flagged location

| Code location | Audit finding(s) | Bucket | Notes |
|---|---|---|---|
| `app/analysis/hard_gates/__init__.py` — HardGate ABC | 5c #3 (clean) | Engine core | ABC moves to engine. GateTradeContext / GateResult get domain references stripped first. |
| `app/analysis/hard_gates/__init__.py` — GateTradeContext, GateResult | 5c #1, #2, #4, #5 | Engine core (after refactor) | Replace `expected_value`, `expiry_date`, `dte` with generic field access. Replace domain verdict strings with action codes. |
| `app/analysis/hard_gates/earnings_gate.py` | 5b #4, 5a #8 | Screening rule library + options_chain adapter | Decompose 4-route tree into atomic rules. `next_earnings_date` producer stays in adapter. |
| `app/analysis/hard_gates/negative_ev_gate.py` | 5b #5 (related), 7.5 #2 | Screening rule library | Becomes a formula. Eliminate the duplicate filter path in `vertical_engine.py:265`. |
| `app/analysis/scoring_factors/asymmetry.py` | 7.2 #1 | Screening rule library | Becomes a registered formula. |
| `app/analysis/strategy_scorer.py` (entire file) | 5a #1, #3, #4, #5; 5c #7; 7.2 #1, #2; 7.5 #1, #3 | Split across three buckets | Orchestration → app-side. Per-rule scoring math → screening rule library. Normalization → engine core (one canonical implementation). |
| `app/analysis/strategy_definitions.py` | 5c #6; 7.5 #1 | Split | Generic fields (key, label, weights, structures, DTE) → engine config schema. Domain fields (delta_min/max, iv_rank, exit levels) — most are dead code (7.5 #1); the live ones move to junction rows or adapter. |
| `app/analysis/strategy_routing.py` | 5a #2 | App-side | Becomes data-driven via the junction. The compatibility predicates collapse into "does the strategy have a junction row enabling this structure type." |
| `app/analysis/strategy_classifier.py` | 5a #6 | App-side | Stays as orchestration. Reads from canonical config (resolves the dual-source). |
| `app/analysis/black_scholes.py` | 5d COMPUTED | options_chain adapter | Canonical Black-Scholes implementation. Called via `populate_computed` callback. Shared with position_health adapter as a provider, not duplicated. |
| `app/analysis/vertical_engine.py` | 5d producer, 7.5 #2, #3 | options_chain adapter | Chain → candidate construction. Engine-internal 35/25/20/15/5 weights are removed (replaced by junction-bound scoring criteria). |
| `app/analysis/long_call_engine.py` | 5d producer, 7.5 #3 | options_chain adapter | Same pattern. 30/25/20/15/10 weights removed. |
| `app/analysis/chain_collection.py` | — | App-side | Persistence concern. Untouched. |
| `app/analysis/health_grade.py` | (now in scope) | Split across position_health adapter + position_health rule library + app-side | Position state → named values goes into the adapter. A/B/C/D/F threshold logic becomes registered scoring + verdict-band rules. Position Monitor Agent (app-side) calls the engine. See F10/F11. |
| `app/analysis/directional_engine.py` | 7.5 #5 | Split across directional adapter + directional rule library + app-side | Third engine consumer. `fitness_score` becomes engine-driven verdict. See follow-on (S8.5 retired in favor of explicit feature, see below). |
| `app/api/analysis_routes.py` — `/analyze/*` | 5d, 7.3 gap | App-side | Rewired to call engine with options_chain adapter. |
| `app/api/evaluation_routes.py` — gate logic at 626–663 | 5b #5, 5c #8 | App-side → screening rule library | Inline gates extracted; route becomes a thin engine invocation. |
| `app/api/evaluation_routes.py` — `_assign_verdict` at 175–182 | 5a #7, 7.2 #2 | App-side | Becomes per-strategy band lookup from config. The hardcoded 70/50 literals go away. |
| `app/agents/*position_monitor*` (Position Monitor Agent) | — | App-side | Picks strategy per position: `position_health_full` when exit levels complete, `position_health_basic` otherwise. Calls engine. Persists `health_grade` to `positions` table from the engine's result record. Alert/insight escalation stays in the agent (invokes the renamed Insight Communicator when verdicts cross thresholds). |
| `web/src/strategy-configs/*.config.js` | 5a #6 (mirror) | App-side | Consolidate to fetch from engine config source via API. Stop being a parallel canonical source. |
| `web/src/config/*-columns.jsx` | — | App-side | UI concern. Untouched. |

## What the audit found is NOT in code but referenced in the sheet

These are gaps the adapter must fill (F3 stories cover them):

| Missing input | Sheet rules that need it | Story |
|---|---|---|
| ATR_14 | Data completeness gate, Cushion vs ATR gate, Cushion barely above ATR floor adjustment | S3.7 |
| IV_rank (true percentile) | Data completeness gate, IV Rank scoring criterion (SP) | S3.8 |
| chart_state (enum) | Chart state confirms direction gate, Mixed chart signal adjustment | S3.9 |
| is_etf | ETF underlying adjustment | S3.10 |
| spread_width tier bounds | Spread width tier compliance gate | F2 lookup table |
| gamma propagation | Theta Gamma Ratio (WG scoring) | S3.6 |

---

# Epic

**Title:** Insight Engine — extract generic evaluation framework, route all OTA rule-based evaluation through it
**Type:** Epic
**Description:**
Extract a domain-agnostic evaluation engine from OTA into a new package (`app/insight_engine/`). All rule-based evaluation in OTA — trade screening, position health grading, and directional thesis comparison — flows through this one engine, each as its own consumer with its own input adapter and rule library. No second evaluation path exists.

The migration is governed by `insight_engine.md` v3 (mechanism) and `business-rules.md` (content, restructured during F9). Audit findings from `rules-engine-audit-2026-05-20.md` (commit `9f293f7`) drive the story-level work.

**Acceptance criteria for the Epic:**
- The engine package imports nothing from `app/analysis/`, `app/api/`, `app/models/`, any domain module, any LLM client, or any database driver. Verified by static check.
- No `if strategy_id == ...` or `if strategy_key == ...` branches in engine code. Verified by grep.
- All rule content — thresholds, weights, gate behaviour, ordering, verdict bands — is resolvable from the runtime tables. No magic numbers in code paths the engine traverses. The spreadsheet is read only by the one-time seed importer, never by the engine.
- Each strategy's configuration for each rule (parameters, `evaluation_order`, `stop_if_fail`, `score_penalty`, weight) comes from exactly one place: the junction row. No defaults, no overrides.
- All consumers (screening, position health, directional) call the same engine API with the same argument shape, including a required `source_app_id`. The engine treats them identically.
- Health grade letter (A/B/C/D/F) and screening verdict (EXECUTE/WAIT/PASS) are both produced by the engine's verdict-band lookup against per-strategy band config — no second code path produces either.
- The engine emits the full per-rule decision trace and drives the injected sink to persist candidate snapshots + evaluation decisions, every candidate every run, stamped with `source_app_id`. No LLM call occurs before the engine verdict (principle 2.6); verified by inspecting the `/evaluate/structured` path.
- End-to-end parity: same Schwab inputs produce the same verdicts as pre-extraction for SP/WG/TR/LT; same position state produces the same health grade as pre-extraction, modulo the audit divergences explicitly fixed during F2.

**Labels:** `framework-portable` (epic-level)

---

# Feature 1 — Engine core extraction

**Type:** Feature
**Parent:** Epic
**Goal:** Build the new `app/insight_engine/` package per `insight_engine.md` v3.
**Size:** L
**Dependencies:** F2 (table model + seed); F9 S9.1 doc landed.
**Labels:** `framework-portable`

### Stories

**S1.1 — Engine package skeleton with domain-decoupling enforcement**
Create `app/insight_engine/` with `__init__.py`, public API surface, and a startup check that fails if the package imports any name from a domain module. Add a CI test that scans the package for forbidden imports.
*References:* §2 principle 5 ("Domain decoupling"); audit 5c findings.

**S1.2 — Core dataclasses**
Implement `Candidate`, `NamedValue`, `Rule`, `Strategy`, `JunctionRow`, `RuleSet` (the resolved strategy+junction view used at runtime), `ResultRecord`, `CandidateSnapshot`, `EvaluationDecision` with fields per §4.2 and §4.3. The result record carries the full per-rule trace including `stop_if_fail`, `was_terminal`, `evaluation_order`, and decision-reason strings.
*References:* §3, §4.2, §4.3.

**S1.3 — Config loader (reads tables)**
Read the three runtime tables (rules, strategies, junction) into the in-memory model. The loader reads **tables**, not the spreadsheet — the spreadsheet is a one-time seed handled in F2. The loader resolves each strategy into a `RuleSet` with rules ordered by `evaluation_order` within phase.
*References:* §6.1, §6.2.

**S1.4 — Startup validation suite**
Implement every check in §6.6, including the new ones: gate junction rows must supply `evaluation_order` and `stop_if_fail`; weight sum = 1.0; monotonic bands; formula registry membership; parameter type/bound conformance; null-semantic compatibility; input-catalog completeness. Loud structured error report on failure; engine refuses to evaluate.
*References:* §6.6; audit 7.2 — startup validation is the structural fix for "thresholds are literals in code."

**S1.5 — Expression library**
Implement the closed set in §6.3: comparison operators, `IN`/`NOT IN`, `BETWEEN` (decomposed at load), `IS NULL`/`IS NOT NULL`, `EQUALS_ENUM`, `formula:<name>` lookup. Reject any expression not in the library.
*References:* §6.3; audit 5b atomic-rule findings.

**S1.6 — Pipeline orchestrator with gate mechanics**
Implement the 7-phase pipeline (§4) in fixed order, with rules within each phase executed in `evaluation_order`. Gate behaviour driven by junction fields: `stop_if_fail = true` → halt and record; `stop_if_fail = false` → record, hold `score_penalty`, continue. Held penalties applied in Phase 5. Adjustments (Phase 6) clamp `[0,100]` after each, and support floor/cap forcing. No hard/soft gate categories in code — only the three phases plus the junction fields.
*References:* §3.6, §4.

**S1.7 — Adapter callback for COMPUTED values**
Implement the `populate_computed(candidates, needed)` callback between Phase 2 and Phase 3. Engine collects the set of COMPUTED names referenced by remaining active rules, passes survivor candidates and the name set to the adapter, ingests the result.
*References:* §5.2.

**S1.8 — Result record builder with mandatory full trace**
Build the result record per §4.2. Full per-rule trace required — every decision including non-stopping and zero-penalty failures. Include `source_app_id`, engine version, config version hash, run timestamp.
*References:* §4.2.

**S1.9 — Bronze record contract + provenance stamping**
Implement the engine-owned bronze record shape (§4.3): map each result record into `CandidateSnapshot` (one per candidate) and `EvaluationDecision` rows (one per rule evaluation), stamping `source_app_id`, `config_version`, `evaluated_at` on every record. This is the singular shape every consuming application emits. The promote-to-column vs. keep-in-JSON split is fixed here so the bronze zone stays uniform across apps.
*References:* §4.3.

**S1.10 — Persistence sink interface**
Define the `PersistenceSink` interface (`write_snapshots`, `write_decisions`). The engine depends on the interface only — never on a database. Provide an in-memory sink for tests. The engine drives the sink at the end of each run; it does not open connections, manage transactions, or know the physical store.
*References:* §4.3, §8.

**S1.11 — `source_app_id` as a required run parameter**
Every `engine.evaluate(...)` call requires a `source_app_id`. The engine validates it is present and stamps it through to every emitted record. For OTA all calls pass `"OTA"`.
*References:* §1, §4.3.

**S1.12 — Engine integration tests**
Build a fixture rule library and a synthetic input adapter (e.g. "evaluate apples by sweetness and price") plus an in-memory sink. Run end-to-end tests proving the engine has no options-specific behavior. Add a test that swaps the adapter, strategy, and `source_app_id`, runs again, gets a different but correctly-structured result and bronze records stamped with the new app id. Add a test proving `stop_if_fail = false` retains a candidate through scoring and emits both the failed-gate decision and the final verdict.

---

# Feature 2 — Configuration tables and seed import

**Type:** Feature
**Parent:** Epic
**Goal:** Build the runtime configuration tables (Rules, Strategies, Junction, Lookups) as the durable source of truth, plus a one-time seed importer that populates them from `Scoring Parameters.xlsx`. Resolve all audit-flagged content inconsistencies during the seed.
**Size:** M
**Dependencies:** None — can start immediately.
**Labels:** `framework-portable` (the structure is generic; the content is options-specific but lives in the source file, not in code)

# Feature 2 — Configuration tables and seed import

**Type:** Feature
**Parent:** Epic
**Goal:** Build the runtime configuration tables (Rules, Strategies, Junction, Lookups) as the durable source of truth, plus a one-time seed importer that populates them from `Scoring Parameters.xlsx`. Resolve all audit-flagged content inconsistencies during the seed.
**Size:** M
**Dependencies:** None — can start immediately.
**Labels:** `framework-portable` (the table structure is generic; the seeded content is options-specific but lives in data, not code)

### Stories

**S2.1 — Define and create the runtime tables**
Create the relational tables that are the runtime source of truth: `rules`, `strategies`, `strategy_rule_junction`, `lookups`. The junction table includes `enabled`, `evaluation_order`, `stop_if_fail`, `score_penalty`, per-parameter value columns (or a typed parameter sub-table), `weight`, `rationale`. The rules table includes `phase`, `tier`, `condition_expression`, `referenced_named_values`, `parameter_schema`, `intent`. Alembic migration. These tables — not the spreadsheet — are what the engine loads.
*References:* §6.1, §6.2.

**S2.2 — Build the seed importer**
A one-time importer reads `Scoring Parameters.xlsx` and writes the three tables. The workbook is restructured conceptually into Rules / Strategies / Junction / Lookups during this import. After the import the workbook is historical; the engine never reads it at runtime. The importer is re-runnable against a fresh DB (idempotent seed) for rebuilds, but production edits happen in the tables via the admin UI, not by re-importing.
*References:* §6.2.

**S2.3 — Decompose compound rules into atomic rules (during seed)**
Per audit 5b findings 1–6, seed these as atomic rules with `evaluation_order` set:
- Chart state confirms direction → two atomic rules
- Stock extended in trade direction → two atomic rules
- Cushion barely above ATR floor → two atomic rules (BETWEEN handled by S1.5)
- Earnings gate 4-route tree → four atomic rules, ordered, with appropriate `stop_if_fail` per route
- Pipeline Gate 2 (credit/debit quality) → two atomic rules
- Cushion penalty graduated bands → two atomic adjustment rules, ordered
*References:* audit §5b; §3.6 (gate mechanics).

**S2.4 — Set gate mechanics per strategy×rule**
For every gate junction row, set `evaluation_order`, `stop_if_fail`, and `score_penalty`. Earnings gate is `evaluation_order = 1` among hard stops for short-DTE strategies (SP/WG/TR) with `stop_if_fail = true`. This story is also where the forward-looking long-DTE pattern is documented: when a 180–360 DTE strategy is added, its earnings-gate junction row uses `stop_if_fail = false, score_penalty = 0`. No code change needed for that future strategy — just junction rows.
*References:* §3.6.

**S2.5 — Reconcile sheet-vs-code divergences**
For each PARTIAL/DIVERGENT row in audit Section 2 (Underlying Price Floor MISSING, Days until next earnings PARTIAL, Earnings buffer past expiry PARTIAL, Per-leg bid/ask DIVERGENT 0.15 vs 0.50, Per-leg OI DIVERGENT 100 vs 10/50, etc.) — decide whether sheet or code is authoritative, then seed the resolved value. Each divergence gets a one-line rationale in the junction row's `rationale` field.

**S2.6 — Fill in TBD scoring formulas**
For each of the 12 TBD formulas in audit Section 4 (Theta Gamma Ratio, Credit Width %, Liquidity, SMA Alignment Score, Delta Quality, IV Percentile Cost, Runway Score, Payout Ratio, Delta OTM Score, Bid Ask Tightness, Open Interest, etc.), supply the canonical formula in the rules table. Where the code's current implementation is canonical, document that. Where it's a proxy (e.g. ATM IV / 0.60 as IV rank), document the proxy and the planned true-percentile replacement.

**S2.7 — Add LT-specific 7-day earnings buffer**
Audit 5a #8: the sheet specifies LT needs a 7-day earnings buffer past expiry; code applies the same 0-day floor to all strategies. Seed the LT junction row with the correct parameter.

**S2.8 — Backfill rules the sheet has but code doesn't, and vice versa**
Audit scorecard: 5 MISSING Universal Pre-Filter gates, 4 MISSING Per-Strategy gates, 2 MISSING Soft Gates, 5 MISSING Post-Scoring Adjustments, 3 MISSING Strategy Scan Parameters, 5 MISSING Width Configuration tiers, plus 8 "code rules not in canonical catalog." Seed what's confirmed; flag for removal what the sheet has but code doesn't (decision per rule during S2.5). Note: former "soft gates" seed as gate-phase rules with `stop_if_fail = false` and a `score_penalty`.

**S2.9 — Named formula registry**
Document every `formula:<name>` reference used in the rules table. The list is the contract for F4's rule library — every name must have a registered implementation when the engine loads.

**S2.10 — ETF detection input**
Audit gap: `is_etf` not available. Add it to the input catalog requirements and to the Width Configuration lookup that the ETF adjustment rule needs.

---

# Feature 3 — Options chain (screening) input adapter

**Type:** Feature
**Parent:** Epic
**Goal:** Build `app/ota_adapters/options_chain/` implementing the §5 contract for trade screening. Move all Schwab + DERIVED + COMPUTED code that serves screening into the adapter.
**Size:** L
**Dependencies:** F1 S1.7 (callback signature defined).
**Labels:** `options-domain`

### Stories

**S3.1 — Adapter package and interface**
Create `app/ota_adapters/options_chain/` with the `OptionsChainAdapter` class implementing the §5 contract: `produce_candidates`, `populate_computed`, `input_catalog`. The Schwab client and Black-Scholes implementation are pulled out as shared providers under `app/ota_adapters/_shared/` so the position_health and directional adapters (F10, F12) can use them too.

**S3.2 — Move Schwab chain fetching**
Move Schwab chain calls from `analysis_routes.py` into the adapter. The route is left with a single call to `adapter.produce_candidates(scan_request)`.

**S3.3 — Move DERIVED producers**
Move into the adapter: DTE, net_debit/credit, spread_width, max_profit, max_loss, breakeven, prob_of_profit (from delta), ev_raw, reward_risk_ratio, cushion_pct, bid_ask_spread_pct, premium_dollars, theta_runway_days, credit_pct_of_width, debit_pct_of_width.
*References:* audit 5d DERIVED table.

**S3.4 — Move Black-Scholes as COMPUTED tier**
Move `black_scholes.py` and the inline B-S code from `evaluation_routes.py:552-569` into the adapter. Wire `populate_computed` to compute `probability_matrix`, `bs_delta` fallback, `total_ev` (and per-strike `p_max_loss`, `p_max_profit`) only for candidates handed back from the engine after DERIVED gating.
*References:* audit 5d COMPUTED table; §5.2 of refined doc.

**S3.5 — Move SMA producers**
Move `compute_sma_signal` and SMA_8/21/50 calculation into adapter. Produce `sma_alignment` enum.
*References:* audit 5d DERIVED `SMA_*`, `sma_alignment`.

**S3.6 — Propagate gamma**
Audit gap: gamma exists in raw chain but is never propagated to scored candidates. Add gamma to the candidate construction so the WG Theta Gamma Ratio criterion can use it.

**S3.7 — ATR_14 producer**
Audit gap: not computed or fetched anywhere; TODO in code since file creation. Implement. Resolves long-standing dependency for Cushion vs ATR rules.

**S3.8 — True IV percentile producer**
Audit gap: current implementation is ATM IV / 0.60 proxy. Implement true percentile from historical IV. Document the data-source decision (Schwab historical IV vs. external source).

**S3.9 — chart_state enum producer**
Audit gap: sheet rules use `chart_state ∈ {Bullish, Bearish, Mixed, Neutral}`; code has SMA alignment but no mapping. Implement the mapping inside the adapter.

**S3.10 — is_etf producer**
Audit gap: no ETF detection exists. Add a producer (likely from symbol reference table).

**S3.11 — Input catalog publish**
Implement and publish the input catalog per §5.1. Every named value the adapter produces is declared with name, tier, type, null semantics, producer reference. The engine validates against this at startup.

**S3.12 — Adapter integration tests**
Test the adapter against the engine with the canonical Scoring Parameters configuration. End-to-end parity check against pre-extraction `/analyze/*` results.

---

# Feature 4 — Screening rule library

**Type:** Feature
**Parent:** Epic
**Goal:** Build `app/options_rules/screening/` — registered formula implementations the engine looks up via `formula:<name>` for trade-screening strategies.
**Size:** L
**Dependencies:** F1 S1.5 (formula registry mechanism); F2 S2.9 (registry contract list).
**Labels:** `options-domain`

### Stories

**S4.1 — Formula registration mechanism**
Implement the decorator or registry hook that lets a formula module register itself under a name the engine can look up. The engine's startup validation (S1.4) verifies every referenced formula is registered.

**S4.2 — Migrate scoring formulas**
For each of the 12 TBD scoring criteria (audit §4) and the 4 already-implemented ones, implement a registered formula in `options_rules/`. Each formula is a pure function `(named_values, params) -> float in [0, 100]`.

**S4.3 — Migrate cushion penalty**
Move `_cushion_penalty` from `strategy_scorer.py:138-142` into a registered post-scoring-adjustment formula. Per S2.2, the graduated penalty is decomposed into two atomic adjustment rules. Per S6.4, thresholds come from the junction, not literals.

**S4.4 — Migrate asymmetry penalty**
Move `scoring_factors/asymmetry.py` into a registered post-scoring-adjustment formula. Thresholds (2.0, 1.5, 1.25) and penalties (25, 15, 8) come from junction rows.

**S4.5 — Migrate earnings gate as atomic rules**
Decompose the 4-route earnings tree (per S2.2) into four atomic rule formulas. Each is a hard gate or post-scoring adjustment depending on the route's effect.

**S4.6 — Migrate NegativeEVGate**
Move into rule library as a registered formula. Consolidate with the duplicate filter path in `vertical_engine.py:265` (audit 7.5 #2).

**S4.7 — Migrate inline gates from evaluation_routes.py**
Move the DTE ≤ 7 hard filter, the DTE 8–13 penalty, and the credit/debit quality gate (lines 626–663) into rule library formulas.
*References:* audit 5b #5; 5c #8.

**S4.8 — Resolve engine-internal scoring weights** *(resolved — OTA-695, confirmed OTA-733)*
Audit found `VerticalSpreadEngine` carries internal weights (EV 35%, R:R 25%, Prob 20%, Liq 15%, Theta 5%) and `NakedOptionEngine` has its own (Delta 30%, Theta 25%, IV 20%, R:R 15%, Liq 10%). These are a parallel scoring system not in the sheet.

**Decision (OTA-695): DELETE.** The per-strategy junction weights (OTA-680) are the sole weighting mechanism. The legacy engine-internal weight sets are superseded, not codified. They remain in the codebase on live scoring paths until the route-rewiring work (S5.2) replaces the legacy engine calls with engine pipeline calls. At that point, `ScoringWeights` (vertical_engine.py), `NakedOptionWeights` (long_call_engine.py), the per-strategy `scoring_weights` dicts (strategy_definitions.py), and the `SystemConfig` weight validation (config_routes.py) are all removed. Until then, the junction weight-sum check (OTA-699, `insight_engine/validation.py:_check_scoring_weights`) is the single enforcement point for the engine's weighting system; the legacy `.validate()` methods and API-level checks coexist but govern only the legacy scoring paths that S5.2 will retire.

**Superseded weight sets (for reference):**
- `VerticalSpreadEngine.ScoringWeights`: EV 0.35, R:R 0.25, Prob 0.20, Liq 0.15, Theta 0.05
- `NakedOptionEngine.NakedOptionWeights`: Delta 0.30, Theta 0.25, IV 0.20, R:R 0.15, Liq 0.10

---

# Feature 5 — App-side wiring

**Type:** Feature
**Parent:** Epic
**Goal:** Rewire routes and UI to call the engine. Remove all rule logic from the app layer.
**Size:** M
**Dependencies:** F1, F3, F4.
**Labels:** mixed

### Stories

**S5.1 — Implement the OTA Azure SQL persistence sink**
Implement a concrete `PersistenceSink` (the interface from S1.10) that writes `candidate_snapshots` and `evaluation_decisions` to Azure SQL per the §4.3 Phase-1 schema. Alembic migration for the two bronze tables. Async writes using `azure.identity.aio` (per the project's async-credential rule). This sink is injected into the engine at app startup. Fire-and-forget semantics consistent with the observability principle — a persistence failure logs but does not block the evaluation response.
*References:* §4.3.

**S5.2 — Rewire /analyze/* routes**
Each `/analyze/*` endpoint becomes: parse request → look up strategy id → call `adapter.produce_candidates` → call `engine.evaluate(candidates, strategy_id, source_app_id="OTA")` → return result records. No filtering, scoring, or verdict logic in the route. The engine's persistence happens inside the call via the injected sink.

**S5.3 — Rewire /evaluate/structured with LLM-precedence**
Same pattern. The route loses its inline gate logic and its hardcoded verdict bands. Critically, per principle 2.6: the engine runs to completion (all gates, scoring, verdict) *before* any Claude narrative call. Claude is invoked only on survivors, only to generate prose about an already-decided verdict — never to discover a rule violation. The current "Claude scoring sandwich" is removed; Claude sits strictly downstream of the engine verdict.
*References:* §2.6.

**S5.4 — Remove hardcoded verdict bands**
Delete `_assign_verdict` literal thresholds. Bands come from the strategy's verdict_band_set in config.
*References:* audit 5a #7.

**S5.5 — Frontend strategy-configs consolidation**
Frontend `web/src/strategy-configs/*.config.js` files become consumers of an API that returns the canonical strategy definition from the runtime tables. Stop being a parallel source of truth.

**S5.6 — Result-record rendering layer**
UI components for verdict cards, scorecards, and diagnostic panels consume `ResultRecord` fields. No re-derivation of scores or verdicts in the UI.

**S5.7 — Wire Position Monitor Agent through the engine**
The Position Monitor Agent currently calls `health_grade.py` directly. After F10/F11 ship, for each open position the agent:
1. Checks `position_exit_levels_complete` (a published named value from F10 S10.2).
2. Selects strategy: `position_health_full` when complete, `position_health_basic` otherwise.
3. Calls `engine.evaluate([position_candidate], strategy_id, source_app_id="OTA")` against the `position_health` adapter.
4. Persists the returned verdict letter to `positions.health_grade`; the full per-rule trace is already persisted by the engine's sink.
5. Continues with existing alert/insight escalation — when a verdict warrants it, invokes the renamed Insight Communicator (per S9.6). The agent's escalation logic stays in the agent; the engine produces verdicts, the Communicator produces prose.

**S5.8 — Wire directional comparison through the engine**
After F12 ships, the directional-comparison route calls the engine against the `directional` adapter with `source_app_id="OTA"`. The `fitness_score` field that `directional_engine.py` produced is replaced by the engine's verdict and weighted score.

---

# Feature 6 — Strategy independence cleanups

**Type:** Feature
**Parent:** Epic
**Goal:** Resolve every finding in audit Section 5a. After this feature, no engine, adapter, or rule library code branches on strategy identity.
**Size:** M
**Dependencies:** F1, F3, F4 (the structure to migrate into).
**Labels:** `options-domain`

### Stories

**S6.1 — Eliminate dual-scorer architecture**
SP and WG no longer share `_score_credit_spread_strategy`. TR and LT no longer share `_score_long_option_strategy`. Each strategy's scoring is the engine's pipeline driven by its junction rows.
*References:* audit 5a #1.

**S6.2 — Eliminate strategy-as-type routing in score_all_strategies**
The `uses_vertical_engine / uses_long_option_engine / else None` three-branch becomes a single engine call with a strategy id.
*References:* audit 5a #2.

**S6.3 — Remove hardcoded TR delta center**
`if strategy_key == "trend-rider"` goes away. TR's delta_center / delta_half_range live in its junction row for the Delta Quality scoring rule. LT's same row supplies its own values (no implicit "everything that isn't TR").
*References:* audit 5a #3.

**S6.4 — Per-strategy cushion penalty thresholds**
Cushion penalty thresholds (1.0%, 2.0%) move from the shared credit-spread scorer into per-strategy junction rows. SP and WG can have different thresholds; today they cannot.
*References:* audit 5a #4.

**S6.5 — Eliminate shared normalization pool**
Min-max normalization happens per-strategy, not across the engine's full candidate pool. SP's normalization range stops being influenced by WG-eligible candidates.
*References:* audit 5a #5.

**S6.6 — Resolve STRATEGIES vs STRATEGY_DTE_REQUIREMENTS dual-source**
Pick one as canonical; delete the other. The strategy classifier reads from the same dict the scorer reads from. (OTA-513 already tracks this; link this story to that ticket.)
*References:* audit 5a #6.

**S6.7 — Per-strategy verdict bands**
Verdict band thresholds move from `_assign_verdict` literals into per-strategy config in the Strategies tab.
*References:* audit 5a #7. Overlaps with S5.3; this story owns the config side, S5.3 owns the code-removal side.

---

# Feature 7 — Domain coupling in engine machinery

**Type:** Feature
**Parent:** Epic
**Goal:** Resolve every finding in audit Section 5c. After this feature, engine-machinery code references zero domain terms.
**Size:** M
**Dependencies:** F1.
**Labels:** `framework-portable` (the cleanups happen on what becomes engine code)

### Stories

**S7.1 — Refactor GateTradeContext**
Replace `expected_value`, `expiry_date`, `dte` with a generic `candidate: Candidate` reference. Rules access named values by key.
*References:* audit 5c #1, #2.

**S7.2 — Generic action codes on GateResult**
Replace domain verdict strings (`PASS`, `WAIT_FOR_EARNINGS`) with action codes (`BLOCK`, `DEFER`, `MODIFY`, `OK`). Domain layer maps action codes to verdict strings.
*References:* audit 5c #4.

**S7.3 — Move gate-specific metadata off framework GateResult**
`_dte_after_earnings`, `_reevaluate_on` come off the framework GateResult onto either a gate-specific result extension or a generic `metadata: dict` field.
*References:* audit 5c #5.

**S7.4 — Split StrategyDefinition**
Split into generic `StrategyConfig` (key, label, weights, structures — lives in engine config) and `OptionsStrategyParams` (delta, IV, exit levels — but per F4 audit, most are dead code; the live ones move to junction or adapter).
*References:* audit 5c #6; 7.5 #1.

**S7.5 — Decompose strategy_scorer.py**
The file disappears. Its content splits: orchestration → app-side route changes (F5); per-rule scoring math → registered formulas (F4); normalization → engine core (S1.2, single canonical implementation).
*References:* audit 5c #7; 7.5 #3.

**S7.6 — Move inline evaluation_routes.py gates to engine**
DTE hard filter, credit/debit quality gate move from `evaluation_routes.py:626-663` into registered engine gates per F4.
*References:* audit 5c #8.

---

# Feature 8 — Cleanup and dedup

**Type:** Feature
**Parent:** Epic
**Goal:** Address audit Section 7.5 code-smell findings that aren't direct independence or coupling violations but block clean extraction.
**Size:** S
**Dependencies:** F3, F4 (some cleanups are by-products of the migration).
**Labels:** mixed

### Stories

**S8.1 — Remove dead StrategyDefinition fields**
Delete `name`, `delta_min`, `delta_max`, `iv_rank_min`, `credit_pct_min`, `credit_pct_max`, `exit_profit_pct`, `exit_loss_multiplier` — declared but never read.
*References:* audit 7.5 #1.

**S8.2 — Consolidate two EV filter paths**
NegativeEVGate (registered hard gate) and the `ev_raw >= min_ev_threshold` filter in `vertical_engine.py:265` become one path. Per F4 S4.6 the gate moves to rule library; this story removes the filter duplicate.
*References:* audit 7.5 #2.

**S8.3 — Consolidate three normalize() implementations**
`_normalize()` in `strategy_scorer.py`, `normalize()` in `vertical_engine.py`, `normalize()` in `long_call_engine.py` — all identical min-max. One canonical implementation in engine core per S7.5.
*References:* audit 7.5 #3.

**S8.4 — Move COMPONENT_DISPLAY_NAMES to UI**
This display-name mapping in `strategy_scorer.py:46-63` is a UI concern in the scoring file. Move to frontend or to a presentation layer module.
*References:* audit 7.5 #4.

**S8.5 — DirectionalEngine disposition (retired)**
Decision made: DirectionalEngine becomes the third engine consumer per the all-evaluation-through-engine principle. Implementation tracked under F12. This story closes as superseded.

**S8.6 — Resolve long-standing ATR(14) TODO**
The TODO at `strategy_scorer.py:129` ("Phase 2.4.x — when ATR(14) is available") resolves automatically once F3 S3.7 (ATR_14 producer) ships. Close as duplicate of S3.7 or as fixed-by.
*References:* audit 7.5 #6.

---

# Feature 9 — Documentation

**Type:** Feature
**Parent:** Epic
**Goal:** Land the engine documentation and reshape business-rules.md to the engine-aligned three-section structure.
**Size:** S
**Dependencies:** None — runs in parallel with F1/F2 from the start.
**Labels:** `framework-portable` (S9.1, S9.3, S9.4); `options-domain` (S9.2, S9.5)

### Stories

**S9.1 — Land insight_engine.md v3 as canonical**
Move the v3 doc into the project at the canonical path. Version-control. This becomes the doc Claude Code reads at the start of every engine session.

**S9.2 — Restructure business-rules.md as a rule catalog**
Reshape into:
1. **Input definitions** — every named value the options adapter produces: how computed, data source, tier, type, null semantics. The prose companion to the §5.1 input catalog.
2. **Rule catalog, grouped by common rule type** (earnings rules, liquidity rules, cushion rules, probability rules, etc.). For each rule: its **intent** (plain-language why, e.g. "never enter within 7 days of earnings because of theta acceleration"), its **logical evaluation formula** (`earnings_date - today() > 7`), its **required inputs**, and its **expected output** (gate pass/fail, score contribution, or adjustment).
3. **Domain semantics** — trading-philosophy decisions that don't fit a single rule (e.g. why PoP uses long-leg delta).

Strategies are **NOT** documented here. They are self-documenting in the Strategies table and the junction rationale. If a strategy needs visuals or long-form explanation, business-rules.md carries a *pointer* to an unstructured doc, never the content inline.
*References:* engine doc §9.

**S9.3 — Update architecture-plan.md**
Add the new package boundaries (`app/insight_engine/`, `app/ota_adapters/*`, `app/options_rules/*`) under the directory map. Replace the prior "domain-specific insight generation" framing with the generic Insight Engine. Add three new sections:
- The **persistence read-path**: the bronze tables (write-path, owned by the engine sink) feeding a Databricks bronze/silver/gold expansion of `payload_json` into analytics tables. This is the Phase 2/3 of the hybrid OLTP + schema-on-read pattern; out of scope for the engine but documented here.
- The **LLM-orchestration contract** (see S9.7).
- The **engine-sink wiring**: how OTA injects its Azure SQL sink at startup, and the path to a shared cross-app bronze zone when STK/FFL arrive.

**S9.4 — Update CLAUDE.md**
Add engine-rule entries:
- Engine code (under `app/insight_engine/`) imports nothing from domain modules.
- No `if strategy_id == ...` or `if strategy_key == ...` branches anywhere.
- The junction is the only home of strategy×rule parameters, `evaluation_order`, `stop_if_fail`, `score_penalty`, and weights.
- All rule content comes from the runtime tables; no magic numbers in code. The spreadsheet is a build-time seed only.
- Every `engine.evaluate(...)` passes `source_app_id`.
- The engine never calls an LLM; all disqualifying rules run before any LLM call (principle 2.6).

**S9.5 — Named formula registry as SKILL.md**
Document the `formula:<name>` registry as a companion SKILL.md the rule-library code reads from. Lists every formula the options consumer registers, with signature and inputs.

**S9.7 — Document the LLM-orchestration contract**
In architecture-plan.md, capture the consumer-side LLM principle (this governs OTA's use of Claude, not the engine): the engine runs to completion before any LLM call; the LLM never discovers a rule violation; LLM calls are minimised in *number* while individual calls may be detailed and precise (spend tokens per call, save tokens by making fewer calls); and model selection is deliberate — Opus for complex analysis, Haiku for simple text responses. This is a guiding principle for downstream orchestration, explicitly not an engine concern (the engine is LLM-agnostic).

**S9.8 — Strategy-administration UI (rules/junction maintenance)**
Build the admin UI per the strategy-page mockup from prior design work. CRUD on rules, strategies, and junction rows — this is the runtime maintenance surface that replaces editing the spreadsheet. After F2 seeds the tables, all ongoing rule/strategy/parameter changes happen here. Scope note: this is a sizeable UI effort and may warrant promotion to its own Feature if it grows; tracked here for now as the thing that makes "tables are the source of truth" operationally real.

**S9.6 — Rename `app/agents/insight_engine.py` → Insight Communicator**
The existing component is the Claude-based observation→insight communicator (per `architecture-plan.md`). With the new generic Insight Engine taking the name, the existing file is renamed:
- `app/agents/insight_engine.py` → `app/agents/insight_communicator.py`
- Class `InsightEngine` (if it exists) → `InsightCommunicator`
- SKILL.md path `app/skills/insight-engine/` → `app/skills/insight-communicator/`
- All call sites updated (Position Monitor Agent and any other agent that invokes it)
- `insights` table name unchanged — it stores Communicator output

Acceptance: `grep -r "insight_engine" app/agents/` returns no hits (except for legitimate references to the new generic engine package); the Communicator's behaviour is unchanged.

**S9.7 — Cross-doc reference sweep**
Update every reference across `architecture-plan.md`, `CLAUDE.md`, `business-rules.md`, and any SKILL.md that previously referred to the Communicator as "Insight Engine." Pattern 5 in `architecture-plan.md` ("The Insight Engine" section) splits into two sections: one describing the new generic Insight Engine, one describing the Insight Communicator. Their relationship is documented: the Communicator may consume engine ResultRecord verdicts as one of its trigger signals.

---

# Feature 10 — Position Health input adapter

**Type:** Feature
**Parent:** Epic
**Goal:** Build `app/ota_adapters/position_health/` implementing the §5 contract. Produces a candidate per open position with named values describing the position's current state versus its entry expectations. Replaces every input that `app/analysis/health_grade.py` currently reads ad hoc.
**Size:** M
**Dependencies:** F1 S1.7; shared providers from F3 S3.1.
**Labels:** `options-domain`

### Stories

**S10.1 — Adapter package and interface**
Create `app/ota_adapters/position_health/` with the `PositionHealthAdapter` class. Inputs: open positions from the `positions` table + current market state for each underlying. Output: one candidate per position.

**S10.2 — RAW producers from the `positions` table**
Pull from each open position:
- `position_entry_price` (the spread's net credit/debit at entry — `entry_price` in current code)
- `position_structure` (enum: bull_put_credit, bear_call_credit, bull_call_debit, bear_put_debit, long_call, long_put — known from position legs at entry, not inferred at evaluate time)
- `position_structure_direction` (enum: bullish / bearish — derived from `position_structure` at adapter load, not at rule evaluation; this replaces the runtime direction inference at `health_grade.py:55-56` that uses `sign(stop - warning)`)
- `position_exit_warning_underlying` (from stored `claude_exit_levels_json.warning`)
- `position_exit_stop_underlying` (from stored `claude_exit_levels_json.stop`)
- `position_exit_scale_out_underlying` (from stored `claude_exit_levels_json.scale_out` — currently parsed but unused in code; promoting to a real input forces a decision in F11 on whether scale_out drives any rule)
- `position_exit_levels_complete` (boolean: both warning and stop are non-null and parseable — drives the "fall back to P&L" decision today as a try/except; in the engine it's a hard-gate input)

**S10.3 — RAW producers from current market state**
Via the shared Schwab provider:
- `current_underlying_price` (the underlying spot — what `health_grade.py` overloads `current_price` to mean inside the exit-levels path)
- `current_position_mark` (the spread's current mark — what `health_grade.py` documents `current_price` as)
The adapter publishes BOTH named values explicitly. The current code's overload of `current_price` disappears; the appropriate rules access the appropriate value.

**S10.4 — DERIVED producers**
- `pnl_pct` = `(current_position_mark - position_entry_price) / abs(position_entry_price)` — the formula at `health_grade.py:_pnl_pct`. The `abs()` in the denominator preserves correct grading for credit spreads (negative entry_price moving toward zero is a win).
- `warning_breached` (boolean) — for bullish structures: `current_underlying_price <= position_exit_warning_underlying`; for bearish structures: `current_underlying_price >= position_exit_warning_underlying`. Atomic, structure-aware.
- `stop_breached` (boolean) — same shape against `position_exit_stop_underlying`.
- `warning_proximity_ratio` (float in `[0, 1+]`) — distance from current_underlying to the warning level, normalised by the warning-to-stop buffer. Captures the "within 20% of warning" concept at `health_grade.py:65-66, 75-76` as a numeric input rather than embedding the 20% threshold in code. The 20% lives in a rule parameter, not in the adapter.
- `days_since_entry`, `days_to_expiration` — straightforward DERIVED, both needed by F11 future scoring rules.

**S10.5 — COMPUTED producers (future, behind a feature flag)**
For positions still inside their B-S validity window: `current_prob_of_profit`, `current_ev`, `probability_of_max_loss_now`. Not used by the v1 health grade (today's code doesn't use them); included as future inputs once Option A (real weighted scoring — see F11 S11.2 design decision) is selected.

**S10.6 — Input catalog publish**
Same pattern as S3.11. Every named value the adapter produces is declared with name, tier, type, null semantics.

**S10.7 — Adapter tests**
End-to-end parity: a fixture of historical positions produces the same letter from the engine (with F11's rules) as from pre-extraction `health_grade.py`. Used as the acceptance check for the Wave 4 wiring story (S5.7).

---

# Feature 11 — Position Health rule library

**Type:** Feature
**Parent:** Epic
**Goal:** Build `app/options_rules/position_health/` — registered formulas for grading open positions as a real weighted score [0, 100] mapped to A/B/C/D/F via verdict bands. After this feature ships, all health-grade logic lives in the configuration source (Scoring Parameters.xlsx) and registered formulas; `health_grade.py` is deleted.
**Size:** M
**Dependencies:** F1 S1.5; F10 S10.6 (catalog).
**Labels:** `options-domain`

### Design — Option A locked in

Health grade is a weighted-score strategy, not a categorical decision tree. Score 0–100 from per-criterion contributions, mapped to A/B/C/D/F by verdict bands. Every threshold, weight, and band lives in the configuration source. No literals in code, no decision-tree control flow.

The current code's two paths (exit-level-driven for positions with stored Claude levels, P&L-driven for positions without) become **two strategies** — `position_health_full` and `position_health_basic`. The Position Monitor Agent (app-side orchestration, S5.7) picks the strategy per position based on `position_exit_levels_complete`. Same way SP vs WG is picked for screening — strategy selection is orchestration; the engine evaluates whichever strategy it's handed.

### Stories

**S11.1 — Define `position_health_full` and `position_health_basic` strategies in config**
Add two rows to the Strategies tab.
- `position_health_full` — for positions where Claude stored warning/stop levels at entry. Uses exit-level proximity as the dominant signal, P&L as supplementary.
- `position_health_basic` — for positions without stored exit levels. Uses P&L alone.

Both share the same verdict bands: A ≥ 90, B ≥ 75, C ≥ 50, D ≥ 25, F < 25 (subject to Don's review when the values are pinned). Scan parameters: monitor-all-open-positions, run daily after market close + on-demand.

**S11.2 — Register data-completeness hard gates**
Per strategy, register hard gates that fail candidates lacking required inputs:
- Both strategies require: `position_entry_price` not null, `current_position_mark` not null.
- `position_health_full` additionally requires: `position_exit_levels_complete = true`, `position_structure_direction` in (bullish, bearish).
The fallback try/except at `health_grade.py:78` (parse failure → P&L path) is replaced by the agent's strategy selection plus these hard gates: if a `_full` candidate fails the completeness gate, the agent re-runs it under `_basic`. No silent fallback inside the engine.

**S11.3 — Register `exit_level_safety_score` scoring formula**
Pure function `(named_values, params) -> float in [0, 100]`. Reads `warning_breached`, `stop_breached`, `warning_proximity_ratio` and a `proximity_buffer_fraction` parameter (the 20% from `health_grade.py:66, 76` — now a junction parameter, not a literal). Returns:
- 0 if `stop_breached` is true
- A low number (parameter-driven) if `warning_breached` is true
- A graduated value based on `warning_proximity_ratio` when inside the buffer
- 100 when well clear of warning
Exact step shape comes out of S11.6 calibration; the formula handles all of it from the junction parameters.

**S11.4 — Register `pnl_band_score` scoring formula**
Reads `pnl_pct`. Returns a value in [0, 100] determined by junction-bound band thresholds (the -0.10 / -0.25 / -0.50 in `health_grade.py:_grade_from_pnl_pct` become four parameter values per strategy). Same formula serves both strategies — each strategy supplies its own band parameters via junction rows.

**S11.5 — Register post-scoring adjustments for hard floors**
Two atomic adjustments, each junction-parameterised:
- `stop_breached_floor` — when `stop_breached` is true, force the final score to a floor value (parameter; default 0 to land in F band). Equivalent to `health_grade.py:60-61, 71-72` "stop → F" rule.
- `warning_breached_cap` — when `warning_breached` is true, cap the final score at a parameter-driven ceiling (default 24 to land in D band). Equivalent to `health_grade.py:62-63, 73-74` "warning → D" rule.
These run after the weighted sum and after `exit_level_safety_score`'s graded output, preserving the categorical "no matter the rest, if stop is breached you're F" guarantee from the current code.

**S11.6 — Junction weights and parameter calibration**
Populate junction rows for `position_health_full`:
- `exit_level_safety_score` weight (proposed 0.70, since current code lets exit-level state override everything when present)
- `pnl_band_score` weight (proposed 0.30)
- Per-formula parameters: `proximity_buffer_fraction = 0.20`, P&L band thresholds matching current `-0.10 / -0.25 / -0.50` values
- Adjustment parameters: `stop_breached_floor = 0`, `warning_breached_cap = 24`

For `position_health_basic`:
- `pnl_band_score` weight 1.0
- Same P&L band thresholds

Calibrate against fixture positions until parity with current `health_grade.py` letters is achieved within an acceptable tolerance (some positions will land on different letters by design — that's the upgrade from Option B to Option A).

**S11.7 — Wire `scale_out` (currently dead config)**
`health_grade.py:31` parses `levels.get("scale_out")` but never uses it. The named value is published by the adapter (S10.2). F11 makes a decision: either retire the field from `claude_exit_levels_json` or add a `scale_out_proximity_score` rule that uses it. The configuration entry forces the choice; dead config doesn't survive the migration.

**S11.8 — Color mapping at presentation layer**
A=green, B=teal, C=yellow, D=orange, F=red — moves to the UI rendering layer (per the bucket-mapping table: this is presentation, not engine). The engine emits the letter; the UI maps to color.

**S11.9 — Rule library tests and parity check**
Fixture positions across the spectrum (just entered with positive P&L, mid-life nearing warning, warning breached but not stop, stop breached, no-exit-levels positions across P&L bands) produce expected letters under both strategies. Wave-4 wiring story S5.7 uses these tests as its acceptance gate.

---

# Feature 12 — Directional comparison adapter and rule library

**Type:** Feature
**Parent:** Epic
**Goal:** Build `app/ota_adapters/directional/` and `app/options_rules/directional/`. After this feature ships, `directional_engine.py`'s `fitness_score` is replaced by an engine verdict.
**Size:** S
**Dependencies:** F1 S1.7; shared providers from F3 S3.1.
**Labels:** `options-domain`

### Stories

**S12.1 — Adapter and interface**
Create `app/ota_adapters/directional/` with the `DirectionalAdapter`. Inputs: a thesis (ticker, direction, conviction) + the Schwab chain. Output: one candidate per (structure, strikes, expiry) combination compatible with the thesis.

**S12.2 — Define the directional strategy(ies)**
The directional comparison may have one strategy ("which structure best fits this thesis") or several (one per thesis-type). Decide and add to the Strategies tab with junction rows.

**S12.3 — Migrate directional formulas**
The `fitness_score` math in `directional_engine.py` decomposes into atomic scoring criteria registered as formulas. Junction rows supply weights.

**S12.4 — Retire `directional_engine.py`**
Once the route calls the engine instead, delete the file. Verify no callers remain.

---

## Sequencing

```
Wave 1 (parallel):  F2  (config) ────┐
                    F9  (docs)   ────┤
                                     │
Wave 2:             F1  (engine core)   ◀── needs F2 tables + seed model defined
                                     │
Wave 3 (parallel):  F3  (chain adapter)         ─┐
                    F10 (position health adapter)─┤ ── all four need F1
                    F12 (directional adapter+rules)┤
                    F4  (screening rules)        ─┘
                                     │
                    F11 (position health rules)  ◀── needs F10's catalog
                                     │
Wave 4:             F5  (wiring) ◀── needs F1, F3, F4, F10, F11, F12
                    F6  (independence) ◀── happens during F4/F5 migration
                    F7  (coupling) ◀── happens during F1 build
                                     │
Wave 5:             F8 (cleanups) — final pass
```

Wave 2 has the longest pole; F1 is L and gates Wave 3. Wave 3 is wide — five features running in parallel after F1 lands (F3, F4, F10, F11, F12), each spawning multiple Claude Code sessions on independent stories. F11 has a soft dependency on F10's input catalog being published.

## What this Epic does not address

Out of scope, mentioned for completeness:

- Backtesting engine — uses different orchestration; will eventually be a fourth consumer of the engine (same pattern as the three in this Epic).
- Insight Engine (the existing `app/agents/insight_engine.py`) — the Claude-based observation→insight communicator. Distinct component; takes the rules-based engine's verdicts as one input but does not duplicate evaluation logic.
- Cross-app extraction (lifting `app/insight_engine/` into its own package or repo) — happens after Wave 5 lands and parity is verified for all three consumers.

Each of the above can be a follow-on Epic once this one ships.