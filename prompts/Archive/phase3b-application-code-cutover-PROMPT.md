# <OTA-TICKET> — Phase 3b: application code cutover (ONE sub-phase per session)

## Sub-phase selector

**>>> BEFORE LAUNCHING CLAUDE CODE, set this line: <<<**

```
SUB_PHASE = 3b.<N>   ## one of 3b.1, 3b.2, 3b.3, 3b.4 — or any further split recommended in phase3a-orm-audit-report.md §7
```

Each sub-phase is its own Claude Code session in a fresh context. Do not chain sub-phases in a single run. After commit, stop and wait for Don to start the next session.

The mapping of sub-phase identifiers to scope comes from **phase3a-orm-audit-report.md §7 (Recommended 3b sub-phase action list)**. That report is the source of truth for what this sub-phase does. If `SUB_PHASE` is not listed in §7, halt and ask Don to clarify.

## Terminal context

- This terminal: Terminal A (single-terminal session)
- Concurrent terminals: none
- Cross-terminal dependencies: none — all prior sub-phases of Phase 3b must be at commit-clean before starting the next one

## Required reading

```powershell
cat claude_context\CLAUDE.md
cat claude_context\architecture-plan.md
cat database-normalization-proposal.md
cat phase3a-orm-audit-report.md
cat phase2-migration-log.md
```

Read **the entirety of §7 of the audit report** plus the section(s) §7 references for this sub-phase (e.g., 3b.1 references Section 1; 3b.2 references Section 3; 3b.3 references Section 4; 3b.4 references Section 2).

## Relevant Context — Do Not Deviate Without Escalation

### Source: phase3a-orm-audit-report.md (authoritative)

The audit report's §7 lists the exact files, lines, severities, and proposed fixes for this sub-phase. **This prompt does not enumerate findings** — it defines the workflow. The audit report enumerates the work.

If §7's recommended fixes conflict with anything else read during this session, the audit report wins for matters of *what to change*. The proposal wins for matters of *what the new schema means*.

### Source: database-normalization-proposal.md §10.7 (api_symbol — relevant if SUB_PHASE = 3b.2)

> "Application code normalizes inbound `$X` API symbols to canonical `X` form before writing to any child table's `symbol` column."

Helper module location and signatures must match what the 3a audit report recommended in Section 3. If the report didn't make a specific recommendation, default to `app/services/symbol_normalization.py` with `to_canonical(api_symbol: str) -> str` and `to_api_symbol(canonical: str, provider: str | None = None) -> str`. Provider-specific overrides come from `symbol_reference.api_symbol` (filtered unique index per §10.7).

### Source: database-normalization-proposal.md §4.6 (insights — relevant if SUB_PHASE = 3b.3)

`insights.source_position_id` and `insights.user_id` are nullable per Phase 2. **Never tighten to NOT NULL in this sub-phase.** Tightening is a later phase after backfill confirms 100% population.

For domain='options' inserts where `entity_id` matches a `positions.position_id`, populate `source_position_id` with the matching value. For other domains, leave `source_position_id` NULL. Always populate `user_id`.

### Source: CLAUDE.md (async-first Azure, two-Claude workflow, commit discipline)

- Azure SDK calls in async FastAPI handlers must use `.aio` variants. Never introduce sync `azure.identity.DefaultAzureCredential()` inside `async def`.
- Each sub-phase = exactly one commit with `OTA-<TICKET>` prefix and the sub-phase identifier in the message.
- Do not advance Jira state. Do not push. Don holds those gates personally.

### Source: phase2-migration-log.md (canonical column names)

The actual schema uses `agent_run_log.otel_trace_id` (not `trace_id`) and `insights.created_at` (not `surfaced_at`). The ORM must reference the actual names. The proposal §7 still contains the stale names in some readers — treat the migration log as canonical.

### Out-of-scope guardrails (apply to every sub-phase)

- No changes to Alembic migrations or DB schema. Phase 2 is at HEAD; do not author new migrations.
- No work that should be in a different sub-phase. If 3b.1 (ORM alignment) requires changing call-site queries, the ORM change is in scope but the call-site fix is 3b.4.
- No dropping of `schwab_tokens`, `user_watchlist`, or `options_chain_snapshots` (plural) — that work is Phase 4, tracked in OTA-523.
- No tightening of any column to NOT NULL.
- No new DB FK additions — application-enforced FKs from §10.2 (`trade_recommendations.trade_key`, `agent_run_log.trade_key`) are application-only.
- No varbinary token migration (§10.4) — separate effort.

## Scope

### Phase 1 — Read the audit report's §7 entry for SUB_PHASE

Open `phase3a-orm-audit-report.md` and locate the `SUB_PHASE` section in §7. Confirm it lists:

- Files in scope
- Specific findings to apply (with severity and proposed fix)
- Estimated LOC
- Whether the sub-phase is independently shippable

If §7 indicates this sub-phase depends on another sub-phase that hasn't shipped yet, halt and notify Don. Do not proceed out of order.

### Phase 2 — Apply the changes

For each finding in §7 for this sub-phase:

1. Open the cited file.
2. Apply the proposed fix verbatim where the audit report was concrete; use your judgment only where the report explicitly says "judgment-required."
3. If applying a fix surfaces a finding the audit didn't capture, stop and report rather than fixing on the fly. The audit is the bounded scope.

For ORM model changes (3b.1):
- Update SQLAlchemy declarations: column type, nullability, FK target, `relationship()` declarations.
- Do not change column **names** of existing columns. Renames are out of scope (Phase 4 contract).
- New columns added at the DB level by Phase 2 (`insights.user_id`, `insights.source_position_id`) get declared in the ORM as nullable with the appropriate `ForeignKey()` reference.

For api_symbol wiring (3b.2):
- Create the helper module at the location specified in the audit report's Section 3 recommendation.
- Add unit tests for the helpers (round-trip identity, `$`-strip, provider lookup, missing-symbol fallback).
- Route every inbound write call site through `to_canonical()`.
- Route every outbound provider call site through `to_api_symbol()` where the audit identified a divergence.

For insights wiring (3b.3):
- For each `insights` write call site listed in audit Section 4, add `user_id` from the request context.
- For domain='options' call sites, resolve `entity_id` to a `position_id` and populate `source_position_id`. If no position can be resolved, leave NULL — log a warning, do not fail the write.

For query fixes (3b.4):
- Apply the per-line fixes from audit Section 2 verbatim.

### Phase 3 — Verify

1. **Syntax / typecheck.** Run the existing typecheck if one is configured. If `mypy` is set up, run it; otherwise skip.
2. **Test suite.** Run the full backend test suite:
   ```powershell
   cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
   .\venv\Scripts\Activate.ps1
   pytest
   ```
   All tests must pass. New tests added for this sub-phase (e.g., 3b.2 helper unit tests) must be among the passing set.
3. **Smoke test the three audit-report Section 5 queries** — repeat the same three queries the audit ran. Each must still succeed with the same or expected row counts.
4. **Frontend build sanity** (only if files under `web/src/` were touched): `npm run build` from `web/`.

If any verification step fails, do **not** commit. Stop and report.

### Phase 4 — Commit

One commit for this sub-phase with this message format:

```
<OTA-TICKET> feat: phase 3b.<N> - <sub-phase title from audit report §7>
```

Example for ORM alignment:
```
OTA-XXX feat: phase 3b.1 - orm model alignment per phase 2 schema
```

After commit, **stop**. Write a brief log file `phase3b-<N>-cutover-log.md` at project root summarizing:

- Findings applied (file path + one-line description)
- Test results
- Smoke-test outcomes
- Any deviations from the audit-report-recommended fix (with reason)
- Banner: SUCCESS / FAIL

Do not proceed to the next sub-phase. Don opens a fresh Claude Code session for that.

## Acceptance criteria

- [ ] `SUB_PHASE` field at the top of this prompt was filled in before launch.
- [ ] Audit report §7 was read in full and the entry for this sub-phase was located.
- [ ] All findings for this sub-phase from the audit report were applied (no extras, no omissions).
- [ ] Test suite passes.
- [ ] Three audit-Section-5 smoke-test queries pass.
- [ ] Frontend builds if `web/` was touched.
- [ ] Exactly one commit with the standardized message format.
- [ ] `phase3b-<N>-cutover-log.md` exists at project root with SUCCESS banner.
- [ ] Don has been notified in chat that this sub-phase is complete.
- [ ] **No** Jira state advance (Don's gate).
- [ ] **No** push (Don's gate).

## Out of scope (per sub-phase)

- Any work outside the audit report's §7 entry for this sub-phase.
- Any work that belongs to a different sub-phase.
- Phase 4 contract work.
- Tightening nullability.
- Varbinary token migration.
- View creation (§8).
- Strategy taxonomy redesign.

## Verification

1. `git status` shows only files relevant to this sub-phase modified (plus the new log file at project root).
2. `git log --oneline -1` shows the standardized commit message.
3. `phase3b-<N>-cutover-log.md` matches the format used by `phase1a-cleanup-log.md` and `phase2-migration-log.md`.
4. No file outside the audit report's §7 scope for this sub-phase was touched.

**QA Level:** depends on sub-phase. 3b.1 (ORM alignment) is Level 2 — mechanical model changes with regression coverage from the test suite. 3b.2 (helpers + wiring) is Level 3 — touches every call site that handles symbols. 3b.3 (insights) is Level 2. 3b.4 (queries) varies by finding count.

## Commit instruction

I have been instructed to commit exactly **one commit** per sub-phase session. After the commit, **stop** and notify Don. Do not advance Jira state. Do not push. Don holds those gates.

## Coordination footer

- Previous: phase3a-orm-audit-report.md must exist and be approved by Don.
- Next: a fresh Claude Code session, with this same prompt, with `SUB_PHASE` set to the next entry in audit §7.
- After all sub-phases ship: Don decides whether Phase 3 is complete or whether the audit revealed work that warrants a follow-up phase (e.g., 3c).
