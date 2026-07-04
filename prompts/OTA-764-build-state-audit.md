---
allowedTools:
  - Read
  - Grep
  - Glob
  - Bash(cat*)
  - Bash(git*)
  - Bash(python*)
  - Bash(pytest*)
  - Bash(grep*)
  - Bash(ls*)
---

# OTA-764 build-state audit + dev-line reconciliation (READ-ONLY)

## Terminal context
- This terminal: Terminal A (single)
- Concurrent terminals: none
- Cross-terminal dependencies: none

## Nature of this prompt
**This is a read-only audit. Make NO edits, NO commits, run NO seeds, and modify NO files.** Inspect git, the source tree, and the test suite, then output a single structured report. The point is to reconcile *actual* build state against Jira-claimed status, because Jira status lags commit state in this project and several tickets are ambiguous.

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/deployment-workflow.md          # branch + slot model
cat claude_context/insight_engine-migration-plan.md # S5.7 Position Monitor; Strategy Admin sections
```

## Context (verify, do not trust blindly)
- **OTA-764 — Wire Position Monitor Agent through the engine.** Jira status: *Prompt Written*. But the dev change log reportedly shows it already built to dev at commit **fe166ea**. Definitive test of whether it is actually built: `app/agents/position_monitor.py` calls `engine.evaluate(...)` (built) vs still calls `_adapter.chat(...)` for grading (not built).
- **OTA-764's hard gate is OTA-844** (seed POSITION_HEALTH into the live engine; registry 36→40, three surfaces load). OTA-844 is at Code & Test Complete. If 844 is truly on this branch, the registry is 40 and `position_health_full` resolves.
- **Pre-prod bundle branch:** `OTA-836-build-to-testable` (per OTA-844). Confirm whether HEAD is on that branch and whether it is merged to the dev line.
- **Strategy Admin branch:** OTA-782–793 (UI) plus backend deps OTA-822/823/825/826/828. Integration on the dev line is *unconfirmed* — report what is actually present.

## Report — answer A–G, then STOP

**A. Branch + HEAD.**
- `git branch --show-current`, `git log --oneline -15`.
- Is `OTA-836-build-to-testable` the current branch? Is it merged into the dev/main line yet? Report the relationship.

**B. OTA-764 — is it built?**
- Show whether commit `fe166ea` exists in the current branch history (`git log --oneline | grep fe166ea` or `git show --stat fe166ea`). Report the files it touched and its message.
- In `app/agents/position_monitor.py`: does the grading path call `engine.evaluate(...)` (built) or still `_adapter.chat(...)` → parse `PositionHealthUpdate.health_grade` (not built)? Quote the relevant lines.
- Is `positions.health_grade` written from an engine result-record verdict letter, or from the Claude-parsed grade?
- Verdict: **OTA-764 is BUILT / PARTIALLY BUILT / NOT BUILT** on this branch, with evidence.

**C. OTA-844 gate — is the surface live?**
- Does `scripts/seed_engine_config.py` seed `position_health_full` / `position_health_basic`?
- Does `build_combined_registry()` include the 4 position-health formulas (registry == 40)?
- Run `pytest tests/insight_engine/test_full_seed_boot.py -q` (read-only) and report whether it asserts `{SCREENING, DIRECTIONAL, POSITION_HEALTH}` and registry == 40, and whether it passes.

**D. OTA-764 test state.**
- Locate and run any position-monitor / position-health tests touched by 764 (e.g. `tests/options_rules/test_position_health_parity.py`, agent tests). Report pass/fail counts. Note known-divergent parity (OTA-844 declared grade accuracy non-blocking) separately from structural failures.

**E. Strategy Admin branch integration.**
- Does the `/strategy-admin` route exist and is it wired in the frontend (search the web app for the route + nav)?
- Search git history for OTA-782–793 and OTA-822/823/825/826/828 commit messages; report which are present on this branch and which are absent.
- One-line verdict: Strategy Admin UI + backend deps **INTEGRATED / PARTIAL / ABSENT** on the dev line.

**F. Known reds baseline.**
- Run `pytest tests/integration/test_options_chain_adapter.py tests/ota_adapters/test_engine_runtime.py -q`. Confirm the OTA-843 reds (expect 11 failing: `negative_ev_gate` unregistered + stale `EngineRuntime` constructor test). Report the actual count so we know the current baseline.

**G. Bottom line.**
A 5–8 line summary: for OTA-764, OTA-844, and the Strategy Admin branch, state actual build state vs Jira-claimed status, and flag any Jira transition that is now warranted (do not perform it — Don holds the gate).

## STOP
Output the report and stop. Make no changes.

## Commit instruction
None — read-only audit, nothing to commit.

## Coordination footer
Independent — no downstream dependency.
