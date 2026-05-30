--  -
allowedTools:
  - Bash
  - Read
  - Glob
  - Grep
---

# Insights Engine Audit — 2026-05-20

## Purpose

Read-only audit of every formula, threshold, weight, and gate in the screening and scoring pipeline. Compare against the canonical rule catalog from `requirements/Scoring Parameters.xlsx` (embedded below). Produce a single audit report at `requirements/insights-engine-audit-2026-05-20.md` that we will use to drive the **Insights Engine** architecture work.

**The Insights Engine is a generic evaluation framework, not a trading-specific module.** Options trading is its first consumer. The engine takes a stream of candidates plus a rule set and runs them through a pipeline (gates → scoring → adjustments → verdicts). The engine has no built-in knowledge of options, deltas, IV rank, or any other domain concept — those live in rules and in an input adapter. A "strategy" is a runtime-bound bundle of rules and parameters, not a code branch.

**This is read-only.** No code edits. No commits. No file changes anywhere except writing the audit report.

## Foundational principles being audited

The audit evaluates the codebase against five foundational principles. Every finding in the report ties back to one or more of these.

1. **Sheet is source of truth.** Every rule, threshold, weight, and structural constraint in the engine should derive from `requirements/Scoring Parameters.xlsx`. Hardcoded values in code are findings.
2. **Strategy independence.** SP, WG, TR, and LT are fully independent rule bundles. A strategy's logic must not name another strategy, share mutable state with another strategy, inherit config from another strategy, or fall through to another strategy's defaults. Each strategy is audited on its own merits — never as "follows SP" or "diverges from TR."
3. **Atomic rules.** Each rule evaluates exactly one condition. Compound conditions (`A AND B`, `A OR B`, nested checks) are findings to be flagged for decomposition.
4. **Pipeline order.** Hard gates → scoring formulas with weights → post-scoring adjustments → verdict bands. Any out-of-order execution, gate skipped after scoring, or score applied to a gate-failed candidate is a finding.
5. **Domain decoupling.** The Insights Engine machinery — config loaders, rule evaluators, pipeline orchestrator, verdict assignment — must contain zero references to options-trading concepts. References to `delta`, `IV_rank`, `credit`, `expiry_date`, `spot`, `ATR`, `chart_state`, etc. are legitimate only inside (a) individual rule definitions and (b) the input adapter that produces candidate records. Anywhere else, they are findings.

## Required reading

Read in this order, in full. Do not skim.

```powershell
cat claude_context/CLAUDE.md
cat claude_context/business-rules.md
cat claude_context/architecture-plan.md
```

## Phase 1 — Discover the analysis surface

Inventory every file under the analysis surface. Treat this as the universe of files Phase 2 will catalog.

```powershell
# Backend scoring + screening
ls app/analysis -Recurse -File | Select-Object FullName

# Frontend strategy configs and column maps
ls web/src/strategy-configs -Recurse -File | Select-Object FullName
ls web/src/config -Recurse -File | Select-Object FullName

# Anywhere else hard gates or scoring factors may have leaked
Get-ChildItem -Path . -Recurse -File -Include *.py,*.js,*.jsx -ErrorAction SilentlyContinue |
  Select-String -Pattern "scoring_factor|hard_gate|ACCEPT IF|REDUCE SCORE|threshold|weight_|compatible_structures" |
  Select-Object Path, LineNumber, Line |
  Format-Table -AutoSize
```

STOP. Print the discovered file list and the grep summary, then proceed.

## Phase 2 — Catalog implementation

For each file in the analysis surface, extract every numeric threshold, formula, weight, gate condition, and structural enforcement point. Record:

- **File path** (relative to repo root)
- **Line range**
- **What is being computed or enforced** (one sentence)
- **The threshold value(s) or formula expression** (verbatim from code where possible)
- **Strategy scope** — which of `SP`, `WG`, `TR`, `LT` this applies to (universal if all four)
- **Data tier** — `RAW` (direct from quote/option chain), `DERIVED` (computed from raw without Claude), `COMPUTED` (Black-Scholes or other heavier math); infer if not annotated

Use grep aggressively. Specific patterns to chase:

```powershell
# Numeric thresholds in conditionals
Select-String -Path app/analysis/*.py,app/analysis/**/*.py -Pattern "(>=|<=|>|<|==)\s*[0-9.]+|[0-9.]+\s*(>=|<=|>|<|==)" 

# Weight declarations
Select-String -Path app/analysis/*.py,app/analysis/**/*.py -Pattern "weight|WEIGHT"

# Hard gate registrations
Select-String -Path app/analysis/hard_gates/*.py -Pattern "register_gate|class.*Gate"

# Scoring factor implementations
Select-String -Path app/analysis/scoring_factors/*.py -Pattern "def evaluate|def score|return.*\*.*weight"

# Strategy definition dicts
Select-String -Path app/analysis/strategy_definitions.py -Pattern "STRATEGIES|STRATEGY_DEFINITIONS|compatible_structures|min_dte|max_dte|min_delta|max_delta|min_iv_rank"

# Frontend strategy configs
Select-String -Path web/src/strategy-configs/*.js -Pattern "min|max|default|weight|threshold|structure"
```

For each finding, record exact `file:line` (e.g. `app/analysis/strategy_scorer.py:147`) so the audit report can be navigated.

### Phase 2b — Targeted grep for engine-machinery and input-producer surface

Additional patterns specifically for Sections 5c and 5d:

```powershell
# Domain terms anywhere in code — Section 5c filters these into "engine machinery" vs "rule/adapter" findings
Get-ChildItem -Path app -Recurse -File -Include *.py |
  Select-String -Pattern "\b(delta|gamma|theta|vega|IV_rank|iv_rank|credit|debit|expiry|DTE|strike|spot|ATR|chart_state|spread_width|bid_ask|open_interest|bull_put|bear_call|bull_call|bear_put|long_call|long_put|iron_condor)\b" |
  Select-Object Path, LineNumber, Line

# Base classes and abstract interfaces — should be domain-free
Select-String -Path app/analysis/*.py,app/analysis/**/*.py -Pattern "class.*\(.*ABC|abstractmethod|class.*Base|class.*Interface"

# Pipeline orchestrator entry points — should receive opaque candidates
Select-String -Path app/analysis/*.py -Pattern "def score|def evaluate|def run_pipeline|def screen"

# Input producers — places where named inputs originate
Select-String -Path app/analysis/**/*.py -Pattern "ATR|SMA_50|SMA_200|chart_state|next_earnings|black_scholes|expected_value|theta_margin"
```

STOP after Phase 2b. Print the engine-machinery candidate sites and the input-producer sites, then proceed to Phase 3.

## Phase 3 — Cross-reference against the canonical rule catalog

The canonical catalog lives at `requirements/Scoring Parameters.xlsx`. The full content as of 2026-05-20 is embedded below as the source of truth for this audit. Treat the embedded version as authoritative even if the file on disk drifts.

### Canonical rule catalog (embedded)

**Hard Gates — Universal Pre-Filter** (applies to all four strategies)

| Rule | Type | Condition | Tier | SP | WG | TR | LT |
|---|---|---|---|---|---|---|---|
| Underlying Price Floor | Formula | `stock_price BETWEEN low AND high` | RAW | Y · 20–99999 | Y · 20–99999 | Y · 20–99999 | Y · 20–99999 |
| Days until next earnings | Formula | `(next_earnings_date − today()) BETWEEN low AND high` | DERIVED | Y · 14–9999 | Y · 14–9999 | Y · 14–9999 | Y · 14–9999 |
| Earnings buffer past expiry | Formula | `(next_earnings_date − expiry_date) BETWEEN low AND high` | DERIVED | Y · 0–9999 | Y · 0–9999 | Y · 0–9999 | Y · 7–9999 |
| Per-leg bid/ask spread | Formula | `spread BETWEEN low AND high` | DERIVED | Y · 0–0.15 | Y · 0–0.15 | Y · 0–0.15 | Y · 0–0.15 |
| Per-leg open interest floor | Formula | `min_leg_OI ≥ threshold` | RAW | Y · 100 | Y · 100 | Y · 100 | Y · 100 |
| Per-leg volume floor | Formula | `min_leg_volume ≥ threshold` | RAW | Y · 500 | Y · 500 | Y · 500 | Y · 500 |
| Maximum DTE | Formula | `DTE ≤ threshold` | RAW | Y · 60 | Y · 60 | Y · 60 | Y · 60 |
| Minimum DTE | Formula | `DTE ≥ threshold` | RAW | Y · 7 | Y · 7 | Y · 7 | Y · 7 |
| Data completeness — IV Rank | Formula | `IV_rank IS NOT NULL` | RAW | Y | Y | Y | Y |
| Data completeness — Delta | Formula | `delta IS NOT NULL` | RAW | Y | Y | Y | Y |
| Data completeness — ATR_14 | Formula | `ATR_14 IS NOT NULL` | DERIVED | Y | Y | Y | Y |

**Hard Gates — Per-Strategy Rule**

| Rule | Type | Condition | Tier | SP | WG | TR | LT |
|---|---|---|---|---|---|---|---|
| DTE Window | Formula | `DTE BETWEEN low AND high` | RAW | Y · 21–45 | Y · 14–20 | Y · 30–45 | Y · 30–60 |
| Credit % of width | Formula | `credit/spread_width BETWEEN low AND high` | DERIVED | Y · 0.30–99999 | Y · 0.30–99999 | N | N |
| Debit % of width | Formula | `debit/spread_width BETWEEN low AND high` | DERIVED | N | N | Y · 0–0.40 | N |
| Total expected value | Formula | `total_EV ≥ threshold` | COMPUTED | Y · 0 | Y · 0 | Y · 0 | Y · 0 |
| Cushion % of price | Formula | `abs(spot − short_strike)/spot ≥ threshold` | DERIVED | Y · 0.01–1 | Y · 0.015–1 | N | N |
| Cushion vs ATR | Formula | `abs(spot − short_strike)/ATR_14 ≥ threshold` | DERIVED | Y · 1–999 | Y · 1.5–999 | N | N |
| Theta load fraction | Formula | `theta_total_over_trade/debit ≤ threshold` | COMPUTED | N | N | N | Y · 0–0.5 |
| Chart state confirms direction | Formula | `chart_state ∈ {Bullish, Bearish} aligned with trade direction` | DERIVED | N | N | Y | Y |
| Spread width tier compliance | Formula | `spread_width WITHIN tier_min/tier_max from Width Configuration sheet` | DERIVED | Y · lookup | Y · lookup | Y · lookup | N |

**Hard Gates — Trade Type** (binary structure enablement)

| Structure | SP | WG | TR | LT |
|---|---|---|---|---|
| Require Credit Spread Structure | Y | Y | N | N |
| Require Directional Debit Spread | N | N | Y | N |
| BULL_PUT_CREDIT | Y | Y | N | N |
| BEAR_CALL_CREDIT | Y | Y | N | N |
| BULL_CALL_DEBIT | N | N | Y | N |
| BEAR_PUT_DEBIT | N | N | Y | N |
| LONG_CALL | N | Y | N | N |
| LONG_PUT | N | Y | N | Y |
| IRON_CONDOR | N | N | N | Y |

> **⚠ Likely divergence from `business-rules.md`.** The docs declare WG → credit-only and LT → SINGLE_LONG_CALL + SINGLE_LONG_PUT. The sheet has WG including LONG_CALL/LONG_PUT and LT including LONG_PUT + IRON_CONDOR. Flag the actual code state under both names in the audit so we can decide whether code follows docs, sheet, or neither.

**Soft Gates — Score Impact** (in the sheet, these duplicate some Post-Scoring penalties below — the sheet explicitly notes this is intentional layering)

| Rule | Condition | Tier | SP | WG | TR | LT |
|---|---|---|---|---|---|---|
| Stock Extended Against Entry | `REDUCE SCORE BY 10 IF abs(spot − SMA_50)/SMA_50 > threshold` | DERIVED | N | N | N | Y · 0.05–1 |
| Stock Extended in Trade Direction | `REDUCE SCORE BY 10 IF abs(spot − SMA_50)/SMA_50 > threshold` | DERIVED | Y · 0.05–1 | Y · 0.05–1 | N | N |

**Scoring Criteria — per-strategy weights** (each strategy's column must sum to 1.00)

| Criterion | Formula | Tier | SP | WG | TR | LT |
|---|---|---|---|---|---|---|
| Theta Margin Ratio | Black-Scholes | COMPUTED | 0.30 | — | — | — |
| Probability of Profit | Black-Scholes | COMPUTED | 0.25 | 0.25 | — | — |
| Expected Value | Black-Scholes | COMPUTED | 0.20 | 0.15 | 0.20 | — |
| Reward / Risk | Black-Scholes | DERIVED | 0.15 | — | — | — |
| IV Rank | Black-Scholes | RAW | 0.10 | — | — | — |
| Theta Gamma Ratio | **TBD** | COMPUTED | — | 0.35 | — | — |
| Credit Width % | **TBD** | DERIVED | — | 0.20 | — | — |
| Liquidity | **TBD** | DERIVED | — | 0.05 | — | — |
| SMA Alignment Score | **TBD** | DERIVED | — | — | 0.30 | — |
| Delta Quality | **TBD** | DERIVED | — | — | 0.25 | — |
| IV Percentile Cost | **TBD** | DERIVED | — | — | 0.15 | — |
| Runway Score | **TBD** | COMPUTED | — | — | 0.10 | — |
| Payout Ratio | **TBD** | DERIVED | — | — | — | 0.45 |
| Delta OTM Score | **TBD** | DERIVED | — | — | — | 0.25 |
| Bid Ask Tightness | **TBD** | DERIVED | — | — | — | 0.20 |
| Open Interest | **TBD** | RAW | — | — | — | 0.10 |

**Post-Scoring Adjustments**

| Rule | Condition | Tier | SP | WG | TR | LT |
|---|---|---|---|---|---|---|
| Stock extended in trade direction | `REDUCE BY 10 IF abs(spot − SMA_50)/SMA_50 > 0.05 AND extension matches trade direction` | DERIVED | Y | Y | Y | Y |
| SMA alignment against trade | `REDUCE BY 15 IF price positioned against trade direction across all 3 SMAs` | DERIVED | Y | Y | N | N |
| Mixed chart signal on directional strategy | `REDUCE BY 25 IF chart_state == "Mixed — No Signal"` | DERIVED | N | N | Y | Y |
| Cushion barely above ATR floor | `REDUCE BY 5 IF cushion_vs_ATR BETWEEN 1.0 AND 1.5` | DERIVED | Y | Y | N | N |
| ETF underlying | `INCREASE BY 5 IF underlying IS ETF` | RAW | Y | Y | Y | Y |

**Verdict Bands** (universal across all strategies, applied to final adjusted score)

| Verdict | Range |
|---|---|
| EXECUTE | `score ≥ 70` |
| WAIT | `50 ≤ score < 70` |
| PASS | `score < 50` |

**Strategy Scan Parameters**

| Parameter | SP | WG | TR | LT |
|---|---|---|---|---|
| Evaluation cap (max trades scored) | 2500 | 1000 | 1000 | 500 |
| DTE priority start (days) | 30 | 14 | 35 | 45 |
| DTE expansion direction | bidirectional | shortest-first | bidirectional | bidirectional |
| Output rank cap (max surfaced) | 20 | 20 | 20 | 20 |

**Width Configuration** (separate sheet, default widths by price tier — engine looks up ticker overrides first, falls back to tier table)

| Price min | Price max | Width min | Width max | Increment |
|---|---|---|---|---|
| 20 | 50 | 1 | 5 | 1 |
| 50 | 150 | 2.5 | 10 | 2.5 |
| 150 | 300 | 5 | 20 | 5 |
| 300 | 500 | 10 | 25 | 5 |
| 500 | 99999 | 25 | 50 | 5 |

## Phase 4 — Produce the audit report

Write to `requirements/rules-engine-audit-2026-05-20.md`. Use this structure exactly. No deviations.

```markdown
# Insights Engine Audit — 2026-05-20

**Generated by:** Claude Code · OTA Insights Engine audit
**Scope:** Every formula, threshold, weight, and gate in the screening and scoring pipeline, plus engine-machinery domain coupling and input-contract inventory
**Compared against:** `requirements/Scoring Parameters.xlsx` as of 2026-05-20
**Audit branch:** [git rev-parse --abbrev-ref HEAD]
**Audit commit:** [git rev-parse HEAD]

---

## Section 1 — Files inventoried

[bullet list of every file walked in Phase 2, grouped by directory]

## Section 2 — Rule-by-rule comparison

For every rule in the canonical catalog (Phase 3), one entry in this exact format:

### [Rule name]

- **Category:** Hard Gate · Universal Pre-Filter / Hard Gate · Per-Strategy / Hard Gate · Trade Type / Soft Gate / Scoring Criterion / Post-Scoring Adjustment / Strategy Scan Parameter / Width Configuration
- **Canonical (sheet):** [per-strategy thresholds and tier from the table above]
- **Implementation status:** IMPLEMENTED · PARTIAL · MISSING · DIVERGENT
- **Code location(s):** [file:line for each occurrence, or "—" if MISSING]
- **Code values found:** [verbatim threshold(s) / weight(s) / formula(s) extracted from code, per strategy]
- **Divergences:** [explicit description of any drift between sheet and code, or "None"]
- **Notes:** [anything that needs human judgment — e.g. "TBD formula", "value hardcoded as literal rather than read from config", "appears in two places with different values"]

## Section 3 — Code rules NOT in the canonical catalog

Anything implemented in the code that has no corresponding row in the spreadsheet. For each:

- **What it does:** [one sentence]
- **Code location:** file:line
- **Recommendation:** [keep and add to sheet · remove · clarify with Don]

## Section 4 — TBD scoring formulas (sheet has weight, code has no formula)

The sheet allocates non-zero weights to 12 scoring criteria whose formulas are marked TBD. Per criterion:

- **Criterion name:** [as in sheet]
- **Strategy(ies) using it:** [SP/WG/TR/LT]
- **Weight(s):** [per strategy]
- **Code status:** any placeholder, no-op, or referenced-but-undefined location found in the codebase
- **Inputs available:** what RAW/DERIVED inputs the engine currently has on hand to feed this formula (helps scope the formula spec work)

## Section 5a — Strategy independence violations

**Principle:** Each strategy is a fully independent rule bundle. A strategy's logic must not reference, depend on, or be defined in terms of any other strategy. SP is blind to WG; LT is blind to TR.

For each finding:

- **What kind of coupling:** one of —
  - **Named reference** — strategy A's code path explicitly names strategy B (`if strategy == "WEEKLY_GRIND"` inside SP logic, shared `elif` chains, etc.)
  - **Shared mutable state** — strategies write to or depend on the same dict/object/global that any one of them can mutate
  - **Fall-through default** — strategy resolution that lands on another strategy's behavior when no explicit match
  - **Inherited config** — strategy A's parameters defined as `STRATEGY_B_DEFAULTS + overrides` instead of standalone
  - **Family-grouped logic** — `if strategy in CREDIT_STRATEGIES` or `if structure in DEBIT_STRUCTURES` style grouping that bundles strategies together
  - **Strategy-as-type** — strategy identity drives a code branch (`if/elif/else` on strategy name) rather than a config lookup
- **Code location:** file:line
- **What it does:** one sentence
- **Why it violates independence:** one sentence
- **Per-strategy audit** of compatible structures, DTE ranges, and any other parameter where the sheet declares a per-strategy value — for each strategy SP/WG/TR/LT separately, what does the code actually do at runtime, regardless of what other strategies do

Also catalog:

- **Dual-dict / dual-source issues** (OTA-513 family): any place a strategy's config can be sourced from more than one location; record which one wins at runtime
- **Verdict bands location:** universal at one place, per-strategy at another, or both — record what's actually wired
- **Multi-earnings-rule status:** the sheet has two earnings rules per strategy (Days until next earnings + Earnings buffer past expiry). For each strategy independently, what earnings logic does the code actually run?

## Section 5b — Compound-rule violations (atomic rules principle)

**Principle:** Rules are atomic. A single rule evaluates a single condition. Compound rules (`A AND B`, `A OR B`, `if A then check B`) get split into multiple atomic rules in the engine.

Catalog every compound condition found in either code or the canonical sheet:

- **Location:** `file:line` for code; `sheet row N` for the spreadsheet
- **The compound expression:** verbatim
- **Decomposition proposal:** what atomic rules this should become
- **Notes:** any case where decomposition would change behavior (e.g. an OR that becomes two rules both of which must fail vs. an OR that becomes two rules either of which must pass — flag the semantic carefully)

Pre-loaded suspects to investigate:

- Sheet rule "Chart state confirms direction" — embeds `chart_state IN {set}` AND `matches trade direction`. Two atomic rules.
- Sheet rule "Stock extended in trade direction" post-scoring — embeds `abs(spot − SMA_50)/SMA_50 > 0.05` AND `extension matches trade direction`. Two atomic rules.
- Sheet rule "Cushion barely above ATR floor" — uses a BETWEEN that is actually two atomic rules (`cushion_vs_ATR ≥ 1.0` AND `cushion_vs_ATR ≤ 1.5`).
- Any code function whose return value depends on more than one threshold check — likely a compound that needs splitting.
- Any code path that short-circuits one check on the result of another (`if min_oi_passes: check spread_tightness`) — that ordering may be implementation detail OR may be a hidden compound; record which.

Note: BETWEEN expressions in the sheet (`X BETWEEN low AND high`) are conventionally two atomic rules (`X ≥ low` AND `X ≤ high`). Flag them as compound but do not treat decomposition as urgent — the engine can support BETWEEN as syntactic sugar over two atomic checks if we choose. Decision is architectural, not auditable.

## Section 5c — Domain coupling in engine machinery (domain decoupling principle)

**Principle:** The Insights Engine machinery — config loaders, rule evaluators, pipeline orchestrator, verdict assignment, and any other "framework" code — must contain zero references to options-trading domain concepts. References to `delta`, `IV_rank`, `credit`, `debit`, `expiry_date`, `DTE`, `spot`, `strike`, `ATR`, `chart_state`, `theta`, `gamma`, `vega`, `spread_width`, `bid`, `ask`, `OI`, `volume`, `iron_condor`, `bull_put_credit`, etc. are legitimate only inside:
- **(a) Individual rule definitions** — a rule named "Credit % of width" can reference `credit` and `spread_width`; that's its job.
- **(b) The input adapter** — the layer that produces candidate records from option chain data.

Anywhere else — in loaders, evaluators, pipeline orchestrators, scorers, verdict assigners, base classes, abstract interfaces, error-message strings, log statements — those references are findings.

For each finding:

- **Code location:** file:line
- **The domain term(s) referenced:** verbatim
- **Why it's in engine machinery vs. a rule or adapter:** one sentence
- **Extraction proposal:** where this knowledge belongs (in a specific rule, in the input adapter, in a domain-specific subclass, etc.)

Specific hot spots to investigate:

- Base classes for `Gate`, `ScoringFactor`, `Strategy` — do they reference any options concepts in method names, attribute names, type hints, or docstrings?
- The pipeline orchestrator / scorer entry point — does it know what it's scoring, or does it receive an opaque candidate?
- Error messages and log statements — do they say "no candidates passed the credit-spread filter" (domain-coupled) or "no candidates passed gate X" (decoupled)?
- The `Verdict` / band assignment code — universal score → grade should be domain-free. Any options vocabulary there is a finding.
- Config loader — should read rules and parameters without knowing what any of them mean.

## Section 5d — Input contract catalog

**Purpose:** Catalog every named input value that rules reference, and where each is produced. This is the contract the input adapter will need to fulfill — and the surface that proves whether the engine is actually domain-decoupled or just hides its coupling.

For each named input referenced anywhere in code (gates, scoring factors, adjustments) or in the canonical sheet:

- **Input name:** as referenced in rules (e.g. `stock_price`, `delta`, `ATR_14`, `chart_state`, `next_earnings_date`)
- **Tier:** RAW (direct from market data API) / DERIVED (computed from raw without Claude) / COMPUTED (Black-Scholes or other heavier math)
- **Producer location:** file:line where this value is computed or fetched
- **Consumed by:** list of rules / gates / scoring factors that reference this input
- **Producer-consumer coupling:** flag if the producer and consumer live in the same module (smell — they should be separated by the engine boundary)
- **Type:** scalar / enum / date / null-allowed — anything the adapter contract needs to know
- **Source:** market data API, derived calculation, user input, config, hardcoded

Group the catalog by tier (RAW first, then DERIVED, then COMPUTED). At the end, list any input referenced by the sheet but NOT produced anywhere in code — those are gaps the input adapter will need to fill before the corresponding rules can run.

## Section 6 — Summary scorecard

| Category | Total rules in sheet | Implemented | Partial | Missing | Divergent |
|---|---|---|---|---|---|
| Hard Gates · Universal Pre-Filter | 11 | | | | |
| Hard Gates · Per-Strategy | 9 | | | | |
| Hard Gates · Trade Type | 9 | | | | |
| Soft Gates · Score Impact | 2 | | | | |
| Scoring Criteria | 16 (12 TBD) | | | | |
| Post-Scoring Adjustments | 5 | | | | |
| Verdict Bands | 1 (3 thresholds) | | | | |
| Strategy Scan Parameters | 4 | | | | |
| Width Configuration | 5 tiers | | | | |

| Additional findings | Count |
|---|---|
| Strategy independence violations (5a) | |
| Compound-rule violations in code (5b) | |
| Compound-rule violations in sheet (5b) | |
| Domain-coupled engine-machinery sites (5c) | |
| Distinct named inputs in catalog (5d) | |
| Inputs referenced in rules but not produced anywhere (5d) | |
| Code rules not in canonical catalog | |
| TBD scoring formulas | |

## Section 7 — Audit notes

Free-form observations to feed the architecture discussion. Specifically:

- Where rules are coupled to strategies (hardcoded `if strategy == "STEADY_PAYCHECK"` etc.) versus declarative
- Where thresholds are literals in code versus pulled from a config file or dict
- Whether the pipeline currently enforces the documented order (gates → scoring → adjustments → verdict)
- Any rule whose tier classification (RAW/DERIVED/COMPUTED) is ambiguous from code
- Notable code smells, dead code paths, or commented-out rules that suggest churn
```

## Phase 5 — Verify and stop

After writing the report:

1. `cat requirements/insights-engine-audit-2026-05-20.md | wc -l` — confirm it's substantial (expect ≥ 600 lines for a complete audit with all eight sections)
2. Spot-check Section 2 by picking three random rules and confirming the file:line references resolve
3. Confirm Section 5a has a per-strategy audit (SP, WG, TR, LT each get their own subsection — no implicit grouping)
4. Confirm Section 5b lists at least the four pre-loaded compound-rule suspects from the sheet
5. Confirm Section 5c distinguishes domain references in engine machinery (findings) from domain references in rules and adapter (legitimate)
6. Confirm Section 5d catalogs inputs grouped by tier, with the "referenced but not produced" gap list at the end
7. Print the Section 6 summary scorecard to stdout
8. STOP. Do not commit. Do not modify any code file. Do not modify the spreadsheet. Don will review the report and commit it himself if he wants it in version control.

## Out of scope

Do not modify, refactor, or "clean up" any of the code you find. Do not propose fixes inline in the report — fix recommendations belong in the next session once Don and Claude Web review this audit together. The architecture discussion happens AFTER this audit lands.
