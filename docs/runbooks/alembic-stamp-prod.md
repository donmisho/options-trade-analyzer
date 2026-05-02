# One-Time Production Database Alembic Stamp

**Baseline revision ID:** `f9e59a180957`
**Baseline file:** `alembic/versions/20260501_2101_f9e59a180957_baseline_schema_matching_production.py`
**OTA ticket:** OTA-540
**Must run before:** any subsequent `alembic upgrade head` is ever executed against production

---

## Background

OTA-540 introduced Alembic as the schema migration framework. Before this, the app used
`metadata.create_all()` (in `app/models/session.py`) plus a hand-written `app/models/migrations.py`
for additive ALTER TABLE changes.

The production Azure SQL database (`options-analyzer-db`) already has all tables from the
ORM's full history. The baseline migration (`f9e59a180957`) represents this current state.

**Stamping** tells Alembic "this database is already at this revision" without running the
migration DDL. It is the correct way to onboard an existing database to Alembic version control.

**WARNING:** Do NOT run `alembic upgrade head` against an unstamped production database.
That would attempt to re-create all tables (which already exist), fail with "table already
exists" errors, and leave the `alembic_version` table in an inconsistent state.

---

## Pre-conditions

- [ ] The OTA-540 build artifact has been deployed to production (App Service `options-analyzer-api`)
- [ ] You are running from a workstation with:
  - `az login` completed as `don.mishory@tmtctech.ai` (prod Entra credentials)
  - Network access to `options-analyzer-sql.database.windows.net` (check firewall rules)
  - The project venv activated: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Unix)
  - All dependencies installed: `pip install -r requirements.txt`
- [ ] `DATABASE_URL` in your local `.env` points to the production Azure SQL database, OR
  set it inline as shown in the commands below

---

## Procedure

### Step 1 — Verify the baseline revision matches current prod schema

Before stamping, visually confirm the baseline migration file represents the actual prod schema.
Run this query against prod Azure SQL (via Azure Portal Query Editor or sqlcmd):

```sql
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Expected tables (25 total):

```
agent_run_log, analysis_runs, analyzed_trades, audit_log, dashboard_layouts,
dashboard_media, insights, option_chain_snapshots, options_chain_snapshots,
position_assessments, positions, schwab_tokens, strategy_configs, symbol_context,
symbol_quotes, trade_log, trade_recommendations, user_configs, user_favorites,
user_sessions, user_watchlist, users, validation_assessments, watchlist_symbols, watchlists
```

If any table is missing, investigate before stamping. Do not stamp if the schema is materially
different from the baseline — open an OTA ticket instead.

### Step 2 — Confirm `alembic_version` does not already exist

```sql
SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'alembic_version';
```

If this table already exists with a row, the database has already been stamped. Stop here —
do not stamp again. Run `alembic current` to see the current revision instead.

### Step 3 — Stamp the database

From the project root (with venv activated and prod credentials):

```bash
alembic stamp f9e59a180957
```

Or with an explicit DATABASE_URL override (if your local .env points to dev):

```bash
DATABASE_URL="mssql+pyodbc://options-analyzer-sql.database.windows.net:1433/options-analyzer-db" \
  alembic stamp f9e59a180957
```

### Step 4 — Verify the stamp succeeded

```bash
alembic current
```

Expected output:
```
f9e59a180957 (head)
```

Also confirm in the database:

```sql
SELECT version_num FROM alembic_version;
-- Expected: f9e59a180957
```

### Step 5 — Capture and attach output to OTA-540

Copy the output of steps 3 and 4 and add it as a comment to OTA-540 in Jira.
This creates the permanent record that the prod database was stamped on this date.

---

## After stamping — ongoing migration discipline

From this point forward, every schema change MUST follow expand/contract discipline:

1. **Expand:** Add new column/table/index via `alembic revision --autogenerate -m "description"`.
   The migration must be additive only (no DROP, no NOT NULL on existing columns without a default).
2. **Deploy:** Ship the application with the new code + migration to production.
3. **Contract (deferred ≥14 days):** After ≥14 days of prod stability, generate a second migration
   to drop obsolete columns/tables. Log the deferred action in OTA-523 (Database Contract Actions)
   before the 14-day window opens.

The CI gate in `build-on-push.yml` will fail any push that modifies `app/models/database.py`
without a corresponding new file in `alembic/versions/`.

---

## Rollback / if something goes wrong

If the stamp runs but you discover the schema differs significantly from the baseline:

```bash
# Remove the stamp (deletes the alembic_version row — does NOT change any application tables)
alembic stamp --purge
```

Then investigate the schema discrepancy, update the baseline migration or create a reconciliation
migration, and re-stamp.

---

## Dev environment note

The development database (shared Azure SQL, same instance) is also untracked until stamped.
Stamp dev first to validate the procedure, then stamp prod:

```bash
# Stamp dev (your local .env DATABASE_URL typically points here already)
alembic stamp f9e59a180957
alembic current  # should print: f9e59a180957 (head)
```

The dev stamp also serves as a dry run that proves the `alembic_version` table can be created
and the revision ID is accepted correctly.
