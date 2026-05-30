---
allowedTools:
  - Read
  - Bash
  - Edit
---

# OTA-656 — D6 narrative drift threshold tweak (Phase 1 + Phase 2)

## Terminal context
- Single-terminal work (~30 minutes total)
- Two phases: Phase 1 is read-only inspection with a stop-and-report gate, Phase 2 is the edit + harness re-run + commit
- Concurrent terminals: none

## Required reading

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1

cat claude_context/CLAUDE.md
cat claude_context/business-rules.md
cat claude_context/prompt-style.md
```

Also read the OTA-653 supporting discovery for the D6 design intent (it was just archived as part of the OTA-653 ADR merge):

```powershell
cat docs/decisions/OTA-653-scoring-agent-discovery.md
```

(Look for Phase 5 — Determinism Analysis, specifically the D6 row.)

## Relevant Context — Do Not Deviate Without Escalation

**Source:** `docs/decisions/OTA-653-scoring-agent-discovery.md` (Phase 5 Determinism Analysis, D6 row)
- D6 (Narrative drift) is an **advisory** assertion, not blocking. Current threshold: `SequenceMatcher` ratio ≥ 0.85. Below this triggers a "narrative drift warning" on the harness output but does not fail the run.
- D6 is intended to detect substantive shifts in `claude_read` narrative content across runs. It is NOT intended to fire on routine LLM surface variance that does not change semantic content.

**Source:** Parent Story OTA-652 (QA harness) and Subtask OTA-656
- The most recent Phase 2 smoke against VOO/TSM/MMM/AAPL surfaced 20 false-positive D6 warnings. These are the data the threshold tune must clear.

**Source:** `CLAUDE.md` (Document Governance Rules) and `business-rules.md` (Validation Baseline section)
- The D6 threshold is part of the Validation Baseline. Tuning it is a **business rule change** and must be recorded in `business-rules.md` with a citation to OTA-656.

**Source:** `prompt-style.md` (Issue numbering discipline)
- Use OTA-656 in commit messages and the business-rules.md citation. Do not invent issue keys.

## Scope

Phase 1 inspects the false positives and proposes a new threshold. Phase 2 applies the change after Don approves.

### Phase 1 — Read-only inspection (STOP and report)

1. Locate the QA harness in the repo. Most likely under `tests/qa_harness/`, `app/harness/`, or similar — find the directory that contains the D6 assertion implementation.
2. Find the D6 threshold constant in the harness code. Note its current value (expected to be 0.85) and the file + line where it lives.
3. Locate the most recent Phase 2 smoke output that produced the 20 false-positive D6 warnings. This is likely under a directory like `tests/qa_harness/output/`, `harness_runs/`, or similar — find where the harness writes its reports.
4. Identify each of the 20 false positives by symbol + strategy + run pair. For each, capture:
   - The `SequenceMatcher` ratio between the two `claude_read` strings that triggered the warning.
   - A short qualitative note: does the difference look like semantic drift (real concern) or surface variance (false positive)? Surface variance examples: word reordering, synonym swaps, minor punctuation differences. Semantic drift examples: a verdict change, an inverted recommendation, a missing risk callout.
5. Propose a new threshold value that:
   - Clears all 20 false positives with at least 0.02 of margin (i.e., the **lowest** false-positive ratio observed, minus 0.02).
   - Stays at or above **0.65**. Below 0.65, D6 loses signal value and could let genuine semantic drift slip through silently.
   - If the lowest false-positive ratio is below 0.67, flag the conflict to Don — the threshold cannot be lowered enough to clear it without weakening the assertion too far. In that case, do not propose a number; recommend keeping the false positive and revising the underlying narrative-generation prompt instead.
6. **STOP. Report findings to Don. Do not edit any code yet.**

The Phase 1 report should be a short table:

```
Symbol  Strategy  Ratio   Verdict
VOO     SP        0.71    surface variance
VOO     WG        0.79    surface variance
TSM     TR        0.66    BORDERLINE — review
...
```

Plus the recommended new threshold (single value) and the rationale (1-2 sentences).

### Phase 2 — Apply (only after Don approves Phase 1 findings)

1. Update the D6 threshold constant in the harness implementation. The new value comes from Phase 1's recommendation, as confirmed by Don.
2. Re-run the harness Phase 2 smoke against the same 5-symbol universe (VOO, TSM, MMM, AAPL, plus the fifth symbol used in the prior run — identify from the Phase 1 inspection). Capture the output.
3. Confirm:
   - All 20 prior false positives now clear (zero D6 warnings).
   - No previously-clearing pair has flipped into warning. The harness report should show the same set of A1–A10 / D1–D5 assertion outcomes as the prior run.
4. Update `claude_context/business-rules.md` Validation Baseline section to document the new D6 threshold. Add a line like:
   - `D6 (narrative drift, advisory): SequenceMatcher ratio ≥ <NEW_VALUE>. Lowered from 0.85 per OTA-656 to suppress surface-variance false positives without weakening semantic-drift detection.`
   - If the Validation Baseline section does not yet exist, add it as a new subsection at the appropriate location in `business-rules.md`.

## Acceptance criteria

- D6 threshold constant in the harness is updated to the new value confirmed in Phase 1.
- Harness Phase 2 smoke re-run is clean: zero D6 warnings on the same 5-symbol input that previously produced 20.
- No previously-clearing assertion (D1–D5, A1–A10) has flipped into warning.
- `business-rules.md` Validation Baseline section reflects the new D6 threshold with a citation to OTA-656.
- No other harness assertions were modified.
- No scoring code, frontend code, or non-harness backend code was modified.

## Out of scope

- Tuning any other harness assertion (D1–D5, A1–A10).
- Re-running other harness phases (Phase 1 Discovery, Phase 3, etc.).
- Modifying SKILL.md prompts (revising the narrative generation prompt is a separate Story if Phase 1 surfaces a need).
- Touching OTA-652 itself.
- Modifying the QA harness orchestration, scheduling, or reporting structure.

## Verification steps

1. `cat <harness_path>/...` (path discovered in Phase 1) — confirm the threshold constant has the new value.
2. Re-run the harness Phase 2 smoke and capture the output. Diff the new report's D6 section against the prior report's D6 section. Expect: 20 → 0 D6 warnings, all other assertions identical.
3. `cat claude_context/business-rules.md` — confirm Validation Baseline section reflects the new threshold and the OTA-656 citation.
4. `git diff` — confirm only the harness threshold file and `claude_context/business-rules.md` show changes.

## Commit instruction

I have been instructed to commit after Phase 2 completes successfully. Do you approve? (yes / no)

## Coordination footer

Independent — no downstream dependency.

## Commit message template (if committing)

```
OTA-656 fix(harness): lower D6 narrative drift threshold to <NEW_VALUE> to clear surface-variance false positives

- Phase 1 inspection: 20 false-positive D6 warnings against VOO/TSM/MMM/AAPL Phase 2 smoke
- Lowest false-positive ratio observed: <X>
- New threshold: <NEW_VALUE> (clears with 0.02 margin; remains above the 0.65 signal floor)
- business-rules.md Validation Baseline updated with new threshold and OTA-656 citation
- No other harness assertions modified
```
