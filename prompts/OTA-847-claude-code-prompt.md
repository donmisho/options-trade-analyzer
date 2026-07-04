# OTA-847 — Screening seed↔adapter named-value reconciliation

## Terminal context
- This terminal: **Terminal A** (the single seed terminal)
- Concurrent terminals: Terminal B (OTA-843, tests-only) · Terminal C (OTA-846, frontend)
- Cross-terminal dependencies: none on file content. You touch `scripts/seed_engine_config.py` (+ validation/runtime wiring in Phase 4). Put any new regression fixture in a **new** test file (see Verification) so you do not collide with OTA-843's edits to `tests/integration/test_options_chain_adapter.py`.

You are working on branch **`OTA-836-build-to-testable`**. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-migration-plan.md
cat claude_context/business-rules.md
cat scripts/seed_engine_config.py
cat app/ota_adapters/options_chain/catalog.py        # the screening (options-chain) adapter catalog = source of truth for names/units
cat app/insight_engine/validation.py                  # §6.6 validate_by_surface
cat app/insight_engine/engine_runtime.py
```

If you cannot locate the exact catalog/validation module by these paths, grep for the emitting catalog and `validate_by_surface` before proceeding — do not guess.

## Relevant Context — Do Not Deviate Without Escalation

Source: `insight_engine.md` §6.6 (named-value catalog) + epic invariants (OTA-679)
- **The adapter catalog is the sole source of truth for named-value names and units.** The seed conforms to the adapter, never the reverse — with the one documented exception of mismatch #2, which is a confirmed phantom in the seed.
- **Fail-closed. No compensating fallbacks. No hardcoded literals. Single scoring path.**
- **No `if strategy_key ==` branching** anywhere.

Source: OTA-847 Phase 0 (complete, accepted) + Phase 0.5 contract
This bug is the root cause of the **"Trades returns no recommendations"** regression: seeded screening named-values/units do not match the options-chain adapter's emitted catalog, so candidates fail data-completeness and are dropped before scoring/verdict. Scope is **four** mismatches (the ticket title lists three; the body is authoritative at four):

| # | Named value | Disposition (the contract) |
|---|---|---|
| 1 | `delta` vs `long_delta`/`short_delta` | **TR:** re-point `delta_quality`'s delta input `delta` → `long_delta`. **WG:** **remove** the `delta` dep entirely (gated on Phase 0.5-A). **LT/SP:** no change. |
| 2 | `cushion_vs_atr_ratio` → `cushion_vs_atr` | Pure rename; re-point the gate ref. This collapses the **OTA-832 phantom** (the distinction was introduced by OTA-832, not the adapter). |
| 3 | `cushion_pct` units (fraction→percent) | Rescale the `cushion_of_price` junction params by **×100 the existing values** — do NOT hand-type new bounds. Plus the cushion-**penalty** twin if Phase 0.5-B confirms it. |
| 4 | `earnings_days_past_expiry` | **DESCOPE.** Remove from the screening data-completeness set so it stops dropping candidates. Do NOT re-point to `dte_after_earnings` — that is sign-inverted against LT's load-bearing 7-day earnings buffer and is tracked in **OTA-849**. Leave a one-line seed rationale referencing OTA-849. |

## Phase 0.5 — Read-only confirm gate (HARD STOP)

Make NO edits. Confirm A–C, then STOP and report.

- **A — WG delta non-load-bearing.** Grep every live screening rule/junction for a consumer of WG's `delta` named value. Removal is valid only if **no** live rule consumes it. If a consumer exists, STOP.
- **B — cushion-penalty twin.** The graduated cushion-penalty adjustment rules (migration plan S4.3 / S6.4, thresholds 1.0% / 2.0%) also consume cushion. Confirm whether those thresholds are seeded in **fraction** (0.01 / 0.02) while `cushion_pct` is confirmed **percent**. If yes, they are a second instance of mismatch #3 and must be rescaled in Phase 1; report it. If they're already in percent, say so.
- **C — §6.6 catalog-feed safety.** Read the OTA-818 / OTA-820 rationale for why the named-value-catalog check is currently dormant. Confirm that converting each adapter's `CatalogEntry` → `NamedValue` and feeding surface-scoped catalogs into `validate_by_surface` (Phase 4) is safe to enable for the **screening** surface. Report the expected blast radius for directional / position-health (those get a STOP-and-report in Phase 4, not a fix).

**GO only if** A confirms non-load-bearing · B is answered (twin present or not) · C confirms the screening feed is safe to wire. NO-GO and STOP on any failure.

## Scope (after GO)

**Phase 1 — Seed reconciliation (`scripts/seed_engine_config.py`):**
1. #1: re-point TR `delta_quality` input → `long_delta`; remove WG's `delta` dep.
2. #2: rename `cushion_vs_atr_ratio` → `cushion_vs_atr` at the gate ref.
3. #3: rescale `cushion_of_price` junction params ×100 the existing values; rescale the penalty twin too if Phase 0.5-B confirmed it.
4. #4: remove `earnings_days_past_expiry` from the screening data-completeness set; add a one-line rationale referencing OTA-849.
5. Reseed and verify a representative live credit-spread candidate passes data-completeness and reaches a verdict.

**Phase 4 — §6.6 recurrence guard (only if Phase 0.5-C was GO):**
1. Convert each adapter's `CatalogEntry` → `NamedValue`; feed surface-scoped catalogs into `validate_by_surface` so `NAMED_VALUE_MISSING` fires at load on future name/unit drift.
2. Boot and run surface validation.
3. **STOP-and-report rule:** if enabling the feed raises `NAMED_VALUE_MISSING` on the **directional** or **position-health** surfaces, that is latent drift on those surfaces — STOP, report the offending names, do NOT fix them here (each is its own bug). The screening fix is already committed from gate #1, so this cannot block the critical-path fix.

## Acceptance criteria
- #1–#3 seeded named-values/units match the adapter catalog exactly (`long_delta`/`short_delta`, `cushion_vs_atr`, `cushion_pct`; penalty twin resolved if confirmed).
- A representative live credit-spread candidate passes data-completeness and reaches a verdict through the real path.
- #4 carved out with a seed rationale referencing OTA-849.
- §6.6 named-value check fires on name/unit drift at load (screening surface).
- A regression fixture covers the previously-mismatched named values.
- No `if strategy_key ==` branching introduced.

## Out of scope
- The `negative_ev_gate` formula reds — that is **OTA-843** (Terminal B).
- Re-pointing `earnings_days_past_expiry` to `dte_after_earnings` — that is **OTA-849**.
- Any fix to directional / position-health named-value drift Phase 4 may surface — report only.
- `position_routes.py`, `position_monitor.py` — do not touch.

## Verification steps
QA Level 2 (engine-config seed + validation wiring). PowerShell:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts/seed_engine_config.py
pytest tests/integration/test_options_chain_adapter.py -q   # screening reaches verdict; exclude negative_ev_gate reds if OTA-843 hasn't landed
pytest tests/insight_engine -q                              # structural — confirm all three surfaces still boot
```
- Put the new named-value regression fixture in a **new** file, e.g. `tests/integration/test_screening_named_value_parity.py`, to avoid colliding with OTA-843's edits to `test_options_chain_adapter.py`.
- If OTA-843 has not yet landed, exclude the `negative_ev_gate` failures from your pass/fail judgment — they are 843's, not a regression you introduced.

## Commit instruction
Do NOT commit. Two manual gates:
- **Gate #1 (after Phase 1):** STOP. Summarize the staged diff (files, line counts) and the reach-verdict result. Don commits the screening fix (`OTA-847 fix:`).
- **Gate #2 (after Phase 4):** STOP. Report whether the §6.6 feed is clean across all three surfaces or surfaced drift. If clean, summarize for Don to commit (`OTA-847 feat:`). If it surfaced drift, report and await Don's call — do not commit a broken boot.

The commit-triggered automation transitions OTA-847 to Code & Test Complete; do not transition it yourself.

## Coordination footer
Independent of OTA-843's and OTA-846's files. OTA-843 should land first so the engine suite is honest; if it hasn't, exclude the `negative_ev_gate` reds from verification (above). Do not deploy — Don holds the deploy gate.

## Commit message template (Don)
```
OTA-847 fix: reconcile screening seed named-values/units to options-chain adapter catalog
OTA-847 feat: wire §6.6 named-value-catalog check into validate_by_surface
```
