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

# OTA-847 — Screening seed↔adapter named-value reconciliation (#2/#3/#4, seed-only)

You are working on branch `OTA-836-build-to-testable`. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## Objective

Live credit-spread screening halts at data-completeness because three seeded rule named-values/units do not match the options-chain (screening) adapter's emitted catalog. Reconcile **only** mismatches #2, #3, and #4 in `scripts/seed_engine_config.py` so that a representative **Weekly-Grind (WG)** credit-spread candidate passes data-completeness and reaches a verdict. The adapter catalog is the source of truth.

**This is a seed-only change.** Phase 0.5 already established the exact dispositions below; your Phase 0 is a *confirm-against-live-code* gate, not fresh discovery.

**Explicitly out of scope — do NOT touch:**
- `data_completeness_delta` binding or `app/options_rules/screening/scoring_formulas.py` — that is **OTA-850** (the `delta` vs `long_delta`/`short_delta` half). SP and TR spread candidates will *remain blocked by the delta gate by design* after this ticket — that is expected, not a regression.
- The §6.6 per-surface catalog feed / `validate_by_surface` rework — that is **OTA-851**.
- Re-pointing `earnings_days_past_expiry` to `dte_after_earnings` — that is **OTA-849**. Here we only *descope* it.
- `negative_ev_gate` formula reds — resolved under **OTA-843** (already Code & Test Complete on this branch).
- `position_routes.py`, `position_monitor.py`.

## The three fixes (from OTA-847 Phase 0.5 — verify, do not trust blindly)

| # | Named value | Disposition |
| --- | --- | --- |
| 2 | `cushion_vs_atr_ratio` → `cushion_vs_atr` | **Pure rename.** Re-point the gate ref to the adapter's emitted name. Collapses the OTA-832 phantom (the `_ratio` distinction was introduced by OTA-832, not the adapter). |
| 3 | `cushion_pct` units (fraction → percent) | **Gate only.** Rescale the `cushion_of_price` junction params ×100: **SP → {low 1.0, high 100.0}**, **WG → {low 1.5, high 100.0}**. The penalty twin (`adj_cushion_penalty_severe` = 1.0, `adj_cushion_penalty_moderate` = 1.0 / 2.0) is **already percent — do NOT rescale it.** It is not a second instance of #3. |
| 4 | `earnings_days_past_expiry` | **Descope from the screening completeness set.** It is load-bearing (order 60, `stop_if_fail`, halts all candidates) and the adapter's `dte_after_earnings` is sign-inverted vs LT's 7-day buffer, so a naive re-point is worse than the bug. Remove it from the screening data-completeness set and leave a one-line seed rationale comment referencing **OTA-849**. |

## Mechanism A — Required Reading (run these first)

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat scripts/seed_engine_config.py
```

Then locate the screening/options-chain adapter catalog and confirm its emitted names:

```
grep -rn "cushion_vs_atr" app/ota_adapters/
grep -rn "cushion_pct" app/ota_adapters/
grep -rn "earnings_days_past_expiry" app/ota_adapters/ app/options_rules/
grep -rn "dte_after_earnings" app/ota_adapters/
```

## Phase 0 — Confirm the embedded values against live code (READ-ONLY, HARD GO/NO-GO STOP)

Make NO edits. Answer A–F, then STOP and report.

**A. #2 rename.** Locate every seed reference to `cushion_vs_atr_ratio` in `seed_engine_config.py`. Confirm the adapter catalog emits `cushion_vs_atr` (no `_ratio`). Confirm there is no *other* consumer of `cushion_vs_atr_ratio` that a rename would break (grep the whole tree). Confirm it is a pure gate-ref rename.

**B. #3 rescale.** Locate the `cushion_of_price` junction params for **SP** and **WG**. Report their *current* values and confirm they are fractional (i.e., the ×100 targets are SP {low 1.0, high 100.0}, WG {low 1.5, high 100.0}). Separately locate the penalty twin (`adj_cushion_penalty_severe`, `adj_cushion_penalty_moderate`) and confirm its params are already in percent (1.0 / 1.0, 2.0) so they are left untouched.

**C. #4 descope.** Locate `earnings_days_past_expiry` in the screening data-completeness set. Confirm order 60 / `stop_if_fail`. Identify exactly what to remove (the completeness-set membership / gate junction row) to descope it — and confirm the descope does not orphan any other rule that references it.

**D. WG clears.** Trace the WG credit-spread gate path *after* #2/#3/#4 are applied and confirm no *other* completeness gate halts WG before scoring. Confirm SP/TR still halt at `data_completeness_delta` (order 140) — that is expected (OTA-850), not something to fix here.

**E. Verdict reachable.** Confirm `negative_ev_gate` is registered on this branch (OTA-843 landed) so a WG candidate can reach a verdict rather than KeyError-ing at the gate.

**F. Blast radius.** Confirm the three surfaces (screening / directional / position-health) all still seed with these edits, and that nothing in `scoring_formulas.py` or the `data_completeness_delta` binding needs to change for #2/#3/#4 (it must not — that is OTA-850).

**GO only if:** #2 is a clean rename with no other consumer · #3 current values confirm the ×100 targets and the penalty twin is already percent · #4 descope point is clear and orphans nothing · WG's remaining path reaches scoring. **NO-GO and STOP** if any of these fail — in particular, if resolving any of #2/#3/#4 turns out to require touching `scoring_formulas.py` or the delta gate, STOP and report (that is OTA-850 scope).

## Phase 1 — Apply #2 (rename)

Re-point the seed gate ref `cushion_vs_atr_ratio` → `cushion_vs_atr` to match the adapter catalog.

## Phase 2 — Apply #3 (rescale, gate only)

Rescale the `cushion_of_price` junction params ×100:
- **SP** → `{low: 1.0, high: 100.0}`
- **WG** → `{low: 1.5, high: 100.0}`

Leave `adj_cushion_penalty_severe` / `adj_cushion_penalty_moderate` **unchanged** (already percent).

## Phase 3 — Apply #4 (descope)

Remove `earnings_days_past_expiry` from the screening data-completeness set so it stops halting every candidate. Add a one-line seed comment: rationale = adapter's `dte_after_earnings` is sign-inverted vs LT's 7-day buffer; earnings-buffer reconciliation tracked by **OTA-849**.

## Phase 4 — Reseed + verify

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts/seed_engine_config.py
```

Then verify:
- A representative **WG** credit-spread candidate passes data-completeness and **reaches a verdict**.
- **SP/TR** spread candidates still halt at `data_completeness_delta` (expected — OTA-850).
- **SP / TR / LT** all still seed, and all three surfaces (screening / directional / position-health) still boot.

```powershell
pytest tests/integration/test_options_chain_adapter.py -q
pytest tests/insight_engine tests/options_rules -q
```

Report the WG verdict result and the seed/boot confirmation. Grade *accuracy* is not the gate here — reaching a verdict is.

## Manual commit gate

STOP. Summarize the staged diff (files touched, line counts) and the verification results. Do NOT commit yourself — Don commits with the `OTA-847 feat:` prefix.

Suggested commit message:
```
OTA-847 feat: reconcile screening seed named-values to adapter catalog (cushion_vs_atr rename, cushion_of_price x100 gate, earnings descope)
```

## Coordination

- Branch `OTA-836-build-to-testable` only. Part of the current pre-prod bundle.
- **Single seed terminal** — this touches `scripts/seed_engine_config.py`; do NOT parallelize with any other seed-touching work.
- **Head of the seed chain.** OTA-850 (delta-completeness redesign) runs *after* this commits and builds on this reconciliation. OTA-849 (earnings buffer) and OTA-851 (§6.6 feed) also follow.
- Do NOT deploy. Don holds the deploy gate. Dev only.

**QA level: 2** (engine-config seed; the cushion rescale is verdict-affecting on the WG surface).
