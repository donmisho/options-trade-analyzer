---
allowedTools: [Read, Grep, Glob, Edit, Bash]
---

# OTA-769 (resume) — Remove hardcoded TR delta center (seed-side only)

> Resume prompt. Phase 0 already ran and returned a **conditional** go. This
> prompt narrows Phase 0 to the two items it left open (delta_quality membership
> + value-sourcing approach), then executes the seed-side change. Do NOT
> re-derive the full Phase 0 — the file/line findings below are carried forward
> from it. `Edit` is in allowedTools for Phase 1 only; Phase 0 is read-only and
> ends in a hard STOP.

## Terminal context
- This terminal: single focused session
- Concurrent terminals: none
- Cross-terminal dependencies: none for this story. **Global ordering:** OTA-779
  (delete legacy `strategy_scorer.py`) MUST NOT run until this and all other
  OTA-766 seed-side stories have landed. That gate lives in OTA-779's prompt, not
  here.

## Required reading
Before any changes:

    cat claude_context/CLAUDE.md
    cat claude_context/insight_engine.md
    cat claude_context/insight_engine-migration-plan.md
    cat claude_context/insight_engine-schema-ddl.md
    cat claude_context/business-rules.md

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-769 descope (2026-05-30) — seed-side only**
This story owns ONLY the junction-row seed. The code-side criteria (removing the
`strategy_key == "trend-rider"` branch; eliminating literals / the implicit
non-TR default) are OWNED BY OTA-779 (legacy scorer deletion). Do NOT edit
`app/analysis/strategy_scorer.py` in this story.

**Source: Phase 0 (carried forward) — `app/analysis/strategy_scorer.py:382-387`**

    if strategy_key == "trend-rider":
        delta_center = (float(cfg.get("delta_min", 0.50)) + float(cfg.get("delta_max", 0.70))) / 2
        delta_half_range = max(0.10, (float(cfg.get("delta_max", 0.70)) - float(cfg.get("delta_min", 0.50))) / 2)
    else:
        delta_center = 0.10
        delta_half_range = 0.10

Effective values (no user config override): TR 0.60 / 0.10 ; LT (else) 0.10 / 0.10.

**Source: Phase 0 (carried forward) — `app/options_rules/screening/scoring_formulas.py:200-215`**
The Delta Quality formula ALREADY reads from params:

    center = params.get("delta_center", 0.35)
    half_range = params.get("delta_half_range", 0.15)

The `0.35 / 0.15` fallbacks match NEITHER TR nor LT. Any strategy whose
delta_quality junction row lacks these params will silently score on the wrong
fallback once OTA-779 removes the scorer. This is the regression risk Phase 0
task 1 must close.

**Source: Phase 0 (carried forward) — `scripts/seed_engine_config.py:1013-1016`**
`delta_center` / `delta_half_range` are already in the rule parameter_schema:

    "parameter_schema": {
        "delta_center": {"type": "number", "description": "Peak delta target"},
        "delta_half_range": {"type": "number", "description": "Half-width of gaussian peak"},
    },

The workbook parser maps Low/High columns to `params["low"]`/`params["high"]`
only — it does NOT currently populate delta_center/delta_half_range. Today those
params are absent from the junction rows and the values reach the formula via the
scorer's runtime injection, not the junction row.

**Source: re-sequence decision (2026-05-30) — order-safety invariant**
Seed the EXACT carry-forward values (TR 0.60/0.10, LT 0.10/0.10). Because they
equal what the scorer injects today, behavior is identical whether the seeded
junction value or the scorer-injected value wins during the window where 769 has
shipped but 779 has not. Do NOT round, re-center, or "improve" these numbers —
exact carry-forward is what makes 769 safe to land before 779.

## Phase 0 — read-only, hard STOP (narrowed)

Resolve both items and STOP for Don's go before any write.

**1. delta_quality strategy membership (REGRESSION GATE).**
Enumerate every strategy that has a `delta_quality` junction row (query the
junction table / seed config — read only).
- If membership == {trend-rider, lottery-ticket}: seed set is TR + LT; proceed to
  the value table below after go.
- If membership ⊋ {TR, LT} (e.g. SP/WG also carry delta_quality): each extra
  strategy was getting the old `else` 0.10/0.10 and will regress to 0.35/0.15
  once OTA-779 lands. STOP and report the full list, and propose seeding each
  extra strategy at 0.10/0.10. Don approves the expanded seed set before you
  proceed.

**2. Value-sourcing approach (DESIGN GATE — Don decides).**
Report whether `Scoring Parameters.xlsx` + the workbook parser can carry named
params (delta_center / delta_half_range) per strategy WITHOUT structural rework
beyond seed-side.
- **Preferred** (project principle — config is the source of truth, no hardcoded
  literals): the values live in the workbook as data, the parser reads them, the
  seed transcribes them to junction params.
- **Fallback** (only if workbook extension is non-trivial): set the values via a
  post-processing hook in `seed_engine_config.py` (`reconcile_divergences` /
  `_inject_junctions`), and flag a follow-up so the literal does not become a
  permanent second home for hardcoded values.

Report feasibility + your recommendation. STOP for Don's pick.

### Carry-forward value table (use after Phase 0 go)
| strategy        | delta_center | delta_half_range | source |
|-----------------|--------------|------------------|--------|
| trend-rider     | 0.60         | 0.10             | strategy_scorer.py:383-384 — computed from TR's configured delta_min/delta_max. **Confirm against the LIVE config row, not the 0.50/0.70 code default.** |
| lottery-ticket  | 0.10         | 0.10             | strategy_scorer.py:386-387 (else branch) |
| (any extra from task 1) | 0.10 | 0.10        | matches old else branch |

## Scope (Phase 1 — after go)
Populate `delta_center` / `delta_half_range` on the `delta_quality` junction rows
for TR, LT (and any extras approved in Phase 0 task 1), using the sourcing
approach Don picked in Phase 0 task 2, with the exact carry-forward values above.

## Acceptance criteria
- TR and LT (and any approved extras) each source `delta_center` /
  `delta_half_range` from their own `delta_quality` junction rows.
- Seeded values exactly equal the carry-forward table. TR's value is confirmed
  against its live configured delta_min/delta_max, not the code default.
- No `delta_quality` junction row previously covered by the scorer is left without
  these params (nothing newly falls through to the 0.35/0.15 formula fallback).

## Out of scope
- `app/analysis/strategy_scorer.py` — branch removal is OTA-779. Do not edit.
- `app/options_rules/screening/scoring_formulas.py` — do not change the formula or
  its fallbacks here.
- Any recalibration of delta values. Exact carry-forward only.

## Verification steps
1. cd + activate (PowerShell):

        cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
        .\venv\Scripts\Activate.ps1

2. Run the seed, then confirm the OTA-698 loader hydrates delta_center /
   delta_half_range onto the TR / LT (+extras) delta_quality junction rows.
3. Confirm OTA-699 startup validation passes (params present + schema-valid).
4. **Equivalence check (REQUIRED):** compute the delta_quality sub-score for one
   TR candidate and one LT candidate before vs after the seed. Scores must be
   identical (exact carry-forward). Report both numbers.
5. **Regression sweep:** confirm no strategy's delta_quality row now resolves to
   the 0.35/0.15 fallback.

## Commit instruction
Do NOT run `git commit` (Don commits manually). When verification passes, stage
the change, present the diff + the proposed commit message, and ask:
**"Verification passed. Approve commit? (yes / no)"** — on yes, Don performs the
commit.

## Coordination footer
**Independent — no downstream dependency.** (Reminder: OTA-779 must not run until
all OTA-766 seed-side stories, including this one, have landed; that gate lives in
OTA-779's prompt.)

## Commit message template
OTA-769 feat: seed per-strategy delta_center/delta_half_range on delta_quality junction rows (TR/LT)

## QA level
**Medium.** Pure seed/config change with exact carry-forward, so runtime behavior
should be unchanged — but it touches live scoring inputs, so the equivalence check
(step 4) and the regression sweep (step 5) are mandatory, not optional.
