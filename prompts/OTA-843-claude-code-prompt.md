# OTA-843 — Test hygiene (Option C): conform stale engine-test reds to post-836/837 reality

## Terminal context
- This terminal: **Terminal B** (tests-only)
- Concurrent terminals: Terminal A (OTA-847, seed) · Terminal C (OTA-846, frontend)
- Cross-terminal dependencies: none. You touch **test files only**. No production code, no seed, no frontend.

You are working on branch **`OTA-836-build-to-testable`**. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## Disposition (decided by Don): Option C
Fix the stale tests to match the post-OTA-836/837 engine reality. **Zero production change.** `negative_ev_gate` was deliberately deregistered in OTA-836; the reds are test-only; dev boots clean; this ticket is **not** a boot-blocker. Your job is to make the engine suite honest so live dev findings aren't masked by known reds — not to re-register anything.

## Required reading
Before any test changes:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat scripts/seed_engine_config.py                         # confirm the live screening config does NOT reference negative_ev_gate
cat app/insight_engine/registry.py                        # the live FormulaRegistry
cat tests/integration/test_options_chain_adapter.py       # 10 of the 11 reds live here
cat tests/ota_adapters/test_engine_runtime.py             # the 11th red (constructor signature)
```

## Relevant Context — Do Not Deviate Without Escalation

Source: OTA-843 ticket + Option C
Repro: `pytest tests/integration/test_options_chain_adapter.py tests/ota_adapters/test_engine_runtime.py -q` → **11 failed, 34 passed** on HEAD (pre-existing; fails independent of OTA-842).

**Root cause 1 — `negative_ev_gate` not registered (10 failures).** `KeyError: "No formula registered for 'negative_ev_gate'"` at `registry.py:83`. The SP/TR screening configs *in the test fixtures* reference a gate formula that has no live implementation because it was deregistered by design in OTA-836. Failing tests:
- `test_options_chain_adapter.py::TestGateFormulaParity::test_negative_ev_gate_passes` / `_fails` / `_missing_ev_passes`
- `::TestEndToEndSteadyPaycheck::test_positive_ev_credit_spread_reaches_verdict` / `test_negative_ev_halted_at_gate` / `test_cushion_penalty_applied`
- `::TestEndToEndTrendRider::test_trend_rider_with_computed_callback`
- `::TestEndToEndMultiCandidate::test_mixed_batch_gate_and_verdict`
- `::TestValidationWithLiveRegistry::test_sp_config_validates` / `test_tr_config_validates`

**Root cause 2 — stale EngineRuntime constructor test (1 failure).** `TypeError: EngineRuntime.__init__() missing 1 required positional argument: 'loadable_version'` at `tests/ota_adapters/test_engine_runtime.py:223`. The test constructs `EngineRuntime(...)` without the now-required `loadable_version`.
- `tests/ota_adapters/test_engine_runtime.py::test_accessor_raises_before_init_and_returns_after`

## Phase 0 — Confirm the reality before editing (HARD STOP if contradicted)

Make NO edits. Establish and report:
1. **Is `negative_ev_gate` genuinely absent from the live registry?** Grep `registry.py` / the live formula registry. Expected: absent.
2. **Does the live (seeded) screening config reference `negative_ev_gate`?** Grep `seed_engine_config.py` and the live SP/TR configs. Expected: **no** — if the live config still referenced it, boot would fail, contradicting "dev boots clean." 
3. **Is there a live replacement?** Determine whether OTA-836/837 *removed* the screening negative-EV gate entirely, or *renamed/replaced* it with a live formula. This decides the test fix:
   - **Removed by design** → drop the `negative_ev_gate` expectations from the fixtures/tests.
   - **Renamed/replaced** → re-point the fixtures/tests to the live formula name.

**HARD STOP condition:** if Phase 0 finds the live config *still references* `negative_ev_gate` (i.e., it is a genuine missing-implementation that should be live, not a deliberate deregistration), then Option C's premise is wrong — STOP and report. Do NOT delete tests that are correctly catching a real gap.

## Scope (after Phase 0 confirms Option C holds)
1. RC1: conform the 10 fixture/tests to the post-836/837 reality per Phase 0's finding (drop or re-point `negative_ev_gate`). Where a test asserted gate-halt behavior that no longer exists, update the assertion to the current live screening gate behavior — do not invent behavior.
2. RC2: add the required `loadable_version` argument to the `EngineRuntime(...)` construction at `test_engine_runtime.py:223`, matching the current constructor signature.

## Acceptance criteria
- `pytest tests/integration/test_options_chain_adapter.py tests/ota_adapters/test_engine_runtime.py -q` → **0 failed**.
- No production code, seed, or config changed — `git diff --stat` shows test files only.
- No test was deleted that was catching a real (non-stale) gap.

## Out of scope
- Registering `negative_ev_gate` or any formula (that would be a production change — not Option C).
- The screening named-value/unit mismatches — that is **OTA-847** (Terminal A).
- Any `seed_engine_config.py`, `registry.py`, or runtime edit.

## Verification steps
QA Level 1 (test-only). PowerShell:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
pytest tests/integration/test_options_chain_adapter.py tests/ota_adapters/test_engine_runtime.py -q
git diff --stat   # must show test files only
```

## Commit instruction
Do NOT commit. STOP after Phase 0 to report the finding and confirm Option C holds; STOP again after the fix to summarize the diff (test files, line counts) and the green result. Don commits with the `OTA-843 test:` prefix. The commit-triggered automation transitions OTA-843; do not transition it yourself.

## Coordination footer
Independent — no file overlap with OTA-847 or OTA-846. **Land this first** so the engine suite is honest before OTA-847 verification runs. Do not deploy.

## Commit message template (Don)
```
OTA-843 test: conform stale engine-suite reds to post-836/837 reality (negative_ev_gate deregistered, EngineRuntime loadable_version)
```
