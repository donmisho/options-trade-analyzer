# Deployment Plan — Write-Prompt Batch (2026-05-06)

**Scope:** 4 terminals, 9 OTA tickets. End-to-end from terminal kickoff through production slot-swap.

**Authority:** Don personally approves every commit, every deploy, every swap. This plan is the operating sequence; Don holds the gates.

---

## Batch contents

| Term | Tickets | Domain | Risk | Production user-visible? |
|---|---|---|---|---|
| A | OTA-515, OTA-549, OTA-509, OTA-510 | Backend trade-eval pipeline + frontend badge | **Medium** — new verdict + new validator in critical path | **Yes** — new verdict, amber badge, regenerated narratives |
| B | OTA-542 | Backend security (data isolation) | **Medium** — fixes silent cross-user delete bug | No (security hardening; no UX change) |
| C | OTA-560 | Frontend filter (Trades page) | **Low** — client-side filter, no backend touch | **Yes** — new filter UI on Trades page |
| D | OTA-584, OTA-585, OTA-586, OTA-587, OTA-588, OTA-595 | Project-level docs only | **None** — no runtime impact | No |

---

## Phase 1 — Pre-flight (before any terminal starts)

Don confirms each, ticking off:

- [ ] All four prompt files reviewed and minor edits applied if needed (file paths, repo conventions Don knows that I don't)
- [ ] Drafts uploaded to Terminal D's Claude Code session (`draft-CLAUDE.md`, `draft-product-roadmap.md`, `draft-development-environment.md`, `draft-deployment-workflow.md`)
- [ ] Local `main` is up to date: `git fetch origin && git log HEAD..origin/main` is empty
- [ ] No uncommitted local changes: `git status` is clean
- [ ] `venv` activated in each terminal that runs Python (Terminal A and Terminal B)
- [ ] Frontend tooling ready in Terminal C: `npm install` is current
- [ ] Each terminal opens with `cat claude_context/CLAUDE.md` as the very first command (Session Start Protocol)
- [ ] Atlassian MCP availability checked — fall back to REST if not surfaced

---

## Phase 2 — Parallel terminal execution

All four terminals start at roughly the same time. Each runs Phase 1 (read-only diagnostic) → STOP → Phase 2 (implementation) → verification → request commit approval.

### Suggested kickoff order (optional)

1. **Terminal D first** (lowest risk, fastest to first commit) — gets a quick win in the Jira queue and removes the docs from the deferred list.
2. **Terminal C second** (frontend-only, isolated scope) — short Phase 1; small implementation.
3. **Terminal A third** (largest scope, deepest reasoning required for verdict-tree integration).
4. **Terminal B in parallel with A** (different file set, no contention).

You can also start all four simultaneously — the slate was designed for parallel safety. The order above is just lowest-effort to highest-effort if you want to context-switch through them.

### Cross-terminal STOP rules (recap from prompts)

| Stop trigger | Action |
|---|---|
| Terminal A's Phase 1 reveals OTA-502/503 missing or moved | Stop; escalate before continuing |
| Terminal B's Phase 1 reveals a fix that needs `app/main.py` edit | Stop; escalate (out of scope this batch) |
| Terminal C's Phase 1 reveals scan-default values aren't surfaced anywhere | Stop; escalate before hardcoding |
| Terminal D missing any expected upload | Stop; ask Don to provide |

### What Don does between Phase 1 and Phase 2 of each terminal

When a terminal stops at the Phase 1 STOP gate, Don:
1. Reads the diagnostic report
2. Either gives go-ahead or sends a course correction back to that Claude Code instance
3. Does NOT advance any other terminal because of this — terminals are independent

---

## Phase 3 — Commit sequence

Each terminal requests commit approval independently. Don approves each in turn. Commit order **does not matter for correctness** — file sets are disjoint — but for cleaner Jira automation timing, the recommended order is:

1. **Terminal D commit** (docs only — fastest auto-transition, no deploy concern)
2. **Terminal C commit** (frontend filter — no backend coordination needed)
3. **Terminal B commit** (data isolation — security fix, contract test must be green)
4. **Terminal A commit** (verdict + validator — largest user-visible change)

Each commit message contains every ticket key it touches (per `CLAUDE.md` Commit Message Convention). Auto-transition fires per Jira automation: `Code & Test Complete` for each referenced key.

### What `Code & Test Complete` means here

The artifact has been **built** by `build-on-push.yml`. It is **not** in production. The transition to `Production Deployed` happens only after a successful slot swap (Phase 5 below).

---

## Phase 4 — Dev deploy + smoke

After all four commits land on `main`:

1. Don triggers `deploy-to-dev.yml` with confirmation token `DEPLOY-DEV`. Single artifact deploys to `options-analyzer-api-dev`. Dev is single-slot — fix-forward, no roll back.

2. **Smoke checklist** on `oa-dev.tmtctech.ai`:

   **OTA-515 / OTA-549 / OTA-509 / OTA-510 (Terminal A):**
   - [ ] Vertical evaluate on a non-earnings symbol still returns EXECUTE / WAIT / PASS as before (regression check)
   - [ ] Vertical evaluate on an earnings-adjacent symbol with `dte_after_earnings >= 14` returns **WAIT_FOR_EARNINGS** with a `reevaluate_on` date populated
   - [ ] Frontend amber badge renders for the WAIT_FOR_EARNINGS verdict; date displayed as `mm-dd-yyyy`; no `$` prefix anywhere on the panel
   - [ ] Negative-EV earnings-adjacent setup verdicts as **PASS**, not WAIT_FOR_EARNINGS (NEG EV gate fires first)
   - [ ] AMZN narrative-validator regression: a deliberately bad narrative (positive-EV claim with negative computed EV) is blocked + regenerated, observable in `agent_run_log`
   - [ ] AMZN SMA hallucination case blocked + regenerated, observable in `agent_run_log`
   - [ ] Naked options evaluate STILL returns 502 (OTA-558 deferred — confirmed expected; no surprise regression there)

   **OTA-542 (Terminal B):**
   - [ ] DELETE `/recommendations/{trade_key}` from a logged-in session: the user's own resource deletes (200/204); a different user's `trade_key` returns 404
   - [ ] Audit log shows the cross-user attempt (if logging exists; not required by ticket)
   - [ ] Quick spot-check of one or two other CRUD endpoints fixed in the audit (positions, watchlists)

   **OTA-560 (Terminal C):**
   - [ ] Trades page renders the new DTE filter above the Vertical spreads section
   - [ ] Setting Min=14, Max=45 narrows results in real time
   - [ ] URL params `?dte_min=14&dte_max=45` persist on refresh and on copy-paste
   - [ ] Reset button restores defaults
   - [ ] Empty-state message renders with inline Reset link when no results match

   **Terminal D:** No runtime smoke needed (docs only). Confirm `git log` on the deployed commit shows all 6 ticket keys.

3. **Deployment Recording** — confirm a row landed in `/changelog` for this dev deploy with build ID, environment=`dev`, timestamp, commit SHAs, all ticket keys parsed. (Per profile-level `build-execution.md` Part 4.) If `/changelog` infrastructure isn't live yet, log the deploy out-of-band and note the gap.

---

## Phase 5 — Production deploy

Only after Phase 4 smoke passes cleanly.

1. Don triggers `deploy-to-prod.yml` with confirmation token `DEPLOY`. Artifact lands in the **staging slot** of `options-analyzer-api`. Production traffic still on the previous artifact.

2. **Staging slot smoke** on the staging slot URL (per `deployment-workflow.md`):
   - Re-run the same checklist from Phase 4 against the staging slot.
   - Pay particular attention to any difference vs dev (different DB, different traffic shape, different load pattern).

3. **Slot swap** — only if staging smoke is green. Don triggers `swap-staging-to-prod.yml` with confirmation token `SWAP`. Staging becomes prod; old prod becomes staging.

4. **Post-swap smoke** on `oa.tmtctech.ai`:
   - Re-run the OTA-515/OTA-560 smoke items (anything user-visible).
   - Spot-check OTA-542 cross-user delete: pick one CRUD endpoint and verify 404 on a known-foreign trade_key.
   - Watch the AI evaluation surface for ~15 minutes. Validator-induced regenerations should appear in logs at a non-zero but reasonable rate. If regenerations spike unreasonably or evaluations start failing, that's a validator over-trigger — see Rollback below.

5. **Deployment Recording** — confirm `/changelog` row for environment=`prod`, including the swap event.

6. **Jira advancement** — Don manually transitions each ticket from `Code & Test Complete` → `Production Deployed`. Don holds this gate; do not delegate.

---

## Rollback

### If smoke fails on dev (Phase 4)
Fix-forward. Dev is single-slot. Open a new prompt for the failing terminal, fix, commit, redeploy.

### If smoke fails on staging slot (Phase 5 step 2)
Do NOT swap. The previous-good artifact is still on prod. Diagnose against the staging slot directly. Fix-forward by deploying a new artifact to staging.

### If something fails post-swap on prod (Phase 5 step 4)
- **For Terminal C and Terminal D failures:** the impact is bounded (a UI bug or a doc misalignment). Decide on the spot whether to roll back via re-swap or fix-forward.
- **For Terminal A failures (validator over-blocks legitimate narratives, or new verdict misroutes):** roll back via re-swap immediately. Validator can mute or block useful trade evaluations — that's a higher-cost regression than waiting.
- **For Terminal B failures (data isolation regression):** roll back via re-swap immediately. A returning isolation bug is the worst-case outcome of this batch.

Re-swap is `swap-staging-to-prod.yml` again — the slots flip back. Old prod (which is now staging) becomes prod again. Confirm with the `SWAP` token.

For longer-lived rollbacks where the previous-good artifact is no longer in staging (e.g., a later deploy already overwrote staging), use `rollback-prod.yml` with the `ROLLBACK` token and the `build_run_id` of the prior good build.

---

## Post-batch hygiene

After Production Deployed for all 9 tickets:

1. **Reparent OTA-509 and OTA-510** under OTA-549 manually (per OTA-549 spec). Use the Atlassian MCP or the Jira UI.
2. **Close any duplicates** that surfaced during work (none expected, but check the queue).
3. **Defer-queue advancement:** With Terminal A landed, the AI/scoring area is unblocked. Next batch candidates:
   - **OTA-558** (502 fix on naked options evaluate) — highest priority next; same area, now safe to touch
   - **OTA-557** (auto-archive bug diagnostic) — frontend console-log read; bug-fix session pattern
   - **OTA-559** (per-strategy DTE windowing at scan time) — needs OTA-513 + OTA-516 to be live first; if both are, ship
   - **OTA-538** (Auth Stack Cleanup) — tier-1-burn-down; clears the way for OTA-544
   - **OTA-544** (Dead Code & Repo Hygiene) — depends on OTA-538
4. **Update the Active Cleanup Items** date in `claude_context/CLAUDE.md` if any framework-v1 stories shipped.
5. **Memory edit candidate:** if anything material from this batch generalizes (e.g., "validator regenerations log to X and we monitor at Y"), propose it as a memory edit before the chat closes.

---

## What I deferred from this batch and why

| Ticket | Reason |
|---|---|
| OTA-557 | Bug — Positions page diagnostic; sequenced after Terminal A to avoid same-area churn |
| OTA-558 | Bug — 502 on Put/Call Evaluate; same `app/api/evaluation_routes.py` Terminal A may touch; sequenced after A |
| OTA-559 | Story — explicit dependencies on OTA-513 + OTA-516; cannot ship until those land |
| OTA-536 | Architecture #1 — AI Stack Unification; touches `main.py` + ai/providers tree; cannot run with A |
| OTA-537 | Architecture #2 — Trade Eval Prompts to SKILL.md; SKILL.md exclusivity with Terminal A |
| OTA-538 | Architecture #3 — Auth Stack Cleanup; touches `main.py` and auth/; sequence after batch |
| OTA-539 | Architecture #4 — Provider Lifecycle Wiring; sequence after Story #6 (route consolidation) lands |
| OTA-541 | Architecture #6 — Route File Consolidation; touches `main.py` heavily; needs solo terminal |
| OTA-543 | Architecture #8 — Resource Shutdown; touches `main.py`; needs solo terminal |
| OTA-544 | Architecture #9 — Dead Code & Hygiene; depends on OTA-538 (MSAL bridge retirement) |
| OTA-546 | Architecture #11 — Strategy Config Resolution; needs persistence-model decision OTA-514 first |
| OTA-589 | Profile-level — Don applies directly at profile location |
| OTA-590 | Profile-level — Don applies directly at profile location |
| OTA-591 | Profile-level — Don applies directly at profile location |
| OTA-592 | Profile-level — Don applies directly at profile location |
| OTA-594 | Profile-level — Don applies directly at profile location |

---

## One-screen execution summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Pre-flight  →  Open 4 terminals  →  Run prompts  →  4 commits to main      │
│                              ↓                                                │
│            Build-on-push fires per commit (no deploy)                        │
│                              ↓                                                │
│  Don triggers deploy-to-dev (DEPLOY-DEV)  →  smoke on oa-dev.tmtctech.ai     │
│                              ↓                                                │
│  Don triggers deploy-to-prod (DEPLOY)  →  smoke on staging slot              │
│                              ↓                                                │
│  Don triggers swap-staging-to-prod (SWAP)  →  smoke on oa.tmtctech.ai        │
│                              ↓                                                │
│  Don manually advances each ticket → Production Deployed                     │
└──────────────────────────────────────────────────────────────────────────────┘
```
