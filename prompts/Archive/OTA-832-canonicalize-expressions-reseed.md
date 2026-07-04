# OTA-832 — Canonicalize condition_expression to §6.3, honor formula_ref, reseed, restore fatal hydration

> **Ticket:** OTA-832 (Bug under Epic OTA-679). The real engine-config hydration fix. **Gated on
> OTA-815.** Removes the OTA-830 non-fatal stopgap and restores fatal step-6d hydration. Keystone:
> no engine consumer is live until this lands — engine routes currently 500 because `_runtime`
> stays `None`. Unblocks OTA-833, OTA-765, OTA-759, OTA-760.

## Terminal context
- This terminal: **Terminal A (single)**
- Concurrent terminals: **none** — edits `scripts/seed_engine_config.py`,
  `app/insight_engine/expressions.py`, and the step-6d path in `app/main.py`. Shared seed file;
  no parallel seed work.
- Cross-terminal dependencies: **STOP until OTA-815 is committed** (the seed must run clean before
  a corrected reseed). Downstream: unblocks OTA-833 (directional seed), OTA-765 (directional
  route), OTA-759 / OTA-760.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
```

Then inspect (read-only, Phase 0):

```
cat scripts/seed_engine_config.py
cat app/insight_engine/expressions.py      # validate_expression; the §6.3 closed operator set
# locate step-6d hydration in app/main.py and the OTA-830 try/except around init_engine_runtime()
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: insight_engine.md §2.1 (tables are the source of truth)**
The seed produces canonical config; the tables are authoritative. **Do NOT patch config in code
just to pass validation.** The fix is in the seed output and the validator, not in hand-edited rows.

**Source: insight_engine.md §6.3 (expression library — closed operator set)**
A rule's `condition_expression` must be a token form drawn from the engine's closed operator set.
Human-readable phrases (e.g. "ACCEPT IF DTE <= threshold", "ACCEPT IF (stock_price) is BETWEEN")
are not valid and fail `validate_expression`.

**Source: OTA-832 (the breakage)**
Startup hydration (`app/main.py` step 6d) rejects the live OTA-680 seed. Of 62 rules bound to the
4 active strategies: 0 canonical, 16 null, 17 formula-ref (the validator ignores `formula_ref` —
a bug), 29 non-canonical with no `formula_ref`. The 29 must be canonicalized; some require new
derived named-values or a `formula_ref`.

**Source: OTA-832 / OTA-830 (the stopgap)**
OTA-830 wrapped step-6d `init_engine_runtime()` in a non-fatal try/except so the app boots, but
`_runtime` stays `None` and every route resolving `get_engine_runtime()` degrades to 500. This
story removes the try/except and restores LOUD/FATAL hydration (the OTA-818 design intent).

## Phase 0 — Read-only discovery, hard GO/NO-GO STOP

No edits. Confirm, then STOP and report GO or NO-GO.

1. Enumerate the §6.3 closed operator set from `expressions.py` and `insight_engine.md` §6.3.
2. Pull the 29 non-canonical `condition_expression` values (no `formula_ref`) bound to active
   strategies. For each, draft the canonical token mapping. **Flag any that cannot be expressed
   atomically** and require a NEW derived named-value or a `formula_ref` — these are the risk items.
3. Reproduce the validator bug: confirm `validate_expression` currently ignores `formula_ref`
   rows (the 17 formula-ref rules pass without being validated as formula refs).
4. Locate the OTA-830 try/except around `init_engine_runtime()` in `app/main.py` step 6d.
5. **Confirm OTA-815 is committed** and the seed runs clean. If not → NO-GO STOP.

Report: the operator set, the 29-row canonicalization table, any new named-values / `formula_ref`s
required, the `validate_expression` fix point, the stopgap removal point, and GO|NO-GO. STOP.

## Scope

1. Canonicalize the 29 non-formula `condition_expression` values to the §6.3 closed operator set,
   adding derived named-values / `formula_ref`s where a phrase cannot be expressed atomically.
2. Fix `validate_expression` to honor `formula_ref` rules (currently ignored).
3. Update `scripts/seed_engine_config.py` to emit canonical tokens.
4. Reseed `engine_*` config from the corrected seed.
5. Remove the OTA-830 non-fatal try/except around step-6d `init_engine_runtime()`; hydration is
   fatal again.

## Acceptance criteria

- Every seeded `condition_expression` is a canonical §6.3 token form OR a valid `formula_ref`;
  zero non-canonical-without-`formula_ref` rules remain.
- `validate_expression` honors `formula_ref` rules.
- `scripts/seed_engine_config.py` emits canonical tokens; a clean reseed populates `engine_*` with
  canonical config.
- Startup hydration succeeds against the reseeded config; `get_engine_runtime()` returns a live
  runtime; engine routes no longer 500.
- The OTA-830 try/except is removed; step-6d hydration is fatal again (bad config crash-loops
  loudly, as designed).

## Out of scope

- The directional three-objective seed (OTA-833) — separate, gated on this.
- Any new strategy/rule content beyond canonicalizing existing expressions and the derived
  named-values / `formula_ref`s those canonicalizations require.

## Verification steps

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts\seed_engine_config.py          # clean reseed from corrected seed
# start the app; confirm step-6d hydration succeeds with no try/except swallow
```
Confirm: `get_engine_runtime()` returns a live runtime; an engine route returns 200 (not 500); a
deliberately bad expression is rejected fatally at load. QA level: **Level 2** — config-load /
validation + startup hydration change; exercise startup hydration and at least one screening engine
route end to end. Document the Level in the commit body.

## Commit instruction

This ships as its own commit (after OTA-815). Present the full diff, the Phase 0 canonicalization
table, and the verification output, then ask: "I have been instructed to commit. Do you approve?
(yes / no)". On approval, Don runs the commit manually — Claude Code does not run `git commit`.

## Coordination footer

STOP until OTA-815 is committed before starting. After this commits and the engine starts clean,
OTA-833 (directional seed) and OTA-765 (directional route) are unblocked.

## Commit message template (Don runs this)

```
OTA-832 fix: canonicalize engine condition_expression to §6.3, honor formula_ref in validator, reseed, restore fatal hydration
```
