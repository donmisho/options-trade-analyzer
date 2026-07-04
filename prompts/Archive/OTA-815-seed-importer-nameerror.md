# OTA-815 — Fix seed importer NameError: verdict_bands

> **Ticket:** OTA-815 (Bug under Epic OTA-679; labels `insight-engine-migration`, `seed`).
> Prerequisite for OTA-832 (canonical reseed) and the whole engine-config hydration chain.
> Narrow fix — restore the seed run only; **no** rule/registry/lookup content changes.

## Terminal context
- This terminal: **Terminal A (single)**
- Concurrent terminals: **none** — touches `scripts/seed_engine_config.py`, the shared seed
  file. Do not run OTA-832 work in parallel; OTA-832 edits the same file and is gated on this.
- Cross-terminal dependencies: none upstream. Downstream: OTA-832 STOPs until this commits.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/insight_engine.md
```

Then inspect (read-only, Phase 0):

```
cat scripts/seed_engine_config.py   # focus: parse_workbook(); the verdict-bands parse path near line 426; build_formula_registry()
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: insight_engine.md §2.1 (tables are the source of truth)**
`Scoring Parameters.xlsx` is a build-time seed; the tables are authoritative after import. This
fix restores the seed importer only. It must NOT change any rule, registry, or lookup content —
the diff is confined to the broken variable reference.

**Source: OTA-815 (symptom)**
`parse_workbook()` raises `NameError: name 'verdict_bands' is not defined` at
`seed_engine_config.py:426`. The verdict-bands parse path references an unbound or renamed
variable. The seed cannot run.

**Source: OTA-815 (impact)**
While broken, `build_formula_registry()` (which scans `engine_rules.formula_ref`) cannot
execute, so the `('SHARED','formula_registry')` lookup cannot be regenerated or reseeded from
the workbook. Restoring the clean seed run is the whole job.

## Phase 0 — Read-only discovery, hard GO/NO-GO STOP

No edits. Confirm, then STOP and report GO or NO-GO.

1. Open `seed_engine_config.py` around line 426. Identify the exact unbound/renamed symbol in
   the verdict-bands parse path — is `verdict_bands` a renamed local, a missing assignment, or
   a typo for an existing variable in scope?
2. Confirm the correct fix is a pure reference/assignment correction — NOT a content or schema
   change.
3. Confirm `parse_workbook()` and `build_formula_registry()` are the only paths affected.

Report the offending line(s), the proposed minimal fix, and GO|NO-GO. STOP for approval.

## Scope

Correct the unbound `verdict_bands` reference in the verdict-bands parse path of
`parse_workbook()` so the seed importer runs cleanly. No other behaviour changes.

## Acceptance criteria

- `parse_workbook()` runs without `NameError`.
- `build_formula_registry()` executes (scans `engine_rules.formula_ref`) without error.
- A seed dry-run / load completes clean.
- Zero rule/registry/lookup content changes — the diff is confined to the verdict-bands parse path.

## Out of scope

- Canonicalizing `condition_expression` tokens, fixing `validate_expression`, reseeding, and
  removing the OTA-830 stopgap — all OTA-832.
- Any directional seed work (OTA-833).

## Verification steps

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts\seed_engine_config.py --dry-run   # use the script's actual dry-run/entrypoint flag
```
Confirm no `NameError`; `parse_workbook()` and `build_formula_registry()` complete. QA level: **Level 1**.

## Commit instruction

This ships as its own commit. Present the full diff and the verification output, then ask:
"I have been instructed to commit. Do you approve? (yes / no)". On approval, Don runs the commit
manually — Claude Code does not run `git commit`.

## Coordination footer

OK to continue to OTA-832 once this is committed. OTA-832 is gated on this fix.

## Commit message template (Don runs this)

```
OTA-815 fix: restore seed importer — bind verdict_bands in parse_workbook verdict-bands path
```
