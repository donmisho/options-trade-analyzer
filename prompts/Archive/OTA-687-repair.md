# OTA-687 (repair) — Bind scoring criteria to strategies (missing weighted junction rows)

> Repair of OTA-687. The strategy rows, gate bindings, adjustment bindings, and all 16 scoring RULES
> seeded correctly, but **zero scoring-weight junction rows were created** — `SUM(weight)` per strategy is
> empty and the 16 scoring rules are orphaned. OTA-687 AC ("scoring weights sum to exactly 1.0000 per
> strategy") is currently failing. Regress OTA-687 to Write Prompt; this repair re-commits as OTA-687.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none — confirm with Don.
- Cross-terminal dependencies: operates on the live dev seed. Touches the seed/importer code and ADDS
  junction rows. Does NOT touch any project-critical shared file (`app/main.py`, `app/database.py`,
  `web/src/api/client.js`).

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md                 # § 3.4 strategy×rule junction, § 6.2, § 6.6 (weights sum to 1.0)
cat claude_context/insight_engine-schema-ddl.md       # § 2 engine_strategy_rule_junction
# The OTA-687 seed code + workbook parsing (paths per repo — locate the strategy-binding logic):
#   the seed importer module (from OTA-682) and the OTA-687 strategy/junction seed step
#   requirements/Scoring Parameters.xlsx  (Sheet1 — per-strategy scoring-criteria columns + weights)
```

## Confirmed state (from dev verification 2026-05-26)
- `engine_strategies`: 4 rows (steady_paycheck, weekly_grind, trend_rider, lottery_ticket) — correct.
- `engine_rules`: 52 rows = 31 gate + 5 adjustment + 16 scoring. The 16 scoring rules all carry
  `formula_ref` and clean snake_case `rule_key`s — **correct, do not touch.**
- `engine_strategy_rule_junction`: 95 rows, ALL `gate` or `adjustment` phase, every `weight` NULL.
  **Zero scoring-phase junction rows exist.** This is the entire defect.
- Target end-state: junction 95 → **114** (19 scoring rows added); `SUM(weight) = 1.0000` for all four.

## PHASE 0 — Diagnose, then STOP and report (no changes yet)
Determine **why** the scoring binding produced zero rows. Read the OTA-687 seed/binding code and the
workbook parsing. Classify the root cause as one of:
- (A) **Importer code gap** — the binding logic loops gate/adjustment rows but has no loop over the
  scoring-criteria-with-weights section; OR it matches scoring criteria by display name (`intent`,
  e.g. "Credit Width %") against `rule_key` (`credit_width`) and silently finds nothing.
- (B) **Run gap** — the scoring-binding step exists but was never invoked.
Report: the root cause (A/B), the exact file:line, and whether the fix belongs in the **importer logic**
(preferred — so re-runs and future rebuilds work) or is a one-off insert. **STOP. Wait for Don's go.**

## PHASE 1 — Repair (after Don's go)
Create the 19 missing scoring-phase junction rows. Prefer fixing the importer's scoring-binding logic
(so a clean rebuild reproduces them), then run it; fall back to a targeted idempotent seed only if Don
directs. Bindings (resolve `strategy_id` by `strategy_key`, `rule_id` by `(owner_app_id='OTA', rule_key)`):

**steady_paycheck (sum 1.00):**
`theta_margin_ratio` 0.30 · `probability_of_profit` 0.25 · `expected_value` 0.20 · `reward_risk` 0.15 · `iv_rank` 0.10
**weekly_grind (sum 1.00):**
`probability_of_profit` 0.25 · `expected_value` 0.15 · `theta_gamma_ratio` 0.35 · `credit_width` 0.20 · `liquidity` 0.05
**trend_rider (sum 1.00):**
`expected_value` 0.20 · `sma_alignment_score` 0.30 · `delta_quality` 0.25 · `iv_percentile_cost` 0.15 · `runway_score` 0.10
**lottery_ticket (sum 1.00):**
`payout_ratio` 0.45 · `delta_otm_score` 0.25 · `bid_ask_tightness` 0.20 · `open_interest` 0.10

Junction field values for each scoring row:
- `weight` = the value above (numeric(7,4)).
- `stop_if_fail` = 0 (scoring rules never halt the pipeline).
- `score_penalty` = NULL (penalties are for non-stopping gate failures, not scoring).
- `evaluation_order` = sequential within the strategy's **scoring** phase (unique per `(strategy, scoring)`),
  in the sheet's listed order.
- `enabled` = 1.
- `parameters` = per the workbook's per-strategy scoring params where present, validated as JSON against
  the rule's `engine_rules.parameter_schema`. **If a `parameter_schema` requires params the workbook does
  not supply (e.g. a delta target band), STOP and report — do NOT invent tuning values.** Where no params
  are needed, NULL.
- `rationale` = optional one-line note.

Idempotency: upsert on the natural key `(strategy_id, rule_id)` — a re-run must not duplicate. Do **not**
modify or delete any of the 16 scoring rules or the 95 existing gate/adjustment junction rows.

## Acceptance criteria
- `engine_strategy_rule_junction` has 19 new scoring-phase rows (114 total); each new row has a non-NULL
  `weight`, `stop_if_fail = 0`, `score_penalty` NULL, and a valid `evaluation_order` unique within
  `(strategy, scoring)`.
- `SUM(weight) = 1.0000` for all four strategies (scoring rows only).
- The 16 scoring rules and the 95 pre-existing junction rows are unchanged (no duplicates, no edits).
- Any `parameters` written are valid JSON satisfying the rule's `parameter_schema`; no fabricated values.
- If the root cause was (A), the importer logic is fixed so a clean rebuild reproduces the 19 rows.

## Out of scope
- Tuning any weight or scoring parameter (values are as captured from the workbook).
- Touching gate/adjustment rows, rules, strategies, or lookups.
- The formula-registry question (OTA-689) — handled separately.
- The `evaluation_order` cosmetic quirk on adjustment rows and the earnings-order question — separate.

## Verification steps
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
# run the repaired importer / seed step, then re-run the SSMS verification grids 5 and 6
```
SSMS:
```sql
-- weights sum (was empty; must now be 1.0000 x4)
SELECT s.strategy_key, COUNT(j.weight) AS weighted_rules, SUM(j.weight) AS weight_sum,
       CASE WHEN ABS(SUM(j.weight)-1.0) <= 0.0001 THEN 'OK' ELSE '*** OFF ***' END AS verdict
FROM dbo.engine_strategies s
JOIN dbo.engine_strategy_rule_junction j ON j.strategy_id = s.strategy_id
WHERE j.weight IS NOT NULL
GROUP BY s.strategy_key ORDER BY s.strategy_key;

-- junction total = 114
SELECT COUNT(*) FROM dbo.engine_strategy_rule_junction;
```
Expect: four rows, `weight_sum = 1.0000`, `verdict = OK`; junction count 114.

Post-Build QA Gate: config-data repair, no existing reader of `engine_*` yet → Level 1. Note in commit body.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer
After this lands, re-run the full seed-verification script; once grids 5/6 pass, the OTA-680 config
substrate is ready for the engine-core review. (Formula-registry / OTA-689 status is a separate check.)

## Commit message template (if committing)
```
OTA-687 fix: bind scoring criteria to strategies (missing weighted junction rows)

Adds 19 scoring-phase junction rows (SP/WG/TR/LT) with weights from Scoring
Parameters.xlsx, each set summing to 1.0000. Root cause: <A importer gap / B run
gap> at <file:line>; fixed in importer so rebuilds reproduce. Existing 16 scoring
rules + 95 gate/adjustment junction rows unchanged. QA Level 1.
```
