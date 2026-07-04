---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash
---

# OTA-838 — Honor catalog null_semantics (SKIP/FAIL_OPEN) at gate evaluation

## Terminal context
- This terminal: **Terminal A (single)**
- Concurrent terminals: **none** — engine-core eval path; never parallelize with seed-touching
  work or any other rule/pipeline change.
- Cross-terminal dependencies: none upstream. Downstream: OTA-833 (v3) waits on this; do not
  start it until this is committed and the engine starts clean.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
```

Then inspect (read-only, Phase 0) the eval path and the null_semantics plumbing:

```
cat app/insight_engine/pipeline.py
cat app/insight_engine/expressions.py
cat app/insight_engine/models.py
cat app/insight_engine/loader.py
cat app/insight_engine/validation.py
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-833 v3 Phase 0 trace (the bug)**
The gate evaluator never consults `null_semantics`; it is dead metadata at runtime. Trace for
`dir_bid_ask_spread_max` (`bid_ask_spread_pct <= max_spread_pct`) on a debit spread:
- `pipeline.py:264` `_run_gate_list` → `_evaluate_rule` → generic predicate
  (`pipeline.py:460-466`) → `evaluate_expression("<=", …)`.
- `expressions.py:196-205` `_eval_comparison`: `lhs = None` → `if lhs is None: return False`
  (the `==`/`!=` null special-cases do not apply to `<=`).
- `pipeline.py:280-300`: `passed = False` + `stop_if_fail = True` → halt, candidate dead.
`null_semantics` is referenced only in `models.py` (field), `loader.py` (pass-through), and
`validation.py:462-488` (a startup FAIL_CLOSED-vs-FAIL_OPEN compatibility check). The
evaluator and pipeline never read it; there is no per-junction skip-on-null field.

**Source: intended contract (this ticket)**
At gate evaluation, when the LHS named value resolves to **null**, consult that named value's
catalog `null_semantics`:
- **SKIP** → skip the rule. Record a `skipped` decision in the per-rule trace; no pass, no
  fail, no halt, no `score_penalty`; continue to the next rule.
- **FAIL_OPEN** → treat null as **pass** (rule does not halt or penalize on null).
- **FAIL_CLOSED** → treat null as **fail** (current de-facto behavior; halts if `stop_if_fail`).
This applies to the **gate/predicate** path. Scoring formulas already null-guard internally
(return a null/zero score) and are out of scope.

**Source: insight_engine.md §3.6 (gate mechanics) + Epic OTA-679 invariants**
- Gate behavior is driven by config + catalog metadata, never by code branching. This fix must
  be driven entirely by the LHS named value's catalog `null_semantics` — **no** `if
  strategy_key ==`, no structure branching, no per-rule special casing.
- The engine emits a full per-rule decision trace; the new `skipped` outcome must appear there.
- Single evaluation path — do not add a parallel null-handling branch elsewhere.

**Source: epic OTA-679 (parity)**
Activating the semantics changes behavior for any currently-live rule whose LHS is tagged
`SKIP`/`FAIL_OPEN` and can be null at eval (today they all fail closed). No **unintended**
verdict shift on screening or position-health is acceptable; intended corrections are
documented in the commit body.

---

## Phase 0 — Read-only discovery (HARD STOP before any edits)

No edits, no writes, no commits. Confirm each, then STOP and report GO/NO-GO.

1. **Insertion point + metadata reachability.** Identify exactly where in the gate path the
   null check should consult `null_semantics`, and confirm the LHS named value's
   `null_semantics` is reachable at that point (carried through `loader.py` to the rule/
   named-value object the pipeline holds at eval). If the metadata is NOT reachable at the
   gate-eval boundary without invasive plumbing beyond this path → report the plumbing needed
   and treat as a scope flag.
2. **Parity blast radius — enumerate.** List every named value tagged `SKIP` or `FAIL_OPEN`
   across all surfaces (screening, position_health, directional), the live rules referencing
   each, and whether the value can be null in practice. This is the set whose behavior changes.
3. **Trace shape.** Confirm how the per-rule decision trace represents outcomes today and how a
   `skipped` outcome should be recorded (distinct from pass and fail).
4. **Startup-validation interaction.** Confirm the `validation.py:462-488` FAIL_CLOSED-vs-
   FAIL_OPEN compatibility check remains correct/unaffected by the runtime change.
5. **Recommendation + QA level (expect Level 2).** Report the insertion approach and the
   parity set.

**GO** if the insertion point is clean and `null_semantics` is reachable at the gate-eval
boundary. **NO-GO** if honoring it requires invasive changes outside the gate path — report
and STOP for a scope decision.

### STOP — report Phase 0 findings and await GO/NO-GO before implementation.

---

## Implementation — only after GO

- At gate eval, when the LHS value is null, branch on the LHS named value's catalog
  `null_semantics`: SKIP → skip (record `skipped`, no halt/penalty); FAIL_OPEN → pass;
  FAIL_CLOSED → fail (unchanged). Driven solely by the catalog field.
- Emit the `skipped` outcome in the per-rule decision trace.
- Keep it on the single gate-eval path; no parallel branch, no structure/strategy branching.

## Acceptance criteria
- Gate eval consults the LHS named value's catalog `null_semantics` on a null LHS; `SKIP`
  skips, `FAIL_OPEN` passes, `FAIL_CLOSED` fails.
- A skipped rule is recorded as `skipped` in the trace and triggers neither `stop_if_fail`
  nor `score_penalty`.
- A `stop_if_fail` gate on a `SKIP`-tagged null LHS (e.g. `bid_ask_spread_pct` on a debit
  spread) no longer halts the candidate — it is skipped.
- Parity: every `SKIP`/`FAIL_OPEN` value + referencing rules from Phase 0 step 2 exercised
  with a null LHS; before/after verdicts captured; no unintended shift on screening or
  position-health (intended corrections documented in the commit body).
- Unit tests cover SKIP × null, FAIL_OPEN × null, FAIL_CLOSED × null, and non-null
  (unchanged) for a representative comparison operator.
- `validation.py` startup compatibility check still passes.
- No `if strategy_key ==` / structure branching introduced.

## Out of scope
- Scoring-formula null handling (formulas already null-guard).
- Per-junction skip-on-null field (rejected approach — semantics live on the catalog).
- The directional seed itself (OTA-833 v3) and its spread-gate wiring.
- Broader golden-fixture harness (OTA-796).

## Verification steps
- `cat` the required-reading files; flag any embedded-context contradiction with the canonical docs.
- Run the engine unit tests + the new null-semantics tests (PowerShell):
  ```powershell
  cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
  .\venv\Scripts\Activate.ps1
  python -m pytest tests/ -k "engine or pipeline or expression or null_semantics" -q
  ```
- Present the before/after parity table for the Phase 0 step-2 set.
- Confirm `grep` shows zero `if strategy_key ==` / structure branching introduced.
- QA level: **Level 2** (engine-evaluated core change; parity regression). Note tests run in the diff summary.

## Commit instruction
I have been instructed NOT to commit. Stage the changes, present the full diff, the test
output, and the before/after parity table, and STOP. Don reviews and commits manually.

## Coordination footer
STOP after presenting the diff. Downstream: OTA-833 (v3 prompt) runs next, after Don commits
this and confirms the engine starts clean.

## Commit message template (Don will apply on approval)
OTA-838 fix: honor catalog null_semantics (SKIP/FAIL_OPEN/FAIL_CLOSED) at gate evaluation
