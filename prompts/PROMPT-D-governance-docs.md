---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
---

# OTA-584 + OTA-585 + OTA-586 + OTA-587 + OTA-588 + OTA-595 — Project-level Governance Documents (atomic commit)

## Terminal context
- This terminal: **Terminal D**
- Concurrent terminals: **A (OTA-515 + OTA-549/509/510), B (OTA-542 data isolation), C (OTA-560 frontend DTE filter)**
- Cross-terminal dependencies:
  - **No code contention.** This terminal touches `claude_context/*` and the repo-root `CLAUDE.md` only — no `app/`, no `web/src/`.
  - **Read-side note for A/B/C:** Terminal A, B, and C each `cat`'d `claude_context/CLAUDE.md` at session start. They are working from the pre-restructure version; that's fine — the slim restructure takes effect for the NEXT batch.
  - **Do NOT touch any file under `app/`, `web/src/`, or `tests/`.** This is a docs-only commit.

## Required reading
Before any edits:

```
cat claude_context/CLAUDE.md           # current (~659 lines per OTA-584); will be replaced
cat claude_context/bugfix.md           # current; OTA-585 is a light refresh, not a rewrite
ls -la claude_context/                  # confirm which target files do/don't already exist
cat CLAUDE.md                           # repo-root pointer; OTA-595 refreshes its 12-doc inventory
```

Then read the source drafts Don will attach to this Claude Code session at `/mnt/user-data/uploads/`:

```
ls /mnt/user-data/uploads/
# Expected files (Don will upload before starting this prompt):
#   draft-CLAUDE.md
#   draft-product-roadmap.md
#   draft-development-environment.md
#   draft-deployment-workflow.md
```

If any expected upload is missing, **stop** and ask Don to provide it. Do not invent content.

## Relevant Context — Do Not Deviate Without Escalation

**Source: `claude_context/CLAUDE.md` § Document Governance Rules**
Rule: Claude Code does not modify SoT docs unsolicited. This Story explicitly authorizes the listed file changes; nothing outside the listed paths is touched.

**Source: profile-level `prompt-style.md` (already shipped at profile level via OTA-590, deferred outside this batch)**
Rule: SoT docs use the same Required Reading + Relevant Context conventions described elsewhere. The drafts referenced here follow those conventions; do not "fix" them stylistically.

**Source: OTA-584 ticket — Restructure deltas vs current CLAUDE.md**
- Hierarchy fixed: Epic → Story → Subtask, **no Feature anywhere**.
- 6 sections extracted to pointers: `prompt-style.md`, `build-execution.md`, `product-roadmap.md`, `development-environment.md`, `deployment-workflow.md`, `jira-structure.md`.
- New `Document Governance Rules` section at top.
- New `Profile-Level Conventions` subsection naming `jira-structure`, `prompt-style`, `build-execution`, `claude-web`.
- `Active Cleanup Items` carries valid-until **2026-06-30**.
- `Post-Build QA Gate` carries `Last Reviewed: 2026-05-06` with 60-day cadence.
- "Common Epic parents" list **removed**.
- Claude Code "review Jira plan?" prompt **removed** from Session Start.
- Bug type ID confirmed as **10215**.
- Drops from ~659 lines to ~290.

**Source: OTA-595 ticket — Repo-root CLAUDE.md pointer must list these 12 SoT docs**
1. CLAUDE.md
2. architecture-plan.md
3. business-rules.md
4. UI-GUIDANCE.md
5. auth-process.md
6. bugfix.md
7. SCHWAB-LOGIN-PROCESS.md
8. azure-naming-conventions.md
9. product-roadmap.md  *(new)*
10. development-environment.md  *(new)*
11. deployment-workflow.md  *(new)*
12. jira-structure.md  *(profile mirror in OTA repo per OTA-569 decision)*

The bootstrap `cat claude_context/CLAUDE.md` instruction at the top of the root pointer is unchanged. The standing reminder cross-references `prompt-style.md` for Mechanism A + B.

**Source: OTA project shared-file rule**
Rule: Other terminals in this batch each cat `claude_context/CLAUDE.md` at session start. Replacing the file mid-batch is safe because A/B/C have already loaded the old version into their context. Do not signal them mid-flight — the change takes effect for the next batch.

---

## Phase 1 — Sanity check (brief; no STOP gate required)

1. Run `ls /mnt/user-data/uploads/` and confirm all four expected drafts are present.
2. Run `git status` — confirm working tree is clean before starting (no in-flight edits from a prior session).
3. Run `git pull --ff-only` — confirm local branch is up to date with `main`.
4. Confirm `claude_context/` is the canonical SoT directory in this repo (the prompt assumes it; if a different path is in use, escalate before editing).

If any of those four checks fails, stop and report. Otherwise proceed to Phase 2.

---

## Phase 2 — Apply the docs

Apply in this exact order. All edits go in a single commit at the end.

### 2a. OTA-584 — Replace `claude_context/CLAUDE.md`
- Replace the entire file with the contents of `/mnt/user-data/uploads/draft-CLAUDE.md`.
- After replacement, `grep -in "feature" claude_context/CLAUDE.md | grep -v "feature flag\|featured\|features list\|featuring" | head` — expect no Feature-as-issue-type references. Any survivor is a defect; stop and surface.

### 2b. OTA-585 — Light refresh of `claude_context/bugfix.md`
- Open `claude_context/bugfix.md` in place. Do NOT rewrite — apply the targeted alignment changes only:
  - Verify hierarchy references say Epic → Story → Subtask (no Feature). Fix any that don't.
  - Verify the Documentation Governance Epic structure references are current (parent for bug-fix session Stories is **OTA-555**).
  - Verify cross-references to other Governance Docs by their current names: `prompt-style.md`, `build-execution.md`, `product-roadmap.md`, `development-environment.md`, `deployment-workflow.md`, `jira-structure.md`.
  - "Source of Truth" and "Governance Document" are interchangeable — leave both forms in place where they exist.
- No protocol changes (triage criteria, rollup format, commit-vs-no-commit rule all stay as-is).

### 2c. OTA-586 — Create `claude_context/product-roadmap.md`
- Create the file from `/mnt/user-data/uploads/draft-product-roadmap.md` (copy verbatim).
- The file must include: OTA ↔ OTAR relationship, all active OTAR Categories with one-line scope summaries, OTAR-27 (TMTC Application Framework) cross-project Category note, procedure for linking new Epics to Categories, procedure for proposing new OTAR Categories, OTAR URL reference.

### 2d. OTA-587 — Create `claude_context/development-environment.md`
- Create the file from `/mnt/user-data/uploads/draft-development-environment.md` (copy verbatim).
- The file must include: backend setup (FastAPI, **`venv` not `.venv`**, HTTPS startup with self-signed certs, port 8000), full `cd` + `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (Unix) commands, frontend setup (Vite, port 5173, proxy to backend), self-signed cert generation via Python `cryptography` library (NOT OpenSSL CLI on Windows), pytest commands, **zombie process warning** (Windows port 8000; `Get-Process python,uvicorn | Stop-Process -Force`; `netstat -ano | findstr ":8000"`), troubleshooting section (404s after route changes → zombie process; HTTPS cert errors).

### 2e. OTA-588 — Create `claude_context/deployment-workflow.md`
- Create the file from `/mnt/user-data/uploads/draft-deployment-workflow.md` (copy verbatim).
- The file must reference: 4-step deploy model (build-on-push → deploy to staging slot → smoke test → swap-staging-to-prod), GitHub Actions confirmation tokens (`DEPLOY`, `DEPLOY-DEV`, `SWAP`, `ROLLBACK`), dev environment (single slot, fix-forward), slot-swap discipline, rollback workflow, all four workflow files (`build-on-push.yml`, `deploy-to-prod.yml`, `swap-staging-to-prod.yml`, `rollback-prod.yml`, `deploy-to-dev.yml`), Alembic migration discipline + perpetual cleanup story OTA-523, Deployment Recording implementation scaffolding (`deploy_log` table, `POST /api/v1/changelog/record`, `GET /api/v1/changelog`, `/changelog` UI route, `DEPLOY_RECORDER_TOKEN` rotation).

### 2f. OTA-595 — Refresh repo-root `CLAUDE.md` pointer
- Open the repo-root `CLAUDE.md` (NOT `claude_context/CLAUDE.md` — the root pointer file).
- Update the "Why this is a pointer" cohesion section to list all 12 SoT docs from Relevant Context.
- Confirm the bootstrap instruction `cat claude_context/CLAUDE.md` at the top is unchanged.
- Confirm the standing reminder cross-references `prompt-style.md` for Mechanism A + B.
- If the root pointer follows the profile-level `CLAUDEMD-root-pointer-template.md` shape, preserve that shape; only the inventory list changes.

### 2g. Pre-commit verification (mandatory)
Run all of these before requesting commit approval:

```
ls -la claude_context/CLAUDE.md \
       claude_context/bugfix.md \
       claude_context/product-roadmap.md \
       claude_context/development-environment.md \
       claude_context/deployment-workflow.md \
       CLAUDE.md
wc -l claude_context/CLAUDE.md   # expect ~290 lines per OTA-584
grep -in "feature" claude_context/CLAUDE.md | grep -v "feature flag\|featured\|features list\|featuring"
grep -c "prompt-style.md\|build-execution.md\|product-roadmap.md\|development-environment.md\|deployment-workflow.md\|jira-structure.md" claude_context/CLAUDE.md
git status
git diff --stat
```

Each of the listed files must exist, the slim CLAUDE.md must hit roughly the expected line count, no Feature-as-issue-type strings must survive, and the pointer references must all be present.

---

## Acceptance criteria

**OTA-584:**
- `claude_context/CLAUDE.md` replaced with the slim restructure (~290 lines).
- No Feature-as-issue-type references remain.
- All 6 extracted sections have pointer paragraphs in their place.

**OTA-585:**
- `claude_context/bugfix.md` aligned with new governance structure (no protocol changes).
- Cross-references to current Governance Doc names resolve.
- Hierarchy references match Epic → Story → Subtask.

**OTA-586:** `claude_context/product-roadmap.md` exists with the contents listed in 2c.

**OTA-587:** `claude_context/development-environment.md` exists with the contents listed in 2d, including the zombie-process workaround and the `venv` (not `.venv`) convention.

**OTA-588:** `claude_context/deployment-workflow.md` exists with the contents listed in 2e, including Deployment Recording implementation scaffolding.

**OTA-595:** Repo-root `CLAUDE.md` lists all 12 current SoT docs in its cohesion paragraph. Bootstrap instruction unchanged.

**Atomic commit:** A single commit lands all six changes. The commit message references all six ticket keys.

## Out of scope

- Profile-level docs (`prompt-style.md`, `build-execution.md`, `claude-web.md`, `jira-structure.md` profile copy, `CLAUDEMD-root-pointer-template.md`) — those are OTA-589/590/591/592/594 and Don applies them at profile level outside this terminal.
- Any code change in `app/` or `web/src/`.
- Reflowing or restyling `bugfix.md` beyond the targeted alignment items.
- Building the `/changelog` endpoint or page (separate Story under OTA-511).

## Verification steps

Run these in order; do not request commit approval until all pass:

1. The Phase 2g verification block above produces clean output (no Feature survivors, all pointer refs present, files exist, line counts roughly match).
2. `git diff --stat` shows changes only to `claude_context/*.md` and the repo-root `CLAUDE.md`. Any other path = scope creep, fix before requesting approval.
3. Open each new/replaced file briefly with `head -30` and `tail -30` and visually confirm the headers and Change Log entries look right.
4. Confirm no broken cross-references: `grep -on "claude_context/[a-z-]*\.md" claude_context/*.md | sort -u` — every file referenced should exist on disk.

## Commit instruction
**I have been instructed to commit. Do you approve? (yes / no)**

## Coordination footer
**Independent — no downstream dependency.** Other terminals proceed in parallel; nothing in this batch waits on Terminal D. The profile-level subtasks (OTA-589/590/591/592/594) are Don's manual application at the profile location and do not block any project work.

## Commit message template (if committing)
```
OTA-584 OTA-585 OTA-586 OTA-587 OTA-588 OTA-595 docs: project-level governance restructure — slim CLAUDE.md, port roadmap/dev-env/deploy-workflow, refresh root pointer
```
