# <OTA-TICKET> — Phase 3a: ORM & application code audit (read-only)

## Terminal context

- This terminal: Terminal A (single-terminal session)
- Concurrent terminals: none
- Cross-terminal dependencies: none — Phase 2 (Alembic revision `ade9a09d8001`) must be at HEAD

## Required reading

Before any inspection:

```powershell
cat claude_context\CLAUDE.md
cat claude_context\architecture-plan.md
cat database-normalization-proposal.md
cat phase1a-cleanup-log.md
cat phase1a-followup-repair-log.md
cat phase1b-migration-log.md
cat phase2-diagnostic-report.md
cat phase2-migration-log.md
```

Note: the normalization-proposal and Phase log files live at **project root**, not under `claude_context\`.

## Relevant Context — Do Not Deviate Without Escalation

### Source: database-normalization-proposal.md §11 (Migration Sequence)

Phase 3 is "Code review & cutover (the body of work)":

- Audit every ORM model in `app/models/database.py` against the new schema.
- Update every query that filters/joins on the affected columns.
- Ship application changes that read/write only new columns.

**Phase 3a is read-only.** No edits to ORM models, schemas, routes, services, or queries. Output is `phase3a-orm-audit-report.md` at project root plus a recommended action list for Phase 3b. Phase 3b applies the changes only after Don approves the report.

### Source: database-normalization-proposal.md §10.7 (api_symbol normalization is Phase 3 wiring)

> "Application code normalizes inbound `$X` API symbols to canonical `X` form before writing to any child table's `symbol` column. The `api_symbol` column on `symbol_reference` exists for the reverse lookup (canonical → provider-specific) when calling external APIs. Phase 1b adds the column; Phase 3 (code review) wires the normalization."

Phase 3a inventories every inbound and outbound symbol code path. Phase 3b implements the helpers and routes the writes through them.

### Source: database-normalization-proposal.md §4.6 (insights wiring is Phase 3 work)

Phase 2 added `insights.source_position_id` and `insights.user_id` as **nullable** FK columns. They will be NULL on every new insight write until application code is updated. Phase 3a inventories every insight write path. Phase 3b wires the writes.

**Tightening these columns to NOT NULL is out of scope.** That happens in a later phase, after backfill confirms 100% population. Do not propose it for 3b.

### Source: phase2-diagnostic-report.md and phase2-migration-log.md

Two §7 column-name stale references were caught during Phase 2 and corrected at index-creation time. Treat the **actual database column names** as canonical:

- `agent_run_log.otel_trace_id` (not `trace_id`)
- `insights.created_at` (not `surfaced_at`)

Phase 3a verifies the ORM uses the actual names. Any ORM declaration referencing `trace_id` or `surfaced_at` is a STALE finding.

### Source: database-normalization-proposal.md §10.2 (trade_key namespace is application-enforced)

`trade_recommendations.trade_key` and `agent_run_log.trade_key` are **not** DB-FK-enforced (heterogeneous namespace, Phase 0 finding). Phase 3a's query audit identifies any join that relies on these being uniform, and Phase 3b adds application-layer guards if needed. Do not propose adding DB FKs.

### Source: CLAUDE.md (Two-Claude workflow, async-first Azure, prompt structure)

- All Azure SDK calls in async FastAPI handlers must use `.aio` async variants — flag any sync `azure.identity` call as BREAKING.
- Phase 3a never commits. The work ends at the report and a chat summary.

## Scope

### Phase 1 — Read-only audit

Output: `phase3a-orm-audit-report.md` at project root, structured as the seven sections below.

#### Section 1. ORM model audit

For every table touched by Phase 1a / 1b / 2, compare `app/models/database.py` (and any per-domain split files if `models/` has been broken up — check first) against the actual database schema.

Tables in scope:

- `users`, `user_sessions`, `user_configs`, `dashboard_layouts`, `audit_log`
- `symbol_reference`, `symbol_quotes`, `symbol_context`
- `option_chain_snapshots`
- `watchlists`, `watchlist_symbols`
- `positions`, `position_assessments`
- `trade_candidates`, `trade_recommendations`, `trade_log`
- `analysis_runs`, `analyzed_trades`
- `agent_run_log`
- `insights`
- `user_favorites`, `validation_assessments`

For the DB side, query `sys.columns`, `sys.foreign_keys + sys.foreign_key_columns`, and `sys.check_constraints`. For the ORM side, parse the model declarations.

For each table, report:

- Column declarations in ORM vs columns in DB. Flag:
  - **Type mismatches** (e.g., `String(255)` for a column that is now `varchar(36)`)
  - **Nullability mismatches**
  - **Missing columns in ORM** (column exists in DB but not in model — `insights.user_id` and `insights.source_position_id` are very likely findings here)
  - **Extra columns in ORM** (model has column but DB doesn't)
- FK declarations in ORM (`ForeignKey()` + `relationship()`) vs FKs in DB. Flag any FK missing from the ORM. Existing relationships that don't yet reflect Phase 2 FKs are common findings.
- Check constraints — informational only (SQLAlchemy doesn't need ISJSON declared at the model level; they're DB-enforced). Just note presence.

Each divergence gets a severity label:

- **BREAKING** — ORM will fail or return wrong results against the current schema.
- **STALE** — ORM uses old patterns but doesn't fail (e.g., over-spec'd width).
- **MISSING-RELATIONSHIP** — FK exists in DB, no `relationship()` in ORM — raw-column joins still work, but `.relationship` access doesn't.

#### Section 2. Query audit

Grep the backend for query patterns that may be affected by the new schema:

- Filters on `user_id` that pass values not normalized to `varchar(36)` shape (the truncated-UUID class of orphan was cleaned in Phase 1a, but new code paths may still emit varying widths).
- Filters or writes on `symbol` columns where the input has not been canonicalized (`$`-prefix or other provider-specific form).
- Cross-table joins that now span a Phase 2 FK boundary — confirm the join uses the FK column and not a stringly-typed parallel field.
- Writes to `insights` — list every call site that constructs an Insight row.
- Writes to `agent_run_log` referencing `trace_id`, `surfaced_at`, or any other stale column name.

Search globs:

```powershell
# Backend
Get-ChildItem -Recurse -Path app -Include *.py
# Frontend (symbol-handling only — not full audit)
Get-ChildItem -Recurse -Path web\src -Include *.js,*.jsx,*.ts,*.tsx
```

For each finding, report file path, line number, current pattern (one-line excerpt), severity, and proposed fix in one sentence.

#### Section 3. api_symbol normalization audit

Per §10.7 the Phase 3 wiring has two halves:

1. **Inbound canonicalization** — wherever a symbol arrives from an external source (Schwab API, Finnhub API, request body, scan input) and gets written to any child table's `symbol` column, strip `$` prefix and resolve via `symbol_reference.api_symbol` lookup if needed. Canonical form is what gets persisted.
2. **Outbound reverse lookup** — wherever the app calls an external provider with a symbol, convert canonical → `api_symbol` if the row's `api_symbol` differs.

For each:

- List every code path that performs the operation today.
- Note whether each path is correct, missing, or partially correct.
- Recommend a single helper-module location (e.g., `app/services/symbol_normalization.py`) and proposed function signatures.

#### Section 4. insights wiring audit

Find every code path that creates or updates a row in `insights`. For each:

- Does it pass `user_id`? If not, what is the user context at the call site?
- For domain='options' insights: does it pass `source_position_id`? If not, where does the `entity_id` (current polymorphic field) come from, and can it be resolved to a `positions.position_id`?

Report file path, line number, severity, and proposed fix per call site.

#### Section 5. Representative query smoke test

Pick three representative read paths and run them against the dev DB as the application code is today. **Do not modify code** — execute via a one-off script or REPL that uses the same SQLAlchemy session factory the app uses.

Candidate read paths:

1. Active positions for a user, joined to `symbol_reference` and `users`.
2. Latest quote for each symbol in a user's default watchlist (`watchlists` + `watchlist_symbols` + `symbol_quotes` + `symbol_reference`).
3. Recent trade candidates for a user joined to `symbol_reference` (last 24 hours).

For each: report success / failure, row count, and any SQLAlchemy warnings. If a query fails or warns, that's a BREAKING finding for Section 1.

#### Section 6. Async credential check

Per CLAUDE.md, every Azure SDK call in async FastAPI handlers must use `azure.identity.aio`. Grep `app/` for `from azure.identity import` (without `.aio`) and any sync `DefaultAzureCredential()` usage inside `async def` handlers. Report findings.

This is a known-risk spot from the BFF work; Phase 3a documents the current state even if the fix is out of scope.

#### Section 7. Recommended 3b sub-phase action list

The report ends with a structured action list grouped by recommended sub-phase. Suggested structure (Claude Code may propose a different split if the audit findings warrant it):

- **3b.1 — ORM model alignment.** Update `app/models/database.py` (and split files if applicable). Add missing columns, add missing relationships, correct type widths, correct stale names.
- **3b.2 — api_symbol normalization helpers + wiring.** Create the helper module from Section 3's recommendation. Route every write/read path identified.
- **3b.3 — insights write wiring.** Populate `user_id` and `source_position_id` on every insight write per Section 4.
- **3b.4 — Query fixes.** Apply the per-line fixes from Section 2.

For each sub-phase, include:

- Estimated LOC changed
- Files touched
- Whether the work is mechanical (low-risk) or judgment-required (high-risk)
- Whether it can ship independently or depends on a sibling sub-phase

**If the total scope across 3b.1–3b.4 exceeds ~500 LOC of code change or touches more than ~20 files, recommend a further split** (e.g., 3b.1a / 3b.1b by domain) and propose the split.

### Phase 2 — Stop and report

Write `phase3a-orm-audit-report.md`. Post a one-screen summary in chat covering: total findings by severity, the three smoke-test outcomes, and the recommended 3b sub-phase split. **Do not write a Phase 3b prompt** — Claude.ai handles that after Don approves the action list.

## Acceptance criteria

- [ ] `phase3a-orm-audit-report.md` exists at project root with all seven sections populated.
- [ ] Every table in the in-scope list is covered in Section 1.
- [ ] Every divergence in Section 1 has a severity label.
- [ ] Section 3 produces a complete inventory of inbound/outbound symbol code paths with file paths and line numbers.
- [ ] Section 4 lists every `insights` write call site.
- [ ] Section 5 reports SUCCESS or FAILURE for each of the three smoke-test queries.
- [ ] Section 7 recommends a sub-phase split with LOC and file-touch estimates.
- [ ] No code changes were committed. No edits to any tracked file other than the new report.
- [ ] Chat summary posted with totals + smoke-test outcomes + recommended split.

## Out of scope

- Any code change. That is Phase 3b.
- Phase 4 contract operations (`schwab_tokens`, `user_watchlist`, `options_chain_snapshots` plural drops — tracked in OTA-523).
- Strategy taxonomy redesign (OTA-436).
- Varbinary token migration (§10.4) — separate effort.
- Views from §8 — separate effort.
- Tightening `insights.user_id` or `insights.source_position_id` to `NOT NULL` — that is a future tightening after backfill.
- Fixing the async credential findings from Section 6 — Section 6 inventories only.

## Verification steps

1. Open `phase3a-orm-audit-report.md` and confirm all seven sections exist.
2. Spot-check three random tables from Section 1 — the ORM column list matches what `sys.columns` returns for that table.
3. Spot-check one Section 2 finding — the cited file/line actually contains the pattern flagged.
4. Confirm Section 5 ran the three smoke-test queries and reported row counts.
5. Confirm no files under `app/` or `web/` were modified (`git status` is clean except for the new report).

**QA Level: Level 1** (read-only audit, no code changes, no regression risk).

## Commit instruction

I have been instructed **NOT to commit anything for this phase**. This is a read-only audit. `git status` must show only the new report file as untracked at the end of the run.

## Coordination footer

Independent. Phase 3b prompt comes from Claude.ai after Don approves the report and the recommended sub-phase split.
