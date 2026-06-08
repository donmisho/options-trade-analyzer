---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-823 — Owner-scoped admin strategy list endpoint

> Wave-1.5 backend gap-fill (OTA-784 Phase 0, 2026-06-03). The admin selector needs to list
> strategies with owner/enabled/status; no such endpoint exists. **Blocked by OTA-822**
> (needs the `status` column). Blocks OTA-784.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: **OTA-822 committed first** (the `status` column must exist). Runs before OTA-784.

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/auth-process.md                  # require_read dependency
cat claude_context/architecture-plan.md
cat claude_context/insight_engine-schema-ddl.md     # §2 engine_strategies row shape
```

## Relevant Context — Do Not Deviate Without Escalation

**1. The gap.** No strategy list endpoint exists. OTA-762 is the restart-gated, SCREENING-only, owner-blind runtime projection over the hydrated config; OTA-782's CRUD returns one row per write. The admin selector (OTA-784) has nothing to call.

**2. What to build.** `GET /api/v1/config/strategies/admin` returning the full strategy table-row shape for **all** surfaces (not SCREENING-only): `owner_app_id`, `strategy_key`, `display_name`, `enabled`, `status`, `consumer_surface`, `compatible_structures`, `dte_min`, `dte_max`, `verdict_band_set`.

**3. Read current DB state — not the hydrated projection.** Query `engine_strategies` directly via `app.models.session.async_session` (raw async SQL, **no new ORM models** — same data-access pattern as OTA-782). This must reflect just-saved writes immediately, unlike OTA-762's restart-gated projection. This is intentionally a *different* read path from the runtime config accessor.

**4. Owner scoping.** Include `owner_app_id` on every row so the UI can render `OTA` rows editable and `SHARED` rows read-only. Return both; do not filter SHARED out.

**5. Auth.** `Depends(require_read)` (`app/auth/dependencies.py`).

**6. Module placement.** Co-locate with the OTA-782 admin CRUD module if it exists at run time; otherwise a dedicated admin-read module. **Do NOT** add this to OTA-762's `engine_config_routes.py` runtime-projection route — keep the current-DB-state admin read distinct from the hydrated-config read.

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)
1. Confirm OTA-822 landed: `engine_strategies.status` exists. If not → STOP (blocked).
2. Does the OTA-782 admin module exist yet (for co-location)? If not, pick the dedicated admin-read module.
3. Confirm the `async_session` raw-SQL pattern and `require_read` import path.
Report GO or STOP.

## Acceptance criteria
- `GET /api/v1/config/strategies/admin` returns all strategies across surfaces with `owner_app_id`, `enabled`, `status`, and header/band fields, read via `async_session` (reflects just-saved writes — not restart-gated).
- `SHARED` rows returned and tagged by `owner_app_id`; `OTA` rows tagged editable.
- Guarded by `require_read`.
- Distinct route/module from the OTA-762 runtime projection (grep confirms it does not reuse the hydrated-config accessor).

## Out of scope
- The `status` column (OTA-822); CRUD writes (OTA-782); the selector UI (OTA-784).

## Verification
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```
1. Boot; `GET /api/v1/config/strategies/admin` (authenticated) returns all strategies across surfaces with owner/enabled/status.
2. Unauthenticated → 401.
3. Edit a row in the DB and confirm the endpoint reflects it without a restart (proves current-state, not hydrated).

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer
OK to continue to OTA-782.md (CRUD) and then OTA-784.md (the shell, which consumes this).

## Commit message template
```
OTA-823 feat: owner-scoped admin strategy list endpoint (GET /config/strategies/admin)

- reads current DB state via async_session (not OTA-762 restart-gated projection); all surfaces
- returns owner_app_id/enabled/status + header/band fields; require_read
```
