---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
---

# OTA-542 — Architecture #7: Data Isolation Hardening (DELETE /recommendations bug + CRUD audit + contract test)

## Terminal context
- This terminal: **Terminal B**
- Concurrent terminals: **A (OTA-515 + OTA-549/509/510), C (OTA-560 frontend), D (governance docs)**
- Cross-terminal dependencies:
  - **No file contention with A or C** in expected scope (A touches scoring/validators, C is frontend-only).
  - **`app/database.py` exclusivity:** Terminal B holds exclusive write access to `app/database.py` for this batch. If Phase 1 audit determines no `database.py` change is required, release that exclusivity by reporting it in the diagnostic. Other architecture stories targeting `database.py` (OTA-541, OTA-538, OTA-543) are deferred and do not run in parallel.
  - **`architecture-plan.md` is read-only here.** OTA-542's spec says §2 is "already drafted; verify it matches implementation." Verify only — do not modify the SoT doc.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/auth-process.md
```

Then survey the route surface:

```
ls -la app/api/
grep -rn "@router\.\(get\|put\|patch\|delete\|post\)" app/api/ | grep "{"
grep -rn "user_id\s*=\s*current_user" app/api/ | head -50
sed -n '1,40p' app/api/agent_routes.py    # confirm DELETE /recommendations location
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: `architecture-plan.md` § 2 (Data Isolation Invariant)**
Rule: Every CRUD endpoint that takes a resource ID MUST filter by `user_id`. Cross-user attempts return **404, not 403** — never reveal existence of resources owned by another user. This applies even in single-user development phase; the system is multi-user by design from day one.

**Source: `architecture-plan.md` Cleanup Roadmap → Must Fix**
Bug: `DELETE /recommendations/{trade_key}` in `agent_routes.py` does not filter by `user_id`. Original catch by Opus-4.7 review § 1.

**Source: `auth-process.md` § Session Lifecycle**
Rule: Authenticated routes resolve `current_user` via the BFF session middleware. The `user_id` filter applies the resolved `current_user.id` (or whatever the canonical identity field is — confirm in Phase 1) to the SQLAlchemy query's WHERE clause. Do NOT trust any `user_id` value supplied by the client (path param, query param, header, body) — always use the session-resolved identity.

**Source: `architecture-plan.md` § 4 (AI Adapter Contract) — async rule**
Rule: All Azure SDK and DB calls in async FastAPI handlers must use async variants. Sync credentials/queries block the event loop in production. If any of the audited endpoints uses sync DB calls in an async handler, flag it in the audit report — fixing it is out of scope for this Story but the bug must be on record.

**OTA project — shared-file rule (`CLAUDE.md`)**
Files that two parallel terminals must never edit simultaneously: `app/main.py`, `app/database.py`, `web/src/api/client.js`, any SKILL.md. Terminal B owns `database.py` for this batch. Do NOT touch `app/main.py`, `web/src/api/client.js`, or any SKILL.md. If the audit reveals a fix that requires editing one of those, escalate — do not silently expand scope.

---

## Phase 1 — Read-only CRUD audit (STOP gate before Phase 2)

Build the audit table. Do not edit any file in Phase 1. The deliverable from Phase 1 is a single table that lists every resource-ID CRUD endpoint, the file/line, the SQLAlchemy query/queries used, whether the query filters by `user_id`, and the proposed fix.

### Audit procedure

1. Enumerate all FastAPI routes that take a resource ID in the path. Pattern: `@router.{get,put,patch,delete}("/.../{id}")` or `@router.{get,put,patch,delete}("/...{trade_key}")`, etc. Common offenders to specifically check (from spec): positions, watchlists, insights, configs, dashboards, recommendations.
2. For each match, locate the underlying SQLAlchemy query (often `db.query(Model).filter(Model.id == id_param)`) and check whether `Model.user_id == current_user.id` (or equivalent) is in the filter chain.
3. Check both the read query and the write/delete query — sometimes only one is filtered.
4. For endpoints that compose multiple queries (e.g., DELETE that first does a SELECT to check ownership), confirm the SELECT itself filters by `user_id`, otherwise an ownership check on a cross-user row leaks existence information.

### Audit table format

| Method | Path | File:Line | Model | Filters by user_id? | Notes / proposed fix |
|---|---|---|---|---|---|
| DELETE | /recommendations/{trade_key} | app/api/agent_routes.py:LINE | Recommendation | NO — KNOWN BUG | Add `Recommendation.user_id == current_user.id` to the SELECT and DELETE chain |
| ... | ... | ... | ... | ... | ... |

**STOP.** Surface the audit table. Do not begin Phase 2 until Don approves the audit and the proposed fixes. If the audit turns up endpoints whose fix would require editing `app/main.py`, `web/src/api/client.js`, or any SKILL.md, escalate — those edits are outside Terminal B's allowed file set for this batch.

---

## Phase 2 — Implementation

### 2a. Fix the known DELETE /recommendations bug
- Add `user_id` filter to the SELECT and to the DELETE chain in `agent_routes.py` (or its renamed equivalent — confirm path in Phase 1).
- Return `HTTPException(status_code=404)` when the resource exists but belongs to a different user. Use the same 404 response shape as a genuinely-missing resource. Do NOT include any field that distinguishes "missing" from "not yours."

### 2b. Apply each remaining fix from the audit
- For every audit row marked NO, apply the user_id filter at every place the audit identified.
- Each fix must follow the same 404-not-403 pattern.

### 2c. Add per-route comment block
- At the top of each route file containing CRUD endpoints with resource IDs, add this comment block (verbatim):

```
# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.
```

### 2d. Contract test
- Create `app/tests/test_data_isolation_contract.py` (or place under the existing tests tree — confirm location in Phase 1).
- The test parametrizes over every CRUD endpoint with a resource ID. For each:
  1. As user A, create the resource.
  2. As user B (different identity), attempt GET / PUT / PATCH / DELETE on user A's resource ID.
  3. Assert response status == 404.
  4. Assert response body does NOT contain any field from the resource (no leak).
- Use the existing test client / session fixtures. Do not introduce a new test framework.
- Tests must run against an isolated test DB or use transactional rollback — do not pollute the dev DB.

### 2e. Verify architecture-plan.md § 2 matches implementation
- Read `claude_context/architecture-plan.md` § 2.
- Confirm the wording matches the implemented behavior (404 not 403, applies to GET/PUT/PATCH/DELETE that take resource ID).
- If wording mismatches reality: report the mismatch in the final report. Do NOT edit the SoT doc — that is a separate doc subtask Don will queue.

---

## Acceptance criteria

- `DELETE /recommendations/{trade_key}` returns 404 for cross-user attempts; never reveals existence.
- Audit table (in commit body or PR description) lists every CRUD endpoint with its filter status BEFORE this commit and AFTER.
- Every CRUD endpoint that previously lacked the filter has been fixed.
- Contract test exists, parametrizes over all in-scope endpoints, and passes.
- Each touched route file has the user_id filter comment block at the top.
- `architecture-plan.md` § 2 either matches implementation as-is, or the mismatch is reported (not silently fixed).
- No edits to `app/main.py`, `web/src/api/client.js`, or any SKILL.md.

## Out of scope

- Restructuring routes (OTA-541 — Route Consolidation, deferred).
- Adding new endpoints.
- Multi-user features (sharing, permissions) — pure isolation enforcement only.
- Fixing any sync-DB-in-async-handler bugs surfaced by the audit (flag them; fix in a separate Story).
- SoT doc edits to `architecture-plan.md`.

## Verification steps

Before requesting commit approval:

1. `pytest app/tests/test_data_isolation_contract.py -v` — every parametrized case passes.
2. `pytest` — full suite passes (no regressions in non-isolation tests).
3. Local uvicorn run + manual `curl` for the DELETE /recommendations bug:
   - As user A, create a recommendation.
   - As user B, attempt DELETE on user A's trade_key. Expect 404.
   - As user A, attempt DELETE on user A's trade_key. Expect 200/204 (resource deleted).
4. `grep -rn "All endpoints in this file must filter by user_id" app/api/` — confirm comment block in every route file the audit modified.
5. Grep for any remaining unfiltered resource-ID query: `grep -rn "filter(.*\.id == " app/ | grep -v "user_id"` — review each result; confirm each is intentional (e.g., a join, a public lookup) or fix it.

## Commit instruction
**I have been instructed to commit. Do you approve? (yes / no)**

## Coordination footer
**Independent — no downstream dependency.** Other terminals proceed in parallel; nothing in this batch waits on Terminal B. Architecture stories that contend on `database.py` (OTA-541, OTA-538, OTA-543) are deferred for sequenced execution after this batch lands.

## Commit message template (if committing)
```
OTA-542 fix: data isolation hardening — DELETE /recommendations user_id filter + CRUD audit + contract test
```
