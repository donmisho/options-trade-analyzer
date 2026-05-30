# OTA Database Normalization Proposal

**Status:** DRAFT — awaiting Don’s approval before code review and migration planning
**Instigating context:** Watchlist FK incident (legacy `user_watchlist` + dual user_id formats + no FK to `symbol_reference`)
**Governing principle:** Tables are normalized with enforced PK→FK relationships. JSON-bearing text columns are exempt from internal normalization but must be validated via `ISJSON()` check constraints. Denormalized projections live as views, not tables.

-----

## 1. Current-State Diagnosis

The schema has **33 user tables** plus `sysdiagrams` (SQL Server managed) and `alembic_version` (Alembic managed). Of these:

- **5 FK constraints exist** across the entire schema (most to `users.id`, one chain to `positions.position_id`).
- **0 FK constraints reference `symbol_reference`** despite at least 10 tables storing `symbol` strings.
- **3 distinct widths** are used for `user_id` columns (`varchar(36)`, `varchar(255)`, `nvarchar(72)`).
- **2 distinct widths** are used for `symbol` columns (`varchar(10)`, `varchar(20)`, plus `nvarchar(40)` on the parent).
- **Multiple short categorical fields are declared `varchar(-1)`** (varchar MAX), most notably in `trade_candidates`.
- **Several JSON-bearing columns are `varchar(-1)`** without `ISJSON` validation.
- **At least 3 tables are dead or duplicate** (`schwab_tokens`, `user_watchlist`, `options_chain_snapshots` — see §2).

The root cause is consistent: tables were added one at a time without a typing standard or FK discipline, and the `skip_auth` development mode allowed orphan `user_id` values into production.

-----

## 2. Tables to Drop

|Table                               |Reason                                                                                                                    |Evidence                                                                                                                                |
|------------------------------------|--------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
|`schwab_tokens`                     |Intentionally unused — Key Vault is the canonical Schwab token store via `SchwabTokenManager`                             |Documented in architecture-plan.md (Schwab token storage); table exists but no code writes to it                                        |
|`user_watchlist`                    |Legacy flat watchlist superseded by `watchlists` + `watchlist_symbols`                                                    |Contains orphan data under three different `user_id` formats; ORM models use the named-watchlist pair                                   |
|`options_chain_snapshots` *(plural)*|Duplicate of `option_chain_snapshots` *(singular)* — different schema shape, different PK type (UUID vs int), no `user_id`|Two tables that conceptually cover the same thing; one is in active use, the other is orphan. **Needs your confirmation which is live.**|

`sysdiagrams` is auto-managed by SQL Server and is left alone.

-----

## 3. Type Standardization Rules

These rules apply uniformly across the schema. Existing columns are migrated to match.

|Concept                                            |Canonical Type                                  |Rationale                                                                                                                                                    |
|---------------------------------------------------|------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
|User ID                                            |`varchar(36)` NOT NULL                          |Entra OID is a UUID (36 chars). `varchar(255)` and `nvarchar(72)` are over-spec’d.                                                                           |
|Symbol                                             |`varchar(20)` NOT NULL                          |All US exchange tickers fit in 10; 20 buys headroom for futures/index API symbols. ASCII-only — `nvarchar` is wasteful.                                      |
|Trade key                                          |`varchar(36)` NOT NULL                          |UUID. Current `varchar(255)`, `varchar(300)`, `varchar(36)` mix is unjustified. **Confirm all existing trade_key values are UUID format** (open question §6).|
|Position ID                                        |`varchar(36)` NOT NULL                          |UUID. Already correct.                                                                                                                                       |
|Surrogate PK for log/audit tables                  |`bigint` IDENTITY                               |Use bigint over int for any append-only table.                                                                                                               |
|Surrogate PK for domain entities                   |`varchar(36)` UUID                              |Use UUID for any row that may be referenced by a key emitted to the client.                                                                                  |
|Boolean                                            |`bit` NOT NULL DEFAULT 0                        |Standardize default + NOT NULL.                                                                                                                              |
|Date (no time)                                     |`date`                                          |For `expiration`, `snapshot_date`, etc. — currently stored as `varchar(20)`.                                                                                 |
|Datetime                                           |`datetime2(3)` NOT NULL DEFAULT SYSUTCDATETIME()|Replace `datetime` with `datetime2` (precision + range improvement). Set DEFAULT on `created_at`/`captured_at`/`updated_at`.                                 |
|Money                                              |`numeric(12,4)`                                 |Positions already use `numeric(10,4)`. Standardize at slightly wider precision.                                                                              |
|Score (0–100)                                      |`numeric(5,2)` NOT NULL                         |Per house style `##.00`. Existing schema mixes `int`, `float`, and `numeric(5,2)`.                                                                           |
|Probability/percentage                             |`numeric(7,4)`                                  |Allows `##.0000%` precision.                                                                                                                                 |
|Greeks (delta/theta/gamma/vega/rho)                |`numeric(9,6)`                                  |Wider precision than money; signed.                                                                                                                          |
|IV                                                 |`numeric(9,6)`                                  |Stored as decimal per memory (frontend multiplies for display).                                                                                              |
|JSON-bearing text                                  |`nvarchar(max)` + `CHECK (ISJSON([col]) = 1)`   |All JSON columns get the constraint. NULL allowed if column is nullable; constraint short-circuits on NULL.                                                  |
|Short categorical (status, verdict, severity, etc.)|`varchar(20)`                                   |No more `varchar(-1)` for enum-like fields.                                                                                                                  |
|Email                                              |`varchar(254)`                                  |RFC 5321 max.                                                                                                                                                |
|Encrypted token                                    |`varbinary(max)`                                |Currently stored as `varchar(-1)` of base64 Fernet output. Encrypted bytes belong in `varbinary`. Open question §6 — table-rewrite cost.                     |

-----

## 4. Proposed Foreign Key Relationships

### 4.1 Identity & Session Domain

```
users (PK: id varchar(36))
  ├── user_sessions.user_id      → users.id       (CASCADE on delete)
  ├── user_configs.user_id       → users.id       (CASCADE)
  ├── audit_log.user_id          → users.id       (SET NULL)   — preserve audit if user deleted
  └── dashboard_layouts.user_id  → users.id       (CASCADE)
```

`user_sessions.user_id` migrates from `varchar(255)` to `varchar(36)` and becomes FK to `users.id`. Existing orphan sessions are deleted as a one-time cleanup.

### 4.2 Symbol Master Domain

```
symbol_reference (PK: symbol varchar(20))
  ├── symbol_quotes.symbol             → symbol_reference.symbol   (RESTRICT)
  ├── symbol_context.symbol            → symbol_reference.symbol   (RESTRICT)
  ├── option_chain_snapshots.symbol    → symbol_reference.symbol   (RESTRICT)
  ├── watchlist_symbols.symbol         → symbol_reference.symbol   (RESTRICT)
  ├── trade_candidates.symbol          → symbol_reference.symbol   (RESTRICT)
  ├── analysis_runs.symbol             → symbol_reference.symbol   (RESTRICT)
  ├── analyzed_trades.symbol           → symbol_reference.symbol   (RESTRICT)
  ├── positions.symbol                 → symbol_reference.symbol   (RESTRICT)
  ├── trade_log.symbol                 → symbol_reference.symbol   (RESTRICT)
  ├── trade_recommendations.symbol     → symbol_reference.symbol   (RESTRICT)
  ├── user_favorites.symbol            → symbol_reference.symbol   (RESTRICT)
  ├── agent_run_log.symbol             → symbol_reference.symbol   (SET NULL)
  └── validation_assessments.ticker    → symbol_reference.symbol   (RESTRICT)
```

`symbol_reference.symbol` migrates from `nvarchar(40)` to `varchar(20)`. All dependent symbol columns standardize at `varchar(20)`.

`RESTRICT` is the default — a symbol cannot be deleted from `symbol_reference` while any dependent row exists. Symbol deletion is rare and explicit. `agent_run_log` uses `SET NULL` because audit must survive symbol pruning.

### 4.3 Watchlist Domain

```
users (PK)
  └── watchlists (PK: id varchar(36))
        └── watchlist_symbols.watchlist_id → watchlists.id   (CASCADE)
        └── watchlist_symbols.symbol       → symbol_reference.symbol  (RESTRICT)
```

`watchlists.user_id` migrates from `varchar(255)` to `varchar(36)` + FK to `users.id` (CASCADE).
`user_watchlist` table is dropped (see §2).

### 4.4 Positions Domain

```
positions (PK: position_id varchar(36))
  ├── positions.user_id              → users.id              (RESTRICT) — preserve positions on user deletion
  ├── positions.symbol               → symbol_reference.symbol (RESTRICT)
  └── position_assessments.position_id → positions.position_id (CASCADE) — already exists ✓
```

`positions.user_id` adds FK (currently missing).

### 4.5 Trade Evaluation & Audit Domain

```
trade_candidates (PK: trade_key varchar(36))
  ├── trade_candidates.user_id       → users.id              (RESTRICT)
  └── trade_candidates.symbol        → symbol_reference.symbol (RESTRICT)

trade_recommendations
  ├── trade_recommendations.user_id  → users.id              (RESTRICT)
  ├── trade_recommendations.symbol   → symbol_reference.symbol (RESTRICT)
  └── trade_recommendations.trade_key → trade_candidates.trade_key (SET NULL)

agent_run_log
  ├── agent_run_log.user_id          → users.id              (SET NULL) — already exists ✓
  ├── agent_run_log.symbol           → symbol_reference.symbol (SET NULL)
  └── agent_run_log.trade_key        → trade_candidates.trade_key (SET NULL)

analysis_runs.user_id                → users.id              (RESTRICT) — already exists ✓
analysis_runs.chain_snapshot_id      → option_chain_snapshots.id (SET NULL) — already exists ✓
analyzed_trades.run_id               → analysis_runs.id      (CASCADE) — already exists ✓
analyzed_trades.user_id              → users.id              (RESTRICT) — already exists ✓
```

Note: `trade_recommendations.trade_key → trade_candidates.trade_key` and the corresponding `agent_run_log.trade_key` FK depend on confirming all existing `trade_key` values share a namespace. If they don’t, these FKs become application-enforced rather than DB-enforced (open question §6).

### 4.6 Insights Domain

```
insights
  ├── insights.source_position_id    → positions.position_id (SET NULL) — NEW COLUMN
  └── insights.user_id               → users.id              (RESTRICT) — NEW COLUMN
```

**Schema change required.** The current `insights` table has `entity_id` (varchar(100)) and `entity_label` (varchar(200)) as a polymorphic pointer, with no FK and no `user_id`. This conflicts with `architecture-plan.md` which describes `source_position_id` as an FK to `positions`.

Recommendation: keep the polymorphic `entity_id`/`entity_label` columns (they support the cross-domain Insight Engine), AND add a typed nullable `source_position_id` FK column for the common options case. The Insight Engine writes both when domain=‘options’ and `entity_id` matches a position_id. This makes the FK enforceable for the options domain while preserving the polymorphic model for future domains.

Also add `user_id` to `insights` — currently insights are not scoped per user, which violates the Data Isolation Invariant.

### 4.7 Other

```
user_favorites.user_id              → users.id              (CASCADE)
user_favorites.symbol               → symbol_reference.symbol (RESTRICT)

trade_log.user_id                   → users.id              (RESTRICT) — already exists ✓
trade_log.symbol                    → symbol_reference.symbol (RESTRICT)

symbol_quotes.user_id               → users.id              (CASCADE) — already exists ✓
symbol_quotes.symbol                → symbol_reference.symbol (RESTRICT)

option_chain_snapshots.user_id      → users.id              (CASCADE) — already exists ✓
option_chain_snapshots.symbol       → symbol_reference.symbol (RESTRICT)

validation_assessments.ticker       → symbol_reference.symbol (RESTRICT)

symbol_context.symbol               → symbol_reference.symbol (RESTRICT)

dashboard_media — no FK changes; widget_id is an opaque identifier
deploy_log — no FK changes; standalone log
audit_log.user_id → users.id (already exists ✓)
```

-----

## 5. JSON Column Validation

Every column currently typed `varchar(-1)` or `nvarchar(-1)` that holds JSON gets:

1. Type migration to `nvarchar(max)` (if not already).
1. `CHECK ([col] IS NULL OR ISJSON([col]) = 1)` constraint.

Columns:

|Table                    |Column                                                                                                                       |Notes                                                                                                                                                  |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
|`positions`              |`trade_structure`, `entry_greeks`, `entry_sma_alignment`, `claude_probability_matrix`, `claude_exit_levels`, `claude_verdict`|All structured JSON per architecture                                                                                                                   |
|`analyzed_trades`        |`score_breakdown`, `scoring_weights`                                                                                         |JSON                                                                                                                                                   |
|`analysis_runs`          |`scoring_weights`, `filter_params`                                                                                           |JSON                                                                                                                                                   |
|`option_chain_snapshots` |`chain_data`                                                                                                                 |JSON                                                                                                                                                   |
|`options_chain_snapshots`|`chain_json`                                                                                                                 |JSON *(if not dropped per §2)*                                                                                                                         |
|`trade_candidates`       |`legs`, `net_metrics`, `pipeline_components`, `claude_evaluation`                                                            |JSON                                                                                                                                                   |
|`trade_log`              |`legs`                                                                                                                       |JSON                                                                                                                                                   |
|`trade_recommendations`  |`market_snapshot`, `trade_snapshot`                                                                                          |JSON                                                                                                                                                   |
|`agent_run_log`          |`market_snapshot`, `trade_snapshot`                                                                                          |`model_response_raw` is excluded — Phase 0 found 94% non-JSON content (raw markdown from Claude). Treated as `nvarchar(max)` free text without `ISJSON`|
|`position_assessments`   |`exit_levels`, `market_snapshot`                                                                                             |`claude_read` is excluded — Phase 0 found 100% non-JSON content (plain prose). Treated as `nvarchar(max)` free text without `ISJSON`                   |
|`insights`               |`recommended_actions`, `source_signals`                                                                                      |JSON                                                                                                                                                   |
|`user_configs`           |`extra_settings`                                                                                                             |JSON                                                                                                                                                   |
|`user_favorites`         |`trade_data`                                                                                                                 |JSON                                                                                                                                                   |
|`symbol_context`         |`signal_value`                                                                                                               |JSON                                                                                                                                                   |
|`dashboard_layouts`      |`layout_json`, `widgets_json`                                                                                                |JSON                                                                                                                                                   |

Free-text columns (`prompt_system`, `prompt_user`, `body`, `verdict_summary`, `observation`, `baseline`) remain `nvarchar(max)` without ISJSON constraint.

-----

## 6. Fields Misdeclared as `varchar(-1)` That Should Be Right-Sized

These are short categorical or label values currently using `varchar(MAX)` for no reason:

|Table             |Column             |Current      |Proposed                                                |
|------------------|-------------------|-------------|--------------------------------------------------------|
|`trade_candidates`|`structure`        |`varchar(-1)`|`varchar(50)`                                           |
|`trade_candidates`|`scan_source`      |`varchar(-1)`|`varchar(50)`                                           |
|`trade_candidates`|`scan_strategy_key`|`varchar(-1)`|`varchar(50)`                                           |
|`positions`       |`source`           |`varchar(10)`|`varchar(10)` ✓ (already correct, listed for visibility)|

The varchar(MAX) misdeclarations in `trade_candidates` are the worst offenders. They cost index efficiency and storage.

-----

## 7. Required Indexes

Every FK gets a supporting index (Azure SQL does not auto-index FKs).

Additional composite indexes for known query patterns:

|Table                   |Index                                 |Purpose                                   |
|------------------------|--------------------------------------|------------------------------------------|
|`symbol_quotes`         |`(user_id, symbol, captured_at DESC)` |Latest quote per user-symbol              |
|`option_chain_snapshots`|`(user_id, symbol, captured_at DESC)` |Latest chain per user-symbol              |
|`option_chain_snapshots`|`(symbol, captured_at DESC)`          |Symbol-anchored time series               |
|`symbol_context`        |`(symbol, signal_type, expires_at)`   |TTL eviction & freshness lookup           |
|`positions`             |`(user_id, status, last_monitored_at)`|Position Monitor sweep                    |
|`positions`             |`(user_id, status)`                   |Active positions per user                 |
|`trade_candidates`      |`(user_id, scanned_at DESC)`          |Recent scans per user                     |
|`trade_candidates`      |`(symbol, scanned_at DESC)`           |Recent scans per symbol                   |
|`agent_run_log`         |`(user_id, created_at DESC)`          |AI call audit per user                    |
|`agent_run_log`         |`(trace_id)`                          |Span lookup                               |
|`agent_run_log`         |`(run_id)`                            |Run grouping                              |
|`analyzed_trades`       |`(run_id, composite_score DESC)`      |Ranked results per run                    |
|`insights`              |`(user_id, domain, surfaced_at DESC)` |Dashboard read pattern                    |
|`insights`              |`(source_position_id)`                |Position-anchored insights                |
|`user_sessions`         |`(session_id)` UNIQUE                 |Cookie lookup                             |
|`user_sessions`         |`(user_id, expires_at)`               |Cleanup + active session check            |
|`watchlist_symbols`     |`(watchlist_id, symbol)` UNIQUE       |Prevent duplicates within a watchlist     |
|`watchlists`            |`(user_id, name)` UNIQUE              |Prevent duplicate watchlist names per user|

-----

## 8. Recommended Views for Denormalized Access

Architecture rule going forward: **any denormalized projection lives as a view**, never as a redundant table.

Proposed initial views:

|View                        |Purpose                                             |Source Tables                                                                   |
|----------------------------|----------------------------------------------------|--------------------------------------------------------------------------------|
|`vw_active_positions`       |Active positions with current symbol metadata joined|`positions` + `symbol_reference` + latest `symbol_quotes`                       |
|`vw_watchlist_with_quotes`  |Watchlist rows joined to latest quote per symbol    |`watchlists` + `watchlist_symbols` + `symbol_reference` + latest `symbol_quotes`|
|`vw_recent_trade_candidates`|Trade candidates with linked Claude evaluation      |`trade_candidates` + `trade_recommendations`                                    |
|`vw_position_health_summary`|Per-user counts of positions by health grade        |`positions` aggregated                                                          |
|`vw_user_session_active`    |Active (non-expired) sessions joined to user profile|`user_sessions` + `users`                                                       |

Materialized views (`WITH SCHEMABINDING ... CREATE INDEX`) are reserved for heavy aggregations where the cost of refresh is justified. The initial five are standard views.

-----

## 9. PK Strategy Reconciliation

Architecture-plan.md notes inconsistent PK types as known-but-low-priority. This proposal does **not** mass-convert existing PKs (the cost-benefit isn’t there for purely internal IDs). Specific rules going forward:

- **Domain entities that emit IDs to clients** → `varchar(36)` UUID (`positions`, `trade_candidates`, `watchlists`, `insights`, `position_assessments`).
- **Append-only log/audit tables that never emit IDs** → `bigint IDENTITY` (`agent_run_log`, `audit_log`, `analyzed_trades`, `analysis_runs`, `symbol_quotes`, `option_chain_snapshots`, `dashboard_media`, `deploy_log`, `trade_log`, `user_favorites`, `user_configs`, `dashboard_layouts`).

For new tables: pick by emission rule above. Existing tables stay with their current PK type unless they emit to clients and use `int` (none in the current schema).

-----

## 10. Resolved Decisions

The six open questions are resolved as follows (Don, 2026-05-18):

1. **Live chain snapshot table:** `option_chain_snapshots` (singular) is live. `options_chain_snapshots` (plural) is dropped per §2.
1. **Trade key namespace:** **RESOLVED via Phase 0 audit (2026-05-18).** Namespace is heterogeneous. `trade_candidates.trade_key` is 100% UUID (334/334). `trade_recommendations.trade_key` is 100% semantic compound keys like `AMZN:215 Call:2026-04-17` (0/25 UUID). `agent_run_log.trade_key` matches that pattern (0/27 UUID). `user_favorites.trade_id` uses a third format (`nc-MO-67.5-…`, 0/2 UUID). Zero cross-table overlap. **FK is application-enforced. Column widths retained at current values** (`varchar(36)` for trade_candidates, `varchar(255)` for trade_recommendations and agent_run_log, `varchar(300)` for user_favorites). Future cleanup of the two-namespace divergence is out of scope for this normalization effort.
1. **Insights schema:** `source_position_id` (nullable FK to `positions.position_id`) and `user_id` (FK to `users.id`) are added. The polymorphic `entity_id`/`entity_label` columns remain for non-options domains.
1. **Session token storage:** `user_sessions.access_token_encrypted`, `refresh_token_encrypted`, and `id_token` migrate to `varbinary(max)`. Application code in `app/auth/session_manager.py` updates to write bytes directly instead of base64-encoding.
1. **`validation_assessments.ticker`:** Renamed to `symbol` for cross-table consistency. FK to `symbol_reference.symbol` (RESTRICT).
1. **Cascade rules:** Proposed defaults are accepted as-is.

### Decisions made after Phase 0 audit findings (2026-05-18)

1. **`$`-prefixed index symbol handling:** Option C from the audit follow-up — add `api_symbol varchar(20) NULL` column to `symbol_reference` with a filtered `UNIQUE` index (where `api_symbol IS NOT NULL`). Application code normalizes inbound `$X` API symbols to canonical `X` form before writing to any child table’s `symbol` column. The `api_symbol` column on `symbol_reference` exists for the reverse lookup (canonical → provider-specific) when calling external APIs. Phase 1b adds the column; Phase 3 (code review) wires the normalization.
1. **Missing common tickers in `symbol_reference`:** Backfill from the union of orphan symbol values found in Phase 0 (GLD, TSLA, VOO, VUG, WDC, WMT, QUAL, AGG, IEFA, IEMG, IJH, and others). Where descriptive metadata is unavailable, `name` defaults to the symbol string. Future symbol_reference re-import from a clean source is out of scope.
1. **Truncated UUID orphans (`6232a881-23e9-4954-8ed0-6303ea7d188`, 35 chars, missing final character):** Remap to Don’s real Entra OID via prefix-match lookup in `users` table. Affects 363 rows across `watchlists`, `trade_candidates`, `positions`, and `user_watchlist`.
1. **`dev-user` and `00000000-0000-0000-0000-000000000001` orphans:** Delete. These are `skip_auth` development artifacts with no historical value. Affects ~18 rows total.
1. **JSON column reclassification:** `position_assessments.claude_read` (128/128 = 100% non-JSON, plain prose) and `agent_run_log.model_response_raw` (608/650 = 94% non-JSON, raw markdown) are removed from §5’s JSON column list. Both remain `nvarchar(max)` free-text columns without `ISJSON` constraint. Only one JSON cleanup remains: `agent_run_log.market_snapshot` has 7 rows with the literal string `"null"` — these are set to SQL NULL in Phase 1a.

-----

## 11. Migration Sequence

Per OTA’s expand/contract Alembic discipline, the work splits across several deploys. A diagnostic phase precedes the structural work.

**Phase 0 — Data Integrity Audit (read-only, no deploy) — ✅ COMPLETE (2026-05-18)**

- Inventory dirty data that would block FK constraints. For each candidate FK in §4: LEFT JOIN to parent and count orphan rows. **Found:** 15 FK candidates with orphan rows, totaling ~5,706 rows. Bulk traces to (a) `$`-prefixed index symbols not in `symbol_reference` and (b) common tickers missing from `symbol_reference`. Findings drove resolved decisions §10.7–§10.11.
- Inventory dirty data that would block ISJSON constraints. **Found:** 2 columns reclassified out of JSON list (§10.11). Only `agent_run_log.market_snapshot` has 7 genuine cleanup rows (literal `"null"` strings).
- Resolve `trade_key` namespace question. **Found:** Heterogeneous, FK is application-enforced (§10.2).
- Inventory `user_id` orphans. **Found:** 363 rows under truncated UUID + ~18 rows under skip_auth artifacts (§10.9–§10.10).
- Output: `phase0-audit-report.md` at project root.

**Phase 1 — Expand (non-breaking, 1 deploy)**

- Apply Phase 0 cleanups (orphan deletions, JSON sanitization, user_id remapping for any rows worth keeping).
- Create new typed columns alongside old ones where width changes (`user_id_new varchar(36)`, etc.).
- Backfill from old columns with normalization.
- Verify zero data loss.

**Phase 2 — Add FK constraints (non-breaking, 1 deploy)**

- Add all FK constraints once new columns are populated and old orphan rows are cleaned up.
- Add all supporting indexes.
- Add ISJSON check constraints (these can fail if dirty JSON exists — clean first).

**Phase 3 — Code review & cutover (the body of work)**

- Audit every ORM model in `app/models/database.py` against the new schema.
- Update every query that filters/joins on the affected columns.
- Ship application changes that read/write only new columns.

**Phase 4 — Contract (after 14-day stability, 1 deploy)**

- Drop old columns.
- Drop dropped tables (§2).
- Rename `_new` columns to canonical names.

**Phase 5 — Architecture-plan update**

- Add a Data Normalization & Integrity ADR section enforcing the rules above.
- Document the views as the only sanctioned denormalization mechanism.
- Add the standardization rules (§3) and FK requirements (§4) as code-review checklist items.

-----

## 12. What Changes in `architecture-plan.md`

After approval, the Data section (currently the “Data Models (Azure SQL)” passage) gets a new subsection: **Data Normalization & Referential Integrity**. Bullet sketch:

- Every `user_id` column is `varchar(36)` with FK to `users.id`.
- Every `symbol` column is `varchar(20)` with FK to `symbol_reference.symbol`.
- Every JSON-bearing text column is `nvarchar(max)` with `ISJSON` check.
- Every FK has a supporting index.
- Denormalized projections are views, not tables. New table proposals must demonstrate why a view is insufficient.
- New table reviews: PR description must declare PK type, FK targets, index plan, and JSON validation choices.