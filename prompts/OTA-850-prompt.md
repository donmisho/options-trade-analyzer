```yaml
---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Bash(cat*)
  - Bash(python*)
  - Bash(pytest*)
  - Bash(grep*)
---
```

# OTA-850 — Structure-aware delta-completeness redesign (SP/TR spread candidates reach a verdict)

You are working on branch `OTA-836-build-to-testable`. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## HARD PRECONDITION — do not proceed if unmet

This ticket **builds on OTA-847's committed seed reconciliation**. Before doing anything, confirm OTA-847 is committed on this branch:

```powershell
git log --oneline -15 | Select-String "OTA-847"
```

If no `OTA-847` commit is present, **STOP and report** — do not start. OTA-850 and OTA-847 both touch `scripts/seed_engine_config.py`; they must be sequential, never concurrent.

## Objective

This is the **SP/TR half of the "Trades returns no recommendations" regression.** The shared gate `data_completeness_delta` (`delta IS NOT NULL`, `stop_if_fail=True`, order 140) is bound to SP, WG, and TR. But the options-chain adapter emits `long_delta`/`short_delta` for spreads and **never** emits `delta`, and `IS NOT NULL` is evaluated on key-presence only (`expressions.py::_eval_null` does not consult `null_semantics`). So **every SP and TR spread candidate fails this gate at order 140 and halts before scoring** → no recommendations. A second blocker: the scoring formulas hardcode `named_values.get("delta", 0)`, so a seed re-point alone is a no-op.

Fix both, structure-aware, with no strategy-id branching, so a representative live **SP** and **TR** spread candidate passes data-completeness and reaches a verdict.

## Engine-faithful design (blessed in OTA-847 Phase 0.5 — verify against live code, do not trust blindly)

* Bind a **`delta`-completeness** rule only to **naked-bearing** strategies (**LT**) — adapter emits `delta` there; correct as-is.
* Add a **`long_delta`-completeness sibling** bound to the **pure-spread** strategies (**SP, TR**).
* **Drop** the delta-completeness dependency for the **mixed** strategy (**WG**) — no single fixed leg-name is valid across its mixed structures.
* **All bindings keyed off each strategy's `compatible_structures`**, never a strategy-id branch.
* **Parameterize `delta_quality`** (and any sibling delta-reading formula on a spread path) to read `referenced_named_values[0]` instead of a hardcoded `"delta"`, so TR resolves `long_delta` and LT resolves `delta`, both from config.

## Out of scope — do NOT touch

* Named-value mismatches #2/#3/#4 — done in **OTA-847**.
* The §6.6 per-surface catalog feed / `validate_by_surface` rework — **OTA-851**.
* `app/insight_engine/expressions.py::_eval_null` — the key-presence semantics are *context*, not a target. Do not change null evaluation here.
* `position_routes.py`, `position_monitor.py`.

## Mechanism A — Required Reading (run first)

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat scripts/seed_engine_config.py
cat app/options_rules/screening/scoring_formulas.py
cat app/insight_engine/expressions.py
```

Locate the delta gate, the adapter's emitted delta names, and every formula that reads `delta`:

```
grep -rn "data_completeness_delta" scripts/ app/
grep -rn "long_delta\|short_delta" app/ota_adapters/
grep -rn "named_values.get(\"delta\"" app/options_rules/screening/scoring_formulas.py
grep -rn "compatible_structures" scripts/seed_engine_config.py
```

## Phase 0 — Read-only discovery (HARD GO/NO-GO STOP)

Make NO edits. Answer A–F, then STOP and report. **Do not proceed to Phase 1 without Don's explicit GO** — one item (SP's long-vs-short leg choice) is a domain call he signs off.

**A. Gate bindings.** Confirm `data_completeness_delta` is bound to SP, WG, TR (and not LT). Report each strategy's `compatible_structures` so the structure-keyed rebind is explicit: which structures are pure-spread (→ `long_delta` sibling), which are naked-bearing (→ `delta`, LT), which are mixed (→ drop, WG).

**B. Adapter truth.** Confirm the options-chain adapter emits `long_delta` and `short_delta` (not `delta`) for spread structures, and `delta` for naked/single-leg structures. Quote the catalog entries.

**C. Formula blast radius.** Enumerate **every** screening scoring formula that reads `named_values.get("delta", ...)` — the ticket names `delta_quality` (:207), `delta_otm_score` (:260), `payout_ratio` (:69), but line numbers may have shifted; grep to confirm the full set. For **each**, report which strategies invoke it and whether it runs on the SP/TR spread path. Any delta-reading formula on a spread path must be parameterized too, or it will `get("delta")→0` and silently mis-score. State your proposed parameterization per formula.

**D. SP leg choice (DECISION — flag for Don).** For a **credit spread**, state which leg's delta the completeness sibling and `delta_quality` should read — `long_delta` vs `short_delta` — and your reasoning. The ticket's design says `long_delta` for the pure-spread group; confirm that's coherent for SP credit spreads (where the *short* leg carries assignment risk) or recommend the alternative. **This is the one point that needs Don's GO before you bind it.**

**E. `delta_quality` dual-use.** Confirm `delta_quality` serves both LT (needs `delta`) and TR (needs `long_delta`), so it cannot be hardcoded to either — the parameterization must source the name from each strategy's rule config (`referenced_named_values[0]`).

**F. Boot + no regressions.** Confirm the plan touches only `seed_engine_config.py` + `scoring_formulas.py`, introduces no `if strategy_key ==` branch, and that all three surfaces still seed/boot. Confirm nothing in OTA-847's #2/#3/#4 fixes is disturbed.

**GO only if:** structure-keyed bindings are unambiguous from `compatible_structures` · the full delta-reading formula set is enumerated with a parameterization plan · Don has signed off the SP leg choice (D). **NO-GO and STOP** if the fix would require touching `expressions.py`, a strategy-id branch, or any file outside the two named.

## Phase 1 — Seed: restructure delta-completeness bindings (after Don's GO)

* Rebind so the `delta`-completeness rule applies only to naked-bearing structures (LT).
* Add the `long_delta`-completeness sibling bound to pure-spread structures (SP, TR), with `referenced_named_values` set to the leg confirmed in Phase 0-D.
* Remove the delta-completeness dependency from WG.
* Drive every binding off `compatible_structures`. No strategy-id branch.

## Phase 2 — Scoring: parameterize the delta-reading formulas

* Parameterize `delta_quality` — and every other delta-reading formula Phase 0-C found on a spread path — to read `referenced_named_values[0]` rather than a hardcoded `"delta"`.
* Verify LT resolves `delta` and TR/SP resolve the confirmed spread leg, all from config.

## Phase 3 — Reseed, verify, add regression fixture

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts/seed_engine_config.py
```

Verify:
* A representative **SP** credit-spread candidate and a **TR** debit-spread candidate each pass data-completeness and **reach a verdict**.
* **LT** still resolves `delta` and scores correctly.
* **WG** no longer carries a delta-completeness dep and still reaches a verdict (its OTA-847 cushion/earnings path intact).
* All three surfaces still seed and boot.

Add a **regression fixture** covering an SP and a TR spread candidate reaching a verdict (so this gate can never silently re-close).

```powershell
pytest tests/integration/test_options_chain_adapter.py -q
pytest tests/insight_engine tests/options_rules -q
```

## Manual commit gate

STOP. Summarize the staged diff (files touched — expect only `scripts/seed_engine_config.py`, `app/options_rules/screening/scoring_formulas.py`, and the new/updated fixture — plus line counts) and the verification results, including the SP and TR verdicts. Do NOT commit yourself — Don commits with the `OTA-850 feat:` prefix.

Suggested commit message:
```
OTA-850 feat: structure-aware delta-completeness — long_delta sibling for SP/TR spreads, parameterized delta_quality, WG dep dropped
```

## Coordination

- Branch `OTA-836-build-to-testable` only. Part of the current pre-prod bundle.
- **Runs only after OTA-847 is committed** (hard precondition above). **Single seed terminal** — do not parallelize with any seed-touching work.
- With OTA-850 committed, the **"Trades returns no recommendations" regression is closed** (WG via OTA-847, SP/TR here) — that's the trigger for a dev deploy + full bundle test.
- Do NOT deploy. Don holds the deploy gate. Dev only.

**QA level: 2** (rule-library + seed; verdict-affecting on the SP/TR screening path — anchor the SP/TR spread verdicts in the regression fixture).
