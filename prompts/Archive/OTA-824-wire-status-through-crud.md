---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-824 — Wire `status` through the as-built OTA-782 strategy CRUD

> Wave-1.5 backend gap-fill (2026-06-03). OTA-782 (CRUD) shipped before the `status`
> column existed, so it neither reads nor writes `status`. **Blocked by OTA-822** (the
> column). Blocks OTA-784 (header status edit) and OTA-791 (`status=draft` drafts).

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: OTA-823 may run in parallel (disjoint files: 823 = list-read module; 824 = the 782 CRUD module). Confirm no shared file before parallelizing.
- Cross-terminal dependencies: **OTA-822 committed first** (the `status` column must exist).

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/insight_engine-schema-ddl.md     # §2 engine_strategies (incl. the OTA-822 status column)
```
Plus the as-built OTA-782 CRUD module (locate in Phase 0).

## Relevant Context — Do Not Deviate Without Escalation

**1. The gap.** OTA-782's strategy CRUD (raw async SQL via `app.models.session.async_session`, no ORM) was built without `status`. After OTA-822 adds the column, the CRUD must read/write it or OTA-784's header edits and OTA-791's drafts can't persist.

**2. Scope = extend, don't rebuild.** Touch only the existing 782 strategy CRUD path: the `StrategyRow` / `StrategyCreate` / `StrategyUpdate` Pydantic models and the `engine_strategies` INSERT / UPDATE / read-back SELECT column lists. No new ORM models; no migration (OTA-822 owns the column).

**3. status ↔ enabled invariant (enforced on write).** `status='active' ⇒ enabled=1`; `status IN ('inactive','deprecated','draft') ⇒ enabled=0`. `enabled` is **derived from `status`** on write — status is the input of record. Do not let a caller set an inconsistent (status, enabled) pair; derive `enabled`.

**4. Domain + default.** Reject `status` not in `{active, inactive, deprecated, draft}` with a 4xx. If `status` is omitted on create, default to `active` (matches the OTA-822 column default).

**5. Runtime untouched.** This is the write path only. The runtime loader (`AzureSqlConfigSource`, still filtering `enabled=1`) and OTA-783's load-validation are not modified.

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)
1. Locate the 782 strategy CRUD module + the `StrategyRow`/`Create`/`Update` models + the raw INSERT/UPDATE/SELECT for `engine_strategies`.
2. Confirm OTA-822 landed: `engine_strategies.status` exists. If not → STOP (blocked).
3. Confirm where the create/update sets `enabled` today (so the invariant derivation slots in cleanly).
Report GO or STOP.

## Acceptance criteria
- POST / PUT to the strategy CRUD accept and persist `status`; the read-back row includes it.
- Invariant holds on every write: active ⇔ enabled=1; inactive/deprecated/draft ⇒ enabled=0 (enabled derived from status).
- Invalid `status` → 4xx; omitted on create → `active`.
- No new ORM models; no migration; runtime loader and OTA-783 untouched.

## Out of scope
- The `status` column / migration (OTA-822); the admin list endpoint (OTA-823); the draft creation flow (OTA-791).

## Verification
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```
1. POST a strategy with `status='inactive'` → persisted; read-back shows `status='inactive'`, `enabled=0`.
2. PUT `status='active'` → read-back shows `enabled=1`.
3. POST with no `status` → defaults to `active`, `enabled=1`.
4. POST `status='bogus'` → 4xx.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer
OK to continue to OTA-784.md (editor shell — needs status writes + the OTA-823 selector). OTA-791 (drafts) also unblocks once this lands.

## Commit message template
```
OTA-824 feat: wire status through the as-built engine_strategies CRUD

- status added to StrategyRow/Create/Update + INSERT/UPDATE/SELECT
- status<->enabled invariant enforced on write (enabled derived from status); domain validated; default active
- no migration (OTA-822), no ORM, runtime loader untouched
```
