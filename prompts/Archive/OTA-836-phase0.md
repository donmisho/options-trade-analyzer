# OTA-836 — Restore fatal engine-config hydration: resolve 2 missing formula implementations + remove OTA-830 stopgap

> **Phase 0 only — read-only discovery with a hard STOP.** No edits. This determines, for each of the two missing formulas, whether to implement it, canonicalize the referencing rules and drop it, or retire it; confirms the registry will reconcile clean once this + OTA-816 land; and plans the OTA-830 try/except removal. Implementation is a separate prompt after Don's decision and after OTA-832 + OTA-816 land.

## Terminal context
- This terminal: single terminal.
- Concurrent terminals: none. Phase 0 is read-only and safe anytime. The implementation must run alone — it touches `app/main.py` and possibly `scripts/seed_engine_config.py`, shared with OTA-832/816/833/834/835.
- Cross-terminal dependencies: implementation lands **after** OTA-832 (canonicalization + validator fix) and OTA-816 (the 5 drift). Both must be in before the try/except can be removed safely.

## Required reading
Before anything else:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-schema-ddl.md
cat claude_context/business-rules.md
```

## Relevant Context — Do Not Deviate Without Escalation

```
Source: OTA-832 Phase 0 finding
Fact: validate_and_raise (the §6.6 suite, OTA-699) has never executed against this
seed — the loader raised first. Once OTA-832 lets load_config succeed, validate_and_raise
runs and throws 9 errors:
  - FORMULA_MISSING_FROM_LIVE_REGISTRY x2: chart_state_matches_direction,
    extension_matches_trade_direction (in contract + referenced by rules; no live impl).
  - FORMULA_REGISTRY_DRIFT x7: the 2 above (contract-not-live) + 5 live-not-contract
    (credit_pct_of_width_floor, debit_pct_of_width_ceiling, dte_hard_filter,
     dte_warning_penalty, negative_ev_gate).
The 5 live-not-contract are owned by OTA-816 (add to contract + reseed lookup). This
ticket owns ONLY the 2 missing-from-live formulas + the fatal-restore.

Source: insight_engine.md § 6.6 (OD-1 (c), dual formula-registry validation)
Rule: formula membership is validated against TWO sources at load — the SHARED
('SHARED','formula_registry') lookup (contract) and the live registered rule library
(does an implementation exist). A name in only one source is a distinct drift error.
So the 2 here can be cleared by EITHER implementing them live (satisfies both) OR
removing them from BOTH the rules' formula_ref AND the contract lookup (canonicalize/retire).

Source: insight_engine.md § 6.3 (expression library)
Rule: §6.3 runtime tokens: >= <= > < == != · IN · NOT IN · IS NULL · IS NOT NULL ·
EQUALS_ENUM · BETWEEN · formula:<name>. Evaluator: LHS = referenced_named_values[0],
RHS = first junction parameter. A rule can be canonicalized to drop a formula ONLY if
its logic reduces to one of these atomic forms over an existing single named value.

Source: insight_engine.md § 2 / Epic OTA-679 acceptance
Rule: tables are the source of truth; no `if strategy_key ==` branches; a formula is a
pure (named_values, params) -> float in [0,100].

Source: OTA-832 Phase 0 — stopgap removal point
Fact: app/main.py:339-353 wraps init_engine_runtime() in the OTA-830 non-fatal
try/except. The TODO(OTA-815) marker is at 333-336. Removing it restores fatal hydration.
```

## Scope (read-only discovery)

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

For **each** of the two formulas — `chart_state_matches_direction`, `extension_matches_trade_direction` — answer:

1. **Referencing rules.** Which `engine_rules` rows reference it via `formula_ref`? Record `rule_key`, `phase`/`tier`, `intent`, `referenced_named_values`, `parameter_schema`, and which of the 4 strategies bind it.
   ```powershell
   rg -n "chart_state_matches_direction|extension_matches_trade_direction" app scripts
   ```
   (Fallback: `Get-ChildItem -Recurse app,scripts -Include *.py | Select-String -Pattern 'chart_state_matches_direction','extension_matches_trade_direction'`.)

2. **Intended computation.** From the rule intent + `business-rules.md` + the contract notes in the `('SHARED','formula_registry')` lookup payload, state in one line what each formula is supposed to compute and over which inputs.

3. **Path recommendation.** Pick one, with reasoning:
   - **(a) Implement live** — the logic is a genuine computed score/condition that can't reduce to a §6.3 atom. Note where it would register (`app/options_rules/screening`) and its signature.
   - **(b) Canonicalize + drop** — the logic reduces to a §6.3 atomic form over an existing single named value. Give the exact token rewrite, and note that the formula must also be removed from the contract lookup.
   - **(c) Retire** — the referencing rule is dead / superseded. Cite the evidence.

4. **Contract coupling.** Confirm both names are present in the `('SHARED','formula_registry')` contract lookup. If the recommendation is (b)/(c), note that the contract row must be removed too (and whether that reseed conflicts with OTA-816's reseed — coordinate, single seed pass).

Then, across the whole ticket:

5. **OTA-816 boundary.** Confirm OTA-816 covers exactly the 5 live-not-contract names and nothing here overlaps it.

6. **Clean-after check.** Model the reseeded config (OTA-832 canonicalization + OTA-816 contract + this ticket's resolution) and confirm `validate_and_raise` would then find **zero** §6.6 errors — i.e., these 9 are the complete set, no hidden tenth.

7. **Restore point.** Confirm `app/main.py:339-353` is the only place the OTA-830 try/except guards hydration, and that removing it makes step-6d fatal. Confirm the `validate_and_raise` call ordering relative to `load_config` and `_runtime` assignment.

8. **QA level.** Level 2 if any path is (a) implement; Level 1 if both are (b)/(c) only.

## Acceptance criteria (for this discovery phase)
- Each of the 2 formulas has: referencing rules, intended computation, and a single recommended path (a/b/c) with reasoning.
- Contract-lookup presence confirmed for both; removal/reseed coordination with OTA-816 noted if (b)/(c).
- OTA-816 boundary confirmed (no overlap).
- Clean-after check: a stated confirmation that the 9 errors are the complete §6.6 set.
- Restore point and `validate_and_raise` ordering confirmed.
- QA level stated.

## Out of scope
- Any edit. No file is modified in this phase.
- The 5 live-not-contract drift (OTA-816).
- The canonicalization + validator fix (OTA-832).
- Removing the try/except now (it stays until OTA-832 + OTA-816 + this ticket's resolution are all in).

## Verification steps
- Re-run the search and confirm every reference to the 2 names is accounted for.
- Open the cited `main.py` lines and confirm the guard + ordering.
- **NO-GO** if discovery finds: a tenth §6.6 error beyond the known 9; or that one of the 2 formulas is load-bearing in a way that blocks both implement and drop; or that OTA-816's scope does not in fact cover all 5 drift names. In any of these, stop and report for reframing rather than recommending a path.

## Commit instruction
I have been instructed NOT to commit. This is a read-only discovery phase; no files are modified.

## Coordination footer
STOP after the report. Present per-formula findings + recommended paths (Q1–Q4), the clean-after confirmation (Q6), and the QA level, then wait. Do not begin implementation — the implementation prompt is authored only after Don's decision and after OTA-832 + OTA-816 have landed.

## Commit message template
(none — read-only phase, no commit)
