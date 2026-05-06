# Bug Fix Session Workflow

**Last Updated:** 2026-05-06 UTC
**Instigating Ticket:** TBD — file under OTA-477 (Architecture Documentation Refresh)
**Session Container Epic:** OTA-555 — *Miscellaneous Bug Fixes - Interactive Claude Code Sessions*

---

This document describes the **bug-fix session** protocol for surgically fixing small defects discovered post-deploy. It is invoked by Don and run by Claude Code. The workflow is intentionally narrow — only small, low-risk fixes are in scope; anything bigger gets deferred to a proper Story.

CLAUDE.md remains the canonical reference for Jira mechanics, transition IDs, hierarchy rules, and SoT doc inventory. This document does not duplicate those — it composes them into a session workflow.

---

## When to use

Use a bug-fix session for: small UI defects, cosmetic regressions, missing log lines, copy fixes, single-file frontend wiring bugs, single-route backend tweaks, simple data display bugs.

Do **not** use a bug-fix session for: new features, multi-file refactors, scoring engine changes, auth flow changes, schema changes, anything that needs deep investigation. Those are Stories.

---

## Invocation

Don says one of:

- **"Start a bug fix session"** → Claude Code auto-creates a new session parent ticket under OTA-555.
- **"Start a bug fix session for OTA-XXX"** → Claude Code resumes an existing session parent (e.g., when continuing across days).

In either case, Claude Code runs Phase 0 setup (below), confirms ready, and waits for the first item.

---

## Phase 0 — Session setup

### Working directory

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

### Read always-required SoT docs

```bash
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
```

Other SoT docs (`UI-GUIDANCE.md`, `auth-process.md`, `business-rules.md`, `SCHWAB-LOGIN-PROCESS.md`, `azure-naming-conventions.md`, `product-roadmap.md`, `development-environment.md`, `deployment-workflow.md`) are read **on demand per item** when the item touches that domain. See CLAUDE.md → Per-domain required reading, or profile-level `prompt-style.md` for the convention.

### Create or resume the session parent ticket

**New session** — create a Story under OTA-555 with these fields:

- **Project:** `OTA`
- **Issue type:** Story (issuetype id `10214`)
- **Parent:** `OTA-555` (passed as the named `parent` parameter, never inside `additional_fields`)
- **Summary:** `Interactive Bug Fix Session - MM-DD-YYYY` using today's date in `mm-dd-yyyy` hyphenated format (e.g., `Interactive Bug Fix Session - 05-06-2026`)
- **Labels:** `["bug-fix-session"]`
- **Description** (`contentFormat: markdown`):

```markdown
## Interactive Bug-Fix Session — MM-DD-YYYY

**Started:** <ISO 8601 UTC timestamp>
**Status:** Active

_Session in progress. Rollup populated at session end._
```

Capture the returned ticket key as `session_parent_key` and the start timestamp as `session_start_iso` in session memory.

**Hierarchy note:** the session parent must be a Story, not a Bug. The OTA project's strict rule is that Subtasks parent only to a Story (or to a Story-level Bug). The `bug-fix-session` label preserves the categorization without breaking hierarchy.

**Resumed session** (when Don specifies a parent key):

- Verify the ticket exists, has label `bug-fix-session`, and is in a non-terminal status.
- Read the existing description; extract the original `Started` timestamp into session memory.
- Read existing fix entries (if any) so the end-of-session rollup appends rather than overwrites.

### Initialize session memory

Track throughout the session:

- `session_parent_key` — parent ticket key
- `session_start_iso` — ISO 8601 UTC start timestamp
- `fixes` — running list of completed fixes, each with `summary`, `files_modified`
- `deferred` — running list of TOO COMPLICATED items, each with `title`, `reason`, `disposition`

### Confirm ready

Reply exactly:

> Session ready. Parent ticket: **OTA-XXX**. Feed me the first item.

Do not pre-emptively scan for bugs. Do not summarize the SoT docs. Do not propose work.

---

## Per-item workflow

For every item Don feeds, follow these steps in order. **Subtasks and commits are NOT created mid-session — they're batched at session end.**

### Step 1 — Triage

Read the item. Do **read-only** investigation if needed (`Grep`, `Read`, log inspection). Cat any domain-specific SoT doc if the item touches that domain. Then classify:

**SMALL FIX (proceed)** — all must be true:

- Touches ≤ 3 files
- No schema changes, Alembic migration, or new dependencies
- No changes to BFF auth, OIDC, certificate handling, `azure.identity` async patterns
- No changes to scoring engine math (SP / WG / TR / LT pipeline internals)
- Root cause identifiable from code inspection alone — not a prod-only mystery
- Estimated diff < 100 lines
- No new test files required (modifying existing tests is OK)

**TOO COMPLICATED (defer)** — any of:

- Multi-file refactor or cross-cutting change
- Touches BFF / OIDC / async credentials / Schwab adapter internals
- Touches scoring pipeline logic or strategy taxonomy
- Needs DB schema or contract changes
- Symptom only reproduces in prod and cannot be reasoned about from code
- Estimated investigation > 10 minutes

State the verdict in **one sentence** with file paths. If TOO COMPLICATED, add the item to the `deferred` list in session memory with a one-line reason and recommended disposition (Story to write, log inspection needed, etc.). Do not create the Story — Don owns ticket strategy.

### Step 2 — Propose

If SMALL FIX, show the proposed diff. Do not apply yet. Wait for explicit approval. Iterate if Don pushes back.

### Step 3 — Apply

After approval:

- Apply the edit(s)
- Run obvious local checks (frontend `npm run type-check` / `npm run lint`, backend single targeted test) when they make sense
- Skip local checks if the bug only manifests in deployed dev / prod — say so explicitly
- Show Don the final diff
- **Capture the modified file paths in session memory** (`fixes[i].files_modified`)

### Step 4 — Update documentation (only if warranted)

If the fix changes behavior described in any living SoT doc, update that doc in the same edit pass. Update the doc's `Last Updated` header and add a Change Log entry referencing the session parent ticket key. Add the doc path to the modified-files list for that fix.

**Rule of thumb:** if a future engineer reading the doc would now find it wrong because of this fix, update it.

State explicitly: "Updated: \<doc list>" or "No doc updates needed."

### Step 5 — Mark complete, ready for next item

Reply briefly: "Fix complete. Ready for next item." Do **not** suggest a commit message or create a Subtask yet — those happen at session end.

---

## Session end protocol

Don signals the end with phrases like *"end the session,"* *"we're done,"* *"wrap it up."*

### Step A — Summarize for review

Compute:

- `bugs_fixed` = `len(fixes)`
- `deferred_count` = `len(deferred)`
- `elapsed_minutes` = (now UTC) − `session_start_iso`, rounded to nearest 5 minutes
- `unique_files` = deduplicated union of all `files_modified` across fixes

Show Don a preview of the rollup table (Step C format) so he can verify content before commit.

### Step B — Suggest one consolidated commit message

Per CLAUDE.md → Commit Message Convention:

```
{SESSION-PARENT-KEY} chore(bug-fix-session): MM-DD-YYYY — N fixes

- Fix 1 short summary
- Fix 2 short summary
- ...
```

Wait. Don commits, pushes, watches the build. He replies with one of:

- **"committed, build green, hash `<sha>`"** → proceed to Step C
- **"build failed"** or regression report → return to triage on the offending fix; do **not** create Subtasks yet
- **"skip the rollup"** → end without writing Subtasks or updating parent

The Jira automation will auto-transition the parent ticket to **Code & Test Complete** because the parent key is in the commit. Expected and harmless.

### Step C — Create Subtasks in batch

For each fix in `fixes`, create a Subtask:

- **Issue type:** Subtask (issuetype id `10002`)
- **Parent:** `session_parent_key`
- **Summary:** the fix's one-line summary
- **Description** (`contentFormat: markdown`):

```markdown
## What was wrong
<1–2 sentences from triage>

## What changed
- Files: `<path/one>`, `<path/two>`
- Key change: <one sentence>

## Commit
<sha from Step B>
```

After creation, transition each Subtask to **Code & Test Complete** using transition id `51` (transition name: "Done"). The commit-triggered automation does not fire for Subtasks because they didn't exist at commit time — manual transition is required.

### Step D — Update parent ticket description with the rollup

Replace the parent's description with this exact format:

```markdown
## Interactive Bug-Fix Session — MM-DD-YYYY

**Bugs fixed:** N (+ X deferred as TOO COMPLICATED, + Y future Story written to screen)
**Elapsed time:** ~N minutes
**Commit:** <sha>

### Fixes shipped

| # | Fix | Files |
|---|-----|-------|
| 1 | <one-line fix summary> | `<file1>`, `<file2>` |
| 2 | <one-line fix summary> | `<file1>` |

### Deferred

- **<deferred item title>** — TOO COMPLICATED. <one-line reason>. <disposition: Story written, log inspection needed in N weeks, etc.>
```

If the session is being resumed (existing parent had a prior rollup), append the new fixes to the existing table rather than overwriting. Update `Bugs fixed`, `Elapsed time`, and `Commit` to reflect the cumulative session.

### Step E — Final ready signal

Reply exactly:

> Session **OTA-XXX** complete. **N** fixes shipped, **X** deferred. Parent ticket updated with rollup.

---

## Hard boundaries

- **Never commit during the session.** All fixes accumulate; Don commits once at session end.
- **Never push, tag, or deploy.**
- **Never modify the parent ticket itself** during the session except for the end-of-session rollup write.
- **Never create Subtasks mid-session.** Batch at session end after commit confirmation.
- **Never create a parent-level Story or Bug** during a session. Don owns ticket strategy.
- **Never touch the Schwab adapter, BFF auth flow, scoring pipeline math, or DB schema** as a small fix.
- **Never delete files** unless Don explicitly instructs.
- **Never create a duplicate Subtask** if a regression is fed back. Comment on the existing Subtask and re-open.

---

## When in doubt

Default to **defer**. The cost of deferring something quick is low. The cost of starting a multi-file rabbit hole inside a rapid-fire session is high.

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-05-06 UTC | TBD | Initial draft. Memorializes the bug-fix session workflow first run under OTA-556 on 2026-05-06. Adopts the rollup format that emerged organically from that first session: `mm-dd-yyyy` hyphenated date, single end-of-session commit, batch Subtask creation, deferred items captured in the parent ticket rollup. References CLAUDE.md for Jira mechanics, transition IDs, hierarchy rules, and SoT doc inventory rather than duplicating. |
