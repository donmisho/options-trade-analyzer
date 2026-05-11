# OTA-624 — Persist trade candidates at scan time for atomic Follow and backtest

## Deployment context
- Deployment: **D3**
- This terminal: **T1**
- Concurrent terminals: T2 (`OTA-629` per-watchlist scan cache — disjoint files), T3 (`OTA-621` export MD — disjoint files)
- Cross-terminal dependencies: **none** — T1 owns the new `trade_candidates` table and the scan/Follow path; T2 and T3 do not touch these

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/auth-process.md
cat claude_context/deployment-workflow.md
```

Plus:

```
cat app/models/migrations.py                  # _m001-_m005 pattern for new _m006
cat app/api/evaluation_routes.py              # /analyze/* endpoints — write trade_candidates rows here
cat app/api/position_routes.py                # POST /positions/follow — reads trade_key after change
cat app/models/database.py                    # if a positions table model needs an FK to trade_candidates
grep -rn "/analyze/" app/                     # full inventory of /analyze/* endpoints
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md § Atomic Follow**
Follow must be a single server-side transaction: reads the persisted trade snapshot, builds the position, writes the assessment. No client-side payload reconstruction. The CSCO 90/100 paper position (May 2026) reproduced the non-atomic failure: Follow inserts a placeholder, then a second UPDATE lands ~30s later. The post-OTA-624 model eliminates the second write entirely.

**Source: business-rules.md § Backtest prerequisite**
A captured candidate snapshot is what makes backtest possible. Without persistence, we cannot replay a candidate's scoring inputs against subsequent price action. The schema must include enough detail that re-scoring is reproducible (per-leg detail, net metrics, underlying spot, pipeline components).

**Source: architecture-plan.md § Data Isolation Invariant**
Every CRUD endpoint that takes a resource ID filters by `user_id`. `trade_candidates` rows must carry `user_id`. `POST /positions/follow` lookups `trade_candidates` filtered by both `trade_key` AND `user_id`; cross-user attempts return 404, not 403.

**Source: architecture-plan.md § Schema evolution**
Schema should generalize across structure types (verticals, long puts/calls, iron condor, calendars, diagonals, butterflies, etc.) with no migration when a new structure is added. `structure` is `text` (not enum); `legs` is JSON; `net_metrics` is JSON.

**Source: deployment-workflow.md § Migration discipline**
Alembic additive only. New table `trade_candidates`. No drops, no column renames. The future cleanup of dropping `claude_*` columns from `positions` (paired with OTA-630 follow-up) lives in a separate Story.

**Source: CLAUDE.md § Async SDK in async handlers**
All Azure SDK calls in async FastAPI handlers must use `.aio` async variants. Only manifests in production. Verify the persistence path stays async-clean.

**Source: CLAUDE.md § Cost guardrail**
Persistence at scan time must NOT trigger an extra Claude API call. The scan already calls Claude once per card; this Story persists what's already there, no new evaluations.

---

## Scope

### 1. Migration `_m006_create_trade_candidates`

Idempotent migration in `app/models/migrations.py`, both MSSQL and SQLite branches following `_is_mssql` pattern from `_m001`–`_m005`:

```sql
CREATE TABLE trade_candidates (
  trade_key            UUID/CHAR(36) PRIMARY KEY,
  user_id              <FK type per existing convention> NOT NULL,
  symbol               TEXT NOT NULL,
  structure            TEXT NOT NULL,        -- 'long_call', 'long_put', 'bull_put_credit',
                                             --   'bear_call_credit', 'bull_call_debit', 'bear_put_debit',
                                             --   'iron_condor', 'iron_butterfly', 'calendar_call', etc.
                                             --   TEXT (not enum) so adding structures needs no migration
  leg_count            INT NOT NULL,
  legs                 JSON/NVARCHAR(MAX),   -- per-leg detail (see contract below)
  net_metrics          JSON/NVARCHAR(MAX),   -- spread-level aggregates (see contract below)
  underlying_spot      NUMERIC NOT NULL,
  pipeline_score       NUMERIC,
  pipeline_components  JSON/NVARCHAR(MAX),   -- subscores for transparency / re-scoring
  scan_source          TEXT NOT NULL,        -- '/analyze/verticals', '/analyze/single_legs', etc.
  scan_strategy_key    TEXT,                 -- 'steady-paycheck' etc., nullable for structure-only scans
  scanned_at           TIMESTAMP NOT NULL,
  claude_evaluation    JSON/NVARCHAR(MAX),   -- the verdict/score/exit_levels/claude_read at scan time
  CONSTRAINT fk_trade_candidates_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX ix_trade_candidates_user_scanned ON trade_candidates(user_id, scanned_at DESC);
CREATE INDEX ix_trade_candidates_symbol_user ON trade_candidates(symbol, user_id);
```

### 2. `legs` JSON contract (deviation requires escalation)

```json
[
  {
    "side": "long" | "short",
    "option_type": "call" | "put",
    "strike": <number>,
    "expiration": "YYYY-MM-DD",
    "qty": <int>,
    "bid": <number>,
    "ask": <number>,
    "delta": <number>,
    "iv": <number>,
    "symbol": "<OCC symbol>"
  },
  ...
]
```

### 3. `net_metrics` JSON contract

```json
{
  "entry_price": <number>,              // debit cost or credit received
  "max_profit": <number>,
  "max_loss": <number>,
  "breakeven": <number> | [<number>, <number>],
  "net_bid_ask": <number>,
  "dte": <int>,
  "iv_rank": <number>,
  "scenario_weighted_ev": <number>,
  "prob_of_profit": <number>,
  "probability_matrix": <object>        // existing shape from agent payload
}
```

### 4. `claude_evaluation` JSON contract

```json
{
  "verdict": "EXECUTE" | "WAIT" | "PASS",
  "score": <number>,
  "exit_levels": <object>,
  "claude_read": "<string>",
  "key_risks": [<string>...],
  "thesis_invalidators": [<string>...],
  "auto_pass_reason": null | "<string>"
}
```

### 5. `/analyze/*` endpoints write `trade_candidates` rows

For every endpoint that returns trade candidates (`/analyze/verticals`, `/analyze/single_legs`, `/analyze/iron_condors`, etc.):

- Generate a `trade_key` UUID per candidate at response build time.
- Insert one `trade_candidates` row per candidate with all fields populated.
- Include `trade_key` in the response payload alongside existing fields. Frontend receives it but does not need to send it back on every interaction — only on Follow.

Write is fire-and-forget async if it would block the response on the critical path (per `architecture-plan.md § Two-Track Observability`). Bulk insert per scan rather than one-by-one.

### 6. `POST /positions/follow` reads `trade_key`

Change `POST /positions/follow` payload from "full card object" to `{ trade_key, user-overridable fields if any }`. The server:

1. SELECTs the `trade_candidates` row by `trade_key AND user_id` (returns 404 if not found — covers Data Isolation Invariant).
2. Builds the position from the captured snapshot.
3. Inserts the position + assessment in a single transaction (the OTA-628 gate validators from D1 still apply against the snapshot data).
4. No second UPDATE row, no payload drift.

### 7. Frontend Follow button

`web/src/pages/TradesPage.jsx` Follow button now POSTs `{ trade_key }` only (plus any user-overridable fields if any exist in the current contract). Remove the payload-rebuild logic. Verify the OTA-628 client-side disable conditions still apply against the visible card's data.

### 8. Retention policy (initial)

For this Story, no automated purge. Manual cleanup is acceptable until volume warrants automation. Note in commit message and architecture-plan.md update that a perpetual cleanup Story will follow (paired with `OTA-523` migration discipline cleanup).

---

## Acceptance criteria

1. Migration `_m006` runs cleanly against empty DB and against a DB with existing positions. Idempotent.
2. Every `/analyze/*` endpoint response includes `trade_key` per candidate.
3. After a scan completes, `SELECT COUNT(*) FROM trade_candidates` increases by the number of candidates returned.
4. `POST /positions/follow` with `{ trade_key }` succeeds for a known candidate and the resulting position's `entry_price`, `claude_verdict`, `claude_exit_levels` match the candidate's captured snapshot exactly.
5. `POST /positions/follow` with a `trade_key` from another user's session returns 404 (Data Isolation Invariant).
6. `POST /positions/follow` with a non-existent `trade_key` returns 404.
7. The OTA-628 gates (validators added in D1) reject a candidate snapshot whose verdict is `WAIT_FOR_EARNINGS`, whose `entry_price` is zero, or whose `auto_pass_reason` is non-empty.
8. **No second UPDATE row** lands ~30s after Follow. The only writes per Follow are the `positions` INSERT and the `position_assessments` INSERT, in one transaction.
9. Async pytest regression that reproduces the original CSCO 90/100 non-atomic failure mode and confirms it no longer manifests post-change.
10. `architecture-plan.md` updated with the new `trade_candidates` table in the data model section and the new Follow path described.

---

## Out of scope

- Dropping the `claude_*` columns from `positions` (separate follow-up Story; pairs with OTA-630 architectural cleanup).
- Backtest engine itself (this Story enables backtest; building the engine is a separate epic).
- Frontend "Show captured snapshot" UI (separate Story if it ever ships).
- Retention/cleanup automation (manual cleanup acceptable for v1).

---

## Verification steps (run before commit)

1. **Migration runs cleanly** in dev DB; new table visible.
2. **Async pytest:**
   - Scan a watchlist → assert `trade_candidates` rows inserted with correct fields.
   - Follow a candidate by `trade_key` → assert position created with matching snapshot data.
   - Follow with cross-user `trade_key` → assert 404.
   - Follow with non-existent `trade_key` → assert 404.
   - Follow a candidate whose snapshot has `WAIT_FOR_EARNINGS` verdict → assert 422 (OTA-628 gate still works).
3. **Manual smoke (dev frontend):**
   - Run a scan on a 5-symbol watchlist → confirm candidates appear with `trade_key` in dev tools network tab.
   - Follow a valid card → position appears on Positions page with matching verdict and exit levels.
   - Check `trade_candidates` table directly (e.g., via a temporary SELECT) for row count consistency.
4. **No regression** in existing scan or Follow flows. Existing pytests in `app/api/evaluation_routes.py` and `app/api/position_routes.py` test scope pass.
5. **No new Claude API calls** introduced — verify by `grep -rn "Provider\\b\\|chat(" app/api/evaluation_routes.py` does not show additional calls beyond what existed before.
6. **architecture-plan.md** diff shows the new table added.

If any verification fails, stop and report.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers OTA-624.

## Push instruction

**DO NOT push. Single push for Deployment 3 will be coordinated by Don after all D3 terminals (T1, T2, T3) report commit.**

## Coordination footer

**Independent — no downstream dependency.** This terminal closes after committing.

## Commit message template

```
OTA-624 feat: persist trade candidates at scan time; Follow reads trade_key; atomic position creation
```
