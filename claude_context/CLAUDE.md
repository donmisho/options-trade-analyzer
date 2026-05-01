# CLAUDE.md

**Last Updated:** 2026-04-30 23:55 UTC
**Instigating Ticket:** OTA-535 (Prompt Writing Convention added — addresses the gap that committed `claude_context/` SoT docs are NOT auto-loaded by Claude Code at session start)

---

This file provides guidance to Claude Code (claude.ai/code) when working in this repository. It is the *how* document — how to start a session, how to use Jira, how to commit, how to deploy, what house style to follow.

The repo has multiple source-of-truth documents, each with a single subject. See **Source of Truth Documents** below for the full inventory. Conflict precedence: each document is authoritative within its own subject. Business rules in particular live exclusively in `business-rules.md`; if any other doc states a business rule, it is wrong and must be removed.

---

## Source of Truth Documents

Each document has one subject. Don't duplicate content across documents — reference instead. When updating any of these, update the `Last Updated` header and add a change log entry referencing the OTA ticket that drove the change.

All source-of-truth documents live in `claude_context/` and are committed to git. The repo's root `CLAUDE.md` (which Claude Code auto-loads at session start) is intentionally not committed — it stays local. **This means Claude Code does NOT auto-load any of the docs in `claude_context/` at session start.** They are read on-demand only, either because a Claude Code prompt explicitly instructs `cat claude_context/<file>.md`, or because the prompt embeds the relevant excerpt directly. See the **Prompt Writing Convention** section below for how this is enforced.

| Document | Path | Subject | Read When |
|---|---|---|---|
| `CLAUDE.md` (this file) | `claude_context/CLAUDE.md` | Workflow, session protocol, Jira mechanics, dev environment, deploy procedures, house style, prompt-writing convention | Every session — must be cat'd at session start |
| `architecture-plan.md` | `claude_context/architecture-plan.md` | Architectural patterns, system structure, data models, agent inventory, deployment architecture, phase history | Before any architectural change; reference whenever in doubt about pattern intent |
| `business-rules.md` | `claude_context/business-rules.md` | Scoring formulas, hard gates, PoP computation, health grade math, position lifecycle states, signal TTLs, validation baseline, cost guardrails | Before any change to scoring, gates, P&L, health, or any computed business field |
| `UI-GUIDANCE.md` | `claude_context/UI-GUIDANCE.md` | UI visual contract — layout decisions, component patterns, color tokens, typography, dashboard rules | Before any frontend work |
| `auth-process.md` | `claude_context/auth-process.md` | Auth flows end-to-end — BFF OIDC, session lifecycle, PKCE, CSRF, token refresh, identity provider configuration | Before any auth, identity, or session work |
| `SCHWAB-LOGIN-PROCESS.md` | `claude_context/SCHWAB-LOGIN-PROCESS.md` | Schwab OAuth flow specifically — authorization code flow, token manager behavior, refresh handling, dev cert requirements | Before any Schwab OAuth, broker integration, or token-manager work |
| `azure-naming-conventions.md` | `claude_context/azure-naming-conventions.md` | Azure resource naming standards, tagging conventions, environment suffixes | Before creating any Azure resource |

`project-hierarchy.md` (formerly `claude_context/project-hierarchy.md`) is being merged into `architecture-plan.md` and will be deleted from the repo. Until the merge ships, treat `architecture-plan.md` as the forward-looking truth and `project-hierarchy.md` as a historical reference only.

---

## Prompt Writing Convention (Claude Web → Claude Code)

Because the repo's committed source-of-truth docs in `claude_context/` are NOT auto-loaded by Claude Code at session start, **every Claude Code prompt that Claude Web writes must include the SoT context the Story requires**. There are two complementary mechanisms; both are required for any prompt that touches architectural patterns, business rules, or domain-specific knowledge.

### Mechanism A — Required Reading at Top of Every Prompt

Every prompt `.md` file Claude Web writes must begin with an explicit `cat` instruction listing the SoT files Claude Code must read before any code changes. Use full repo paths.

```markdown
## Required reading
Before any code changes:

cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md   # if scoring/gates/computation
cat claude_context/UI-GUIDANCE.md       # if frontend work
cat claude_context/auth-process.md      # if auth/identity/session work
```

Per-domain required-reading combinations:

| Story domain | Always cat | Plus |
|---|---|---|
| Architecture / patterns / providers | CLAUDE.md, architecture-plan.md | — |
| Scoring / gates / health / P&L | CLAUDE.md, architecture-plan.md, business-rules.md | — |
| Frontend / components / styling | CLAUDE.md, UI-GUIDANCE.md | architecture-plan.md if cross-cutting |
| Auth / identity / session / BFF | CLAUDE.md, auth-process.md | architecture-plan.md (Pattern 6) |
| Schwab / broker / market data | CLAUDE.md, SCHWAB-LOGIN-PROCESS.md | architecture-plan.md (Pattern 1, § 3) |
| Azure resource changes | CLAUDE.md, azure-naming-conventions.md | architecture-plan.md (§ 7) |
| Deploy / migration / observability | CLAUDE.md, architecture-plan.md (§ 6, § 7) | — |

### Mechanism B — Embedded Relevant Context Block

Every prompt must also include a "Relevant Context" block that copy-pastes the specific decisions, formulas, invariants, or rules from the SoT docs that govern THIS Story's implementation. Each item cites its source doc + section so Claude Code can verify.

This block is necessary because:
- Claude Code may skim large cat'd files under token pressure
- Embedded context survives token-budget compression more reliably than referenced context
- Giving Claude Code the exact rule it must enforce eliminates "reasoning from stale memory" failures

```markdown
## Relevant Context — Do Not Deviate Without Escalation

Source: architecture-plan.md § 2 (Data Isolation Invariant)
Rule: Every CRUD endpoint that takes a resource ID must filter by user_id.
Cross-user attempts return 404 (not 403, to avoid leaking existence).

Source: architecture-plan.md § 4 (AI Adapter Contract)
Contract: chat(system, user, max_tokens) -> {text, input_tokens,
output_tokens, model, provider}. Both FoundryAdapter and AnthropicAdapter
must implement this exact dict shape.

Source: business-rules.md § Cost Guardrails
Rule: Any refresh that triggers more than one Claude API call must show
a confirmation dialog before firing.

Source: CLAUDE.md § House Style Rules
Rule: Date format mm-dd-yyyy via formatDate(); no $ prefix on monetary;
##.00 monetary precision; 0–100 score scale ##.00 everywhere.
```

The embedded items must be specific enough that Claude Code does not need to re-derive the rule from prose. If the rule is conditional or has edge cases, embed those too.

### Mechanism A + B Together — Why Both

- **Mechanism A** ensures the canonical doc is in Claude Code's context window for verification of any embedded claim and for adjacent context Claude Code might need.
- **Mechanism B** ensures the critical rules are unmissable even if Claude Code's attention is elsewhere.

If only Mechanism A is used, Claude Code may skim the file and miss the relevant section. If only Mechanism B is used, Claude Code has no way to verify the embedded text against the canonical source or to find adjacent rules.

### Prompt File Template

Every Claude Code prompt `.md` file follows this structure:

```markdown
# OTA-XXX — [Story title]

## Required reading
[Mechanism A — explicit cat commands per the per-domain table]

## Relevant Context — Do Not Deviate Without Escalation
[Mechanism B — embedded rules with source citations]

## Scope
[The actual work this prompt does]

## Acceptance criteria
[Verifiable outcomes]

## Out of scope
[Boundaries to prevent scope creep]

## Verification steps
[How Claude Code confirms the work is correct before commit]

## Commit message template
OTA-XXX [other-tickets] feat: <one-line summary>
```

### When Embedded Context Goes Stale

Embedded context is a snapshot. If `architecture-plan.md` or `business-rules.md` changes, embedded excerpts in past prompts do not auto-update. This is acceptable because:
- Past prompts that have already shipped don't need updating
- Active prompts in flight that span doc changes get re-issued

The risk is a long-running prompt drafted against an older doc version. Mitigation: Mechanism A requires Claude Code to also read the canonical file, so if the embedded snippet contradicts the current source, Claude Code surfaces the contradiction and escalates to Don rather than proceeding.

### Standing Reminder for Claude Code

When Claude Code receives a prompt that does NOT include both Mechanisms A and B, it should pause and request the missing context before making code changes. This is the single most common failure mode for stale-knowledge errors.

---

## Product Roadmap (OTAR)

Strategic prioritization for the OTA project lives in a separate **Jira Product Discovery (JPD)** project: **OTA Roadmap (key: OTAR)**. The OTAR project holds Roadmap Categories — high-level groupings that capture business context, target outcomes, and scope before any work becomes a delivery Idea in the OTA project.

**The relationship between projects:**

- **OTAR** (Product Discovery) — *what and why*. Holds Categories (Idea issue type) representing strategic themes. Each Category has business context, target outcome, scope, and named Umbrella Epics.
- **OTA** (Software Project) — *how and when*. Holds Epics, Stories, and Subtasks representing actual delivery work.
- **Polaris work item links** connect OTA Epics to their umbrella OTAR Category. **Every OTA Epic should link to exactly one OTAR Category.** The link is bidirectional and visible from both sides.

This structure exists because earlier phase-based grouping (Phase 2.x, 3.3.x, Sprint N) created friction — those numbers mapped to neither Jira hierarchy nor a meaningful business unit, and they bred cross-talk every time work was prioritized.

**Active OTAR Categories (as of last update):**

| Key | Category | Scope summary |
|---|---|---|
| OTAR-7 | Trade Evaluation Quality | Hard gates, scoring weights, narrative grounding, validation reviews. Highest-impact category. |
| OTAR-8 | Trade-to-Strategy Journey (Path B) | From a found trade, identify best-fit strategy lens. Trade detail Sections A–E, Follow/Take Position. |
| OTAR-9 | Strategy-to-Trade Journey (Path A) | From a chosen strategy, find conforming trades. Strategy page, config drawer, parameter wiring. |
| OTAR-10 | Position Management & Monitoring | Position lifecycle, daily monitoring, health grades, Schwab portfolio integration. |
| OTAR-11 | Trade Discovery & Scanning | Multi-symbol scan, named watchlists, smart symbol search. |
| OTAR-12 | Live Trade Execution | Schwab order entry, OCO brackets, conditional stops, post-fill reconciliation. |
| OTAR-15 | Identity & Access | BFF OIDC, multi-IdP registry, External Services connection screen, future Identity Agent. |
| OTAR-16 | Insights & Agentic Platform | Insight Engine, multi-agent orchestration, Agent 365 governance, A2A protocol. |
| OTAR-19 | Data Sources & Market Intelligence | Earnings calendar, OpenBB, social sentiment, fundamentals, catalyst calendars. |
| OTAR-21 | Backtesting & Strategy Validation | Polygon.io historical data, backtest engine, 12-security validation set. |
| OTAR-23 | UX Foundation & Design System | Experience Framework v3 contract, shared components, formatting rules, mockup-driven design. |
| OTAR-24 | Platform Architecture, Operations, and Observability | OTel + Log Analytics, App Service ops, deployment discipline, documentation governance. |

(OTAR-1 is the seed template and OTAR-13 is a duplicate of OTAR-16; both are scheduled for archive.)

**When creating a new OTA Epic:**

1. Identify which OTAR Category best fits.
2. Create the OTA Epic.
3. Create a Polaris work item link from the new Epic to the chosen OTAR Category.
4. If no existing OTAR Category fits, talk to Don before creating a new Category — Categories are deliberate strategic groupings, not catch-alls.

**OTAR URL:** `https://tmtctech-team.atlassian.net/jira/polaris/projects/OTAR`

---

## Session Start Protocol

### Required every session

1. Ask Don: *"Should I review the current Jira plan for the OTA project before we start? (Project: tmtctech-team.atlassian.net, OTA project)"* Wait for yes/no.
2. If yes, pull open issues from the OTA project. Filter for `status != "Production Deployed" AND status != Cancelled`, ordered by status ascending so Schedule items appear before In Progress items. Use the List view, not the Board view.
3. `cat claude_context/CLAUDE.md` — full read, every session, no exceptions. The repo's root `CLAUDE.md` (auto-loaded by Claude Code) may be stale; the canonical version lives in `claude_context/`.
4. Before editing any file, `cat` the actual current contents. Never rely on memory of "what the file looked like last time."

### Reading SoT docs beyond CLAUDE.md

Other source-of-truth documents (`architecture-plan.md`, `business-rules.md`, `UI-GUIDANCE.md`, `auth-process.md`, `SCHWAB-LOGIN-PROCESS.md`, `azure-naming-conventions.md`) are read on-demand based on the Story domain. The expectation is that the Claude Code prompt itself instructs which docs to read (per the **Prompt Writing Convention** above) and embeds the relevant context.

If a session begins without a prompt that specifies required reading, and the work touches an area governed by SoT docs, Claude Code should request the missing required-reading list and embedded context from Don rather than proceeding from session-start memory alone.

The OTA project does not use sprints. List view URL: `https://tmtctech-team.atlassian.net/jira/software/projects/OTA/list`.

**Atlassian MCP availability:** The Atlassian MCP connector intermittently fails to surface in Claude Code's `tool_search` (tracked under OTA-249). When it surfaces, use it directly. When it doesn't, use the REST API workaround documented below.

---

## Workflow Phases

The OTA project uses a 6-stage workflow plus one terminal cancellation state. This is *phases*, not sprints.

| # | Status | Status ID | Category | Who Acts | Meaning |
|---|--------|-----------|----------|----------|---------|
| 0 | Idea | 10000 | To Do | Product Owner | Raw backlog item, not yet committed to |
| 1 | Schedule | 10001 | To Do | Product Owner | Promoted — confirmed candidate for next work set |
| 2 | Write Story | 10002 | In Progress | Claude Web | Refining the Story description, requirements, scope |
| 3 | Write Prompt | 10003 | In Progress | Claude Web | Story complete; writing the Claude Code execution prompt |
| 4 | Code & Test Complete | 10004 | In Progress | Claude Code | Code committed and built; artifact ready to deploy. **Not yet in production.** |
| 5 | Production Deployed | 10157 | Done | Automation / manual override | Live in prod after manual deploy + smoke test + slot swap |
| C | Cancelled | 10158 | Done | Product Owner / Claude Web | Work absorbed elsewhere, superseded, or no longer needed. **Not deployed; intentionally not done.** |

**Transition ID reference (for REST API and MCP calls):**

| Transition Name | From | To | ID |
|---|---|---|---|
| Idea | Any | Idea | 11 |
| To Do | Any | Schedule | 21 |
| In Progress | Any | Write Story | 31 |
| Write Prompt | Any | Write Prompt | 41 |
| Done | Any | Code & Test Complete | 51 |
| Claude Code Build | Write Prompt | Code & Test Complete | 6 |
| Override | Code & Test Complete | Production Deployed | 9 |
| Cancel (from Idea) | Idea | Cancelled | 12 |
| cancel (from Write Prompt or Write Story) | Write Prompt / Write Story | Cancelled | 14 |

The Override transition exists for cases where a ticket was deployed but the auto-transition didn't fire. Cancellation requires the source-status-specific transition (12 from Idea, 14 from Write Prompt or Write Story). If a Cancel transition is missing from a status, it is added in the workflow editor — do not work around with reverse-then-cancel.

---

## Jira Issue Hierarchy — Strict

The OTA project uses a strict 3-level hierarchy. Every API-created ticket must respect this structure or it will not appear correctly on the board.

- Stories and Subtasks are the only levels that represent actionable build work.
- Subtasks must always be parented to a Story or Feature — never directly to an Epic.
- Stories and Features must always be parented to an Epic.
- Never create a Feature as a child of another Feature.
- Issue type IDs: Epic = 10001, Feature = 10003, Story = 10214, Subtask = 10002.

**Before creating any ticket via API:**

1. Identify the correct Epic.
2. Identify or create the correct Feature parent under that Epic (or use a Story under the Epic if no Feature is appropriate).
3. Create the implementation ticket as a Subtask under that Feature/Story (or as a Story directly under the Epic for Feature-sized work).

**Common Epic parents for reference:**

- OTA-4 — Phase 2.0.x
- OTA-8 — Dashboard work
- OTA-14 — Ongoing: Strategy Validation Reviews
- OTA-19 — DEV Housekeeping (bugs, hotfixes, dev process)
- OTA-236 — Development Workflow — Planning & Toolchain
- OTA-393 — Phase 2.11
- OTA-477 — Architecture Documentation Refresh
- OTA-507 — Ongoing: Trade Evaluation Anomaly Resolution
- OTA-511 — Deploy & Environment Operations

When in doubt about the correct Epic or Feature parent, ask Don before creating tickets.

---

## Jira REST API Workaround

When the Atlassian MCP tools are not surfaced by `tool_search`, use the REST API via curl. **Always ask Don before using this approach:** *"Should I use the Jira temporary solution (REST API via curl) for this?"* Wait for confirmation.

**Base URL:** `https://tmtctech-team.atlassian.net`
**Auth:** Basic auth with Don's Atlassian email + API token from environment variable `$JIRA_API_TOKEN`. Don's email available as `$JIRA_EMAIL`.
**Project key:** `OTA`
**Cloud ID:** `53c395d7-bac7-4a5f-baf2-ee2b0f375a2b`

The Jira API token must be fetched from Azure Key Vault (`options-analyzer` vault, secret name `jira-api-token`). Never assume it's in an env var without verifying.

**Create an issue:**

```bash
curl -s -X POST \
  "https://tmtctech-team.atlassian.net/rest/api/3/issue" \
  -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$JIRA_API_TOKEN" | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": { "key": "OTA" },
      "summary": "Issue summary here",
      "issuetype": { "id": "10214" },
      "description": {
        "type": "doc",
        "version": 1,
        "content": [
          {
            "type": "paragraph",
            "content": [
              { "type": "text", "text": "Description text here" }
            ]
          }
        ]
      },
      "parent": { "key": "OTA-XXX" },
      "labels": ["framework-portable"]
    }
  }'
```

**Set parent:** Pass `"parent": { "key": "OTA-XXX" }` as a direct named field in the create payload. Never inside `additional_fields` — that path silently fails.

**Description format:** Atlassian Document Format (ADF) only when using REST. The MCP tools accept `contentFormat: "markdown"` which is much easier; prefer the MCP path when available.

**Transition an issue:**

```bash
curl -s -X POST \
  "https://tmtctech-team.atlassian.net/rest/api/3/issue/OTA-XXX/transitions" \
  -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$JIRA_API_TOKEN" | base64)" \
  -H "Content-Type: application/json" \
  -d '{ "transition": { "id": "21" } }'
```

After creating issues via the REST API, always report the created issue keys back to Don for verification.

---

## Commit Message Convention + Jira Automation

A Jira automation rule fires on every commit to main:

- **Trigger:** Commit created
- **Condition:** Status not in (Cancelled, Production Deployed, Code & Test Complete)
- **Action:** Transition referenced work items to Code & Test Complete (status 10004)

**Commit message format:** Always prefix with all OTA ticket numbers addressed in the session.

```
OTA-152 OTA-153 feat: implement StrategyScorecard and SecurityDashboard
```

The automation only fires for ticket numbers present in the commit message. Always include every ticket number addressed in the session, not just the primary one.

**What "Code & Test Complete" means under the slot-swap deploy model:** the artifact has been built and is ready to deploy. It is **not** in production. The transition to Production Deployed (status 10157) happens after a successful manual deploy, smoke test, and staging-to-prod slot swap. Tickets sit in Code & Test Complete until that swap fires.

Single-change deployment discipline still applies, but the blast radius is smaller now because the staging slot catches broken deploys before the swap.

---

## Working Patterns

### Parallel Session Strategy

Claude Web (this context) plans, groups, and writes Claude Code prompts as `.md` files. Don opens parallel Claude Code windows and runs them simultaneously when the work is independent.

Two streams are safe to parallelize when:

- They edit disjoint files (no overlapping write paths)
- They don't share imports that one stream is rewriting
- They don't both touch the same SKILL.md
- They don't both modify `main.py`, `database.py`, or `client.js`

When streams overlap on any of those, sequence them: finish stream A, commit, then start stream B against the new HEAD. Two streams editing the same file in parallel produces merge conflicts that take longer to resolve than the time saved by parallelism.

The standard rhythm is: Claude Web writes 2–4 prompt `.md` files in one planning session → Don runs them in parallel terminals → each commits with the OTA-prefixed message → Claude Web reviews the commits and either ships or queues follow-up work.

### Prompt File Conventions

Claude Code prompt files follow a shared shape:

- `allowedTools` YAML frontmatter (`Bash, Read, Write, Edit` with wildcards as needed)
- Always begin with `cat CLAUDE.md` and `cat` of any other targeted source files before any change
- Explicit file lists, acceptance criteria with specific values, verification steps
- Commit message template at the bottom with OTA ticket numbers
- Temporary diagnostic log lines explicitly flagged for removal after confirmation
- For Jira-touching prompts: fetch `JIRA_API_TOKEN` from Azure Key Vault — never assume the env var

---

## Development Environment

### Backend (FastAPI)

```bash
# Setup
python -m venv venv
venv\Scripts\activate          # Windows (PowerShell)
source venv/bin/activate       # Unix
pip install -r requirements.txt

# Run with HTTPS (required for Schwab OAuth + dev parity with prod)
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000

# API docs: https://127.0.0.1:8000/docs
# Health:   https://127.0.0.1:8000/health
```

The venv directory is `venv` (not `.venv`) — always include the full `cd` and activate commands in prompts.

For self-signed cert generation, use Python's `cryptography` library, not OpenSSL CLI. PowerShell on Windows handles backtick line continuation poorly with OpenSSL.

### Frontend (React + Vite)

```bash
cd web
npm install
npm run dev     # Vite dev server (HTTPS) with proxy to FastAPI backend
npm run build   # Production build
npm run lint    # ESLint
```

The Vite dev server runs on `https://localhost:5173` and proxies `/api` requests to `https://127.0.0.1:8000`. Both use self-signed certificates in development.

### Testing

```bash
pytest                          # All tests
pytest tests/test_something.py  # Specific file
pytest --cov=app                # With coverage
```

Test infrastructure today is minimal — most validation happens via Swagger UI at `/docs`. Auth, provider, and route coverage is a known gap tracked under the Architecture Optimization epic.

### Zombie Process Warning (Windows)

Before restarting the backend, always kill existing Python and uvicorn processes first:

```powershell
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
netstat -ano | findstr ":8000"
```

Windows does not always release port 8000 cleanly. A zombie uvicorn process will answer requests silently, making new route registrations invisible and causing confusing 404s.

---

## Environments

| Environment | Frontend Origin | Backend Origin | App Service | DB | Notes |
|---|---|---|---|---|---|
| Local dev | `https://localhost:5173` (Vite) | `https://127.0.0.1:8000` (FastAPI) | n/a | Shared Azure SQL via Key Vault | Self-signed certs, full HTTPS |
| Dev | `oa-dev.tmtctech.ai` | Same origin via SWA → App Service proxy | `options-analyzer-api-dev` (B1) | Shared Azure SQL | MSI + Key Vault, mirrors prod topology |
| Prod | `oa.tmtctech.ai` | Same origin via SWA → App Service proxy | `options-analyzer-api` (B1) with `staging` slot | Production Azure SQL | MSI + Key Vault, slot-swap deploy gate |

The frontend is hosted on Azure Static Web Apps for CDN and edge routing. The backend is a separate Azure App Service. SWA proxies `/api/*` to the App Service backend so the browser sees one origin per environment. This is the deliberate architecture; see `architecture-plan.md` Pattern 7 for the rationale.

---

## Deployment Workflow

The deploy model is **manual-trigger with pre-prod slot gate**. Pushing to `main` builds an artifact but does not deploy. Deploys are explicit, tokenized, and gated by a smoke test against the staging slot.

| Step | Trigger | Workflow | Confirmation Token | Effect |
|---|---|---|---|---|
| 1 — Build | `git push origin main` | `build-on-push.yml` | none | Builds and uploads artifact only. No deploy. |
| 2 — Deploy to staging slot | Manual via GitHub Actions UI | `deploy-to-prod.yml` | `confirm_deploy=DEPLOY` | Deploys artifact to `staging` slot, runs smoke test, pauses |
| 3 — Promote staging to prod | Manual via GitHub Actions UI | `swap-staging-to-prod.yml` | `confirm_swap=SWAP` | Slot swap: staging becomes prod, prod becomes staging |
| 4 — Emergency rollback | Manual via GitHub Actions UI | `rollback-prod.yml` | `confirm_rollback=ROLLBACK` | Re-swap (or redeploy a prior `build_run_id` artifact) |

Dev deploy uses `deploy-to-dev.yml` with `confirm_deploy=DEPLOY-DEV` and no slot. Dev is a single-slot environment; if dev breaks, it gets fixed forward, not rolled back.

The staging and prod slots share the same Azure SQL database. This forces **expand/contract** discipline on every schema change: additive migrations only, with column drops deferred to a follow-up after prod has been stable on the new code. Deferred schema cleanups are tracked perpetually under OTA-523 (Database Contract Actions).

---

## Post-Build QA Gate

At the end of every build run — before marking any ticket as done or creating a PR — assess the scope of changes and recommend a QA level.

### QA Levels

**Level 0 — No QA needed:**

- Cosmetic fixes: typos, copy changes, comment updates
- Documentation-only changes
- Changes to files outside `app/` and `web/src/`
- Just commit and move on.

**Level 1 — Targeted validation:**

- Changes to a single component's styling or layout
- Token value changes in `web/src/styles/tokens.js`
- Changes scoped to one ticket's UI
- Run the UX agent against only the affected ticket(s).

**Level 2 — Full regression:**

- Changes to `app/services/` (vertical_engine, filter_engine, greeks, P&L calculators)
- Changes that touch multiple components
- Changes to provider adapters or SKILL.md files
- Changes to auth, database models, or SecretsManager
- Any build run that touched 3+ tickets across parallel streams
- Run both QA agents: full UX sweep of all Done tickets plus full 64-config data matrix.

### Before committing, state your recommendation:

```
Build complete. Changes: [list files touched]
Recommended QA level: [0/1/2]
Reason: [one sentence]
Run QA? [waiting for your answer]
```

The human approves, adjusts, or skips. Never run QA without asking. Never skip the recommendation — always state the level even if you expect Level 0.

### Regression Runs

When running Level 2 QA, compare current results against the baseline files in `agents/qa-context/`. A test that failed in the previous run and still fails is a known issue. A test that passed in the previous run and now fails is a **REGRESSION** — mark severity BLOCKER and escalate immediately to Teams.

After a clean Level 2 run where all tests pass, snapshot the results as the new baseline:

- Copy UX results to `agents/qa-context/baseline-ux.json`
- Copy data results to `agents/qa-context/baseline-data.json`

### Keeping QA Configuration in Sync

If you modify the QA gate levels, thresholds, or agent behavior described in this section, also update the corresponding sections in:

- `agents/qa-ux/CLAUDE.md`
- `agents/qa-data/CLAUDE.md`
- `agents/fe-dev/CLAUDE.md`
- `agents/be-dev/CLAUDE.md`

All five files must stay in sync. When in doubt, read the agent CLAUDE.md files to verify consistency before making changes.

---

## Chrome Extension Notes

The **"Allow CORS: Access-Control-Allow-Origin"** Chrome extension is **disabled by default**. It may be needed for local development when testing cross-origin API calls from the browser.

- **Default state:** Disabled
- **When to enable:** Only if you encounter CORS errors during browser-based local dev testing. Ask Don to enable it before proceeding.
- **After testing:** Ask Don to disable it again.
- **Why it matters:** When enabled, it blocks the Claude in Chrome extension from connecting, which breaks Claude Web's browser automation tools.

The Claude in Chrome browser extension is also disabled by default. If a session involves browser tasks, ask Don to enable it first (`chrome://extensions`, toggle on). At the end of that session, ask him to disable it again.

---

## Architecture Summary

Full details in `architecture-plan.md`. Seven foundational patterns:

1. **Provider Adapter Pattern** — every external source (market data, AI, brokerage, signals) implements a standard interface. Provider lifecycle states (Active / Inactive / Deprecated / Removed) are first-class. Schwab is the sole Active market data provider today; Tradier was Removed via OTA-524.
2. **Skill-Driven Prompt Architecture** — every AI prompt lives in a `SKILL.md` file under `app/skills/{skill_name}/SKILL.md`, loaded via `app/skills/skill_loader.py`. No prompts hardcoded in Python or React.
3. **Two-Track Observability** — every AI invocation produces both an OpenTelemetry trace into Application Insights and a permanent business record in the `agent_run_log` SQL table, linked by `trace_id`.
4. **Unified Position Model** — paper and live positions share one schema. Distinguishing fields are `source` (PAPER | LIVE) and `status` (FOLLOWING | LIVE | CLOSED). All monitoring, scoring, and analytics work identically for both.
5. **Generic Insight Engine** — domain-agnostic detect → score → communicate pattern. Domain-specific behavior lives in per-domain `SKILL.md` files. Designed for OTA + future TMTC apps (manufacturing, customer health) without forking.
6. **Backend-for-Frontend Identity** — FastAPI is the OIDC confidential client. Browser holds an HttpOnly session cookie, never an identity token. PKCE + signed state + Fernet-encrypted server-side session storage + CSRF middleware.
7. **Two Deployables, One Logical App, One Origin** — frontend on Azure Static Web Apps for CDN/routing, backend on Azure App Service for FastAPI. SWA proxies `/api/*` to App Service so the browser sees one origin per environment. Auth domain is unified.

**Provider routing rule:** Never hardcode a provider name in API routes. Always use `_get_provider()` or `settings.default_market_data_provider`.

---

## House Style Rules

- **Date format:** Always `mm-dd-yyyy`. With time: `mm-dd-yyyy hh:mm`. Use `formatDate()` from `web/src/utils/formatDate.js`. No locale strings, no other date formatting allowed.
- **Context document timestamps:** When any document in `claude_context/` or any source-of-truth markdown (CLAUDE.md, architecture-plan.md, business-rules.md, UI-GUIDANCE.md, auth-process.md) is modified, update the header `Last Updated` field in the format `yyyy-mm-dd hh:mm UTC` and add an entry to the change log at the bottom of the file. The change log entry must reference the OTA ticket that drove the change.
- **No `$` in UI:** Display `567.23` not `$567.23`. Currency context is implied throughout the app.
- **Monetary display:** `##.00` via `.toFixed(2)`.
- **Probabilities:** `##.00%`.
- **IV rank:** `##.00%`.
- **Config percentages:** `##%` (no decimals).
- **Scores (0–100 scale):** `##.00` everywhere — inline row, expansion panel, total row. Consistent format is required.
- **Health pips:** Each pip is its own column in the table — never grouped in a single cell.
- **`getHealthPips` signature:** Always `getHealthPips(trade, systemVars)`.
- **Schwab index symbols:** Use the `apiSymbol` field for mapping (e.g. `.INX` → `$SPX`).
- **Provider routing:** Never hardcode a provider name. Always use `_get_provider()` or settings.
- **Prompts in SKILL.md:** Never hardcode prompts in Python or React. Always load via `skill_loader.py`.
- **Position source labels:** Display "Paper" and "Live" (not "PAPER" / "LIVE") in UI.
- **Health grades:** Display as letter (A/B/C/D/F) with color: A=green, B=teal, C=yellow, D=orange, F=red.
- **Trade type display names:** Title case, no underscores. "Bear Put Debit" not "BEAR_PUT_DEBIT".
- **Bull/Bear trade badges:** Bull = green, Bear = red.
- **Strategy names:** Display in their assigned strategy color. Claude advice badge: white outlined (`rgba(255,255,255,0.06)` background, `rgba(255,255,255,0.35)` border) — never purple.
- **Buttons:** Sized to content, never full-width unless explicitly designed that way. Always have a visible border or background in default state.
- **`var(--bg2)` (#161b22):** Restricted to filter bars, QuoteBar, and pill badge backgrounds only. Never on table rows, headers, or expansion panels.
- **Dark theme CSS variables only:** Never inline hex colors. All color values come from `web/src/styles/tokens.js`.
- **Claude API cost guardrail:** Canonical rules in `business-rules.md` → Cost Guardrails. Summary: refresh actions that trigger more than one Claude API call must show a confirmation dialog before firing; single-call refreshes run without confirmation; one daily auto-refresh per position post-market-close; no page-load or timer-driven Claude calls. UI implementation pattern (`RefreshConfirmDialog.jsx`) is documented in `UI-GUIDANCE.md`.

---

## Provider Lifecycle (Quick Reference)

Every external data provider has one of four lifecycle states. Full state machine in `architecture-plan.md` under Pattern 1.

- **Active** — registered in factory, live credentials in Key Vault, selectable at runtime, used by at least one code path
- **Inactive** — registered in factory with `state: inactive`, no live code path routes through it, reactivation is a config flip
- **Deprecated** — in codebase but flagged not for new use, with a documented end-date
- **Removed** — gone from codebase entirely, Key Vault credentials cleaned up; re-adding requires a fresh adapter Story

Schwab is the sole Active market data provider today. Tradier was Removed via OTA-524. Provider state changes require an explicit Story; "not currently used" does not imply Removed.

---

## Active Cleanup Items

A multi-stream architecture cleanup is in flight under the **Architecture Optimization (Framework v1) Epic** (OTA-535) which links to OTAR-24 (Platform Architecture) and OTAR-27 (TMTC Application Framework). The Epic contains 12 cluster Stories (OTA-536 through OTA-547) plus four reparented predecessor Stories (OTA-513, OTA-514, OTA-522, OTA-525). Drift items being actively addressed include the dual AI stack, MSAL bridge retirement, prompt migration to SKILL.md, route renames (`agent_routes` / `agents_routes`), dead frontend components, ProviderRegistry rename + lifecycle states wiring, AI adapter contract formalization, data isolation invariant audit, resource shutdown discipline, schema migration tooling, and the Opus-review-caught security/leak fixes.

When working on anything that touches these areas, check the Architecture Optimization Epic for in-flight or planned work to avoid stepping on a parallel stream.

---

## Known Limitations

- No backend test coverage for auth flows, providers, or routes (analysis-layer tests exist; auth/provider/route gap is tracked in the Architecture Optimization Epic)
- MCP integration (Phase 4) not started
- Live trading execution (Phase 5) not started — `/positions/take` records intent only, not wired to Schwab order entry
- Social sentiment, fundamentals providers not yet built
- Iron condors section in TradesPage not yet built (coming soon placeholder)

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-04-30 23:55 UTC | OTA-535 | Added **Prompt Writing Convention** section to address Claude Code's session-start file-loading limitation. The repo's root `CLAUDE.md` (which Claude Code auto-loads) is intentionally not committed to git; the canonical source-of-truth docs live in `claude_context/` and are not auto-loaded. The new convention requires every Claude Code prompt that Claude Web writes to include both (A) explicit `cat` instructions for the SoT files relevant to the Story domain, and (B) an embedded "Relevant Context — Do Not Deviate" block that copy-pastes the specific decisions/rules governing the Story, each citing source doc + section. Updated Source of Truth Documents table to use full `claude_context/` paths and to note the auto-load limitation explicitly. Restructured Session Start Protocol to defer SoT-doc reading to per-prompt instruction rather than session-start cat lists, since Claude Code cannot reliably know which SoT docs to read without prompt-level direction. Per-domain required-reading combinations table added. Prompt file template documented. |
| 2026-04-30 23:30 UTC | OTA-535 | Updated placeholder references to real ticket numbers: Architecture Optimization Epic is OTA-535; new TMTC Application Framework OTAR Category is OTAR-27. Active Cleanup Items section now lists the 12 cluster Stories (OTA-536 through OTA-547) and four reparented predecessor Stories (OTA-513, OTA-514, OTA-522, OTA-525). |
| 2026-04-30 22:50 UTC | OTA-495 | Added Product Roadmap (OTAR) section after Source of Truth Documents. Captures the OTA ↔ OTAR relationship (OTAR is a separate Jira Product Discovery project holding strategic Categories; each OTA Epic links to one OTAR Category via Polaris work item links). Lists all 12 active OTAR Categories (OTAR-7 through OTAR-24) with one-line scope summaries. Documents the procedure for linking new Epics to their umbrella Category. This context was missing from the prior CLAUDE.md and only existed in past chat history; surfacing it here makes it permanent session context for Claude Code. |
| 2026-04-30 22:05 UTC | OTA-495 | Cost-guardrail rule extracted from House Style Rules to `business-rules.md` → Cost Guardrails. CLAUDE.md retains a one-line reference to the canonical rule with a pointer to UI-GUIDANCE.md for the implementation pattern. This is the first concrete extraction completing OTA-495's "no business rules in CLAUDE.md" objective; remaining extractions (display formatting precision rules, health grade letter/color mapping, position lifecycle states) are tracked under OTA-495's continued implementation work. |
| 2026-04-30 21:50 UTC | OTA-495 + Architecture Optimization Epic (OTA-535) | Added Source of Truth Documents section with full inventory: CLAUDE.md, architecture-plan.md, business-rules.md, UI-GUIDANCE.md, auth-process.md, SCHWAB-LOGIN-PROCESS.md, azure-naming-conventions.md. Established the principle that business rules live exclusively in business-rules.md and are not duplicated in any other doc. Restructured Session Start Protocol into "Required every session" (CLAUDE.md, ask about Jira, cat files before editing) and "Conditional reads" (UI-GUIDANCE / auth-process / SCHWAB-LOGIN-PROCESS / azure-naming-conventions / business-rules / architecture-plan, each with the trigger condition). Noted project-hierarchy.md as being merged into architecture-plan.md and slated for deletion. Created business-rules.md as a shell file under OTA-495 to enable the SoT inventory reference. |
| 2026-04-30 21:33 UTC | Architecture Optimization Epic (OTA-535) | Complete rewrite. Absorbs cancelled OTA-244 (parallel session strategy), OTA-246 (commit message convention), OTA-247 (session start checklist), OTA-474/475 (SWA deprecation — direction reversed; SWA stays), OTA-521 (dev/commit/deploy workflow). Adds workflow phase terminology (Idea → Schedule → Write Story → Write Prompt → Code & Test Complete → Production Deployed; Cancelled as terminal absorbed-state). Adds three-environment table (Local / Dev / Prod). Adds slot-swap deploy workflow with confirmation tokens. Adds provider lifecycle quick-reference (Active / Inactive / Deprecated / Removed; Schwab Active, Tradier Removed via OTA-524). Adds Architecture Summary referencing seven patterns with Pattern 7 reframed as "Two Deployables, One Logical App, One Origin." Adds House Style cost-guardrail and color-token rules. Removes stale references: OptionsTerminal, AskClaudePanel, SecurityDashboard, watchlist-localStorage-only, Tradier-as-fallback, Common Patterns recipes referencing retired components, Phase 2.9+/3.5+ markers in instructional sections. |
| 2026-04-11 22:00 | (prior) | Previous version. See git history for prior changelog. |
