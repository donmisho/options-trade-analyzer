# OTA-835 — screening_verdicts lookup carries band thresholds — defer threshold authority to per-strategy verdict_band_set

> **This prompt is Phase 0 only — read-only discovery with a hard STOP.** It makes no edits. Its job is to determine whether anything reads band thresholds off the `screening_verdicts` lookup, then recommend Path A (drop) or Path B (repoint then drop). The implementation prompt is authored after Don picks the path.

## Terminal context
- This terminal: single terminal (no parallel work).
- Concurrent terminals: none. Phase 0 is read-only and safe to run anytime, but the **implementation** that follows edits `scripts/seed_engine_config.py` and must NOT run concurrently with OTA-832 or OTA-833, which edit the same file.
- Cross-terminal dependencies: implementation lands after OTA-832 (canonical reseed) and ideally after OTA-833, riding the reseed OTA-832 already performs. Phase 0 has no dependency.

## Required reading
Before anything else:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-schema-ddl.md
cat claude_context/insight_engine-migration-plan.md
cat claude_context/business-rules.md
```

## Relevant Context — Do Not Deviate Without Escalation

```
Source: insight_engine.md § 3.8 (Verdict bands)
Rule: Verdict bands are a per-strategy mapping from final score to a categorical
verdict. The prior universal EXECUTE/WAIT/PASS thresholds (70/50) hardcoded in
evaluation_routes.py were called out as a VIOLATION of tables-as-source — not
evidence that bands should be universal. Bands are configurable per strategy from
day one. The per-strategy source of truth is engine_strategies.verdict_band_set.

Source: insight_engine.md § 4.1 (Phase 7 — Verdict band lookup)
Rule: The engine maps the final adjusted score to a verdict via THE STRATEGY'S
bands. There is one band-lookup code path; no second path produces a verdict.

Source: insight_engine-schema-ddl.md (engine_strategies)
Fact: verdict_band_set is a NOT NULL per-strategy JSON column on engine_strategies.
This is the authoritative band store the Phase-7 lookup reads.

Source: Epic OTA-679 acceptance criteria
Rule: All rule content — thresholds, weights, gate behaviour, ordering, verdict
bands — is resolvable from the runtime tables, from exactly one place. No second
code path produces a verdict. No `if strategy_key ==` branches in engine code.

Source: OTA-815 dry-run finding (the reason this story exists)
Fact: scripts/seed_engine_config.py builds a `screening_verdicts` lookup whose
per-row payload carries thresholds, not just labels:
    sort_order=1  EXECUTE  {'min_score': 70, 'max_score': 100}
    sort_order=2  WAIT     {'min_score': 50, 'max_score': 69.99}
    sort_order=3  PASS     {'min_score': 0,  'max_score': 49.99}
    sort_order=4  WAIT_FOR_EARNINGS  {'label': ..., 'kind': 'HALT_VERDICT', ...}
This is a second, OTA-wide copy of thresholds that already live per-strategy in
verdict_band_set. The duplication predates OTA-815 and OTA-773; OTA-815 only
restored the loop that writes it. This story decides what the payload should be.
```

## Scope (read-only discovery)

Setup:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

Answer all six questions. Capture exact `file:line` evidence for each.

1. **Lookup builder.** Locate the `screening_verdicts` lookup builder in `scripts/seed_engine_config.py` (the loop restored under OTA-815, ~line 426). Record the lookup's full key — `(scope, name)` — and the exact per-row payload dict written for each band and for the halt verdict(s).

2. **Lookup storage + read mechanism.** Identify the lookups table/model and the runtime helper(s) that read a lookup by key (e.g. a `get_lookup` / lookup-resolver). Record the function name and signature.

3. **Consumers — the decision input.** Enumerate every reader of this lookup across the repo. Run both searches and account for every hit:

   ```powershell
   rg -n "screening_verdicts" app scripts web
   rg -n "min_score|max_score" app scripts web
   ```

   (PowerShell fallback if `rg` is unavailable: `Get-ChildItem -Recurse app,scripts,web -Include *.py,*.js,*.jsx | Select-String -Pattern 'screening_verdicts','min_score','max_score'`.)

   For each hit, classify it: **writes** the lookup (the seed) vs **reads** the lookup, and if it reads, whether it reads the **thresholds** (`min_score`/`max_score`) or only **label / sort_order / kind**.

4. **Phase-7 source confirmation.** Trace the engine's Phase-7 verdict assignment and confirm it reads the per-strategy `verdict_band_set` — NOT the `screening_verdicts` lookup. Cite the code path (`file:line`).

5. **Vestigial check.** State plainly whether the `screening_verdicts` lookup is read by anything at all, or whether it is written by the seed and never read.

6. **Recommendation.** Based on 3–5, recommend:
   - **Path A — drop thresholds** if NO reader consumes `min_score`/`max_score` from the lookup. Payload becomes label + `sort_order` (+ `kind`); threshold authority deferred entirely to `verdict_band_set`.
   - **Path B — repoint then drop** if any reader consumes the thresholds. Name the exact reader(s) and the repoint target (`verdict_band_set` or a strategy-scoped band resolver).

## Acceptance criteria (for this discovery phase)
- Lookup key and exact payload shape recorded from source.
- Every `screening_verdicts` / `min_score` / `max_score` hit in `app/`, `scripts/`, `web/` is listed and classified (writer / threshold-reader / label-only-reader).
- Phase-7 source confirmed as `verdict_band_set` with a cited code path.
- A single recommended path (A or B) with evidence.

## Out of scope
- Any edit. No file is modified in this phase.
- Changing `verdict_band_set` or the Phase-7 lookup.
- The Verdict Bands UI editor (OTA-788).
- Any reseed (the implementation rides the OTA-832 reseed).
- OTA-832 / OTA-833 work.

## Verification steps
- Re-run the two searches and confirm the consumer list is exhaustive — zero unclassified hits.
- Confirm the Phase-7 citation actually resolves `verdict_band_set` (open the cited lines).
- If discovery contradicts the premise — e.g. Phase-7 reads the `screening_verdicts` lookup rather than `verdict_band_set`, or the lookup is the authoritative engine-consumed source — this is **NO-GO**: stop, do not recommend a drop, and report the contradiction for reframing.

## Commit instruction
I have been instructed NOT to commit. This is a read-only discovery phase; no files are modified, so there is nothing to commit.

## Coordination footer
STOP after the report. Present findings (Q1–Q5) and the recommended path (Q6) to Don, then wait. Do not begin implementation — the implementation prompt is authored only after Don picks Path A or Path B.

## Commit message template
(none — read-only phase, no commit)
