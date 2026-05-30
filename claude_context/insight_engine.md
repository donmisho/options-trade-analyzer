# Insight Engine

> **Status:** Framework v3 · 2026-05-21
> **Scope:** This document describes how the Insight Engine operates. It does not describe options trading, strategies, gates, scoring formulas, or any other domain content. Those live in the configuration tables and in `business-rules.md`, and are fed to the engine at runtime. The engine is intentionally domain-agnostic — options trading is its first consumer, not its only conceivable one.

---

## 1. What the Insight Engine is

The Insight Engine is a generic evaluation framework. It takes:

- a **stream of candidates** (records of any shape produced by a consumer-specific input adapter), and
- a **strategy** (a named selection of rules, each parametrised through the strategy×rule junction)

and runs them through a deterministic pipeline that produces, for each candidate:

- a **pass/fail decision** from the gating rules,
- a **weighted score** in `[0, 100]`,
- an **adjusted score** after post-scoring modifiers,
- a **verdict** assigned from configured score bands, and
- a **complete per-rule decision trace** emitted to persistence.

The engine has no built-in knowledge of any domain. It does not know what a `delta` is, what a `credit spread` is, or what `IV rank` means. It moves named values through rules that reference them by name. The names and the values come from outside.

A different consumer (e.g. fantasy football lineup optimisation, or a stock-trade analyzer) supplies its own adapter, named values, rules, and strategies. The engine source code does not change.

> **All rule-based evaluation flows through the engine.** Within a single application, every distinct evaluation surface (for OTA: trade screening, position health grading, directional thesis comparison) is its own consumer of the same engine — its own input adapter, its own strategies, its own verdict bands. There is no second evaluation path. Duplicative rule logic across consumers is a design defect, not an acceptable shortcut.

> **The engine serves more than one application.** Every call carries a `source_app_id` (`OTA`, `FFL`, `STK`, …). The engine stamps it onto every record it emits, so a single shared bronze zone can hold the evaluation history of many applications, queryable per-app or across apps. Applications never mix at evaluation time; they can be analysed together afterward.

## 2. Foundational principles

These are the non-negotiable properties of the engine. Every architectural decision below derives from them. Each is enforced at startup or at evaluation — none is left to discipline alone.

1. **The tables are the source of truth.** All rules, thresholds, weights, gate behaviour, ordering, and verdict bands live in the rule / strategy / junction tables. The engine hardcodes no rule content. The spreadsheet (`Scoring Parameters.xlsx`) is a **build-time seed** used to populate the tables once; after that, the tables are authoritative and are maintained through the application's strategy-administration UI. *Enforced by:* startup config loader reads tables; engine has no rule literals.
2. **Strategy independence.** A strategy is a named selection of rules and their per-strategy parameters, expressed as the strategy's slice of the junction. Strategies are runtime values, not code branches. No strategy's logic may reference, depend on, or be defined in terms of any other strategy. No inheritance, no cross-strategy fallback, no shared mutable state. *Enforced by:* engine routes strategies by config lookup only; no `if strategy_id == X` branches anywhere in engine code.
3. **Atomic rules.** Every rule evaluates exactly one condition. Compound conditions (`A AND B`, `A OR B`) are expressed as multiple rules with sequential evaluation and ordering. The engine does not parse compound expressions. *Enforced by:* expression library admits only single-condition forms.
4. **Fixed pipeline order, configurable rule order.** The pipeline phases run in a fixed order (gates → scoring → adjustments → verdict). Within a phase, rules execute in a per-strategy `evaluation_order`. A score is never adjusted before it exists; a verdict is never assigned before adjustments apply. *Enforced by:* the orchestrator is the only execution path; phase sequence is in code, rule order is in the junction.
5. **Domain decoupling.** Engine machinery — config loader, rule evaluator, pipeline orchestrator, verdict assignment, result builder, persistence driver — contains zero references to any domain concept. Domain terms appear only inside (a) individual rule formula implementations registered with the engine, and (b) the consumer-specific input adapter. *Enforced by:* import-time check; engine package must not import from any domain package.
6. **Full deterministic evaluation precedes any LLM call.** The engine is a deterministic, LLM-free pipeline. Any consuming application that uses an LLM downstream (e.g. OTA's narrative generation) must run the **entire** engine evaluation — every disqualifying rule included — before that LLM call. An LLM must never be the thing that discovers a candidate violates a rule. The engine produces the verdict; the LLM, if used at all, explains or elaborates on survivors. *Enforced by:* the engine has no LLM dependency; the LLM-precedence rule is a consumer-orchestration contract documented in `architecture-plan.md`.

## 3. Core concepts

### 3.1 Candidate

A record evaluated by the engine. The engine sees a candidate as an opaque container of **named values**. The consumer's input adapter produces candidates; the engine consumes them.

A candidate is the unit of evaluation. One pipeline run produces one verdict per candidate.

The engine does not care what a candidate represents. For the OTA options consumer, candidates can be prospective trades (screening), open positions (health grading), directional thesis comparisons, or any future evaluation target. Each is its own input adapter with its own strategies — the engine is the same.

### 3.2 Named value

A scalar, enum, date, or null-allowed value that a candidate carries. Each named value has:

- a **name** (`stock_price`, `chart_state`, `next_earnings_date`, `player_age`, `team_record` — opaque to the engine)
- a **tier** (RAW · DERIVED · COMPUTED — see §3.5)
- a **type** (scalar number, enum from a set, date, boolean)
- **null semantics** (whether absent or `null` is allowed; rules can require non-null via data-completeness gates — see §3.6)

Named values are the only vocabulary rules use. The engine never invents a new named value — they all come from the input adapter.

### 3.3 Rule

A rule is an independent, reusable atom. It defines what the condition is and why it exists, but never to what parameters, weights, or stop behaviour any particular strategy applies it. Concretely:

- an **id** (stable identifier, the key in the rules table)
- a **phase** (gate · scoring criterion · adjustment — see §3.6)
- a **condition expression** (the predicate or formula, drawn from the engine's expression library — see §6.3)
- a **parameter schema** (which parameters the rule expects to be supplied per binding, with type and bounds — but no values; values live in the junction)
- a **tier** (RAW · DERIVED · COMPUTED — see §3.5)
- **referenced named values** (which inputs the rule needs)
- an **intent** (free text — why this rule exists at all, independent of any strategy; e.g. "never enter within 7 days of earnings because of theta acceleration")

The engine reads rules; it does not write them. Rules live in the rules table.

> **Rules may be shared across applications.** A rule like a negative-EV gate could apply to both an options trade (OTA) and a stock trade (STK). Rule ids are intended to be globally unique across applications; whether a given rule is used by a given application is determined entirely by whether a junction row exists. This keeps a single rule library reusable while keeping each application's strategies scoped to that application. (The exact rule-table DDL for global vs. app-scoped ids is settled during the build, not here.)

### 3.4 Strategy and the strategy×rule junction

A strategy is an independent, named entity. It does not, on its own, carry any rule logic. Concretely a strategy is:

- an **id** (stable identifier)
- a **label** (human-friendly name)
- a **verdict band set** (the score-to-grade mapping for this strategy — see §3.8)
- **scan parameters** (engine-level knobs like evaluation cap, output cap — see §3.7)
- a **description** (free text — what this strategy is for)

The strategy×rule binding is a separate first-class entity, the **junction**. One junction row exists per (strategy, rule) pair the strategy uses. Each junction row carries:

- a reference to the **strategy id**
- a reference to the **rule id**
- an **enabled** flag (the rule is bound but currently switched off — preserves audit trail without deletion)
- an **evaluation_order** (integer; the rule's execution position within its phase, for this strategy — see §3.6)
- a **stop_if_fail** flag (for gate rules: does a failure halt the candidate, or merely record and continue — see §3.6)
- a **score_penalty** (for gate rules that apply a reduction on failure; may be zero or null — see §3.6)
- the **parameter values** for this strategy's use of this rule (e.g. `dte_min=14, dte_max=21` for Weekly Grind × DTE Range)
- the **weight** if the rule is a scoring criterion (else null)
- a **rationale** (free text — why this strategy uses this rule with these specific parameters; the strategy-specific *why*)

There are no defaults inherited from the rule. There are no overrides of a base rule. The junction row is the only place the strategy's configuration for the rule exists. If the row does not exist, the rule is not part of the strategy.

> **Junction-only invariant.** The engine refuses to evaluate a strategy×rule pairing whose parameter values, ordering, and gate behaviour are not fully supplied in the junction. There is no fallback to "what the rule says." A missing required field is a startup-time validation failure.

This model applies uniformly to: gates (enabled, order, stop behaviour, optional penalty, thresholds), scoring criteria (enabled, order, weight, parameters), and adjustments (enabled, order, parameters).

### 3.5 Calculation tier

Every named value and every rule has a tier:

- **RAW** — produced directly by the input adapter from a primary data source (market data API for the options consumer; a stats API for fantasy football). Cheap. Always available for every candidate.
- **DERIVED** — computed from RAW values without external calls (DTE from expiration; net_debit from bid/ask; player_age from birthdate). Cheap. Deterministic. Produced by the adapter.
- **COMPUTED** — produced by heavier math (Black-Scholes probability matrix for the options consumer; ML inference, regression, simulation for any consumer). Expensive. Triggered selectively.

The tier system is a performance contract. The engine's pipeline (§4) honors it: RAW gates eliminate first, then DERIVED, then COMPUTED. A candidate that fails an earlier-tier gate is never sent through COMPUTED.

### 3.6 Rule phase and gate mechanics

A rule belongs to one of three **phases**, distinguished by *when* it runs and *what data it can read* — a real pipeline constraint, not a human label:

- **Gate** — evaluates against the candidate's inputs (named values), before any score exists. Cannot read the score. Runs in tier order (RAW → DERIVED → COMPUTED).
- **Scoring criterion** — produces a value in `[0, 100]`, multiplied by its junction weight. The candidate's raw score is the weighted sum across active criteria.
- **Adjustment** — evaluates after the raw score exists. Can read the score and the inputs. Adds or subtracts a configured amount, or forces a floor/cap.

> **"Hard gate" and "soft gate" are not separate phases.** They are the same gate phase with different junction settings. A gate's behaviour on failure is fully described by two junction fields:
> - **`stop_if_fail`** — `true`: failure halts the candidate (the classic "hard gate"). `false`: failure is recorded and the candidate continues to be scored (the classic "soft gate," or a record-only gate).
> - **`score_penalty`** — a reduction applied to the raw score if the gate fails and the candidate continues. May be a negative number (soft-gate reduction), or zero (record-only — fail it, log why, but don't penalise).
>
> This collapses a former category distinction into configuration. The same rule can be a hard stop for one strategy and a non-stopping recorded failure for another, set entirely in the junction.

**Why `stop_if_fail` matters — the long-DTE case.** A 180–360 DTE strategy may fail an earnings-window gate (next earnings is next week) yet still want its score captured for future evaluation, since the event will have passed long before expiry. That strategy sets `stop_if_fail = false, score_penalty = 0` on the earnings gate: the failure is logged with its reason, the candidate is still scored, and the perpetual evaluation log retains it for re-evaluation later. A short-DTE strategy sets `stop_if_fail = true` on the same rule: failure is terminal.

**Data-completeness gates.** A gate may require a named value to be non-null. These are ordinary gates (typically `stop_if_fail = true`) that fail a candidate when a required input is absent.

**Ordering within a phase.** Each gate, criterion, and adjustment carries an `evaluation_order` per strategy. Gates are evaluated cheapest/most-decisive first — for OTA, the earnings gate is typically order 1 among hard stops, because it is the hardest, cheapest kill. A `stop_if_fail = true` gate that fails halts evaluation immediately, so ordering directly controls how much work a doomed candidate consumes.

### 3.7 Scan parameters

Engine-level knobs that do not evaluate candidates but control how the engine processes them. For any consumer:

- evaluation cap (max candidates scored per scan)
- candidate priority ordering (which candidates are scored first when the cap binds)
- expansion direction (how the engine widens the candidate window if the cap allows)
- output rank cap (max candidates surfaced after scoring)

Scan parameters belong to a strategy, not to a rule. The engine reads them at run start.

### 3.8 Verdict bands

A monotonic mapping from final adjusted score to a categorical verdict, defined per strategy. The engine treats verdict labels as opaque strings — the label `EXECUTE` (or `A`, or `START`) has no meaning to the engine.

> **Per-strategy bands.** The audit found the current OTA implementation hardcodes universal `EXECUTE/WAIT/PASS` thresholds (70/50) in `evaluation_routes.py` — a violation of the tables-as-source principle, not evidence that bands should be universal. The engine treats bands as configurable per strategy from day one. Screening uses `EXECUTE/WAIT/PASS`; health grading uses `A/B/C/D/F`; both come from the same Stage-8 band lookup.

## 4. Pipeline

A pipeline run takes a stream of candidates, a strategy id, and a `source_app_id`, and emits an evaluated result per candidate. The pipeline phases run in fixed order; rules within a phase run in junction `evaluation_order`.

```
                  +------------------------------+
   candidates --->| 1. Gates (RAW)               |
                  |    order = evaluation_order   |
                  +------------------------------+
                       | stop_if_fail & fail --> halt (record decision)
                       | pass / non-stopping fail (record, hold penalty)
                       v
                  +------------------------------+
                  | 2. Gates (DERIVED)           |
                  +------------------------------+
                       |
                       v
       +------------------------------------------------+
       | <> Adapter callback: populate COMPUTED values  |
       |    only for candidates still alive here         |
       +------------------------------------------------+
                       |
                       v
                  +------------------------------+
                  | 3. Gates (COMPUTED)          |
                  +------------------------------+
                       |
                       v
                  +------------------------------+
                  | 4. Scoring criteria          |-- weighted sum [0,100]
                  +------------------------------+
                       |
                       v
                  +------------------------------+
                  | 5. Apply held gate penalties |-- from non-stopping fails
                  +------------------------------+
                       |
                       v
                  +------------------------------+
                  | 6. Adjustments               |-- penalties, bonuses, floors/caps
                  +------------------------------+
                       |
                       v
                  +------------------------------+
                  | 7. Verdict band lookup       |-- final categorical verdict
                  +------------------------------+
                       |
                       v
       +------------------------------------------------+
       | Emit result record --> persistence sink (4.3)  |
       | stamped with source_app_id, config_version     |
       +------------------------------------------------+
                       |
                       v
       =========== engine evaluation complete ===========
       Only here may a consuming application invoke an LLM,
       and only on survivors (principle 2.6).
```

### 4.1 Phase details

**Phases 1–3: Gates by tier (RAW, DERIVED, COMPUTED).** Within a tier, gates run in `evaluation_order`. A `stop_if_fail = true` gate that fails halts the candidate immediately and records the decision. A `stop_if_fail = false` gate that fails records the decision, holds any `score_penalty`, and the candidate continues. Gates are pure functions of inputs — no gate depends on another gate's result, only on the candidate's named values.

**Adapter callback for COMPUTED inputs.** Between Phase 2 and Phase 3, the engine calls back into the adapter with the surviving candidate set, asking it to populate any COMPUTED named values referenced by remaining active rules (Phase-3 gates, scoring criteria, adjustments). The adapter computes only for survivors — never for the full input stream.

**Phase 4: Scoring.** Each active scoring criterion produces a value in `[0, 100]`, multiplied by its junction weight. The weighted sum is the raw score. Weights across a strategy's active scoring criteria must sum to 1.0; the loader rejects any strategy that does not.

**Phase 5: Held gate penalties.** Penalties accumulated from non-stopping gate failures (Phases 1–3) are subtracted from the raw score.

**Phase 6: Adjustments.** Each adjustment evaluates its condition in `evaluation_order`; if triggered, it adds, subtracts, floors, or caps. The score is clamped to `[0, 100]` after each adjustment, not just at the end. Adjustments that force a floor/cap (e.g. "if stop level breached, force score below the F band") are how categorical hard-floor behaviour is expressed within a scoring model.

**Phase 7: Verdict band lookup.** The final score is mapped to a verdict via the strategy's bands.

### 4.2 Result record

For each candidate, the pipeline produces a result record. It is the engine's complete output and the input to persistence (§4.3). It contains:

- candidate id and `candidate_type`
- `source_app_id` and `strategy_id` evaluated against
- terminal phase (where the candidate exited — halted at gate X, or completed through verdict)
- per-gate results: rule id, phase, tier, `evaluation_order`, the value(s) evaluated, the parameters evaluated against, pass/fail, `stop_if_fail`, whether this decision was actually terminal, any held penalty, a decision reason string
- per-criterion scoring breakdown: rule id, raw value, junction weight, weighted contribution
- raw score (after Phase 4)
- held gate penalties applied (Phase 5)
- per-adjustment results: rule id, amount, condition triggered, score before/after, decision reason
- final adjusted score
- verdict
- engine metadata: config version hash, engine version, run timestamp

> **Full per-rule trace is mandatory.** Without it the engine is unauditable against the tables, and the premise — that the tables are the source of truth and the engine merely runs them — becomes unverifiable. The trace is part of the result record's required shape, and every decision in it (including non-stopping and zero-penalty failures) is persisted.

### 4.3 Persistence — the bronze contract and the sink

The engine **owns the shape** of what gets persisted and **drives the write**, but does not own the **write mechanics**. This split is what lets many applications share one bronze zone while keeping the engine portable.

**The engine owns the bronze record contract.** The engine defines the canonical persisted shape, stamps provenance (`source_app_id`, `config_version`, `evaluated_at`) onto every record, and builds two record streams per run:

1. **Candidate snapshots** — one per candidate, every run, perpetually. Carries the full named-value set and the result-record summary. This is what allows a candidate to be re-evaluated later against changed rules (and is why non-stopping gate failures are retained — see §3.6).
2. **Evaluation decisions** — one per rule evaluation. Carries the FK to its candidate snapshot, the FK to the rule, the phase, `evaluation_order`, the value evaluated, the parameters evaluated against, pass/fail, `stop_if_fail`, whether it was terminal, any score contribution/penalty, and the decision reason.

Because every application that runs the engine emits the **identical** bronze shape, a single shared bronze zone holds the evaluation history of OTA, FFL, STK, … discriminated by `source_app_id` — queryable per-app or across apps.

**A pluggable sink owns the write mechanics.** The engine depends on a sink **interface**, never on a database. At startup the consuming application injects a concrete sink:

```
sink.write_snapshots(records: list[CandidateSnapshot]) -> None
sink.write_decisions(records: list[EvaluationDecision]) -> None
```

The default OTA sink writes to Azure SQL using the Phase-1 schema below. A test harness injects an in-memory sink. A future application points its sink at the **same** shared bronze zone — which is precisely what makes cross-application analysis physically possible (a hardcoded per-app write would fragment the bronze zone and defeat the goal).

**Phase-1 storage schema (hybrid OLTP + schema-on-read).** Relational core columns for everything queried in a WHERE/JOIN/GROUP BY; a versioned JSON payload for the rest. The golden rule: if a field appears in a filter, it is promoted to a typed column; otherwise it lives in `payload_json`.

```sql
candidate_snapshots (
  snapshot_id      bigint primary key,
  source_app_id    varchar(8)   not null,   -- OTA | FFL | STK
  candidate_type   varchar(50)  not null,   -- options_trade | position | directional | ...
  symbol           varchar(16),
  strategy_id      varchar(50)  not null,
  evaluated_at     datetime2    not null,
  config_version   varchar(64)  not null,
  final_score      decimal(6,2),            -- null if halted before scoring
  verdict          varchar(32),             -- null if halted before verdict
  terminal_phase   varchar(32)  not null,
  payload_version  int          not null,
  payload_json     nvarchar(max)            -- full named-value set + result-record summary
)

evaluation_decisions (
  decision_id        bigint primary key,
  snapshot_id        bigint       not null,  -- FK -> candidate_snapshots
  source_app_id      varchar(8)   not null,
  rule_id            varchar(50)  not null,  -- FK -> rules table
  phase              varchar(32)  not null,  -- gate | scoring | adjustment | verdict
  tier               varchar(16),            -- RAW | DERIVED | COMPUTED (gates)
  evaluation_order   int          not null,
  passed             bit          not null,
  stop_if_fail       bit          not null,
  was_terminal       bit          not null,
  score_contribution decimal(6,2),           -- weighted contribution / penalty / adjustment
  evaluated_at       datetime2    not null,
  payload_version    int          not null,
  payload_json       nvarchar(max)           -- value evaluated, params, decision reason, formula trace
)
```

This is the write path (bronze, OLTP). The read path — typed projection views, then a Databricks bronze/silver/gold expansion of `payload_json` into analytics tables — is **out of scope for the engine** and lives in `architecture-plan.md`. `payload_version` is resolved in the context of `candidate_type` (snapshots) and `phase` (decisions), since each table holds multiple payload shapes.

## 5. The input adapter contract

The engine receives candidates from a consumer-specific **input adapter**. The adapter is the only place domain knowledge lives on the input side of the engine.

The adapter is responsible for:

- fetching raw data from whatever source the consumer uses (Schwab API, fantasy stats API, anything)
- computing DERIVED values from raw data
- producing **COMPUTED** values **on demand** — the engine calls back into the adapter between DERIVED and COMPUTED gating with the surviving candidate set; the adapter populates the requested COMPUTED named values only for those candidates
- delivering candidates to the engine with named values populated to the requested tier
- declaring the **input catalog** — the names, tiers, types, and null semantics of every value it produces

The adapter does not run rules. The adapter does not assign scores. The adapter does not know about strategies, junctions, or verdict bands.

The engine does not fetch domain data. The engine does not compute domain values. The engine does not know the meaning of any named value.

This boundary is enforced architecturally. Engine code that references a domain name is a defect.

### 5.1 The input catalog

The adapter publishes a catalog of every named value it produces: name, tier, type, null semantics, and producer reference (which adapter method produces it — for diagnostics, not for engine routing).

The engine validates at startup that every named value referenced by an active rule is present in the catalog with a compatible type. References to absent names fail loudly at startup, never silently at evaluation.

### 5.2 COMPUTED callback contract

The engine drives COMPUTED population by callback rather than asking the adapter to precompute all tiers up front:

- The OTA Black-Scholes probability matrix is heavy enough that running it on every candidate before DERIVED gates have eliminated most is wasteful — which is exactly why the current code computes it selectively.
- The adapter knows *how* to compute a COMPUTED value but not *which* candidates need it (that depends on which gates the strategy bound). The engine knows the survivor set. The callback puts each responsibility where it belongs.

```
adapter.populate_computed(candidates: list[Candidate], needed: set[str]) -> list[Candidate]
```

The engine passes the survivor set and the names of COMPUTED values any remaining active rule will need. The adapter returns candidates with those fields populated.

## 6. Configuration: the runtime tables

The engine constructs strategies and their rule bindings at runtime from three tables. These tables **are the source of truth**. The spreadsheet seeds them once during the build; thereafter the application's strategy-administration UI maintains them.

### 6.1 Three-table model

**1. Rules table.** One row per rule. Columns: `rule_id`, `phase`, `tier`, `condition_expression`, `referenced_named_values` (list), `parameter_schema` (parameter names with types/bounds), `intent` (why the rule exists). Independent of any strategy.

**2. Strategies table.** One row per strategy. Columns: `strategy_id`, `label`, `verdict_band_set`, `scan_parameters`, `description`. Independent of any rule.

**3. Junction table (strategy × rule).** One row per (strategy, rule) the strategy uses. Columns: `strategy_id`, `rule_id`, `enabled`, `evaluation_order`, `stop_if_fail`, `score_penalty`, parameter values (one per parameter in the rule's schema), `weight` (scoring criteria only), `rationale`. The only place a strategy's configuration for a rule exists.

### 6.2 Build-time seed vs. runtime source of truth

`Scoring Parameters.xlsx` is a one-time seed. A seed importer reads the workbook and populates the three tables. After the import, the workbook is historical; edits happen in the tables, surfaced through the strategy-administration UI (per the strategy-page mockup from prior design work). The engine never reads the workbook at runtime — it reads the tables.

This is a change from earlier framing where "the sheet is the source of truth." The sheet was always going to be a poor runtime source (no concurrency, no audit, no UI). The tables are the durable home; the sheet bootstraps them.

### 6.3 Expression library

Condition expressions are drawn from a closed set the engine understands:

- comparison: `>=`, `<=`, `>`, `<`, `==`, `!=`
- set membership: `IN`, `NOT IN`
- range: `BETWEEN` (sugar for two atomic comparisons — engine decomposes at load)
- null semantics: `IS NOT NULL`, `IS NULL`
- enum match: `EQUALS_ENUM`
- named formula reference: `formula:<name>` — the engine looks up `<name>` in the registered rule library and calls the implementation with the candidate's named values and the rule's bound parameters

Rules needing more than one comparison are expressed as multiple rules. The atomicity principle (§2.3) prevents the expression library from growing AND/OR/NOT operators.

### 6.4 Grouping is not an engine concept

Source material groups rules into "Universal Pre-Filter," "Per-Strategy," "Trade Type," and similar buckets. These are content-organisation aids for humans (and a natural axis for `business-rules.md`, see §9). The engine does not see them. To the engine, every rule is either bound to a strategy via a junction row or it is not. "Universal" means "every strategy has a junction row for this rule" — a fact about the junction, not a property of the rule. There is no engine path that applies a rule to all strategies regardless of the junction.

### 6.5 Reload behavior

Restart-only initially. The startup validation set (§6.6) is comprehensive enough that hot-reload would need to repeat all of it transactionally, and the operational need is not present. When the strategy-administration UI writes table changes, they take effect on the next engine start. Hot-reload is added if and when operational pressure demands it.

### 6.6 Startup validation

The loader rejects the configuration with a loud, structured error report if any of the following hold:

- a rule references a named value not in the input catalog
- a junction row references a rule_id or strategy_id that does not exist
- a junction row does not supply every parameter in the rule's schema
- a gate junction row omits `evaluation_order` or `stop_if_fail`
- a strategy's active scoring criteria do not have junction weights summing to 1.0 (within a documented tolerance)
- a verdict band set is not monotonic
- a condition expression references a named formula not in the registered rule library
- a junction parameter value violates the rule's parameter type or bound
- a named value referenced by a rule has null semantics incompatible with the rule's needs

These are not advisory warnings. The engine refuses to evaluate any strategy until the configuration loads cleanly. This is what makes "the tables are the source of truth" enforceable rather than aspirational.

## 7. Extensibility

### 7.1 Adding a new rule

1. Add a row to the rules table (phase, tier, condition expression, parameter schema, referenced named values, intent).
2. If the expression uses `formula:<name>`, implement the formula in the rule library.
3. Add a junction row for every strategy that should use the rule (order, stop behaviour, penalty, parameters, weight, rationale).

No engine code change.

### 7.2 Adding a new strategy

1. Add a row to the strategies table.
2. Add junction rows for every rule the strategy uses.

No engine code change.

### 7.3 Adding a new consumer (application or evaluation surface)

1. Build an input adapter implementing the §5 contract.
2. Build a rule library — formula implementations operating on the new domain's named values.
3. Populate the tables for the new domain's rules and strategies.
4. Inject a persistence sink (typically pointed at the shared bronze zone, with the new `source_app_id`).
5. Run the engine.

No engine code change.

## 8. Boundaries

The engine is **not** responsible for:

- fetching market data or any domain data (the adapter does this)
- computing Greeks, IV rank, ATR, SMAs, or any domain value (the adapter does this)
- deciding what a candidate "is" (the adapter produces candidates from raw sources)
- presenting results (the consumer's UI renders the result record)
- executing trades or any consumer-side action (the engine produces verdicts; downstream code acts)
- calling an LLM (the engine is deterministic; LLM use is downstream consumer orchestration, and only on survivors — principle 2.6)
- the persistence **sink's mechanics** — connection, credentials, transactions, retry, the physical store

The engine **is** responsible for:

- loading and validating the configuration tables (§6.6)
- validating that the input adapter provides every named value referenced by active rules (§5.1)
- running the pipeline deterministically in the documented phase order, honoring per-strategy `evaluation_order` (§4)
- honoring the tier system (no COMPUTED for already-halted candidates)
- calling the adapter back for COMPUTED population between Phase 2 and Phase 3 (§5.2)
- producing the result record per candidate, including the mandatory full per-rule trace (§4.2)
- **owning the bronze record contract**: defining the persisted shape, stamping `source_app_id` / `config_version` / timestamps, and driving the injected sink to write candidate snapshots and evaluation decisions (§4.3)
- enforcing the foundational principles at load and at evaluation (§2)

## 9. Relationship to other documents

| Document | Owns |
|---|---|
| `insight_engine.md` (this file) | How the engine operates. Mechanism only. |
| Rules / Strategies / Junction tables | The runtime configuration. Source of truth for all rule content. |
| `Scoring Parameters.xlsx` | Build-time seed for the tables. Historical after import. |
| `business-rules.md` | The options consumer's content: input definitions and the **rule catalog**, grouped by common rule type. Does **not** document strategies. |
| `architecture-plan.md` | Where the engine, adapters, and sink live in the deployed system; the read-path analytics (Databricks bronze/silver/gold); the LLM-orchestration contract (which model, how few calls). |

### 9.1 What `business-rules.md` documents

`business-rules.md` is the human-readable rule catalog for the options consumer, grouped by common rule type (e.g. earnings rules, liquidity rules, cushion rules, probability rules). For each rule it records:

- **intent** — why the rule exists in plain language (e.g. "never enter a trade within 7 days of earnings because of theta acceleration")
- **logical evaluation formula** — the condition in precise terms (e.g. `earnings_date - today() > 7`)
- **required inputs** — the named values the rule needs from the adapter
- **expected output** — what the engine does with the result (pass/fail gate, score contribution, adjustment)

It also documents **input definitions** — how the options adapter populates each named value (data source, tier, type, null semantics) — the prose companion to the §5.1 input catalog.

### 9.2 What `business-rules.md` does NOT document

Strategies are **not** documented in `business-rules.md`. A strategy is self-documenting in the Strategies table (its description, verdict bands, scan parameters) and the junction (its per-rule rationale). If a strategy ever needs visuals or long-form explanation beyond what the tables hold, `business-rules.md` (or the strategy record) carries a **pointer** to an unstructured document — never the strategy content inline. This keeps strategy definitions in data, consistent with principle 2.1.

The hand-off between this file and `business-rules.md` is the input adapter contract (§5) and the table schema (§6.1). If you can read either document and answer "how does the engine evaluate candidates" without reading the other, the boundary is correct.

## 10. Open architectural decisions

- **Concurrent evaluation.** Single-threaded per scan in v1. Rule library functions are required to be pure (no shared state), keeping the door open for parallel evaluation later. Deferred until performance pressure justifies the complexity; the purity contract is a forward commitment.
- **Rule id scope (global vs app-scoped).** §3.3 states the intent — globally unique rule ids so a rule can be shared across OTA and STK. The exact DDL (one global rules table vs. per-app, how shared rules are versioned when one app needs a tweak the other doesn't) is settled during the build, not here.

Resolved (in the body):

- ~~Source of truth~~ — runtime tables; sheet is build-time seed; §2.1, §6.2.
- ~~Hard vs soft gate categories~~ — collapsed into the gate phase plus `stop_if_fail` and `score_penalty` junction fields; §3.6.
- ~~Within-phase ordering~~ — per-strategy `evaluation_order` in the junction; §3.6, §4.
- ~~LLM precedence~~ — full deterministic evaluation precedes any LLM call; principle 2.6.
- ~~Persistence ownership~~ — engine owns the bronze contract and stamps `source_app_id`; injected sink writes to a shared bronze zone; §4.3, §8.
- ~~COMPUTED triggering~~ — engine callback between DERIVED and COMPUTED; §5.2.
- ~~Reload behavior~~ — restart-only; §6.5.
- ~~Diagnostics~~ — full per-rule trace required and persisted; §4.2.
- ~~Verdict bands universality~~ — per-strategy; §3.8.
- ~~DirectionalEngine / health grade disposition~~ — additional engine consumers, not separate paths; §1.
- ~~Naming collision~~ — new framework is the **Insight Engine**; existing `app/agents/insight_engine.py` renamed **Insight Communicator**.

## 11. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-20 | Initial framework draft. Pending audit results. | Don + Claude |
| 2026-05-21 | v2. Junction model formalised. Adapter callback for COMPUTED. Startup validation. Principles annotated with enforcement. | Don + Claude |
| 2026-05-21 | v2.1. All evaluation flows through the engine; health grading and directional comparison as additional consumers. Candidate definition broadened. | Don + Claude |
| 2026-05-21 | v2.2. Naming resolved (Insight Engine vs. Insight Communicator). Health-grade decomposition captured in plan. | Don + Claude |
| 2026-05-21 | v3. Runtime tables are source of truth; sheet is build-time seed (2.1, 6.2). Gate categories collapsed into stop_if_fail + score_penalty + evaluation_order in the junction (3.4, 3.6). LLM-precedence principle added (2.6). Persistence contract added: engine owns bronze shape and stamps source_app_id; injected sink writes to a shared bronze zone; two-table Phase-1 schema (4.3). business-rules.md restructured to a rule catalog grouped by type; strategies not documented there (9). | Don + Claude |