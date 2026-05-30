# OTA-669 — Phase 3b.3: Insights Write Wiring

## Terminal context

- This terminal: Terminal A (single-terminal session)
- Concurrent terminals: none
- Cross-terminal dependencies: Phase 3b.1 (OTA-667) must be committed and validated. The `Insight` ORM model must have the `user_id` and `source_position_id` columns added in 3b.1 before this sub-phase starts. 3b.2 (OTA-668) is recommended to ship first per the audit's sequential order, but 3b.3 does not depend on 3b.2's helpers.

## Required reading

Before any code changes:

```powershell
cat claude_context\CLAUDE.md
cat claude_context\architecture-plan.md
cat database-normalization-proposal.md
cat phase3a-orm-audit-report.md
cat phase2-migration-log.md
cat phase3b-1-cutover-log.md
```

If `phase3b-2-cutover-log.md` exists at project root, read it as well. 3b.3 doesn't depend on 3b.2, but if both are in the history, the SUCCESS banners should be confirmed.

Read **Sections 2.6 and 4 of the audit report in full** plus **§7.3b.3**. Section 4 enumerates the two BREAKING call sites in `insight_engine.py` plus the caller context in `position_monitor.py`. Section 2.6 captures the related STALE finding (`AgentRunLog` write missing `user_id` at `insight_engine.py:192`). §7.3b.3 collapses them into three action lines.

## Relevant Context — Do Not Deviate Without Escalation

### Source: phase3a-orm-audit-report.md (authoritative for *what* to change)

The audit report's §7.3b.3 lists the three actions for this sub-phase. Sections 2.6 and 4 list every per-call-site finding. **This prompt does not enumerate findings** — it defines the workflow. The audit report enumerates the work.

If §7.3b.3's actions conflict with anything else read during this session, the audit report wins for matters of *what to change*.

### Source: phase3a-orm-audit-report.md §4 (call site detail)

The sole caller of `InsightEngine.generate()` today is `PositionMonitorAgent._trigger_insights()` at `app/agents/position_monitor.py:372–380`. At that call site, both `pos.user_id` and `pos.position_id` are available — they just aren't forwarded to `InsightEngine.generate()` because the method signature doesn't accept them. Section 4.3 is explicit: this is a wiring gap, not a resolution problem. The fix is to add the parameters to `generate()` and forward the values from the caller.

`entity_id` is a separate, domain-specific identifier that already exists in `InsightEngine.generate()` (passed as `pos.position_id` from PositionMonitorAgent today). It stays. The new `source_position_id` is the typed FK column for the `positions` join. They happen to hold the same value when domain='options', but they're semantically different — `entity_id` is the domain identifier, `source_position_id` is the FK.

### Source: architecture-plan.md (Data Isolation Invariant)

The Data Isolation Invariant says every CRUD endpoint that takes a resource ID must filter by `user_id`. The `GET /api/v1/insights` endpoint cannot filter by user today because no insight row has `user_id` populated. 3b.3 is the wiring side of that fix — it ensures new insight rows written from this point forward have `user_id` populated. Existing insight rows are not backfilled in this sub-phase; backfill is a separate concern, and the column remains nullable to accommodate legacy rows.

### Source: CLAUDE.md (commit discipline, two-Claude workflow)

- Exactly one commit for this sub-phase, with `OTA-669` prefix.
- Do not advance Jira state. Do not push. Don holds those gates personally.

### 3b.3-specific guardrails

- **NULL + log warning on resolution failure; never raise.** Today's caller (PositionMonitorAgent) always has `pos.user_id` and `pos.position_id` available. If for any reason a future caller can't supply either value (e.g., a position is malformed, the call is from a non-options domain), the contract is: pass `None` for `source_position_id`, log a warning at WARNING level, and let the write proceed. Never raise an exception from `InsightEngine.generate()` for missing FK values — the column is nullable by design. This is forward-design guidance; the only path 3b.3 actually wires (PositionMonitorAgent → InsightEngine) never hits this case, but the function body should be written to accept `source_position_id=None` cleanly.

- **`user_id` is required, not optional, on `InsightEngine.generate()`.** Unlike `source_position_id`, `user_id` should be a required positional or keyword parameter. The Data Isolation Invariant requires it. If a caller can't supply `user_id`, the right behavior is to fail loudly at the caller — not write a NULL-user_id insight. The `Insight.user_id` DB column is nullable only for backwards compatibility with pre-existing rows; new writes from 3b.3 onward should always populate it.

- **`entity_id` is unchanged.** Do not remove, rename, or repurpose the existing `entity_id` parameter on `InsightEngine.generate()`. It serves a different purpose than `source_position_id`. The audit Section 4.3 is explicit on this distinction.

- **`AgentRunLog` user_id wiring is Action 3, separate from the insight write.** Audit §2.6 identified that `insight_engine.py:192` writes `AgentRunLog` with `user_id=None` even though `pos.user_id` is available indirectly. The fix is mechanical: pass `user_id` to `AgentRunLog()` as part of Action 3. This is the same `user_id` value that's already being threaded through for the `Insight` write.

### Out-of-scope guardrails

- No changes to `app/models/database.py` — 3b.1's territory.
- No changes to `app/services/symbol_normalization.py` or any inbound/outbound symbol wiring — 3b.2's territory.
- No changes to `app/api/` route files — that's where 3b.4's query fixes live.
- **No backfill of existing insight rows with `user_id` or `source_position_id`.** Existing rows stay as-is. Only new writes get the fields populated. Backfill is a separate effort tied to eventual tightening of nullability (future phase).
- No tightening of `insights.user_id` or `insights.source_position_id` to NOT NULL.
- No new Alembic migrations or DB schema changes.
- No new test infrastructure. Existing tests should cover the regression; if a test needs updating because it called `InsightEngine.generate()` with a signature that no longer matches, the test update is in scope, but new functional tests are not required.

## Scope

### Phase 1 — Read the audit report's 3b.3 entry and confirm 3b.1 preconditions

1. Open `phase3a-orm-audit-report.md` and locate §7.3b.3. Confirm the three actions match what's described above.
2. Open Sections 2.6 and 4 and read them in full.
3. Open `app/models/database.py` and confirm the `Insight` model has the `user_id` and `source_position_id` columns added by 3b.1. If they're missing, halt — 3b.1 didn't ship cleanly and 3b.3 cannot proceed.
4. Open `app/agents/insight_engine.py` and `app/agents/position_monitor.py` and locate the exact line ranges cited in audit Section 4.2 / 4.3. Confirm the current code shape matches what the audit described.

### Phase 2 — Update `InsightEngine.generate()` (Actions 1 + 3)

In `app/agents/insight_engine.py`:

- **Action 1: Add `user_id` and `source_position_id` parameters to `generate()`.** Add `user_id: str` as a required parameter (positional or keyword — match the existing signature style). Add `source_position_id: str | None = None` as an optional parameter, defaulting to `None`. Pass both through to the `Insight()` constructor at both call sites identified in audit Section 4.2 (the create path at lines 162–180 and the update path at lines 144–159).

- **Action 3: Pass `user_id` to the `AgentRunLog()` write at line 192.** The same `user_id` value received by `generate()` is forwarded to the `AgentRunLog` row. This fixes the STALE finding from audit §2.6.

Both actions live in the same file and ship in the same commit. They're listed as separate audit actions because they target different write paths.

If the update path at lines 144–159 doesn't currently take a position-context parameter (the audit suggests it's reading an existing row), make sure both `user_id` and `source_position_id` are preserved or overwritten correctly per the audit's wording — preserving an existing non-null FK is the safer default; overwriting is only correct if the audit explicitly says so.

### Phase 3 — Update `PositionMonitorAgent._trigger_insights()` (Action 2)

In `app/agents/position_monitor.py`:

- **Action 2: Forward `pos.user_id` and `pos.position_id` to `InsightEngine.generate()`.** The call at lines 372–380 currently passes `entity_id=pos.position_id` (among other args). Add two new keyword arguments: `user_id=pos.user_id` and `source_position_id=pos.position_id`. `entity_id` stays as it is.

If `pos.user_id` or `pos.position_id` is ever None at this call site, the contract from the 3b.3 guardrails applies: log at WARNING and pass `None`. Today this case should never fire — `pos` is always a fully-hydrated `Position` row coming from the monitor's main query — but the guardrail makes the wiring robust.

### Phase 4 — Verify

1. **Syntax / import check.**
   ```powershell
   cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
   .\venv\Scripts\Activate.ps1
   python -c "from app.agents import insight_engine, position_monitor; print('imports OK')"
   ```

2. **Test suite.**
   ```powershell
   pytest --ignore=scratch --ignore=dev-agents
   ```
   Matches the pytest scope from `phase3b-1-cutover-log.md`. If 3b.2's cutover log used a different scope, reconcile. All tests must pass. If any test fails because it called `InsightEngine.generate()` with the old signature, update the test's call to pass `user_id` (and `source_position_id` where the test is exercising an options-domain path) — that's part of 3b.3's scope.

3. **Three audit Section 5 smoke-test queries.** Same three queries from prior sub-phases. Row counts will continue to drift; the structural pass is what matters.

4. **Diff-level verification.** Confirm by reading the final diff:
   - `InsightEngine.generate()` signature now declares `user_id` and `source_position_id`.
   - Both `Insight()` constructor calls in `insight_engine.py` pass `user_id` and `source_position_id`.
   - The `AgentRunLog()` write in `insight_engine.py` passes `user_id`.
   - The call to `InsightEngine.generate()` in `position_monitor.py` passes `user_id=pos.user_id` and `source_position_id=pos.position_id`.
   - `entity_id` is unchanged at the call site.

5. **No frontend touched.** `npm run build` is not required for 3b.3.

If any verification step fails, do **not** commit. Stop and report.

### Phase 5 — Commit

One commit for this sub-phase with this message format:

```
OTA-669 feat: phase 3b.3 - insights write wiring
```

After commit, **stop**. Write a brief log file `phase3b-3-cutover-log.md` at project root summarizing:

- The three actions applied (with file paths and line ranges)
- Test results (`pytest` summary, scope of `--ignore` flags used)
- Smoke-test outcomes (3 queries, pass/fail, row counts)
- Any deviations from the audit-report-recommended fix (with reason)
- Any findings surfaced during application that the audit didn't capture
- Banner: SUCCESS / FAIL

Do not proceed to 3b.4. Don opens a fresh Claude Code session with `phase3b-4-query-fixes-PROMPT.md` after confirming 3b.3 is committed and validated.

## Acceptance criteria

- [ ] Audit report §7.3b.3 and Sections 2.6 and 4 were read in full before any code change.
- [ ] `phase3b-1-cutover-log.md` was read and shows SUCCESS; `Insight` model has `user_id` and `source_position_id` columns.
- [ ] `InsightEngine.generate()` signature accepts `user_id: str` (required) and `source_position_id: str | None = None` (optional).
- [ ] Both `Insight()` constructor calls in `insight_engine.py` (create at 162–180; update at 144–159) pass `user_id` and `source_position_id`.
- [ ] The `AgentRunLog()` write at `insight_engine.py:192` passes `user_id` (fixes audit §2.6).
- [ ] `PositionMonitorAgent._trigger_insights()` passes `user_id=pos.user_id` and `source_position_id=pos.position_id` to `InsightEngine.generate()`. `entity_id` is unchanged.
- [ ] No file other than `app/agents/insight_engine.py` and `app/agents/position_monitor.py` is modified (plus the cutover log at project root, and any test files whose call sites needed updating).
- [ ] `python -c "from app.agents import insight_engine, position_monitor"` succeeds with no warnings.
- [ ] `pytest --ignore=scratch --ignore=dev-agents` passes (or the same scope used by 3b.1's log).
- [ ] Three audit-Section-5 smoke-test queries pass structurally.
- [ ] Diff-level verification confirms the four points listed in Phase 4 step 4.
- [ ] Exactly one commit with message `OTA-669 feat: phase 3b.3 - insights write wiring`.
- [ ] `phase3b-3-cutover-log.md` exists at project root with SUCCESS banner.
- [ ] Don has been notified in chat that 3b.3 is complete.
- [ ] **No** Jira state advance (Don's gate).
- [ ] **No** push (Don's gate).

## Out of scope

- Any file in `app/models/` (3b.1's territory; closed).
- Any file in `app/services/symbol_normalization.py` or the inbound/outbound symbol wiring (3b.2's territory).
- Any file in `app/api/` (3b.4 / OTA-670).
- Any file in `web/src/` (3b.4 / OTA-670).
- Backfill of existing insight rows with `user_id` or `source_position_id`.
- Tightening any column to NOT NULL.
- New Alembic migrations or DB schema change.
- New functional or integration test infrastructure (existing tests cover regression).
- Async credential cleanup (OTA-671).

## Verification

1. `git status` shows only `app/agents/insight_engine.py`, `app/agents/position_monitor.py`, the cutover log at project root, and any test files whose signatures needed updating.
2. `git log --oneline -1` shows the standardized commit message.
3. `phase3b-3-cutover-log.md` matches the format of `phase3b-1-cutover-log.md` and `phase3b-2-cutover-log.md`.
4. No file outside the §4 / §2.6 scope was touched.

**QA Level:** Level 2 — mechanical, low-risk wiring within two well-bounded files. Existing test suite is the primary regression check. The function-signature contract change is the only surface where a regression could surface, and it's caught by `pytest` failures on any call site that wasn't updated.

## Commit instruction

I have been instructed to commit exactly **one commit** for this sub-phase. After the commit, **stop** and notify Don. Do not advance Jira state. Do not push. Don holds those gates.

"I have been instructed to commit. Do you approve? (yes / no)"

## Coordination footer

- Previous: OTA-667 (Phase 3b.1) at Code & Test Complete or beyond. `Insight` model must have `user_id` and `source_position_id` columns — verified in Phase 1 of this prompt. 3b.2 (OTA-668) recommended to ship first per the audit's sequential order, but not a hard dependency.
- Next: a fresh Claude Code session with `phase3b-4-query-fixes-PROMPT.md` (OTA-670). Don opens that session after confirming 3b.3 is committed and validated. 3b.4 depends on 3b.1's `ValidationAssessment.ticker → symbol` rename for the call-site sweep.
