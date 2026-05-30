# Phase 3a — ORM & Application Code Audit Report

**Run at:** 2026-05-19 10:00 UTC
**Database:** options-analyzer-sql-cus.database.windows.net/options-analyzer-db
**Alembic head:** ade9a09d8001 (Phase 2)
**Status:** READ-ONLY AUDIT — no code changes made

---

## Section 1. ORM Model Audit

Compared `app/models/database.py` ORM declarations against actual database schema via `sys.columns` and `sys.foreign_keys`. No per-domain split files exist — all models are in `database.py`.

### 1.1 `symbol_reference` — NO ORM MODEL EXISTS

**Severity: BREAKING**

The `symbol_reference` table exists in the database with 8 columns (symbol PK, name, exchange, sector, sub_industry, asset_type, last_updated, api_symbol) and is the parent of 16 FK relationships. No ORM model class exists in `database.py`. All current queries to `symbol_reference` use raw SQL (`text()`).

This means:
- No `relationship()` declarations can reference it
- No ORM-based joins to `symbol_reference` are possible
- The table is invisible to Alembic autogenerate

### 1.2 `users`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `password_hash` | `String(255)` | `nvarchar(510)` (255 chars) | OK — nvarchar byte length is 2x |
| All other columns | Match | Match | OK |
| Relationships | `config`, `trades`, `audit_events` | — | OK |

No issues.

### 1.3 `user_sessions`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `user_id` | `String(255)` | `varchar(36)` | **STALE** — ORM over-spec'd |
| FK `user_id → users.id` | Not declared | `fk_user_sessions_user_id_users` (CASCADE) | **MISSING-RELATIONSHIP** |
| All other columns | Match | Match | OK |

### 1.4 `user_configs`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `default_symbol` | `String(10)` | `varchar(20)` | **STALE** — ORM under-spec'd |
| FK `user_id → users.id` | Declared | Exists (CASCADE) | OK |

### 1.5 `dashboard_layouts`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `user_id → users.id` | Not declared | `fk_dashboard_layouts_user_id_users` (CASCADE) | **MISSING-RELATIONSHIP** |
| All columns | Match | Match | OK |

### 1.6 `audit_log`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `user_id → users.id` | Declared | `fk_audit_log_user_id_users` (SET NULL) | OK |
| All columns | Match | Match | OK |

### 1.7 `symbol_quotes`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `symbol` | `String(10)` | `varchar(20)` | **STALE** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_symbol_quotes_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |

### 1.8 `symbol_context`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_symbol_context_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| All columns | Match | Match | OK |

### 1.9 `option_chain_snapshots`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `symbol` | `String(10)` | `varchar(20)` | **STALE** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_option_chain_snapshots_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |

### 1.10 `watchlists`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `user_id` | `String(255)` | `varchar(36)` | **STALE** — ORM over-spec'd |
| FK `user_id → users.id` | Not declared | `fk_watchlists_user_id_users` (CASCADE) | **MISSING-RELATIONSHIP** |

### 1.11 `watchlist_symbols`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_watchlist_symbols_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `watchlist_id → watchlists.id` | Declared (CASCADE) | Exists (CASCADE) | OK |

### 1.12 `positions`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `user_id → users.id` | Not declared (comment: "SKIP_AUTH compat") | `fk_positions_user_id_users` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_positions_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| All columns | Match | Match | OK |

### 1.13 `position_assessments`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `position_id → positions.position_id` | Declared | Exists (NO_ACTION) | OK |
| All columns | Match | Match | OK |

### 1.14 `trade_candidates`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `user_id → users.id` | Not declared | `fk_trade_candidates_user_id_users` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_trade_candidates_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| All columns | Match | Match | OK |

### 1.15 `trade_recommendations`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_trade_recommendations_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |

### 1.16 `trade_log`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `symbol` | `String(10)` | `varchar(20)` | **STALE** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_trade_log_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |

### 1.17 `analysis_runs`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `symbol` | `String(10)` | `varchar(20)` | **STALE** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_analysis_runs_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |
| FK `chain_snapshot_id → option_chain_snapshots.id` | Declared | Exists (NO_ACTION) | OK |

### 1.18 `analyzed_trades`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `symbol` | `String(10)` | `varchar(20)` | **STALE** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_analyzed_trades_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `run_id → analysis_runs.id` | Declared | Exists (NO_ACTION) | OK |
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |

### 1.19 `agent_run_log`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_agent_run_log_symbol_symbol_reference` (SET NULL) | **MISSING-RELATIONSHIP** |
| FK `user_id → users.id` | Declared | Exists (NO_ACTION) | OK |
| `otel_trace_id` | Correctly named | Correctly named | OK |
| All columns | Match | Match | OK |

### 1.20 `insights`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `user_id` column | **Not in ORM** | `varchar(36)` nullable | **BREAKING** |
| `source_position_id` column | **Not in ORM** | `varchar(36)` nullable | **BREAKING** |
| FK `user_id → users.id` | Not declared | `fk_insights_user_id_users` (NO_ACTION) | **MISSING-RELATIONSHIP** |
| FK `source_position_id → positions.position_id` | Not declared | `fk_insights_source_position_id_positions` (SET NULL) | **MISSING-RELATIONSHIP** |
| All other columns | Match | Match | OK |

### 1.21 `user_favorites`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| `symbol` | `String(10)` | `varchar(20)` | **STALE** |
| FK `user_id → users.id` | Not declared | `fk_user_favorites_user_id_users` (CASCADE) | **MISSING-RELATIONSHIP** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_user_favorites_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |

### 1.22 `validation_assessments`

| Aspect | ORM | DB | Severity |
|--------|-----|-----|----------|
| Column name | ORM: `ticker` | DB: `symbol` | **BREAKING** — column renamed in Phase 1b; ORM still uses old name |
| Index | ORM: `ix_validation_assessments_ticker` on `ticker` | DB: `ix_validation_assessments_symbol` on `symbol` | **STALE** |
| FK `symbol → symbol_reference.symbol` | Not declared | `fk_validation_assessments_symbol_symbol_reference` (NO_ACTION) | **MISSING-RELATIONSHIP** |

### 1.23 Check Constraints (Informational)

29 `ISJSON` check constraints exist in the database (all added in Phase 2). SQLAlchemy does not need these declared at the model level — they are DB-enforced. All constraints verified in `phase2-migration-log.md`.

### Section 1 Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **BREAKING** | 4 | No `SymbolReference` model; `insights` missing `user_id` + `source_position_id` columns; `validation_assessments.ticker` → `symbol` rename |
| **STALE** | 8 | `symbol` width `String(10)` vs DB `varchar(20)` (×6 tables); `user_id` width `String(255)` vs DB `varchar(36)` (×2 tables) |
| **MISSING-RELATIONSHIP** | 21 | FK exists in DB but no `ForeignKey()` or `relationship()` in ORM |

---

## Section 2. Query Audit

### 2.1 user_id filter patterns

All `user_id` filter call sites use `user["sub"]` or `user.get("sub")` from the JWT, which is a 36-char UUID. Runtime behavior is correct. The two ORM declarations with `String(255)` (`watchlists`, `user_sessions`) accept any length but the DB column is now `varchar(36)`.

- **No BREAKING findings.** Filters work correctly against `varchar(36)` columns.

### 2.2 Symbol writes without canonicalization

| File | Line(s) | Pattern | Severity |
|------|---------|---------|----------|
| `app/api/trade_evaluation_routes.py` | 260, 497, 516, 616 | `symbol=request.symbol` written to `trade_recommendations` and `agent_run_log` without `.upper()` | **BREAKING** |
| `app/api/evaluation_routes.py` | 566, 679, 737, 750 | `request.symbol` used in prompts and `AgentRunLog` writes without `.upper()` | STALE |
| `web/src/components/TradeEvaluationView.jsx` | 186 | `spread.symbol` sent to `getProbabilityMatrix` without `.toUpperCase()` | STALE |

### 2.3 Cross-table joins

No ORM-level `.join()` calls were found that cross Phase 2 FK boundaries. All multi-table queries use separate `select()` statements or raw SQL. No BREAKING joins exist.

### 2.4 Writes to `insights`

Single call site: `app/agents/insight_engine.py:162–180`. Does NOT pass `user_id` or `source_position_id` (columns missing from ORM). See Section 4 for details.

### 2.5 Stale column names

No references to `trace_id` as a column name found. The local variable `trace_id` in `app/agents/telemetry.py:126` is correctly mapped to ORM field `otel_trace_id`. No references to `surfaced_at` found anywhere.

### 2.6 Writes to `agent_run_log`

9 call sites found, all using the correct column name `otel_trace_id`:

| File | Line(s) | Stage |
|------|---------|-------|
| `app/api/evaluation_routes.py` | 197, 675, 1023, 1420 | validate_narrative, auto_pass, structured_eval, trade_verdict |
| `app/api/trade_evaluation_routes.py` | 110 (via helper) | triage/deep_dive/followup |
| `app/api/position_routes.py` | 1451 | position_refresh |
| `app/api/mcp_routes.py` | 276 | tool_call |
| `app/agents/insight_engine.py` | 187 | generate |
| `app/agents/position_monitor.py` | 184 | health_check |

`insight_engine.py:192` writes `user_id=None` to `AgentRunLog` even though the user context is available indirectly via `pos.user_id`. Severity: STALE.

---

## Section 3. `api_symbol` Normalization Audit

### 3.1 Current state

**No normalization helpers exist.** There is no function to strip `$` prefixes, no `symbol_reference.api_symbol` lookup, and no `SymbolReference` ORM model. The `symbol_reference` table is queried only for `asset_type` (via raw SQL in `schwab.py`).

### 3.2 Inbound symbol paths (External → DB write)

| # | File | Line(s) | Target Table | Normalization | Assessment |
|---|------|---------|--------------|---------------|------------|
| 1 | `app/api/position_routes.py` | 664–666, 750–752 | `positions` | `.upper()` only | Partial — no `$`-strip |
| 2 | `app/api/analysis_routes.py` | 227–234, 508 | `option_chain_snapshots` | `.upper()` via caller | Partial |
| 3 | `app/analysis/chain_collection.py` | 55–65 | `options_chain_snapshots` | None inside function | Missing — relies on caller |
| 4 | `app/agents/context_store.py` | 75 | `symbol_context` | `.upper()` | Partial |
| 5 | `app/api/analysis_routes.py` | 378–392, 462–476 | `trade_candidates` | `.upper()` via caller | Partial |
| 6 | `app/api/trade_evaluation_routes.py` | 260, 497 | `agent_run_log`, `trade_recommendations` | None | **Missing** |
| 7 | `app/api/evaluation_routes.py` | 679, 737 | `agent_run_log` | None | **Missing** |

All paths apply `.upper()` at most. No path strips `$` prefixes or resolves via `symbol_reference.api_symbol`.

### 3.3 Outbound symbol paths (App → External Provider)

| # | File | Line(s) | Provider | Normalization | Assessment |
|---|------|---------|----------|---------------|------------|
| 1 | `app/providers/schwab.py` | 91–101 | Schwab quotes | `.upper()` only | **Missing** — no index symbol translation (canonical `SPX` → Schwab `$SPX`) |
| 2 | `app/providers/schwab.py` | 182 | Schwab chains | `.upper()` only | **Missing** — same gap |
| 3 | `app/providers/schwab_context_source.py` | 60 | Schwab via `get_quote()` | Inherits from #1 | **Missing** |
| 4 | `app/providers/finnhub_earnings.py` | 135 | Finnhub | `.upper()` | Correct (Finnhub uses standard tickers) |

### 3.4 Recommended helper module

**Location:** `app/services/symbol_normalization.py`

**Proposed functions:**

```python
def canonicalize(symbol: str) -> str:
    """Strip $ prefix, uppercase. For inbound writes."""

async def to_api_symbol(db: AsyncSession, symbol: str, provider: str) -> str:
    """Canonical → provider-specific form. Looks up symbol_reference.api_symbol."""

async def from_api_symbol(db: AsyncSession, api_symbol: str) -> str:
    """Provider-specific → canonical form. Reverse lookup on api_symbol column."""
```

---

## Section 4. Insights Wiring Audit

### 4.1 ORM model gap

The `Insight` model (`database.py:543–579`) is **missing two columns** that exist in the database:

- `user_id` — `varchar(36)`, nullable, FK to `users.id`
- `source_position_id` — `varchar(36)`, nullable, FK to `positions.position_id`

### 4.2 Call sites

| # | File | Line(s) | Operation | `user_id` passed? | `source_position_id` passed? | Severity |
|---|------|---------|-----------|-------------------|------------------------------|----------|
| 1 | `app/agents/insight_engine.py` | 162–180 | Create `Insight()` | NO — not in model | NO — not in model | **BREAKING** |
| 2 | `app/agents/insight_engine.py` | 144–159 | Update existing `Insight` | NO | NO | **BREAKING** |

### 4.3 Caller context

The sole caller is `app/agents/position_monitor.py:372–380` (`_trigger_insights()`):

- `pos.user_id` is available at the call site but not forwarded to `InsightEngine.generate()`
- `pos.position_id` is available (used as `entity_id`) but not separately passed as `source_position_id`
- The `InsightEngine.generate()` method signature has no `user_id` or `source_position_id` parameter

### 4.4 Impact

Without `user_id` on insight rows, the Data Isolation Invariant is violated — the `GET /api/v1/insights` endpoint cannot filter by user without joining through `positions`. Without `source_position_id`, the FK to `positions` is never populated, making the Phase 2 FK inert.

---

## Section 5. Representative Query Smoke Tests

All tests run against dev DB (`options-analyzer-sql-cus`) using the application's `async_session` factory. User: `6232a881-23e9-4954-8ed0-6303ea7fd188` (Don).

### Test 1: Active positions joined to `symbol_reference` and `users`

- **ORM query:** `select(Position).where(user_id, status IN ('FOLLOWING','LIVE'))` — **SUCCESS**, 39 rows
- **Raw SQL join:** `positions ⟕ symbol_reference ⟕ users` — **SUCCESS**, 39 rows, all symbols resolved
- **No SQLAlchemy warnings**
- **Note:** ORM query cannot join `symbol_reference` because no `SymbolReference` model exists

### Test 2: Default watchlist + latest quotes per symbol

- **ORM query:** `select(NamedWatchlist).where(user_id, is_default)` — **SUCCESS**, 1 watchlist
- **Raw SQL join:** `watchlist_symbols ⟕ symbol_reference ⟕ (latest symbol_quotes)` — **SUCCESS**, 6 rows
- **No SQLAlchemy warnings**

### Test 3: Recent trade candidates joined to `symbol_reference`

- **ORM query:** `select(TradeCandidate).where(user_id, scanned_at >= cutoff)` — **SUCCESS**, 10 rows
- **Raw SQL join:** `trade_candidates ⟕ symbol_reference` — **SUCCESS**, 5 rows (FETCH NEXT 5)
- **No SQLAlchemy warnings**

### Smoke Test Summary

| Test | ORM Query | Raw SQL Join | Warnings |
|------|-----------|--------------|----------|
| 1 — Active positions | SUCCESS (39 rows) | SUCCESS (39 rows) | None |
| 2 — Watchlist + quotes | SUCCESS (6 rows) | SUCCESS (6 rows) | None |
| 3 — Trade candidates | SUCCESS (10 rows) | SUCCESS (5 rows) | None |

All queries succeed. The main finding is that ORM-based joins to `symbol_reference` are impossible until a `SymbolReference` model is created.

---

## Section 6. Async Credential Check

### BREAKING findings

| # | File | Line(s) | Pattern | Impact |
|---|------|---------|---------|--------|
| 1 | `app/core/secrets.py` | 89 | `self._client.get_secret()` (sync `SecretClient`) | Blocks event loop on every secret read; called from auth service, changelog routes |
| 2 | `app/core/secrets.py` | 125 | `self._client.set_secret()` (sync `SecretClient`) | Blocks event loop on secret write |
| 3 | `app/api/dashboard_routes.py` | 189, 197, 203 | Sync `DefaultAzureCredential()` + sync `BlobServiceClient.get_user_delegation_key()` | Blocks event loop per-request in `async def get_media()` |
| 4 | `app/auth/service.py` | 54, 151 | Calls `self.secrets.get()` (sync) from async handlers transitively | Inherits BREAKING-1 |
| 5 | `app/api/changelog_routes.py` | 93 | `_secrets_manager.get()` (sync) in FastAPI dependency for async handler | Inherits BREAKING-1 |

### INFO findings (safe by design)

| # | File | Line(s) | Pattern | Why safe |
|---|------|---------|---------|----------|
| 1 | `app/models/session.py` | 71–73 | Sync `DefaultAzureCredential.get_token()` in `do_connect` event | Runs in aioodbc's thread pool, not event loop |
| 2 | `app/core/secrets.py` | 39–45 | Sync `SecretClient` constructor at startup | One-time startup block, not per-request |

### Correct async usage confirmed

| File | Pattern |
|------|---------|
| `app/core/secrets.py:180,220` | `get_async()` / `set_async()` using `azure.identity.aio` |
| `app/auth/client_assertion.py:46` | `azure.identity.aio.DefaultAzureCredential` |
| `app/providers/finnhub_earnings.py:94` | `azure.identity.aio.DefaultAzureCredential` |

**Note:** Async variants (`get_async`, `set_async`) exist in `secrets.py` but are not used by the primary call paths (`auth/service.py`, `changelog_routes.py`). The sync `get()`/`set()` remain the dominant path.

---

## Section 7. Recommended 3b Sub-Phase Action List

### 3b.1 — ORM Model Alignment

**Scope:** Update `app/models/database.py` to match the current database schema. Add missing model, columns, FK declarations, and `relationship()` links. Correct stale type widths.

| Action | Files | LOC | Risk |
|--------|-------|-----|------|
| Create `SymbolReference` model with all 8 columns | `database.py` | ~25 | Low (mechanical) |
| Add `user_id` and `source_position_id` columns to `Insight` model | `database.py` | ~4 | Low |
| Rename `ValidationAssessment.ticker` → `symbol`; update index | `database.py` | ~4 | Low but search for usages first |
| Correct 6× `symbol` columns from `String(10)` → `String(20)` | `database.py` | ~6 | Low |
| Correct 2× `user_id` columns from `String(255)` → `String(36)` (`watchlists`, `user_sessions`) | `database.py` | ~2 | Low |
| Add 21 missing `ForeignKey()` declarations + `relationship()` where useful | `database.py` | ~60 | Medium — must confirm cascade behavior matches DB |
| Remove stale "WHY no FK" comments on `Position`, `NamedWatchlist`, `UserFavorite` | `database.py` | ~3 | Low |

**Total estimated:** ~104 LOC changed in 1 file
**Risk:** Low-to-medium (mechanical, but FK cascade must match DB)
**Dependencies:** None — can ship independently. No Alembic migration needed (DB already correct; ORM is catching up).

### 3b.2 — `api_symbol` Normalization Helpers + Wiring

**Scope:** Create `app/services/symbol_normalization.py` with `canonicalize()`, `to_api_symbol()`, `from_api_symbol()`. Wire into all inbound write paths and outbound provider calls.

| Action | Files | LOC | Risk |
|--------|-------|-----|------|
| Create `symbol_normalization.py` with 3 functions | New file | ~50 | Low |
| Wire `canonicalize()` into 7 inbound write paths | `position_routes.py`, `analysis_routes.py`, `chain_collection.py`, `context_store.py`, `trade_evaluation_routes.py`, `evaluation_routes.py` | ~14 | Low |
| Wire `to_api_symbol()` into Schwab outbound calls | `schwab.py`, `schwab_context_source.py` | ~10 | Medium — index symbol mapping must be correct |

**Total estimated:** ~74 LOC across 1 new + ~8 existing files
**Risk:** Medium — incorrect outbound mapping could break Schwab quotes for index symbols
**Dependencies:** Depends on 3b.1 (needs `SymbolReference` model for DB lookup)

### 3b.3 — Insights Write Wiring

**Scope:** Add `user_id` and `source_position_id` parameters to `InsightEngine.generate()` and wire them through from `PositionMonitorAgent`.

| Action | Files | LOC | Risk |
|--------|-------|-----|------|
| Add `user_id` + `source_position_id` params to `InsightEngine.generate()` | `insight_engine.py` | ~8 | Low |
| Pass `pos.user_id` and `pos.position_id` from `PositionMonitorAgent._trigger_insights()` | `position_monitor.py` | ~4 | Low |
| Set `user_id` on `AgentRunLog` writes in insight engine | `insight_engine.py` | ~2 | Low |

**Total estimated:** ~14 LOC across 2 files
**Risk:** Low (mechanical)
**Dependencies:** Depends on 3b.1 (needs `user_id` and `source_position_id` on `Insight` model)

### 3b.4 — Query Fixes

**Scope:** Fix symbol normalization at write-time in `trade_evaluation_routes.py` and `evaluation_routes.py`. Fix `validation_assessments` references from `ticker` to `symbol`.

| Action | Files | LOC | Risk |
|--------|-------|-----|------|
| Add `.upper()` normalization to `trade_evaluation_routes.py` endpoints | `trade_evaluation_routes.py` | ~6 | Low |
| Add `.upper()` normalization to `evaluation_routes.py` endpoints | `evaluation_routes.py` | ~4 | Low |
| Update all `ValidationAssessment.ticker` references to `.symbol` | Search all files | ~10 | Low but must audit all usages |
| Add `.toUpperCase()` to frontend symbol values sent to API | `TradeEvaluationView.jsx` | ~2 | Low |

**Total estimated:** ~22 LOC across ~4 files
**Risk:** Low (mechanical)
**Dependencies:** 3b.4 ticker→symbol fix depends on 3b.1 model rename

### Scope Check

| Sub-phase | Est. LOC | Files | Risk | Independent? |
|-----------|----------|-------|------|-------------|
| 3b.1 ORM alignment | ~104 | 1 | Low–Med | Yes |
| 3b.2 api_symbol wiring | ~74 | ~9 | Medium | No — needs 3b.1 |
| 3b.3 Insights wiring | ~14 | 2 | Low | No — needs 3b.1 |
| 3b.4 Query fixes | ~22 | ~4 | Low | Partial — ticker rename needs 3b.1 |
| **Total** | **~214** | **~14** | | |

**214 LOC across 14 files is well under the 500 LOC / 20 file threshold.** No further split is recommended. The work can be executed as a single Phase 3b session with sub-phases ordered: 3b.1 → 3b.2 → 3b.3 → 3b.4.

### Out of scope (confirmed)

- Tightening `insights.user_id` / `source_position_id` to NOT NULL — future phase
- Async credential fixes (Section 6) — separate story, not part of normalization
- Table drops (`schwab_tokens`, `user_watchlist`, `options_chain_snapshots`) — Phase 4
- `varbinary` token migration — separate effort
- Views from normalization proposal §8 — separate effort
