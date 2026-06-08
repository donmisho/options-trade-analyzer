---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-822 — Add `status` lifecycle column to `engine_strategies`

> Wave-1.5 backend gap-fill (surfaced by OTA-784 Phase 0, 2026-06-03). Migration + backfill +
> doc only — CRUD wiring is OTA-824. Runs FIRST in the F13 chain — blocks OTA-823, OTA-824, OTA-784.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: none upstream. Downstream OTA-823 / OTA-782 / OTA-784 depend on this. Migration is its own deliberate commit.

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/deployment-workflow.md           # migration runbook
cat claude_context/architecture-plan.md             # schema-migration discipline
cat claude_context/insight_engine-schema-ddl.md     # §2 engine_strategies (the table + Change Log to update)
```

## Relevant Context — Do Not Deviate Without Escalation

**1. The gap.** `engine_strategies` has only `enabled: bool`; no `status` column exists. The whole F13 admin UI assumes one (OTA-784 edits it; OTA-781/790/791 use `status=draft`).

**2. Column.** Add `status varchar(16) NOT NULL DEFAULT 'active'`. Domain (enforced at the write/model layer, **no DB CHECK** — mirrors OTA-709's "validate at load, not via DB constraint"): `active | inactive | deprecated | draft`. active/inactive/deprecated per OTA-525 lifecycle vocabulary; `draft` reserved for the OTA-791 preview mechanism.

**3. Migration discipline (OTA-819 lesson).** One additive Alembic migration with a **unique revision id** and a correct `down_revision` chaining after the current head. Before writing: `alembic heads` must resolve to a single head; after: `alembic upgrade head` applies cleanly and `alembic downgrade` drops the column. Do not reuse any existing revision id.

**4. Backfill.** In the migration (or its data step): `enabled=1 → status='active'`, `enabled=0 → status='inactive'`.

**5. status ↔ enabled invariant.** `status='active'` ⇔ `enabled=1`; `status IN ('inactive','deprecated','draft')` ⇒ `enabled=0`. **Do NOT change the runtime loader** — `AzureSqlConfigSource` keeps filtering `enabled=1`, so non-active/draft rows stay excluded from the live engine and the OTA-818 keystone is untouched. The CRUD layer (OTA-824) enforces the invariant on writes; this story only defines it.

**6. Models / CRUD wiring → OTA-824 (out of scope here).** Do NOT touch the OTA-782 Pydantic models (`StrategyRow`/`Create`/`Update`) or the CRUD SQL — wiring `status` through the as-built CRUD is OTA-824. This story is migration + backfill + doc only.

**7. Doc update (same commit).** Update `insight_engine-schema-ddl.md` §2 `engine_strategies` to show the `status` column, with a dated Change Log entry — same-commit, per the OTA-709 precedent. This makes OTA-782's "all columns per §2" AC include `status` automatically.

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)
1. Confirm `engine_strategies` currently has no `status` column (only `enabled`).
2. `alembic heads` → single head; capture the current head revision for `down_revision`.
3. Confirm the Alembic migrations directory + naming convention for the new revision.
4. Confirm `AzureSqlConfigSource` filters `enabled=1` (so this story need not touch it).
Report GO or STOP.

## Acceptance criteria
- `engine_strategies.status varchar(16) NOT NULL DEFAULT 'active'` after `alembic upgrade head`; downgrade drops it.
- `alembic heads` → single head; new revision id unique.
- Backfill: `enabled=1 → active`, `enabled=0 → inactive`.
- `insight_engine-schema-ddl.md` §2 updated + dated Change Log entry.
- Runtime read path unchanged (`AzureSqlConfigSource` still `enabled=1`).

## Out of scope
- Pydantic models + CRUD write/read of `status` + invariant enforcement (OTA-824); admin list endpoint (OTA-823); switching the loader to `status`.

## Verification
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
alembic heads        # expect 1
alembic upgrade head # clean
```
Then confirm the column + backfilled values, and `alembic downgrade -1` drops it cleanly (then re-upgrade).

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)
*(Migration + backfill + doc, one commit. Stage and present the message; Don executes.)*

## Coordination footer
OK to continue to OTA-823.md and OTA-824.md (both need this column; disjoint files, can run in parallel).

## Commit message template
```
OTA-822 feat: add status lifecycle column to engine_strategies

- status varchar(16) NOT NULL DEFAULT 'active' (active/inactive/deprecated/draft); migration + backfill from enabled
- status<->enabled invariant defined; runtime loader unchanged (still filters enabled=1)
- insight_engine-schema-ddl.md §2 updated (CRUD wiring is OTA-824)
```
