# OTA-667 — Phase 3b.1: ORM Model Alignment

## Terminal context

- This terminal: Terminal A (single-terminal session)
- Concurrent terminals: none
- Cross-terminal dependencies: none — Phase 3a (OTA-665) must be at Code & Test Complete or beyond. Phase 3b.1 ships independently of 3b.2 / 3b.3 / 3b.4.

## Required reading

Before any code changes:

```powershell
cat claude_context\CLAUDE.md
cat claude_context\architecture-plan.md
cat database-normalization-proposal.md
cat phase3a-orm-audit-report.md
cat phase2-migration-log.md
```

Read **Section 1 of the audit report in full** plus **§7's 3b.1 entry**. Section 1 enumerates the 33 individual findings (4 BREAKING + 8 STALE + 21 MISSING-RELATIONSHIP); §7's 3b.1 entry collapses them into the seven action lines that scope this sub-phase. Both views must agree before any change is applied.

## Relevant Context — Do Not Deviate Without Escalation

### Source: phase3a-orm-audit-report.md (authoritative for *what* to change)

The audit report's §7.3b.1 lists the seven actions for this sub-phase. Section 1 of the same report lists every per-table finding the actions resolve. **This prompt does not enumerate findings** — it defines the workflow. The audit report enumerates the work.

If §7.3b.1's actions conflict with anything else read during this session, the audit report wins for matters of *what to change*. The proposal wins for matters of *what the new schema means*.

**Exception — ORM-DB rename catch-up is in scope.** The general Phase 3b guardrail is "no column renames; renames are Phase 4 contract." That guardrail applies to DB renames. Where the audit identifies a column that has *already been renamed in the DB by an earlier phase* but the ORM still uses the old name, updating the ORM to match the DB is an **ORM correction**, not a DB rename. The `validation_assessments.ticker → symbol` finding (Section 1.22) is the known case. The ORM field name, the index name, and any in-code references all move; no Alembic migration is authored.

### Source: phase2-migration-log.md (canonical column names)

The actual schema uses `agent_run_log.otel_trace_id` (not `trace_id`) and `insights.created_at` (not `surfaced_at`). The ORM must reference the actual names. The proposal §7 still contains the stale names in some readers — treat the migration log as canonical.

### Source: database-normalization-proposal.md (relationship cascade behavior)

For every new `ForeignKey()` declaration this sub-phase adds, the cascade behavior in the ORM must match the cascade behavior the DB already has. The audit report's Section 1 tables list the per-FK cascade for each missing relationship — `CASCADE`, `NO_ACTION`, or `SET NULL`. Read those columns before authoring any `ForeignKey()` line.

### Source: CLAUDE.md (commit discipline, two-Claude workflow)

- Exactly one commit for this sub-phase, with `OTA-667` prefix and the sub-phase identifier in the message.
- Do not advance Jira state. Do not push. Don holds those gates personally.
- Azure SDK calls in async FastAPI handlers must use `.aio` variants. (No async Azure work is in 3b.1 scope, but the rule still governs any incidental edit that touches credentials.)

### 3b.1-specific guardrails

- **Explicit `back_populates` on every new `relationship()`.** SQLAlchemy will issue mapper-config warnings (or in some cases ambiguity errors) if a bidirectional `relationship()` is declared without `back_populates` matching on both sides. When in doubt, declare the relationship as one-directional from the child side only (the side that owns the FK) — that is sufficient for query needs and avoids the ambiguity. If a bidirectional `relationship()` is genuinely needed, both sides must name each other via `back_populates`.
- **Do not copy-paste cascade settings between sibling models.** Two FK declarations that look syntactically identical can have different cascade behaviors at the DB level. Always cross-check the cascade column for the specific FK in audit Section 1 before authoring the line. A stray `ondelete='CASCADE'` introduced by copy-paste from a sibling model is a data-loss bug, not a code-style nit.
- **No Alembic migration is authored in this sub-phase.** The DB is already at the Phase 2 head (`ade9a09d8001`). 3b.1 catches the ORM up to that head. If at any point a finding seems to require a DB schema change, halt and report — that's a contract issue, not an ORM alignment.
- **Search for `ValidationAssessment.ticker` usages before renaming.** The rename itself is one line in the model file, but every reference in the codebase must move with it. The audit's 3b.4 covers the call-site sweep, but if any in-file reference (e.g., a `__table_args__` index, a query inside `database.py` itself) lives in `database.py`, it ships with the 3b.1 rename. References *outside* `database.py` are 3b.4's job, not 3b.1's.

### Out-of-scope guardrails

- No changes outside `app/models/database.py` except the dedicated log file at project root.
- No tightening of any column to NOT NULL. `insights.user_id` and `insights.source_position_id` are declared as nullable (matching the DB).
- No Alembic migration or DB schema change.
- No varbinary token migration (§10.4 of the proposal) — separate effort.
- No view creation (§8 of the proposal) — separate effort.
- No async credential cleanup (audit Section 6) — separate Story (OTA-671).
- No call-site changes for the `ticker → symbol` rename outside `database.py` itself — that's 3b.4 (OTA-670).

## Scope

### Phase 1 — Read the audit report's 3b.1 entry

Open `phase3a-orm-audit-report.md` and locate §7.3b.1. Confirm the seven actions match what's described above. Open Section 1 and skim §§1.1, 1.20, 1.22 (the three BREAKING entries) plus every section listed in the audit's STALE / MISSING-RELATIONSHIP summary table.

If anything in §7.3b.1 conflicts with Section 1, halt and notify Don. Do not proceed on a mismatch.

### Phase 2 — Apply the changes to `app/models/database.py`

Apply the seven §7.3b.1 actions in this order. Each action is bounded to the file; no other files are touched in this sub-phase.

1. **Add `SymbolReference` model.** Eight columns: `symbol` (PK, `String(20)`), `name`, `exchange`, `sector`, `sub_industry`, `asset_type`, `last_updated`, `api_symbol`. Mirror the DB column types and nullability from Section 1.1 of the audit. No `relationship()` declarations from this side — children declare their own FK back-reference, one-directional.

2. **Add the two missing columns to the `Insight` model.** `user_id: Mapped[str | None]` with `ForeignKey('users.id')` matching the `NO_ACTION` cascade per Section 1.20. `source_position_id: Mapped[str | None]` with `ForeignKey('positions.position_id', ondelete='SET NULL')` per Section 1.20. Both nullable.

3. **Rename `ValidationAssessment.ticker` → `symbol`.** Update the column declaration, the `__table_args__` index name (`ix_validation_assessments_ticker` → `ix_validation_assessments_symbol`), and any reference *inside `database.py` itself*. References elsewhere in the codebase belong to 3b.4 and are out of scope here.

4. **Widen six `symbol` columns from `String(10)` to `String(20)`.** The six tables are listed in Section 1's STALE rows: `symbol_quotes`, `option_chain_snapshots`, `trade_log`, `analysis_runs`, `analyzed_trades`, `user_favorites`. (Verify against the audit before changing — Section 1's per-table tables are the source.)

5. **Narrow two `user_id` columns from `String(255)` to `String(36)`.** `watchlists.user_id` (Section 1.10) and `user_sessions.user_id` (Section 1.3). Both should match `varchar(36)` at the DB level.

6. **Add the 21 missing `ForeignKey()` declarations.** For each missing-relationship row in Section 1, add the `ForeignKey()` with the cascade behavior listed in the audit's cascade column. The full list spans `user_sessions`, `dashboard_layouts`, `symbol_quotes`, `symbol_context`, `option_chain_snapshots`, `watchlists`, `watchlist_symbols`, `positions` (×2), `trade_candidates` (×2), `trade_recommendations`, `trade_log`, `analysis_runs`, `analyzed_trades`, `agent_run_log`, `insights` (×2, see action 2), `user_favorites` (×2), `validation_assessments`. Add `relationship()` declarations only where useful for upcoming sub-phases — minimally, declare from the child side (the side with the FK). Bidirectional relationships require explicit `back_populates` on both sides.

7. **Remove stale "WHY no FK" / "SKIP_AUTH compat" comments** on `Position`, `NamedWatchlist`, `UserFavorite`. The comments are now contradicted by the FK declarations being added in action 6.

If applying any action surfaces a finding the audit didn't capture, stop and report rather than fixing on the fly. The audit is the bounded scope.

### Phase 3 — Verify

1. **Syntax / import check.**
   ```powershell
   cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
   .\venv\Scripts\Activate.ps1
   python -c "from app.models import database; print('imports OK')"
   ```
   Imports must succeed with no SQLAlchemy mapper-config warnings.

2. **Test suite.**
   ```powershell
   pytest
   ```
   All tests must pass. If any test depended on the old `ValidationAssessment.ticker` attribute, that's a 3b.4 finding to log in the cutover log — do not patch the test in this sub-phase unless the test lives in a file that *only* tests ORM model shape.

3. **Smoke test the three audit Section 5 queries.** Repeat the same three queries the audit ran against the same user (`6232a881-23e9-4954-8ed0-6303ea7fd188`). Each must still succeed with the same row counts (39 / 6 / 10). After 3b.1, Test 1's ORM query can additionally `.join(SymbolReference)` — but this prompt does not require demonstrating that; only confirm the original three pass.

4. **No frontend touched.** `npm run build` is not required for 3b.1.

If any verification step fails, do **not** commit. Stop and report.

### Phase 4 — Commit

One commit for this sub-phase with this message format:

```
OTA-667 feat: phase 3b.1 - orm model alignment per phase 2 schema
```

After commit, **stop**. Write a brief log file `phase3b-1-cutover-log.md` at project root summarizing:

- The seven actions applied (one bullet per action, with line-count and any per-action notes)
- Test results (`pytest` summary)
- Smoke-test outcomes (3 queries, pass/fail, row counts)
- Any deviations from the audit-report-recommended fix (with reason)
- Any findings surfaced during application that the audit didn't capture (escalation list for Don)
- Banner: SUCCESS / FAIL

Do not proceed to 3b.2. Don opens a fresh Claude Code session with `phase3b-2-api-symbol-normalization-PROMPT.md` after confirming 3b.1 is committed and validated.

## Acceptance criteria

- [ ] Audit report §7.3b.1 and Section 1 were read in full before any code change.
- [ ] `SymbolReference` model exists with all 8 columns matching DB schema.
- [ ] `Insight` model has `user_id` and `source_position_id` columns, both nullable, with correct cascade FKs.
- [ ] `ValidationAssessment.ticker` is renamed to `symbol`; index name updated to match.
- [ ] Six `symbol` columns widened from `String(10)` to `String(20)`.
- [ ] Two `user_id` columns narrowed from `String(255)` to `String(36)`.
- [ ] 21 missing `ForeignKey()` declarations added, each with cascade behavior matching the audit's cascade column for that FK.
- [ ] Every new `relationship()` either is one-directional (from the FK-owning side) or has explicit matching `back_populates` on both sides.
- [ ] Stale "WHY no FK" / "SKIP_AUTH compat" comments on `Position`, `NamedWatchlist`, `UserFavorite` are removed.
- [ ] No file other than `app/models/database.py` is modified (plus the new log file at project root).
- [ ] `python -c "from app.models import database"` succeeds with no SQLAlchemy mapper warnings.
- [ ] Full `pytest` run passes.
- [ ] Three audit-Section-5 smoke-test queries pass with original row counts.
- [ ] Exactly one commit with message `OTA-667 feat: phase 3b.1 - orm model alignment per phase 2 schema`.
- [ ] `phase3b-1-cutover-log.md` exists at project root with SUCCESS banner and the audit's seven actions enumerated.
- [ ] Don has been notified in chat that 3b.1 is complete.
- [ ] **No** Jira state advance (Don's gate).
- [ ] **No** push (Don's gate).

## Out of scope

- Any file other than `app/models/database.py` (and the cutover log).
- Any work in §7.3b.2, §7.3b.3, or §7.3b.4 of the audit report.
- Call-site fixes for the `ValidationAssessment.ticker → symbol` rename outside `database.py` (that's 3b.4 / OTA-670).
- `api_symbol` normalization helpers (3b.2 / OTA-668).
- Insights write wiring (3b.3 / OTA-669).
- Async credential cleanup (Section 6 of the audit / OTA-671).
- Tightening any column to NOT NULL.
- New Alembic migrations or any DB schema change.
- Varbinary token migration, view creation, strategy taxonomy redesign, table drops.

## Verification

1. `git status` shows only `app/models/database.py` modified plus the new log file at project root.
2. `git log --oneline -1` shows the standardized commit message.
3. `phase3b-1-cutover-log.md` matches the format used by `phase1a-cleanup-log.md` and `phase2-migration-log.md`.
4. No file outside `app/models/database.py` was touched.

**QA Level:** Level 2 — mechanical model changes with regression coverage from the existing test suite. The 21 FK additions are the medium-risk surface and are mitigated by the cascade-cross-check rule (Phase 2, action 6).

## Commit instruction

I have been instructed to commit exactly **one commit** for this sub-phase. After the commit, **stop** and notify Don. Do not advance Jira state. Do not push. Don holds those gates.

"I have been instructed to commit. Do you approve? (yes / no)"

## Coordination footer

- Previous: OTA-665 (Phase 3a audit) at Code & Test Complete or beyond.
- Next: a fresh Claude Code session with `phase3b-2-api-symbol-normalization-PROMPT.md` (OTA-668). Don opens that session after confirming 3b.1 is committed and validated. 3b.2 depends on `SymbolReference` existing in the ORM — do not start 3b.2 until 3b.1 is on disk.
