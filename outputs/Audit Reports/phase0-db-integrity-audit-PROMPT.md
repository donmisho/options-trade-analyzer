-----

prompt_name: Phase 0 — Database Integrity Audit
phase: 0
mode: read-only
ticket: TBD (no Jira ticket yet)
prerequisites:

- database-normalization-proposal.md exists at project root
- venv is activated
- .env (or App Service env vars) point to the database to be audited
  gates:
- DO NOT modify any database schema
- DO NOT create or run Alembic migrations
- DO NOT delete or update any rows
- DO NOT advance any Jira ticket
- DO NOT commit (a script file is created and the report is written, but no git commit is made)
  allowedTools:
- Read
- Write
- Glob
- Grep
- Bash

-----

# Phase 0 — Database Integrity Audit

## What This Prompt Accomplishes

This is a **read-only** audit of the OTA Azure SQL database. The purpose is to surface every piece of data that would block the Phase 1 normalization migrations from succeeding — orphan foreign-key targets, malformed JSON, format anomalies in identifier columns, and namespace inconsistencies in `trade_key`.

The output is a single markdown report (`phase0-audit-report.md` at project root) that lists each finding with row counts and concrete examples. The report is what Phase 1’s cleanup migration is built from.

**No schema changes. No row updates. No commits. No Jira advancement.** This prompt is pure diagnostic.

-----

## Step 1 — Verify Environment

Before doing anything else:

1. Confirm `venv` is activated. If not, ask the user to activate it and stop.
1. Confirm `database-normalization-proposal.md` exists at the project root. If not, stop with the message: *“Phase 0 prompt requires database-normalization-proposal.md at project root. Drop the file there and re-run.”*
1. Print the current database target. Read it from `app/core/config.py` settings or the actual env vars (`DATABASE_URL` or whatever the project uses). Print the resolved server + database name so the user knows which environment is about to be audited.
1. Wait for the user to confirm the target is correct before proceeding.

This confirmation is mandatory. Auditing the wrong environment wastes time and produces a misleading report.

-----

## Step 2 — Locate ORM Models

Read `app/models/database.py` (the 928-line single file per architecture-plan.md). Build an internal mental map of:

- Which ORM model corresponds to each table named in the audit targets below
- Which columns in those models are nullable
- Which columns already have FK constraints declared in the ORM

You do not need to write this mapping anywhere — it informs your queries (you’ll need correct quoted identifiers, and you’ll need to know whether to filter NULLs from orphan counts).

If a model is missing for a table that exists in the database (e.g., `user_watchlist` or `options_chain_snapshots`), note it. The audit still queries the table by its raw name.

-----

## Step 3 — Generate the Audit Script

Create `scripts/audits/phase0_db_integrity.py` (create the `scripts/audits/` directory if it doesn’t exist).

The script must:

1. Use the existing app’s database connection mechanism (likely `from app.models.session import async_session_maker` or equivalent — find the actual import in the codebase).
1. Be async and use SQLAlchemy 2.x.
1. Run every audit query listed in Step 4 below.
1. Collect results in memory and emit the report file at the end (do not interleave file writes with queries).
1. Be re-runnable — no side effects of any kind.

Print a one-line status to stdout for each audit section as it runs (e.g., `[1/N] Auditing user_id FK candidates...`). Print final summary counts to stdout at the end so the user sees the headline numbers without opening the report.

-----

## Step 4 — Audit Targets

The audit has four sections. Run them in order.

### Section A — Foreign Key Orphan Counts

For each (child_table, child_column, parent_table, parent_column) below, count rows where `child.col IS NOT NULL` and there is no matching row in `parent.col`. Capture: the count, and up to 5 sample orphan values (for the report’s “examples” subsection).

The complete FK candidate list is in **§4 of the proposal**. For Phase 0 audit purposes, include both NEW FKs and ALREADY-EXISTING FKs. The already-existing FKs are technically already enforced, so the orphan count should be zero — but verifying that is part of the audit. If a should-be-enforced FK reports orphans, that is a bug to surface.

The complete list to audit:

|Child Table           |Child Column      |Parent Table          |Parent Column|Notes                                                                                                     |
|----------------------|------------------|----------------------|-------------|----------------------------------------------------------------------------------------------------------|
|user_sessions         |user_id           |users                 |id           |Width mismatch (255 vs 36) — check both literal-match orphans and the count of values longer than 36 chars|
|user_configs          |user_id           |users                 |id           |Already FK ✓ — verify zero orphans                                                                        |
|audit_log             |user_id           |users                 |id           |Already FK ✓ — verify zero orphans                                                                        |
|dashboard_layouts     |user_id           |users                 |id           |                                                                                                          |
|symbol_quotes         |user_id           |users                 |id           |Already FK ✓                                                                                              |
|symbol_quotes         |symbol            |symbol_reference      |symbol       |                                                                                                          |
|symbol_context        |symbol            |symbol_reference      |symbol       |                                                                                                          |
|option_chain_snapshots|user_id           |users                 |id           |Already FK ✓                                                                                              |
|option_chain_snapshots|symbol            |symbol_reference      |symbol       |                                                                                                          |
|watchlists            |user_id           |users                 |id           |Width mismatch (255 vs 36)                                                                                |
|watchlist_symbols     |watchlist_id      |watchlists            |id           |Already FK ✓                                                                                              |
|watchlist_symbols     |symbol            |symbol_reference      |symbol       |                                                                                                          |
|user_watchlist        |user_id           |users                 |id           |Table is slated for drop — but count orphans anyway, to confirm it’s drop-safe                            |
|user_watchlist        |symbol            |symbol_reference      |symbol       |Same — count orphans, confirm drop-safe                                                                   |
|trade_candidates      |user_id           |users                 |id           |                                                                                                          |
|trade_candidates      |symbol            |symbol_reference      |symbol       |                                                                                                          |
|trade_recommendations |user_id           |users                 |id           |Width mismatch (72 vs 36)                                                                                 |
|trade_recommendations |symbol            |symbol_reference      |symbol       |                                                                                                          |
|agent_run_log         |user_id           |users                 |id           |Already FK ✓                                                                                              |
|agent_run_log         |symbol            |symbol_reference      |symbol       |                                                                                                          |
|analysis_runs         |user_id           |users                 |id           |Already FK ✓                                                                                              |
|analysis_runs         |symbol            |symbol_reference      |symbol       |                                                                                                          |
|analysis_runs         |chain_snapshot_id |option_chain_snapshots|id           |Already FK ✓                                                                                              |
|analyzed_trades       |run_id            |analysis_runs         |id           |Already FK ✓                                                                                              |
|analyzed_trades       |user_id           |users                 |id           |Already FK ✓                                                                                              |
|analyzed_trades       |symbol            |symbol_reference      |symbol       |                                                                                                          |
|positions             |user_id           |users                 |id           |                                                                                                          |
|positions             |symbol            |symbol_reference      |symbol       |                                                                                                          |
|position_assessments  |position_id       |positions             |position_id  |Already FK ✓                                                                                              |
|trade_log             |user_id           |users                 |id           |Already FK ✓                                                                                              |
|trade_log             |symbol            |symbol_reference      |symbol       |                                                                                                          |
|user_favorites        |user_id           |users                 |id           |                                                                                                          |
|user_favorites        |symbol            |symbol_reference      |symbol       |                                                                                                          |
|validation_assessments|ticker            |symbol_reference      |symbol       |Column will be renamed to `symbol` in Phase 1                                                             |
|dashboard_media       |(no FK candidates)|—                     |—            |Skip                                                                                                      |
|deploy_log            |(no FK candidates)|—                     |—            |Skip                                                                                                      |

For each orphan finding, also report **distinct count** of orphan values (e.g., “user_id has 1,247 orphan rows but only 4 distinct orphan values: dev-user, 00000000-0000-0000-0000-000000000001, …”).

### Section B — `trade_key` Namespace Audit

This section answers proposal §10 question 2.

For each of:

- `trade_candidates.trade_key`
- `trade_recommendations.trade_key`
- `agent_run_log.trade_key`
- `user_favorites.trade_id` (note column name is `trade_id` here — confirm whether it shares the namespace)

Report:

1. **Total non-null row count**
1. **Distinct value count**
1. **Min length, max length, average length**
1. **UUID format conformance**: count of values matching `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` (case-insensitive), and count NOT matching. For Azure SQL use `LIKE` with the pattern equivalent or test via Python regex by pulling distinct values.
1. **Up to 10 sample non-UUID values** (so the user can see the actual format)

After per-table stats, compute namespace overlap:

1. **Count of `trade_key` values present in `trade_recommendations` but NOT in `trade_candidates`** (orphan recommendation keys)
1. **Count of `trade_key` values present in `agent_run_log` but NOT in `trade_candidates`** (orphan agent-run keys)
1. **Count of `trade_id` values in `user_favorites` that ARE valid UUIDs and ARE present in `trade_candidates.trade_key`** (to determine if `trade_id` is actually `trade_key` under a different name)

### Section C — JSON Column Validity

For every column listed in **§5 of the proposal**, run:

```sql
SELECT COUNT(*) FROM <table> WHERE <col> IS NOT NULL AND ISJSON(<col>) = 0
```

The complete list of JSON columns to test:

|Table                 |Column                   |
|----------------------|-------------------------|
|positions             |trade_structure          |
|positions             |entry_greeks             |
|positions             |entry_sma_alignment      |
|positions             |claude_probability_matrix|
|positions             |claude_exit_levels       |
|positions             |claude_verdict           |
|analyzed_trades       |score_breakdown          |
|analyzed_trades       |scoring_weights          |
|analysis_runs         |scoring_weights          |
|analysis_runs         |filter_params            |
|option_chain_snapshots|chain_data               |
|trade_candidates      |legs                     |
|trade_candidates      |net_metrics              |
|trade_candidates      |pipeline_components      |
|trade_candidates      |claude_evaluation        |
|trade_log             |legs                     |
|trade_recommendations |market_snapshot          |
|trade_recommendations |trade_snapshot           |
|agent_run_log         |market_snapshot          |
|agent_run_log         |trade_snapshot           |
|agent_run_log         |model_response_raw       |
|position_assessments  |claude_read              |
|position_assessments  |exit_levels              |
|position_assessments  |market_snapshot          |
|insights              |recommended_actions      |
|insights              |source_signals           |
|user_configs          |extra_settings           |
|user_favorites        |trade_data               |
|symbol_context        |signal_value             |
|dashboard_layouts     |layout_json              |
|dashboard_layouts     |widgets_json             |

For each column report: total non-null rows, invalid-JSON row count, and if invalid-JSON count > 0, capture up to 3 sample invalid values (truncated to first 200 chars each).

**Special case — `agent_run_log.model_response_raw`**: the proposal flagged this as “may not be JSON in every case.” Report invalid-JSON counts separately for this column without flagging them as errors. The finding informs whether the ISJSON constraint applies to this column or not.

### Section D — Width and Format Anomalies

Run the following analyses:

1. **`user_id` columns wider than 36 chars in actual data.** For each table with a `user_id` column, count rows where `LEN(user_id) > 36`. Report sample values from each (truncated to 60 chars).
1. **`symbol` columns wider than 20 chars in actual data.** Same pattern for each table holding a `symbol` column. Include `validation_assessments.ticker`.
1. **`trade_candidates` short-categorical columns currently typed `varchar(MAX)`:**
- `structure`: report distinct value count and max observed length
- `scan_source`: same
- `scan_strategy_key`: same
   
   The proposal proposes shrinking these to `varchar(50)`. The audit answers: do any actual values exceed 50 chars?
1. **`expiration` columns currently typed `varchar(20)`** (in `analyzed_trades`, `trade_log`, `trade_candidates` (if present), `trade_recommendations`):
- Sample 10 distinct values from each
- Identify the format (`YYYY-MM-DD`, `MM-DD-YYYY`, `YYYY-MM-DD HH:MM:SS`, mixed)
- Count rows where the value does not parse to a date
1. **`insights.entity_id` cross-domain check (per proposal §4.6 resolution):**
- For rows where `domain = 'options'`, count `entity_id` values that match the format of `positions.position_id` (UUID).
- Of those, count how many `entity_id` values are present in `positions.position_id` (this informs the backfill of the new `source_position_id` column in Phase 1).

-----

## Step 5 — Generate the Report

Write the report to `phase0-audit-report.md` at project root.

Structure:

```markdown
# Phase 0 Database Integrity Audit — Report

**Run at:** <timestamp UTC>
**Database target:** <server>/<database>
**Generated by:** Phase 0 audit prompt (read-only)

## Executive Summary

- Total FK candidates audited: N
- FK candidates with orphan rows: N (listed below)
- JSON columns audited: N
- JSON columns with invalid JSON values: N
- Total invalid-JSON rows: N
- `trade_key` namespace finding: [one-sentence conclusion]
- Width/format anomalies: [one-sentence summary]

## Section A — Foreign Key Orphans

[Table per FK candidate. Columns: child, parent, orphan rows, distinct orphan values, sample values, severity (BLOCKER | WARN | OK).]

A finding is BLOCKER when orphans exist and the FK is a NEW constraint being added in Phase 2. A finding is WARN when orphans exist and the FK already exists in the schema (this means the ORM declares an FK that isn't enforced at the DB level — separate investigation needed). A finding is OK when zero orphans.

## Section B — `trade_key` Namespace

[Per-table stats + cross-table overlap. End with a one-sentence recommendation: "trade_key can be standardized at varchar(36) UUID with DB-enforced FK" OR "trade_key namespace is heterogeneous — FK must remain application-enforced, retain wider column type."]

## Section C — JSON Validity

[Table per JSON column. Columns: table, column, non-null rows, invalid-JSON rows, percent invalid, sample invalid values, recommendation (APPLY ISJSON CHECK | CLEAN FIRST | DO NOT APPLY).]

## Section D — Width and Format Anomalies

[Subsection per anomaly type.]

## Cleanup Tasks for Phase 1

[Numbered list. One task per BLOCKER finding from Section A and per CLEAN FIRST finding from Section C. Each task has: table, column, action, estimated row impact.]

## Open Items for User Review

[Any finding where the audit cannot recommend automatically — e.g., orphan user_ids that may be legitimate test data, JSON columns where the invalid rows might be intentional NULLs-as-string. The user decides keep-vs-purge.]
```

-----

## Step 6 — Stop Gate

After the report is written:

1. Print the executive summary to stdout
1. Print the absolute path of `phase0-audit-report.md`
1. Print the absolute path of `scripts/audits/phase0_db_integrity.py`
1. **Stop.**

Do **not**:

- Commit any files
- Create or modify any Alembic migration
- Modify any ORM model
- Advance any Jira ticket
- Suggest follow-up actions (the user reviews the report and decides Phase 1 scope)

Confirm in the final stdout message that no schema changes were made and no rows were modified.