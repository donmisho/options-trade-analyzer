# CLAUDE.md

**Last Updated:** 2026-05-19 UTC
**Governing Story:** OTA-573 (Documentation Governance — Project (OTA))

---

This file provides guidance to Claude Code when working in the OTA (Options Trade Analyzer) repository. It is the *how* document for OTA — how to start a session, how to use Jira, what house style to follow, where to find canonical project knowledge.

The repo has multiple source-of-truth documents, each with a single subject. See **Source of Truth Documents** below for the inventory. Conflict precedence: each document is authoritative within its own subject. Business rules in particular live exclusively in `business-rules.md`; if any other doc states a business rule, it is wrong and must be removed.

---

## Document Governance Rules

These rules are non-negotiable and apply to every SoT document referenced in this file:

- **Authority:** only Don and Claude Web modify SoT docs. Claude Code reads them but does not modify them unless explicitly instructed by a prompt. Self-initiated updates to SoT docs (including this file's Change Log) by Claude Code are forbidden.
- **Material change discipline:** material changes to any SoT doc are filed as Subtasks under the doc's governing Story (under the Documentation Governance Epic). A material change is one that alters scope, rules, structure, or interpretation — not typos, link fixes, or formatting cleanup.
- **Pre-commit verification:** before committing any change to this file, the editor (Don or Claude Web) verifies that the Workflow Phases table, Transition ID table, Issue Type IDs, and Issue Hierarchy section reflect live Jira reality. Stale values in these sections cause downstream automation failures.

---

## Profile-Level Conventions

Some conventions apply across all of Don's projects under this profile, not just OTA. They live as separate documents at the profile level:

| Document | Subject | Read When |
|---|---|---|
| `jira-structure.md` | Cross-project Jira hierarchy, issue types, parenting rules | Before any Jira API operation that creates or transitions issues |
| `prompt-style.md` | How Claude Web writes prompts for Claude Code (Mechanism A + B, prompt template) | Before authoring any Claude Code prompt |
| `build-execution.md` | Parallel session protocol, subagent orchestration, terminal coordination footer, explicit commit gate | Before authoring any Claude Code prompt; whenever multi-terminal work is planned |

The profile-level docs are governed by their own Documentation Governance Epic. OTA-specific overrides to any profile-level convention live in this file (CLAUDE.md), never in the profile-level doc itself.

---

## Source of Truth Documents (OTA)

Each document has one subject. Don't duplicate content across documents — reference instead. When updating any of these, update the `Last Updated` header and add a Change Log entry referencing the OTA ticket that drove the change.

All project SoT documents live in `claude_context/` and are committed to git. The repo's root `CLAUDE.md` (which Claude Code auto-loads at session start) is intentionally not committed — it stays local. **Claude Code does NOT auto-load any of the docs in `claude_context/` at session start.** They are read on-demand only, either because a Claude Code prompt explicitly instructs `cat claude_context/<file>.md`, or because the prompt embeds the relevant excerpt directly. See `prompt-style.md` for the convention.

| Document | Path | Subject | Read When |
|---|---|---|---|
| `CLAUDE.md` (this file) | `claude_context/CLAUDE.md` | OTA workflow, Jira mechanics, house style, governance rules | Every session — must be cat'd at session start |
| `architecture-plan.md` | `claude_context/architecture-plan.md` | Architectural patterns, system structure, data models, agent inventory, deployment architecture, phase history | Before any architectural change; reference whenever in doubt about pattern intent |
| `business-rules.md` | `claude_context/business-rules.md` | Scoring formulas, hard gates, PoP computation, health grade math, position lifecycle states, signal TTLs, validation baseline, cost guardrails | Before any change to scoring, gates, P&L, health, or any computed business field |
| `UI-GUIDANCE.md` | `claude_context/UI-GUIDANCE.md` | UI visual contract — layout decisions, component patterns, color tokens, typography, dashboard rules | Before any frontend work |
| `auth-process.md` | `claude_context/auth-process.md` | Auth flows end-to-end — BFF OIDC, session lifecycle, PKCE, CSRF, token refresh, identity provider configuration | Before any auth, identity, or session work |
| `bugfix.md` | `claude_context/bugfix.md` | Bug-fix session workflow — invocation phrase, per-item triage criteria, batched Subtask creation at session end, parent-ticket rollup format | When Don says "start a bug fix session" or any equivalent phrase |
| `SCHWAB-LOGIN-PROCESS.md` | `claude_context/SCHWAB-LOGIN-PROCESS.md` | Schwab OAuth flow specifically — authorization code flow, token manager behavior, refresh handling, dev cert requirements | Before any Schwab OAuth, broker integration, or token-manager work |
| `azure-naming-conventions.md` | `claude_context/azure-naming-conventions.md` | Azure resource naming standards, tagging conventions, environment suffixes | Before creating any Azure resource |
| `product-roadmap.md` | `claude_context/product-roadmap.md` | OTAR Categories, OTA ↔ OTAR linking procedure, strategic roadmap context | Before creating a new Epic or when prioritizing the queue |
| `development-environment.md` | `claude_context/development-environment.md` | Local dev setup, FastAPI/Vite startup, venv conventions, zombie-process handling, Schwab cert generation | When setting up dev or troubleshooting environment issues |
| `deployment-workflow.md` | `claude_context/deployment-workflow.md` | Slot-swap deploy workflow, GitHub Actions confirmation tokens, rollback, dev environment topology | Before deploying or when coordinating a release |

---

## Per-domain required reading

This table tells Claude Web which SoT docs to cat in a Claude Code prompt's Required Reading section, based on the Story's domain. The structure of Required Reading sections themselves is governed by `prompt-style.md`.

| Story domain | Always cat | Plus |
|---|---|---|
| Architecture / patterns / providers | CLAUDE.md, architecture-plan.md | — |
| Scoring / gates / health / P&L | CLAUDE.md, architecture-plan.md, business-rules.md | — |
| Frontend / components / styling | CLAUDE.md, UI-GUIDANCE.md | architecture-plan.md if cross-cutting |
| Auth / identity / session / BFF | CLAUDE.md, auth-process.md | architecture-plan.md (Pattern 6) |
| Schwab / broker / market data | CLAUDE.md, SCHWAB-LOGIN-PROCESS.md | architecture-plan.md (Pattern 1, § 3) |
| Azure resource changes | CLAUDE.md, azure-naming-conventions.md | architecture-plan.md (§ 7) |
| Deploy / migration / observability | CLAUDE.md, deployment-workflow.md, architecture-plan.md (§ 6, § 7) | — |
| Local dev environment troubleshooting | CLAUDE.md, development-environment.md | — |

Bug-fix sessions follow their own SoT-loading protocol; see `bugfix.md`.

---

## Session Start Protocol

1. `cat claude_context/CLAUDE.md` — full read, every session, no exceptions. The repo's root `CLAUDE.md` (auto-loaded by Claude Code) may be stale; the canonical version lives in `claude_context/`.
2. Before editing any file, `cat` the actual current contents. Never rely on memory of "what the file looked like last time."
3. Other SoT docs are read on-demand based on the prompt's Required Reading section. Claude Code does not pull the open Jira queue at session start — that context belongs to Claude Web during planning, not to Claude Code during execution.

If a session begins without a prompt that specifies Required Reading and the work touches an area governed by SoT docs, Claude Code requests the missing context from Don rather than proceeding from session-start memory alone.

**Atlassian MCP availability:** the Atlassian MCP connector intermittently fails to surface in Claude Code's `tool_search` (tracked under OTA-249). When it surfaces, use it directly. When it doesn't, use the REST API workaround documented below.

---

## Workflow Phases

The OTA project uses a 6-stage workflow plus one terminal cancellation state. This is *phases*, not sprints.

| # | Status | Status ID | Category | Who Acts | Meaning |
|---|--------|-----------|----------|----------|---------|
| 0 | Idea | 10000 | To Do | Don | Raw backlog item, not yet committed to |
| 1 | Schedule | 10001 | To Do | Don | Promoted — confirmed candidate for next work set |
| 2 | Write Story | 10002 | In Progress | Claude Web | Refining the Story description, requirements, scope |
| 3 | Write Prompt | 10003 | In Progress | Claude Web | Story complete; writing the Claude Code execution prompt |
| 4 | Prompt Written | 10228 | In Progress | Claude Web | Prompt MD file created and ready for Claude Code to execute |
| 5 | Code & Test Complete | 10004 | In Progress | Claude Code | Code committed and built; artifact ready to deploy. **Not yet in production.** |
| 6 | Production Deployed | 10157 | Done | Automation / manual override | Live in prod after manual deploy + smoke test + slot swap |
| C | Cancelled | 10158 | Done | Don / Automation | Work absorbed elsewhere, superseded, or no longer needed. **Not deployed; intentionally not done.** Tickets in Idea, Schedule, Write Story, or Write Prompt may be cancelled. Code & Test Complete tickets are not cancelled — they are deployed or rolled back via a follow-up Story. |

### Transition ID reference

| Transition Name | From | To | ID |
|---|---|---|---|
| Idea | Any | Idea | 11 |
| To Do | Any | Schedule | 21 |
| In Progress | Any | Write Story | 31 |
| Write Prompt | Any | Write Prompt | 41 |
| Done | Any | Code & Test Complete | 51 |
| MD File Created for Prompt | Write Prompt | Prompt Written | 16 |
| Override (to Prompt Written) | Any | Prompt Written | 17 |
| Claude Code Build | Write Prompt | Code & Test Complete | 6 |
| Deployed to Prod | Code & Test Complete | Production Deployed | 5 |
| Override | Code & Test Complete | Production Deployed | 10 |
| Cancel (from Idea) | Idea | Cancelled | 12 |
| Cancel (from Schedule) | Schedule | Cancelled | TBD — confirm in workflow editor; add if missing |
| Cancel (from Write Prompt or Write Story) | Write Prompt / Write Story | Cancelled | 14 |

The Override transition exists for cases where a ticket was deployed but the auto-transition didn't fire. Cancellation requires a source-status-specific transition. If a Cancel transition is missing from any of Idea, Schedule, Write Story, or Write Prompt, it is added in the workflow editor — do not work around with reverse-then-cancel.

The cross-project hierarchy and parenting rules are in profile-level `jira-structure.md`. The OTA-specific facts below override or supplement those rules.

---

## Jira Issue Hierarchy — OTA Project Specifics

The OTA project's Jira license does not include the Feature issue type. The hierarchy is therefore:

**Epic → Story → Subtask**

Bug is an issue type that may sit at either Story level (parented to an Epic, sibling to Stories) or Subtask level (parented to a Story).

This is a license-imposed compromise; if the license tier changes, this section will be revisited. Until then, **never reference or attempt to create Features in the OTA project.**

### Issue type IDs

| Type | ID |
|---|---|
| Epic | 10001 |
| Story | 10214 |
| Subtask | 10002 |
| Bug | 10215 |

### Parenting rules

- Stories parent directly to an Epic
- Bugs at Story level parent directly to an Epic (sibling to Stories)
- Subtasks parent to a Story (or to a Story-level Bug)
- Bugs at Subtask level parent to a Story
- Subtasks have no children — they are leaf nodes

### Issue numbering

Never invent or pre-assign OTA numbers. Jira assigns the key (e.g., `OTA-561`) when the issue is created; use the Jira-returned key in all references, commit messages, branch names, prompt files, and change-log entries. If a ticket reference is needed before creation, create the ticket first and then use the assigned key. `OTA-XXX` placeholders are permitted only in template documents that demonstrate format.

### Issue title conventions

Titles describe the **work**, not the **execution order**. Phase numbers, sprint numbers, "Step N — " prefixes, and similar sequencing metadata belong in descriptions, commit messages, or prompt files — never in titles. Execution order is a property of the queue, not the work item; a Subtask's parent and the prompts/artifacts that drove it carry the sequencing context. Titles that survive across reorderings and audit revisions are titles that don't embed sequencing.

Examples:

- ❌ `Phase 3b.1 — ORM model alignment` → ✅ `ORM model alignment`
- ❌ `Sprint 7 — User onboarding flow` → ✅ `User onboarding flow`
- ❌ `Step 2 of cutover — symbol normalization` → ✅ `Symbol normalization`

This rule is the OTA-specific surface of the profile-level convention in `jira-structure.md` § Title conventions. Project overrides are not permitted.

### Before creating any ticket via API

1. Identify the correct Epic.
2. Create the Story (or Story-level Bug) under that Epic.
3. Create any Subtasks under the Story when work spans multiple commits or sessions.

Don or Claude Web supplies the appropriate Epic parent for each Story or Story-level Bug. If Claude Code is uncertain about the right parent, it stops and asks rather than guessing.

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
          { "type": "paragraph", "content": [ { "type": "text", "text": "Description text here" } ] }
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

**Exception — bug-fix sessions:** commits made during an interactive bug-fix session (see `bugfix.md`) reference only the session parent ticket key. The per-fix Subtasks don't exist at commit time — they're created in batch after the commit lands and are transitioned to Code & Test Complete manually. The session parent is auto-transitioned by the commit-triggered automation as normal.

**What "Code & Test Complete" means under the slot-swap deploy model:** the artifact has been built and is ready to deploy. It is **not** in production. The transition to Production Deployed (status 10157) happens after a successful manual deploy, smoke test, and staging-to-prod slot swap. Tickets sit in Code & Test Complete until that swap fires.

---

## Working Patterns

Build execution conventions — parallel session protocol, terminal coordination, explicit commit gate, future subagent orchestration — live in profile-level `build-execution.md`. Read that file when authoring any Claude Code prompt or planning multi-terminal work.

Project-specific shared-file rules for OTA (files that two parallel terminals must never edit simultaneously):

- `app/main.py`
- `app/database.py`
- `web/src/api/client.js`
- Any `SKILL.md` file under load by both terminals

When two streams overlap on any of these, sequence them. The general parallelization safety rules in `build-execution.md` still apply.

Bug-fix session protocol — invocation, per-item triage, end-of-session rollup — lives in `bugfix.md`. The session pattern: Claude Code auto-creates a Story under OTA-555, triages each item Don feeds, applies small fixes immediately without commit, and at session end suggests a single consolidated commit, batch-creates Subtasks under the parent, and updates the parent's description with the rollup.

---

## Development Environment

Local dev setup (FastAPI, Vite, venv conventions, Schwab cert generation, zombie-process handling) is documented in `development-environment.md`. Read that file when setting up the project for the first time or troubleshooting environment issues.

---

## Environments

| Environment | Frontend Origin | Backend Origin | App Service | DB | Notes |
|---|---|---|---|---|---|
| Local dev | `https://localhost:5173` (Vite) | `https://127.0.0.1:8000` (FastAPI) | n/a | Shared Azure SQL via Key Vault | Self-signed certs, full HTTPS |
| Dev | `oa-dev.tmtctech.ai` | Same origin (Cloudflare → App Service direct) | `options-analyzer-api-dev` (B1) | Shared Azure SQL | MSI + Key Vault, mirrors prod topology |
| Prod | `oa.tmtctech.ai` | Same origin (Cloudflare → App Service direct) | `options-analyzer-api` (B1) with `staging` slot | Production Azure SQL | MSI + Key Vault, slot-swap deploy gate |

Cloudflare proxies each custom domain directly to the App Service, which serves both the API (`/api/v1/*`, `/health`, `/docs`) and the SPA (bundled in `static/` at build time, served via catch-all `/{path:path}` in `main.py`). Same-origin is trivial — BFF session cookies work without proxy workarounds. See `architecture-plan.md` Pattern 7 for details.

Full deployment workflow (slot swap, confirmation tokens, rollback, dev deploy) is documented in `deployment-workflow.md`.

---

## Post-Build QA Gate

**Last Reviewed:** 2026-05-06
**Review cadence:** every 60 days, or whenever `architecture-plan.md` changes materially. If today's date is more than 60 days past Last Reviewed, Claude Web flags this section for re-validation before any next change to it lands.

At the end of every build run — before marking any ticket as done or creating a PR — assess the scope of changes and recommend a QA level.

### QA Levels

**Level 0 — No QA needed:**

- Cosmetic fixes: typos, copy changes, comment updates
- Documentation-only changes
- Changes to files outside `app/` and `web/src/`
- Just commit and move on.

**Level 1 — Targeted validation:**

- Single-route API change → curl the route, verify response shape
- Single-component UI change → manual click-through of the touched component
- Single backend function change with no caller-side impact → existing test or targeted manual exercise

**Level 2 — Regression validation:**

- Cross-cutting refactor → run the full backend test suite + manual click-through of three workflows the change might affect (auth, scoring, position management)
- Schema or data-model change → run the AMZN regression suite and the MSFT anchor regression endpoint (OTA-284)
- Provider-routing change → exercise the change against Schwab and confirm no fallback paths broke

**Level 3 — Full regression:**

- Auth flow change, BFF change, OIDC change → all auth paths plus the full backend test suite
- Scoring engine math change → AMZN regression + MSFT anchor + manual scoring-narrative consistency check on three symbols
- Cross-environment change (dev cert, prod cert, secrets management) → dev deploy first, smoke test, then prod path

Document which Level was applied in the commit message body or in the prompt's Verification steps section.

---

## House Style Rules

- **Date format:** Always `mm-dd-yyyy`. With time: `mm-dd-yyyy hh:mm`. Use `formatDate()` from `web/src/utils/formatDate.js`. No locale strings, no other date formatting allowed.
- **Context document timestamps:** When any document in `claude_context/` or any source-of-truth markdown is modified, update the header `Last Updated` field in the format `yyyy-mm-dd hh:mm UTC` and add an entry to the change log at the bottom of the file. The change log entry must reference the OTA ticket that drove the change.
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

**Valid until 2026-06-30.** After this date, Claude Web must ask Don to confirm or refresh this section before relying on it.

A multi-stream architecture cleanup is in flight under the Architecture Optimization (Framework v1) Epic — see OTA-535 for live status. The Epic itself is the live source of truth; the inline content that previously lived in this section was a snapshot and got stale fast.

---

## Known Limitations

- No backend test coverage for auth flows, providers, or routes (analysis-layer tests exist; gap tracked under the Architecture Optimization Epic)
- MCP integration not started
- Live trading execution not started — `/positions/take` records intent only, not wired to Schwab order entry
- Social sentiment, fundamentals providers not yet built
- Iron condors section in TradesPage not yet built (coming-soon placeholder)

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-05-19 UTC | OTA-673 | Added "Issue title conventions" subsection under Jira Issue Hierarchy. Titles describe the work, not the execution order; phase numbers, sprint numbers, and step prefixes belong in descriptions, commit messages, or prompt files. Cross-references `jira-structure.md` § Title conventions for the profile-level rule. Backfilled the Governing Story field to OTA-573 (no longer a placeholder). Also corrected the Transition ID table: Override is transition `10` (not `9` as previously listed); added the `Deployed to Prod` transition (id `5`) which also targets Production Deployed. Both corrections caught during the same day's transition work on OTA-673 / OTA-674. |
| 2026-05-06 UTC | TBD (Documentation Governance Epic) | Major restructure. (1) Removed all references to Feature issue type — OTA Jira license does not include Feature; hierarchy is now Epic → Story → Subtask, with Bug as sibling to Story (or as Subtask). (2) Extracted Prompt Writing Convention to profile-level `prompt-style.md`; replaced with per-domain required-reading table. (3) Extracted Parallel Session Strategy to profile-level `build-execution.md` (renamed and broadened to cover future subagent orchestration). (4) Extracted Product Roadmap (OTAR Categories) to project-level `product-roadmap.md`. (5) Extracted Development Environment to project-level `development-environment.md` (includes zombie-process warning). (6) Extracted Deployment Workflow to project-level `deployment-workflow.md`. (7) Removed "Common Epic parents" list — Don/Claude Web supplies parent in practice. (8) Removed Claude Code's "review Jira plan?" prompt at session start — that context belongs to Claude Web during planning. (9) Added Document Governance Rules section codifying: Claude Code does not modify SoT docs unsolicited; material changes filed as Subtasks under governing Stories; pre-commit verification of Workflow Phases, Transitions, and Hierarchy required. (10) Added Profile-Level Conventions subsection naming `jira-structure.md`, `prompt-style.md`, `build-execution.md`. (11) Added Last Reviewed date to Post-Build QA Gate with 60-day review cadence. (12) Active Cleanup Items section now carries an explicit valid-until date and points to OTA-535 as the live source. |
| 2026-05-06 05:00 UTC | OTA-555 / 556 | Added bugfix.md to SoT inventory; added Bug Fix Sessions reference under Working Patterns. |
| 2026-04-30 23:55 UTC | OTA-535 | Added Prompt Writing Convention section (now extracted to `prompt-style.md`). |

Older Change Log entries archived to git history.
