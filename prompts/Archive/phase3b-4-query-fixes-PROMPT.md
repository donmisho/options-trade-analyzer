# OTA-670 — Phase 3b.4: Query Fixes

## Terminal context

- This terminal: Terminal A (single-terminal session)
- Concurrent terminals: none
- Cross-terminal dependencies: Phase 3b.1 (OTA-667) must be committed and validated — `ValidationAssessment.symbol` must exist in the ORM for the call-site sweep. Phase 3b.2 (OTA-668) must be committed and validated — `canonicalize()` is the normalization primitive this sub-phase uses for write-path fixes (see the deviation note below).

## Required reading

Before any code changes:

```powershell
cat claude_context\CLAUDE.md
cat claude_context\architecture-plan.md
cat database-normalization-proposal.md
cat phase3a-orm-audit-report.md
cat phase2-migration-log.md
cat phase3b-1-cutover-log.md
cat phase3b-2-cutover-log.md
cat phase3b-3-cutover-log.md
```

Read **Section 2.2 and Section 1.22 of the audit report in full** plus **§7.3b.4**. Section 2.2 lists the four symbol-write call sites that 3b.2 didn't cover (two in `trade_evaluation_routes.py`, two in `evaluation_routes.py`) plus the lone frontend site. Section 1.22 captures the `ValidationAssessment` rename context that drives the call-site sweep. §7.3b.4 collapses them into four action lines.

Also confirm all three prior sub-phases shipped cleanly by reading their cutover logs — the SUCCESS banners are preconditions for 3b.4.

## Relevant Context — Do Not Deviate Without Escalation

### Source: phase3a-orm-audit-report.md (authoritative for *what* to change)

The audit report's §7.3b.4 lists the four actions for this sub-phase. Sections 1.22 and 2.2 list every per-call-site finding. **This prompt does not enumerate findings** — it defines the workflow. The audit report enumerates the work.

If §7.3b.4's actions conflict with anything else read during this session, the audit report wins for matters of *what to change*.

### Deviation from §7's literal wording: `canonicalize()`, not `.upper()`

§7.3b.4 actions 1 and 2 say "Add `.upper()` normalization." That wording is a holdover from before 3b.2 created the `canonicalize()` helper in `app/services/symbol_normalization.py`. The audit was drafted with `.upper()` because the helper didn't exist yet.

**Use `canonicalize()` for both actions 1 and 2.** Reasoning:
- The call sites in question (per audit §2.2) write to `agent_run_log.symbol` and `trade_recommendations.symbol`, both of which have FK constraints to `symbol_reference.symbol` (added in 3b.1). The canonical form (no `$`, uppercased) is the only safe form for these columns.
- 3b.2's pattern threads `canonicalize()` through every other inbound write path in the same two files. Mixing `.upper()` for some lines and `canonicalize()` for others in the same file produces confusing inconsistency.
- `canonicalize()` is idempotent — applying it to an already-canonical symbol is a no-op. There's no risk of double-normalization.

This deviation must be noted in the cutover log.

Action 4 (frontend) uses `.toUpperCase()` as the audit specifies — no JS-side helper exists, and the frontend's job is just to send a clean canonical string to the API; the backend will run `canonicalize()` on it again before any DB write.

### Source: phase3a-orm-audit-report.md §2.2 (the four backend sites 3b.4 covers)

The audit's §2.2 lists 8 backend sites; 3b.2 covered 4 of them (the ones also listed in §3.2 as inbound DB-write paths). The remaining 4 sites are 3b.4's scope:

- `app/api/trade_evaluation_routes.py` lines **516** and **616** — `symbol=request.symbol` written without normalization (BREAKING per §2.2; not covered by 3b.2)
- `app/api/evaluation_routes.py` lines **566** and **750** — `request.symbol` used in prompts and `AgentRunLog` writes without normalization (STALE per §2.2; not covered by 3b.2)

If 3b.2's commit already touched any of these lines (e.g., line numbers drifted), reconcile against the actual current state of the files. The audit's line numbers are a starting point; the canonical reference is the actual symbol-write or symbol-reference at each site.

### Source: phase3a-orm-audit-report.md §1.22 (the rename context)

3b.1 renamed `ValidationAssessment.ticker → symbol` inside `app/models/database.py` only. Action 3 of this sub-phase is the call-site sweep — every reference to `ValidationAssessment.ticker` (or `validation_assessment.ticker` instance access, or filter expressions like `ValidationAssessment.ticker == X`, or constructor calls passing `ticker=...`) anywhere else in the codebase must move to `.symbol`.

### Source: CLAUDE.md (commit discipline, two-Claude workflow)

- Exactly one commit for this sub-phase, with `OTA-670` prefix.
- Do not advance Jira state. Do not push. Don holds those gates personally.

### 3b.4-specific guardrails

- **Search broadly for `ValidationAssessment.*ticker` references, but filter by model context.** Not every `.ticker` reference in the codebase is to `ValidationAssessment`. PowerShell grep gives candidates; verifying each candidate is *actually* a `ValidationAssessment` reference (vs. a different model with a `ticker` field, or a dict key named `ticker`, or a variable named `ticker`) is mandatory before rewriting it. False positives that aren't `ValidationAssessment` references are left alone.

- **Scope discipline on the frontend.** Audit §2.2 row 3 names exactly ONE frontend site: `web/src/components/TradeEvaluationView.jsx` line 186. If Claude Code encounters other frontend sites that look like they should also normalize, halt and report — do not expand scope. Frontend normalization beyond the named line is a future ticket.

- **`trade_key` namespace guard is explicitly out of scope.** Proposal §10.2 calls out a heterogeneous `trade_key` namespace between `trade_recommendations.trade_key` and `agent_run_log.trade_key` and suggests an application-layer guard. §7.3b.4 does **not** call for that guard. It stays out of scope for 3b.4. Don decides if/when it becomes its own ticket.

- **No new helpers, no new modules.** 3b.4 is purely call-site fixes. `app/services/symbol_normalization.py` was created in 3b.2; 3b.4 only consumes it.

### Out-of-scope guardrails

- No changes to `app/models/database.py` — 3b.1's territory.
- No changes to `app/services/symbol_normalization.py` — 3b.2's territory.
- No changes to `app/agents/insight_engine.py` or `app/agents/position_monitor.py` — 3b.3's territory.
- No additional frontend changes beyond `TradeEvaluationView.jsx` line 186.
- No `trade_key` namespace guard.
- No backfill of existing rows with normalized values.
- No tightening of any column to NOT NULL.
- No new Alembic migrations or DB schema changes.
- No async credential cleanup (OTA-671).
- No varbinary token migration, view creation, strategy taxonomy redesign, table drops.

## Scope

### Phase 1 — Read the audit and confirm all prior sub-phase preconditions

1. Open `phase3a-orm-audit-report.md` and locate §7.3b.4. Confirm the four actions match what's described above.
2. Open Sections 2.2 and 1.22 and read them in full.
3. Confirm prior sub-phases shipped:
   - `phase3b-1-cutover-log.md` shows SUCCESS; `ValidationAssessment.symbol` exists in `app/models/database.py`.
   - `phase3b-2-cutover-log.md` shows SUCCESS; `app/services/symbol_normalization.py` exists with `canonicalize`.
   - `phase3b-3-cutover-log.md` shows SUCCESS.
4. Open `app/api/trade_evaluation_routes.py` and `app/api/evaluation_routes.py` and locate the actual current positions of the symbol-write sites near the audit's cited line numbers (lines 516, 616 in the first; 566, 750 in the second). The audit's line numbers may have drifted by a few lines due to 3b.2's edits. The audit-cited *patterns* are the canonical reference, not the line numbers themselves.

### Phase 2 — Apply `canonicalize()` to the four remaining backend sites (Actions 1 + 2)

For each of the four sites identified in Phase 1 step 4:

1. Import `canonicalize` from `app.services.symbol_normalization` at the top of each file (if not already imported by 3b.2's commit).
2. Replace `request.symbol` (or `request.symbol.upper()`, or any other bare/half-normalized reference) with `canonicalize(request.symbol)` at the write or use site.
3. If the site is using the symbol in a prompt or log message rather than a DB write column, still apply `canonicalize()` — the goal is consistent canonical form across all symbol handling in these files, not just DB writes.

These are the four sites:

- `app/api/trade_evaluation_routes.py` near audit line 516 (BREAKING per §2.2)
- `app/api/trade_evaluation_routes.py` near audit line 616 (BREAKING per §2.2)
- `app/api/evaluation_routes.py` near audit line 566 (STALE per §2.2)
- `app/api/evaluation_routes.py` near audit line 750 (STALE per §2.2)

### Phase 3 — `ValidationAssessment.ticker → .symbol` call-site sweep (Action 3)

1. Run a PowerShell search to identify candidate references:
   ```powershell
   Get-ChildItem -Path .\app, .\tests -Recurse -Include *.py | Select-String -Pattern '\.ticker'
   ```
   (Add or omit `tests/` based on whether tests live there in this repo.)
   
2. For each match, open the file and confirm:
   - The `.ticker` reference is on a `ValidationAssessment` instance, class, or constructor call.
   - Or it's a filter expression like `select(...).where(ValidationAssessment.ticker == ...)`.
   - Or it's a kwarg like `ValidationAssessment(ticker=...)`.
   
   References that are clearly on a *different* model or are unrelated variables named `ticker` are left alone.

3. Rewrite confirmed `ValidationAssessment.ticker` references to `.symbol`. The semantics are unchanged — only the attribute name moves.

4. Build a per-file list of references rewritten, for the cutover log. If the sweep finds zero references outside `database.py`, that is a valid outcome and is noted as such in the log.

### Phase 4 — Frontend `.toUpperCase()` (Action 4)

In `web/src/components/TradeEvaluationView.jsx` near line 186:

1. Locate the call to `getProbabilityMatrix` (or wherever `spread.symbol` is sent to the API).
2. Pass `spread.symbol.toUpperCase()` instead of `spread.symbol`.
3. No other frontend file is touched.

### Phase 5 — Verify

1. **Syntax / import check (backend).**
   ```powershell
   cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
   .\venv\Scripts\Activate.ps1
   python -c "from app.api import trade_evaluation_routes, evaluation_routes; from app.services import symbol_normalization; print('imports OK')"
   ```

2. **Test suite.**
   ```powershell
   pytest --ignore=scratch --ignore=dev-agents
   ```
   Matches the pytest scope from prior cutover logs. All tests must pass.

3. **Three audit Section 5 smoke-test queries.** Same three queries from prior sub-phases. Structural pass only.

4. **Frontend build.** This sub-phase touches `web/src/`, so the frontend build is required:
   ```powershell
   cd web
   npm run build
   ```
   Must complete successfully with no new errors. Pre-existing warnings (if any from earlier work) are noted but don't fail the gate.

5. **Diff-level verification.** Confirm by reading the final diff:
   - All four §2.2 backend sites now route through `canonicalize()`.
   - The `ValidationAssessment.ticker` sweep results match the per-file list in the cutover log.
   - `TradeEvaluationView.jsx` line ~186 has `.toUpperCase()` applied to `spread.symbol`.
   - No file outside the prompt's scope is modified.

6. **Optional sanity smoke.** Hit one of the trade-evaluation API endpoints (e.g., `POST /api/v1/trade-evaluation/triage`) with a lowercase or `$`-prefixed symbol like `$spx` and confirm the response and any logged `agent_run_log` row show `SPX`. Not required if testing infrastructure makes this expensive — the unit-level tests and diff verification are sufficient.

If any verification step fails, do **not** commit. Stop and report.

### Phase 6 — Commit

One commit for this sub-phase with this message format:

```
OTA-670 feat: phase 3b.4 - query fixes
```

After commit, **stop**. Write a brief log file `phase3b-4-cutover-log.md` at project root summarizing:

- The four actions applied (with file paths and line ranges as they ended up after edits)
- Per-file list of `ValidationAssessment.ticker` references rewritten (or "zero outside database.py" if none)
- **Explicit note of the deviation from §7's literal `.upper()` wording** to `canonicalize()`, with reasoning
- Test results (`pytest` summary, scope of `--ignore` flags used)
- Smoke-test outcomes (3 queries, pass/fail, row counts)
- `npm run build` result
- Any deviations beyond the `canonicalize()` substitution (with reason)
- Any findings surfaced during application that the audit didn't capture
- Banner: SUCCESS / FAIL

After 3b.4 commits, **Phase 3b is structurally complete**. The OTA-666 umbrella Story can move to Code & Test Complete at Don's discretion once all four Subtask cutover logs show SUCCESS.

## Acceptance criteria

- [ ] Audit report §7.3b.4 and Sections 1.22 and 2.2 were read in full before any code change.
- [ ] All three prior cutover logs read; all show SUCCESS.
- [ ] All four §2.2 backend sites now route through `canonicalize()` (deviation from §7's `.upper()` wording explicitly noted in cutover log with reasoning).
- [ ] `ValidationAssessment.ticker → .symbol` call-site sweep complete; per-file results documented in the cutover log.
- [ ] `web/src/components/TradeEvaluationView.jsx` line ~186 has `.toUpperCase()` applied to `spread.symbol`.
- [ ] No file outside the prompt's scope is modified.
- [ ] `python -c "from app.api import trade_evaluation_routes, evaluation_routes"` succeeds with no warnings.
- [ ] `pytest --ignore=scratch --ignore=dev-agents` passes.
- [ ] Three audit-Section-5 smoke-test queries pass structurally.
- [ ] `npm run build` succeeds with no new errors.
- [ ] Exactly one commit with message `OTA-670 feat: phase 3b.4 - query fixes`.
- [ ] `phase3b-4-cutover-log.md` exists at project root with SUCCESS banner.
- [ ] Don has been notified in chat that 3b.4 is complete and Phase 3b is structurally done.
- [ ] **No** Jira state advance (Don's gate).
- [ ] **No** push (Don's gate).

## Out of scope

- Any file in `app/models/` (3b.1).
- Any file in `app/services/symbol_normalization.py` (3b.2).
- Any file in `app/agents/` (3b.3).
- Any inbound symbol write path that was already wired by 3b.2 (the §3.2 sites in `trade_evaluation_routes.py` and `evaluation_routes.py`).
- Any other inbound or outbound symbol path not listed in audit §2.2.
- Any frontend file beyond `TradeEvaluationView.jsx`.
- `trade_key` heterogeneous namespace guard from proposal §10.2.
- Backfill of existing rows with normalized values.
- Tightening any column to NOT NULL.
- New Alembic migrations or DB schema change.
- New helper modules, new test infrastructure, new frontend components.
- Async credential cleanup (OTA-671).

## Verification

1. `git status` shows only: `app/api/trade_evaluation_routes.py`, `app/api/evaluation_routes.py`, `web/src/components/TradeEvaluationView.jsx`, any files touched by the `ValidationAssessment` sweep, and the cutover log at project root.
2. `git log --oneline -1` shows the standardized commit message.
3. `phase3b-4-cutover-log.md` matches the format of the prior three cutover logs.
4. No file outside §2.2 / §1.22 scope was touched.

**QA Level:** Level 2 — mechanical normalization fixes plus a contained sweep. The medium-risk surface is the `ValidationAssessment.ticker` sweep (the "search all files" step has false-positive risk); the model-context filter in Phase 3 step 2 is the mitigation.

## Commit instruction

I have been instructed to commit exactly **one commit** for this sub-phase. After the commit, **stop** and notify Don. Do not advance Jira state. Do not push. Don holds those gates.

"I have been instructed to commit. Do you approve? (yes / no)"

## Coordination footer

- Previous: OTA-667 (3b.1), OTA-668 (3b.2), OTA-669 (3b.3) all at Code & Test Complete or beyond.
- Next: Phase 3b is structurally complete after this commit lands. The OTA-666 umbrella Story can be moved to Code & Test Complete once Don confirms all four sub-phase cutover logs show SUCCESS. After 3b ships, OTA-671 (async credential cleanup) is the next item in this Epic's queue but is independent — opened by Don at his discretion.
