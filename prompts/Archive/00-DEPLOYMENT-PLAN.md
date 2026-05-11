# Write-Prompt Deployment Plan — 4-Terminal Build

**Author:** Claude Web
**Date:** 2026-05-06 UTC
**Scope:** All 26 OTA tickets currently in Write Prompt status, allocated across four parallel Claude Code terminals plus a profile-level manual track.

---

## Executive summary

26 tickets live in Write Prompt today. They split into three execution tracks:

- **21 tickets** become 14 Claude Code prompt files distributed across four terminals (A/B/C/D). 8 are bundled into 2 multi-OTA prompts (one per terminal); the rest are single-OTA.
- **5 tickets** are profile-level documentation drops that Don applies manually outside the OTA repo. They do not get Claude Code prompts.

Critical-path gates and cross-terminal dependencies are explicitly listed below and re-stated in each prompt's coordination footer.

---

## Track 1 — Profile-level (Don manual; no Claude Code prompt)

These five Subtasks all explicitly state "Done by Don directly at profile level." Claude Web cannot reach the profile location from project context, and Claude Code does not operate there. Don applies the drafts (already in this chat session as `/mnt/user-data/outputs/*.md`) to his profile directory and transitions each Subtask to Code & Test Complete after applying.

| Ticket | Action |
|---|---|
| OTA-589 | Update profile-level `jira-structure.md` per the proposed wording |
| OTA-590 | Create profile-level `prompt-style.md` |
| OTA-591 | Create profile-level `build-execution.md` |
| OTA-592 | Create profile-level `claude-web.md` |
| OTA-594 | Create profile-level `CLAUDEMD-root-pointer-template.md` |

Recommend doing all five in one sitting since the drafts are already in hand.

---

## Track 2 — Four-terminal Claude Code build

### Terminal allocation rationale

The hard constraints driving the allocation:

- `app/main.py` is project-critical shared (per OTA CLAUDE.md). Four stories touch it (OTA-538, 541, 543, 544) — these all live on the same terminal and serialize.
- `app/api/evaluation_routes.py` is touched by both OTA-549 (Terminal A) and OTA-537 (Terminal C) — Terminal C's prompt has an explicit STOP gate until Terminal A's OTA-549 commits.
- `app/providers/factory.py` is touched by OTA-539 (Terminal D); OTA-536 (Terminal C) deletes `app/providers/ai/` (separate location) — coordinated but should not collide. Terminal D's OTA-539 prompt has a recommended sequencing note.
- Pipeline / scoring / verdict work all touches scoring + skill files. These all live on Terminal A.
- Provider lifecycle, strategy config, and repo doc apply work share no overlap with the other three terminals — Terminal D.

### Allocation table

| Terminal | Prompt | Tickets | Touches | Gate |
|---|---|---|---|---|
| **A** | A1 | OTA-558 | `evaluation_routes.py` (logging) | None — start immediately |
| A | A2 | OTA-549 + OTA-509 + OTA-510 | `app/validators/`, `evaluation_routes.py` (validator wiring), AMZN regression suite | After A1 commits |
| A | A3 | OTA-515 | verdict enum, decision-tree module, `evaluation_routes.py`, `SKILL.md`, UI badge | After A2 commits |
| A | A4 | OTA-557 | Positions page console-log triage; small frontend or backend fix depending on root cause | After A3 commits (or interleaved if Don wants) |
| A | A5 | OTA-559 | vertical scanner | **GATED — confirm OTA-516 is Production Deployed before starting; if not, hold** |
| **B** | B1 | OTA-538 | `app/api/auth_routes.py`, `entra_auth_routes.py`, `dependencies.py`, `main.py`, startup assertions | None — start immediately |
| B | B2 | OTA-543 | `main.py` lifespan, `FoundryEvalAdapter`, scheduler, token task | After B1 commits |
| B | B3 | OTA-541 | route file renames, `main.py` includes, `client.js` callers, `architecture-plan.md` § 3 | After B2 commits |
| B | B4 | OTA-544 | many delete operations + `.gitignore` | After B3 commits |
| **C** | C1 | OTA-536 | `app/ai/base.py`, `app/providers/ai/` (delete), `agent_routes.py` | None — start immediately |
| C | C2 | OTA-537 | `app/skills/trade-evaluation/SKILL.md`, `app/ai/prompts.py` (delete), `evaluation_routes.py` | **GATED — wait for Terminal A's OTA-549 commit before starting** |
| **D** | D1 | OTA-539 | `app/providers/factory.py` (rename), `PROVIDER_REGISTRY`, frontend data-source picker | Recommended after Terminal C's C1 commits to avoid factory-area churn |
| D | D2 | OTA-546 | `app/analysis/strategy_definitions.py`, persistence model decision (Don gate) | Don decides Option A/B/C before starting |
| D | D3 | OTA-584 + OTA-585 + OTA-586 + OTA-587 + OTA-588 + OTA-595 | `claude_context/*.md` only — six SoT doc apply operations in one commit | None — independent of all code work |

### Sequence-of-operations diagram

```
T0 ────────────────────────────────────────────────────────────────────►
       ↓                ↓                ↓                ↓
   Terminal A       Terminal B       Terminal C       Terminal D
       ↓                ↓                ↓                ↓
     A1: 558         B1: 538          C1: 536          D3: docs (584+585+586+587+588+595)
       ↓                ↓                ↓                ↓
     A2: 549+509+510 B2: 543          [WAIT for A2]   D1: 539 (after C1)
       ↓                ↓                ↓                ↓
     A3: 515         B3: 541          C2: 537          D2: 546 (after Don's decision)
       ↓                ↓                ↓
     A4: 557         B4: 544
       ↓
     A5: 559 (gated)
```

D3 (the doc-apply multi-OTA) is independent of every code stream and can be picked up by Don at any moment — recommend running it first on Terminal D so the new SoT docs are in place before later prompts cat them.

---

## Coordination protocol

Each prompt file ends with one of three coordination footers per `build-execution.md`:

- `OK to continue to <NEXT-PROMPT>.md` — chains forward
- `STOP until Terminal X completes <TICKET-KEY>` — gates on another terminal
- `Independent — no downstream dependency` — terminal closes after this prompt

Each prompt also carries one of two commit gates:

- "I have been instructed to commit. Do you approve? (yes / no)"
- "I have been instructed NOT to commit. The next prompt will commit our combined work."

For this build, **every prompt commits its own work** (no deferred commits). This minimizes the blast radius if any individual ticket fails verification. The single exception is that the multi-OTA prompts (A2 and D3) commit all of their bundled tickets in one transaction.

---

## Prompt file inventory

All prompt files live in `/mnt/user-data/outputs/` after this session. Filenames:

```
00-DEPLOYMENT-PLAN.md           ← this file
A1-OTA-558.md
A2-OTA-549-509-510.md           ← multi-OTA
A3-OTA-515.md
A4-OTA-557.md
A5-OTA-559.md
B1-OTA-538.md
B2-OTA-543.md
B3-OTA-541.md
B4-OTA-544.md
C1-OTA-536.md
C2-OTA-537.md
D1-OTA-539.md
D2-OTA-546.md
D3-OTA-584-585-586-587-588-595.md  ← multi-OTA
```

---

## Don's checklist before kickoff

- [ ] Confirm **OTA-516** status. If not Production Deployed, A5 (OTA-559) holds.
- [ ] Decide **OTA-546 persistence model** (Option A / B / C from the ticket). D2 cannot start until this decision is in.
- [ ] Confirm Terminal C's C1 (OTA-536) is on the schedule before Terminal D's D1 (OTA-539) starts — both touch provider plumbing in adjacent code paths. If D wants to start sooner, run D2 or D3 first.
- [ ] Decide whether to run all five **profile-level subtasks** (Track 1) before or after the code build. Recommend before — gets the new conventions live so code-work prompts can reference them.
- [ ] Confirm dev environment topology — several B-track stories touch `main.py` lifespan; if dev is currently down or in a weird state, fix that first.
- [ ] If running Claude in Chrome for any browser-based smoke testing during this build, **enable the extension first** (chrome://extensions, toggle on), and **disable it at the end of the session**.

---

## Failure-recovery protocol

If any prompt fails verification on any terminal:

1. That terminal stops at the failed prompt and reports the failure.
2. Don notifies any downstream terminals waiting on that ticket (Terminal C's C2 explicitly waits on Terminal A's A2 — that's the only cross-terminal hard gate in this plan).
3. Claude Web (separate context) diagnoses, issues a fix prompt, and resumes the chain.

The terminal does not auto-retry. The terminal does not roll back. Both are Don's calls per `build-execution.md` Part 3.
