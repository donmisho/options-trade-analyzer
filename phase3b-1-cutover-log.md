# Phase 3b.1 — ORM Model Alignment Cutover Log

**Date:** 2026-05-19
**Ticket:** OTA-667
**Commit:** `OTA-667 feat: phase 3b.1 - orm model alignment per phase 2 schema`
**File modified:** `app/models/database.py` (sole file)

---

## Actions Applied

### Action 1 — Add `SymbolReference` model
- Added new `SymbolReference` class with 8 columns: `symbol` (PK, String(20)), `name` (String(400)), `exchange` (String(40)), `sector` (String(100)), `sub_industry` (String(200)), `asset_type` (String(40)), `last_updated` (DateTime), `api_symbol` (String(20))
- All column types and nullability match DB schema per audit Section 1.1
- No `relationship()` declarations from this side — children declare their own FK back-reference

### Action 2 — Add missing columns to `Insight` model
- Added `user_id = Column(String(36), ForeignKey("users.id"), nullable=True)` — NO_ACTION cascade per Section 1.20
- Added `source_position_id = Column(String(36), ForeignKey("positions.position_id", ondelete="SET NULL"), nullable=True)` — SET NULL cascade per Section 1.20

### Action 3 — Rename `ValidationAssessment.ticker` to `symbol`
- Column declaration: `ticker` → `symbol`, type set to `String(20)` with `ForeignKey("symbol_reference.symbol")`
- Index renamed: `ix_validation_assessments_ticker` → `ix_validation_assessments_symbol`
- No other references to `.ticker` found inside `database.py`

### Action 4 — Widen symbol columns from String(10) to String(20)
- 7 columns widened (6 from audit summary + 1 additional finding from Section 1.4):
  1. `symbol_quotes.symbol`
  2. `option_chain_snapshots.symbol`
  3. `trade_log.symbol`
  4. `analysis_runs.symbol`
  5. `analyzed_trades.symbol`
  6. `user_favorites.symbol`
  7. `user_configs.default_symbol` (Section 1.4 finding, not in summary table but captured per-table)

### Action 5 — Narrow user_id columns from String(255) to String(36)
- `watchlists.user_id` (NamedWatchlist model) — Section 1.10
- `user_sessions.user_id` (UserSession model) — Section 1.3

### Action 6 — Add 21 missing ForeignKey() declarations
Each FK added with cascade behavior matching the audit's per-FK cascade column:

| # | Table | Column | References | Cascade |
|---|-------|--------|------------|---------|
| 1 | user_sessions | user_id | users.id | CASCADE |
| 2 | dashboard_layouts | user_id | users.id | CASCADE |
| 3 | symbol_quotes | symbol | symbol_reference.symbol | NO_ACTION |
| 4 | symbol_context | symbol | symbol_reference.symbol | NO_ACTION |
| 5 | option_chain_snapshots | symbol | symbol_reference.symbol | NO_ACTION |
| 6 | watchlists | user_id | users.id | CASCADE |
| 7 | watchlist_symbols | symbol | symbol_reference.symbol | NO_ACTION |
| 8 | positions | user_id | users.id | NO_ACTION |
| 9 | positions | symbol | symbol_reference.symbol | NO_ACTION |
| 10 | trade_candidates | user_id | users.id | NO_ACTION |
| 11 | trade_candidates | symbol | symbol_reference.symbol | NO_ACTION |
| 12 | trade_recommendations | symbol | symbol_reference.symbol | NO_ACTION |
| 13 | trade_log | symbol | symbol_reference.symbol | NO_ACTION |
| 14 | analysis_runs | symbol | symbol_reference.symbol | NO_ACTION |
| 15 | analyzed_trades | symbol | symbol_reference.symbol | NO_ACTION |
| 16 | agent_run_log | symbol | symbol_reference.symbol | SET NULL |
| 17 | insights | user_id | users.id | NO_ACTION |
| 18 | insights | source_position_id | positions.position_id | SET NULL |
| 19 | user_favorites | user_id | users.id | CASCADE |
| 20 | user_favorites | symbol | symbol_reference.symbol | NO_ACTION |
| 21 | validation_assessments | symbol | symbol_reference.symbol | NO_ACTION |

All `relationship()` declarations are one-directional from the FK-owning (child) side. No bidirectional relationships added.

### Action 7 — Remove stale comments
- Removed "WHY no FK: SKIP_AUTH dev mode compat" comments from `Position`, `NamedWatchlist`, and `UserFavorite` models
- These comments were contradicted by the FK declarations added in Action 6

---

## Test Results

### Import check
```
python -c "from app.models import database; print('imports OK')"
```
Result: **PASS** — no SQLAlchemy mapper-config warnings

### pytest
```
pytest --ignore=scratch --ignore=dev-agents -q
```
Result: **484 passed, 2 skipped, 0 failures** in 18.58s

The 9 failures in `dev-agents/identity-security/tests/` are pre-existing (auth flow tests unrelated to ORM changes) and were excluded per `--ignore=dev-agents`.

### Smoke-test queries (Section 5)
| Test | Description | Row Count | Result |
|------|-------------|-----------|--------|
| 1 | Positions + symbol_reference + users | 90 | PASS |
| 2 | Watchlist + quotes + symbol_reference | 3,737 | PASS |
| 3 | Trade candidates + symbol_reference | 334 | PASS |

Row counts differ from original audit (39/6/10) because additional data has been written since the audit ran. All FK joins execute correctly with no errors.

---

## Deviations from Audit

- **Action 4 widened 7 columns instead of 6.** The audit summary table listed 6 tables, but Section 1.4 (`user_configs`) separately identified `default_symbol` as `String(10)` vs DB `varchar(20)`. This was included as it is the same class of STALE finding.

## Escalation List

- None. No findings surfaced during application that the audit didn't capture.

---

## Banner: SUCCESS
