# OTA-833 — Seed three directional objective strategies with gates and verdict bands

> **Ticket:** OTA-833 (Story under Epic OTA-679; labels `IE-Completion`, `directional`,
> `options-domain`). Supersedes the orphan directional definition from OTA-754, which sits
> at Production Deployed in error (its `config.py` never landed in the seeded DB). OTA-754's
> status correction is a separate Don-gated transition.
>
> **v3 (post second Phase 0 NO-GO):** the gate spec is corrected for engine atomicity —
> data-completeness and liquidity are decomposed into atomic single-value rules (the engine
> reads one named value + one param per rule). Earnings and negative-EV remain formula-backed
> (OTA-837). See **Relevant Context → engine atomicity** and the rewritten gate section.

## Terminal context
- This terminal: **Terminal A (single)**
- Concurrent terminals: **none** — `scripts/seed_engine_config.py` is a shared seed file;
  never parallelize any other seed-touching work against this run.
- Cross-terminal dependencies: both prerequisite code stories have **landed** —
  **OTA-834** (directional adapter inputs + the four `dir_*` scoring formulas) and
  **OTA-837** (the two directional gate formulas `dir_earnings` / `dir_negative_ev`).

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
```

Then inspect (read-only, Phase 0) the live code this prompt supersedes and mirrors:

```
cat scripts/seed_engine_config.py
cat app/ota_adapters/directional/config.py
cat app/options_rules/directional/__init__.py
cat app/options_rules/directional/scoring_formulas.py
cat app/options_rules/directional/gate_formulas.py
cat app/insight_engine/expressions.py
cat app/ota_adapters/position_health/config.py
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: insight_engine.md §2.1 (tables are the source of truth)**
All rules, thresholds, weights, gate behaviour, ordering, and verdict bands live in the
seeded config tables. The engine hardcodes no rule content. No `if strategy_key == X`
branching anywhere.

**Source: live Phase 0 discovery — engine atomicity (the v2 NO-GO root cause)**
The runtime evaluator reads **exactly one named value as LHS and one param as RHS per rule**
(`expressions.py:180` `_get_lhs` → `named_values[referenced_named_values[0]]`;
`expressions.py:187` `_get_rhs` → first param only). Confirmed precedent in
`app/ota_adapters/position_health/config.py`: one IS NOT NULL gate per field; boolean checks
via `==` + `{expected: ...}`; membership via `IN` + `{allowed_values: [...]}`. Consequence:
a gate that needs to check multiple fields or carry multiple thresholds must be **multiple
atomic rules**, exactly as SCREENING splits liquidity into
`per_leg_bid_ask_spread` / `per_leg_open_interest_floor` / `per_leg_volume_floor`.

**Source: insight_engine.md §3.4 (junction) + §3.6 (gate mechanics)**
Junction row carries `enabled`, `evaluation_order`, `stop_if_fail`, `score_penalty`, param
values, `weight` (scoring only). `stop_if_fail` true = halt; false = record-and-continue;
`score_penalty` 0 = record-only. Same rule can be hard stop for one strategy, record-only for
another — set entirely in the junction. A missing required junction field is a startup
validation failure.

**Source: OTA-837 (directional gate formulas — shipped)**
Earnings and negative-EV are **formula-backed** bool gates registered via the `gate_formula`
decorator; their seed rows carry `formula_ref` (NO `condition_expression`), like screening's
`earnings_routeN`. Failure consequence is junction-driven.
- `dir_earnings(named_values, params) -> bool` — reads `next_earnings_date`, `expiration`,
  `params["buffer_days"]`. False only when `next_earnings_date` is known and
  `<= expiration + buffer_days`; null `next_earnings_date` → True (fail-open). **Param: `buffer_days`.**
- `dir_negative_ev(named_values, params) -> bool` — reads `ev_raw` else `total_ev`; False only
  when resolved EV `< params.get("threshold", 0.0)`; both null → True. **Param: `threshold`.**

**Source: insight_engine.md §4 (Phase 4 scoring)**
Active scoring-criterion weights for a strategy must sum to 1.0 (loader rejects otherwise).
Each criterion returns [0,100]; registry hard-enforces the range.

**Source: insight_engine.md §3.8 (verdict bands per-strategy)**
Bands are per-strategy. Each of the three strategies gets its own band set. Mirror the live
SCREENING band shape (Phase 0 confirms it — expected `{min_score, max_score}`), NOT the
orphan `directional_verdicts` label-only shape. (OTA-835 will deduplicate band-threshold
storage across screening AND these new directional sets; do not pre-optimize here — mirror
screening as-is.)

**Source: live Phase 0 discovery (directional surface)**
- Directional exists ONLY as orphan row-dicts in `app/ota_adapters/directional/config.py`
  (OTA-754); not imported by the seed or any test. First-time wiring.
- SHARED `null_semantics` lookup (FAIL_OPEN / FAIL_CLOSED / SKIP) is already seeded — reused,
  not redefined.
- Scoring formulas registered: `dir_probability`, `dir_buffer`, `dir_budget_fit`,
  `dir_defined_risk`, plus OTA-834's four. `dir_probability` / `dir_buffer` are KEPT;
  `dir_budget_fit` / `dir_defined_risk` are bound by no strategy.
- Direction literals are lowercase `bullish` / `bearish`. Do NOT use BULL/BEAR.

**Source: planning session (locked spec — this Story)**
Three strategies on DIRECTIONAL; direction is a candidate attribute, not a strategy. Six
scoring factors (skew deferred). Gates: data-completeness, earnings, liquidity, budget,
negative-EV. Negative-EV hard stop on all three. Budget never rejects. Earnings hard stop for
Income only; record-only for the other two; unknown earnings flags, never kills.

## Phase 0 — Read-only discovery, hard GO/NO-GO STOP

No edits. Items 1, 2, 4, 5, 6 were already confirmed GO in the prior Phase 0 — re-verify
briefly. The new gating questions are 3a–3c. Report all, then STOP.

1. **Prereq formulas registered:** scoring (OTA-834) `dir_expected_value`, `dir_max_loss_pct`,
   `dir_reward_risk`, `dir_payoff_multiple` (+ existing `dir_probability`, `dir_buffer`);
   gates (OTA-837) `dir_earnings`, `dir_negative_ev`. Missing any → NO-GO.
2. **Prereq adapter inputs present** (OTA-834): `next_earnings_date`, `earnings_unknown`,
   `open_interest`, `volume`, `bid_ask_spread_pct`. Missing any → NO-GO.
3. **(PRIMARY) Null-semantics on a stop-gate LHS — does the evaluator honor SKIP?**
   `bid_ask_spread_pct` is null-by-design for debit spreads (adapter.py:139, SKIP). Determine
   exactly how the gate evaluation layer treats a null LHS whose named value has SKIP
   null-semantics: does the rule **skip** (candidate passes the gate) or does the comparison
   return False and a `stop_if_fail` gate **halt** the candidate? Read the evaluator and how
   `position_health` / SCREENING rely on null_semantics for conditionally-null inputs.
   - **GO** if SKIP causes the rule to be skipped (spreads pass the spread gate without halt).
   - **NO-GO / escalate** if a `stop_if_fail` rule on a SKIP-null LHS halts the candidate and
     there is no per-junction mechanism to skip-on-null — that is an engine gap to resolve
     before wiring (do NOT work around by branching on structure).
3b. **Required-non-null key list (enumerate).** Derive the data-completeness key set: the RAW
   named values consumed by the six bound scoring formulas and the earnings/liquidity/budget/
   negative-EV gates, **excluding** the conditionally-null set
   {`next_earnings_date`, `earnings_unknown`, `ev_raw`, `total_ev`, `bid_ask_spread_pct`,
   `reward_risk_ratio`} and any value a formula already null-guards internally. Report the
   exact final list and the resulting total gate count per strategy.
3c. **Verdict-band shape.** Report the live SCREENING verdict-band lookup payload shape and
   whether screening also stores bands in a per-strategy `verdict_band_set` field — so the
   three new sets mirror it exactly.
4. **Seed-row shape harvested** from the SCREENING block (strategy / engine_rule gate+scoring /
   junction / verdict-band, including screening's `formula_ref` gate-row shape and its split
   liquidity rules).
5. **Canonical-seed chain landed (OTA-832 → OTA-815):** seed imports, no NameError.
6. **Orphan present** `app/ota_adapters/directional/config.py`.

Report as a table (item / expected / found / GO|NO-GO). STOP for approval.

## Scope

Add a DIRECTIONAL block to `scripts/seed_engine_config.py` (mirroring the SCREENING block's
row shape):

### 1. Three strategies (consumer_surface = DIRECTIONAL)

| `strategy_key` | display_name | verdict band set |
|---|---|---|
| `directional_income` | Directional — Income | `directional_income_verdicts` |
| `directional_growth` | Directional — Steady Growth | `directional_growth_verdicts` |
| `directional_longshot` | Directional — Big-Bet Longshot | `directional_longshot_verdicts` |

`compatible_structures`: `bull_call`, `bear_put`, `long_call`, `long_put`. `dte_min`/`dte_max`:
None/None. Scan parameters: mirror screening defaults; note any deviation for Don.

### 2. Scoring junction rows (six criteria per strategy, weights sum to 1.00)

| order | `rule_key` | Income | Growth | Longshot |
|---|---|---|---|---|
| 1 | `dir_probability` | 0.32 | 0.18 | 0.09 |
| 2 | `dir_buffer` | 0.22 | 0.14 | 0.02 |
| 3 | `dir_expected_value` | 0.16 | 0.21 | 0.21 |
| 4 | `dir_max_loss_pct` | 0.16 | 0.12 | 0.16 |
| 5 | `dir_reward_risk` | 0.09 | 0.19 | 0.23 |
| 6 | `dir_payoff_multiple` | 0.05 | 0.16 | 0.29 |

`dir_buffer` keeps existing params (cap 10, scale 100); `dir_probability` keeps (scale 100).
The four OTA-834 formulas bind per OTA-834's declared param schema (defaults fine unless
specified). Do NOT bind `dir_budget_fit` or `dir_defined_risk`.

### 3. Gate junction rows — ATOMIC (one named value + one param per rule)

Gate evaluation order: data-completeness (per-field) first, then earnings, the three liquidity
rules, budget, negative-EV. Exact `evaluation_order` integers assigned in sequence during wiring.

**3a. Data-completeness — one IS NOT NULL gate per required RAW key** (the enumerated Phase 0
3b list). Each: generic predicate `IS NOT NULL` over a single named value; `stop_if_fail: true,
score_penalty: null`; all three strategies. Exclude the conditionally-null set (see 3b).

**3b. Earnings — `formula_ref: dir_earnings`** (no `condition_expression`). Param `buffer_days = 0`.
Income: `stop_if_fail: true`. Growth/Longshot: `stop_if_fail: false, score_penalty: 0`.

**3c. Liquidity — THREE atomic gates** (mirroring screening's split):

| `rule_key` (mirror screening naming) | predicate | params | Income | Growth | Longshot |
|---|---|---|---|---|---|
| `dir_bid_ask_spread_max` | `bid_ask_spread_pct <= max_spread_pct` (SKIP-null → spreads skip) | Income/Growth `max_spread_pct = 10.00`; Longshot `= 20.00` | stop | stop | stop |
| `dir_open_interest_floor` | `open_interest >= min_oi` | Income/Growth `min_oi = 100`; Longshot `= 50` | stop | stop | stop |
| `dir_volume_floor` | `volume >= min_volume` | Income/Growth `min_volume = 50`; Longshot `= 25` | stop | stop | stop |

The `dir_bid_ask_spread_max` rule must rely on the SKIP null-semantics confirmed in Phase 0
step 3 so debit spreads (null `bid_ask_spread_pct`) are skipped, not halted. If Phase 0 step 3
returned NO-GO, do not wire this rule — escalate.

**3d. Budget flag — generic predicate boolean is-false** over `fits_budget`. All three:
`stop_if_fail: false, score_penalty: 0` (record-only, never rejects).

**3e. Negative-EV — `formula_ref: dir_negative_ev`** (no `condition_expression`). Param
`threshold = 0.00`. All three: `stop_if_fail: true`.

New gate `engine_rules` rows are created here: the two formula-ref rows carry `formula_ref`
(no `condition_expression`); the data-completeness, liquidity, and budget rows carry the
generic predicate + the single named value confirmed in Phase 0.

### 4. Three verdict-band sets (per strategy) — SCREENING band shape

| set | EXECUTE | WAIT | PASS |
|---|---|---|---|
| `directional_income_verdicts` | 75.00–100 | 55.00–74.99 | 0–54.99 |
| `directional_growth_verdicts` | 70.00–100 | 50.00–69.99 | 0–49.99 |
| `directional_longshot_verdicts` | 62.00–100 | 45.00–61.99 | 0–44.99 |

Use the live SCREENING band shape confirmed in Phase 0 step 3c (expected `{min_score, max_score}`).
The old single `directional_verdicts` set is replaced by these three; remove it if nothing
else references it (grep first).

### 5. Retire the orphan

Delete `app/ota_adapters/directional/config.py`. Grep
(`get_strategy_row|get_rule_rows|get_junction_rows|get_all_config_rows|directional/config`)
immediately before deletion; zero external references required, else STOP.

## Acceptance criteria

- Seed runs clean (dry-run / load) with the DIRECTIONAL block present.
- Loader accepts all three strategies: each scoring-weight vector sums to 1.00; every junction
  row has all required fields; every `rule_key` / formula name / `formula_ref` resolves.
- Gates per strategy are the atomic set: N data-completeness IS NOT NULL gates (N = the Phase 0
  3b count), `dir_earnings` (formula_ref), three liquidity gates, `dir_budget_flag`,
  `dir_negative_ev` (formula_ref). No multi-field or multi-threshold single gate remains.
- The `dir_bid_ask_spread_max` gate does not halt debit-spread candidates (null
  `bid_ask_spread_pct` is skipped per SKIP null-semantics).
- `dir_earnings` / `dir_negative_ev` rows carry `formula_ref` (no `condition_expression`),
  params `buffer_days` / `threshold`, and resolve to the OTA-837 formulas.
- Three verdict-band sets present in the SCREENING band shape.
- `dir_budget_fit` and `dir_defined_risk` bound by no strategy.
- `app/ota_adapters/directional/config.py` deleted; grep shows zero references.
- No `if strategy_key ==` branching introduced.

## Out of scope

- Any change to the directional adapter or scoring/gate formula code (OTA-834 / OTA-837).
- Band-threshold deduplication across screening + directional (OTA-835).
- Routing directional through the engine (OTA-765); retiring `directional_engine.py` (OTA-756).
- Restoring fatal startup hydration / removing the OTA-830 stopgap (OTA-836).
- Backtest calibration of weights or bands (post-cutover).

## Verification steps

1. Dry-run/load the seed (PowerShell):
   ```powershell
   cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
   .\venv\Scripts\Activate.ps1
   python scripts\seed_engine_config.py --dry-run   # use the script's actual dry-run flag if present; else load against dev
   ```
2. Confirm no weight-sum rejection and no unresolved-reference error for the three directional
   strategies; the two `formula_ref` rows resolve to `dir_earnings` / `dir_negative_ev`.
3. Grep proves the orphan is gone and unreferenced.
4. Report a summary table: strategy / # scoring rows / weight sum / # data-complete gates /
   # liquidity gates / total gate rows / band set.
5. QA level: **Level 1** (config/seed change; no engine-math change). Document in the commit body.

## Commit instruction

I have been instructed NOT to commit. Present the diff and the verification summary; Don
commits manually after review.

## Coordination footer

STOP after this prompt. Downstream: OTA-835 (defer band thresholds to per-strategy
`verdict_band_set` — across screening and these directional sets) then OTA-836 (restore fatal
hydration — the engine-goes-live keystone), both single-terminal on the same seed file; then
OTA-765 / OTA-756. Do not begin any until Don confirms this seed is committed.

## Commit message template (Don runs this)

```
OTA-833 feat: seed three directional objectives (income/growth/longshot) with atomic gates (per-field data-complete, 3 liquidity, 2 formula-ref) and per-strategy verdict bands; retire orphan directional config
```
