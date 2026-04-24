# Options Analyzer — CLAUDE.md (Updated 2026-04-11 22:00)

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Options Analyzer is a FastAPI-based options analysis, portfolio tracking, and trading platform with:
- Multi-user support with three-tier security (READ/WRITE/TRADE)
- Pluggable provider architecture for market data, AI, and signal sources
- React web frontend for analyzing option spreads and naked positions
- AI-powered trade evaluation via Azure Foundry (Claude)
- Strategy scoring, position tracking, and outcome analytics
- Generic Insight Engine for anomaly detection and AI-generated alerts
- Future support for MCP integration, live trading, and additional signal sources

## Session Start Protocol

At the start of every new Claude Code chat for this project, ask the following
before doing anything else:

> "Should I review the current Jira plan for the OTA project before we start?
> (Project: tmtctech-team.atlassian.net, OTA project)"

Wait for a yes/no response. If yes, use the Atlassian MCP to pull open issues
from the OTA project before proceeding with any work. Filter for status != Done,
ordered by status ascending (so 1-To Do appears before 2-In Review, etc.).

**Note:** The OTA project does not use sprints. Always use the List view, not
the Board view. The board is sprint-based and will appear empty.
List view URL: https://tmtctech-team.atlassian.net/jira/software/projects/OTA/list

**Atlassian MCP workaround (as of March 2026):** Atlassian MCP tools do not surface
in Claude.ai tool_search. Workaround: export Jira CSV manually, or use Claude in
Chrome to navigate the list view URL above. When MCP tools become available, update
this protocol to use them directly instead of browser automation.

## Jira Workflow — Status Definitions

The OTA project uses a 5-stage workflow. When reading or updating Jira status,
always map to these definitions:

| # | Status | Status ID | Who Acts | Meaning |
|---|--------|-----------|----------|---------|
| 0 | IDEA | 10000 | Product Owner | Raw backlog item, not yet committed to |
| 1 | TO DO | 10001 | Product Owner | Promoted — confirmed candidate for next work set |
| 2 | IN PROGRESS | 10002 | Claude (Web) | Claude Web will actively review, group, sequence, and write prompts |
| 3 | IN REVIEW | 10003 | Claude (Code) | Prompt written and handed to Claude Code — actively executing |
| 4 | DONE | 10004 | Automation | Claude Code pushed to GitHub → Jira auto-closes via commit trigger |

**Workflow rules:**
- Product Owner selects items from IDEA → promotes to TO DO (transition ID: 3)
- Claude Web reviews TO DO items, groups them logically, sequences dependencies, and writes Claude Code prompts → moves to IN PROGRESS (transition ID: 2)
- Claude Web writes the Claude Code prompt → moves to IN REVIEW (transition ID: 4)
- Claude Code executes the prompt, pushes to GitHub with OTA ticket numbers in commit message
- Jira automation moves IN REVIEW → DONE automatically on commit (transition ID: 5)

**Transition ID reference (for REST API calls):**

| Transition | From | To | ID |
|------------|------|----|----|
| Idea Selected | IDEA | TO DO | 3 |
| Selected by PM for Build | TO DO | IN PROGRESS | 2 |
| Claude.ai writes prompts | IN PROGRESS | IN REVIEW | 4 |
| Developer feeds prompts. C.code write. Pushes to GitHub. | IN REVIEW | DONE | 5 |
| To Do (any status) | Any | TO DO | 21 |
| In Progress (any status) | Any | IN PROGRESS | 31 |
| In Review (any status) | Any | IN REVIEW | 41 |
| Done (any status) | Any | DONE | 51 |

## Jira Temporary Solution

The Atlassian MCP connector is active but its tools do not surface via `tool_search`
(tracked as OTA-249). Until the permanent fix is available, use the **Jira REST API
via curl** to create, update, and transition issues.

**Always ask Don before using this approach:** "Should I use the Jira temporary
solution (REST API via curl) for this?" Wait for confirmation before proceeding.

When the permanent MCP solution is resolved (OTA-249), this section will be removed
and replaced with MCP tool instructions. Don will update the claude.ai project docs
copy of CLAUDE.md at that time.

### Jira REST API Reference

**Base URL:** `https://tmtctech-team.atlassian.net`
**Auth:** Basic auth with Don's Atlassian email + API token from environment variable `$JIRA_API_TOKEN`
**Project key:** OTA
**Cloud ID:** `53c395d7-bac7-4a5f-baf2-ee2b0f375a2b`

### Issue Type IDs

| Type | ID |
|------|------|
| Epic | 10001 |
| Feature | 10003 |
| Subtask | 10002 |

### Create an Issue
```bash
curl -s -X POST \
  "https://tmtctech-team.atlassian.net/rest/api/3/issue" \
  -H "Authorization: Basic $(echo -n 'DON_EMAIL:$JIRA_API_TOKEN' | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": { "key": "OTA" },
      "summary": "Issue summary here",
      "issuetype": { "id": "10003" },
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

### Set Parent (Epic Link)

Pass `"parent": { "key": "OTA-XXX" }` as a direct named field in the create
payload — NOT inside `additional_fields`. Silent failure otherwise.

### Transition an Issue

Transition ID for "To Do": `21`
```bash
curl -s -X POST \
  "https://tmtctech-team.atlassian.net/rest/api/3/issue/OTA-XXX/transitions" \
  -H "Authorization: Basic $(echo -n 'DON_EMAIL:$JIRA_API_TOKEN' | base64)" \
  -H "Content-Type: application/json" \
  -d '{ "transition": { "id": "21" } }'
```

### Important Notes

- Don's Atlassian email and API token must be available as environment variables
- The `parent` field is how Features link to Epics — always use direct field, never `additional_fields`
- Description must use Atlassian Document Format (ADF), not plain text
- After creating issues, report the created issue keys back to Don for verification

---

### Jira Issue Hierarchy — STRICT

The OTA project uses a strict 3-level hierarchy. Every API-created ticket
must respect this structure or it will not appear correctly on the board.

**Rules:**
- Subtasks are the ONLY level that represents actionable build work
- Subtasks must ALWAYS be parented to a Feature — never directly to an Epic
- Features must ALWAYS be parented to an Epic
- NEVER create a Feature as a child of another Feature
- NEVER create implementation tickets as Feature type — use Subtask (id: 10002)
- Issue type IDs: Epic=10001, Feature=10003, Subtask=10002

**Before creating any ticket via API:**
1. Identify the correct Epic (e.g. OTA-8 for Dashboard work)
2. Identify or create the correct Feature parent under that Epic
3. Create the implementation ticket as a Subtask under that Feature

**Board visibility rule:**
The Jira board displays items by status. Subtasks appear as actionable TO DO
items. Features parented directly to Epics will appear as planning items but
their children will not flow through the board correctly.

**Common Feature parents for reference:**
- OTA-34 — Config Drawer Popout Sidebar (Dashboard / Settings work)
- OTA-33 — Dashboard Sections Build (Dashboard widget work)
- OTA-28 — Positions Frontend Phase 2.10 Stream B (Positions UI work)
- OTA-19 — DEV Housekeeping (bugs, hotfixes, dev process)
- OTA-14 — Ongoing: Strategy Validation Reviews (validation work)

When in doubt about the correct Feature parent, ask Don before creating tickets.

---

## Jira Automation

A Jira automation rule fires on every commit to main:
- **Trigger:** Commit created
- **Condition:** Status does not equal Done
- **Action:** Transition work item to Done

**Commit message format required:** Always prefix with OTA ticket numbers.
Example: `OTA-152 OTA-153 feat: implement StrategyScorecard and SecurityDashboard`

This automation only works if ticket numbers appear in the commit message.
Always include ALL ticket numbers addressed in a session in the commit prefix.

**Verification status (2026-03-27):** Automation rule configured; manual verification
pending. To test: push a commit to main with an OTA ticket number and check ticket
status in Jira within a few minutes of the push.

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
Reason: [one sentence — why this level]
Run QA? [waiting for your answer]
```

The human approves, adjusts, or skips. Never run QA without asking. Never skip the recommendation — always state the level even if you expect a Level 0.

### Regression Runs

When running Level 2 QA, compare current results against the baseline files in `agents/qa-context/`. A test that failed in the previous run and still fails is a known issue. A test that passed in the previous run and now fails is a REGRESSION — mark severity BLOCKER and escalate immediately to Teams.

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

The **"Allow CORS: Access-Control-Allow-Origin"** Chrome extension is **disabled
by default**. It may be needed for local development when testing cross-origin
API calls from the browser.

- **Default state:** Disabled
- **When to enable:** Only if you encounter CORS errors during browser-based
  local dev testing. Ask Don to enable it before proceeding.
- **After testing:** Ask Don to disable it again.
- **Why this matters:** When enabled, it blocks the Claude in Chrome extension
  from connecting, which breaks Claude Web's browser automation tools.

## Development Commands

### Backend (FastAPI)

```bash
# Setup
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Unix
pip install -r requirements.txt

# Run backend (with auto-reload)
uvicorn app.main:app --reload

# Run with HTTPS (required for Schwab OAuth)
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000

# API docs
# https://127.0.0.1:8000/docs (Swagger UI)
# https://127.0.0.1:8000/health (Health check)
```

### Frontend (React + Vite)

```bash
cd web
npm install
npm run dev     # Starts dev server with HTTPS proxy to backend
npm run build   # Production build
npm run lint    # ESLint
```

**Important**: The Vite dev server runs on HTTPS (https://localhost:5173) and proxies `/api` requests
to the FastAPI backend at https://127.0.0.1:8000. Both use self-signed certificates in development.

### Testing

```bash
pytest                          # Run all tests
pytest tests/test_something.py  # Run specific file
pytest --cov=app                # With coverage
```

Note: Test infrastructure is minimal. Most validation happens via Swagger UI at /docs.

### Zombie Process Warning (Windows)

Before restarting the backend, always kill existing processes first:
```powershell
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
netstat -ano | findstr ":8000"
```
Windows does not always release port 8000 cleanly. A zombie uvicorn process will answer
requests silently, making new route registrations invisible and causing confusing 404s.

---


## Architecture Summary

See `architecture-plan.md` for full details including directory structure, data models, API endpoints, and agent inventory. Key patterns:

1. Provider Adapter Pattern — all external sources implement a standard interface
2. Skill-Driven Prompt Architecture — all AI prompts live in SKILL.md files
3. Two-Track Observability — OTel traces + SQL business records
4. Unified Position Model — paper follows and live trades share identical data model
5. Generic Insight Engine — domain-agnostic detect → score → communicate
6. Backend-for-Frontend Identity — FastAPI is the OIDC confidential client, cookies only
7. Unified Deployment — FastAPI serves API + React SPA from one App Service

**Provider routing rule:** Never hardcode a provider name in API routes. Always use `_get_provider()` or `settings.default_market_data_provider`.

---

## Common Patterns

### Adding a New Strategy (Phase 2.9+)

1. Create `web/src/strategy-configs/your-strategy.config.js` with full config schema
2. Register in `strategy-configs/index.js`
3. Add scoring logic to `app/analysis/strategy_scorer.py`
4. Strategy scores appear in the scorecard panel and OptionsTerminal renders it automatically

### Adding a New Signal Source (Phase 3.5+)

1. Create `app/providers/your_source.py` implementing `ContextSource`
2. Register in `ProviderFactory`
3. Define `ttl_seconds()` for appropriate freshness window
4. Position Monitor Agent automatically picks it up on next run

### Adding a New Insight Domain (Phase 3.6+)

1. Create `app/skills/insight-engine/domains/your-domain/SKILL.md`
2. Create observation source adapter for the domain
3. Deploy with `domain='your-domain'` in insight records
4. Dashboard feed filters by domain automatically

### Adding a New API Endpoint

1. Define Pydantic schemas in `app/models/schemas.py`
2. Add route in appropriate `app/api/*_routes.py`
3. Add corresponding function to `web/src/api/client.js`

---

## Important Implementation Details

### Schwab OAuth Flow

Schwab requires HTTPS. Backend must run on https://127.0.0.1:8000 with self-signed certs.
See SCHWAB-LOGIN-PROCESS.md for full details.

### Black-Scholes Probability Matrix

Computed in `app/analysis/black_scholes.py`. NOT by Claude. Claude receives the
pre-computed matrix as context. Inputs: current price, IV, DTE, risk-free rate.
Output: probability of price at each level (±10% in $10 steps) at dates:
expiry-9, expiry-6, expiry-3, expiry.

### Strategy Config Schema

Each strategy config file exports a `configSchema` array. ConfigDrawer renders
whatever schema the active strategy defines. Fields have type, label, min, max,
default, and step. This replaces the static 14-field systemVars approach.

### Position Health Grade

Computed by Position Monitor Agent from deterministic math against Claude's exit
levels stored at position entry. Grade: A (on track) → F (thesis invalid).
Updated daily after market close. Also computable on-demand.

### Insight Engine Escalation

Position Monitor detects a threshold crossing → calls `InsightEngine.generate()`
with observation context → Claude call using domain SKILL.md → structured insight
written to SQL → appears on Dashboard feed. One Claude call per detected deviation
per position per day maximum.

### AskClaudePanel Deprecation

`AskClaudePanel` is retired in Phase 2.11. It is replaced by:
- `StrategyScorecard` — shows strategy scores per symbol or trade
- `TradeEvaluationCard` — shows Claude's structured output per strategy
- `ProbabilityMatrix` — shows B-S probability table

The new flow is: select strategies → single Evaluate call → structured cards back.
No open-ended chat. Claude is an analytical engine, not a conversationalist.

---

## UI Decisions — Read This First

All finalized UI decisions live in `UI-GUIDANCE.md` in `claude_context/`.
Before building or modifying ANY frontend component, read that file.
It is the visual contract. When it conflicts with other sources, it wins.

Key decisions summarized (v3.2 — 04-02-2026):
- Nav: Left rail (200px fixed). Items: Dashboard · Security Strategies · Trades · Positions. Strategy sub-nav: Steady Paycheck / Weekly Grind / Trend Rider / Lottery Ticket.
- Verticals and Puts & Calls merged into TradesPage.jsx (Sprint 4). VerticalsPage.jsx and LongCallsPage.jsx deleted.
- QuoteBar is ONE shared component used identically on every page
- Watchlist click navigates to Security Strategies for that symbol
- Trades page has 3 collapsible sections: Vertical spreads (live) · Puts & calls (live) · Iron condors (coming soon). Each section has its own ⚙ Config drawer (SectionConfigDrawer).
- Strategy filtering MUST use trade_structure field, never hardcoded strategy names
- Shared components: StrategyPill (SP/WG/TR/LT pills with tooltip), TradeTypeBadge (directional color, title case), ScoreCell (bar + number with threshold color)
- Claude summary advice badge: white outlined (rgba(255,255,255,0.06) bg, rgba(255,255,255,0.35) border) — not purple
- StrategyPage.jsx — full strategy page with header, editable parameters, read-only scoring weights, "Find trades →" navigation, and strategy-filtered positions table with Refresh all cost guardrail.
- RefreshConfirmDialog.jsx — reusable confirmation dialog for multi-position Claude API refresh. Used on both PositionsPage and StrategyPage.
- PositionsPage.jsx — v3 design with StrategyPill (abbreviated 2-letter pills), health grade letter badges (A-F), versioned re-reads with white outlined Claude advice badge, exit plan levels, group by strategy/symbol/health.
- Claude API cost guardrail: Refresh all shows confirmation dialog when >1 position. Single position refresh runs without confirmation. One daily auto-refresh per position after market close. Never on page load or timers.
- Trade detail Sections A-E fully wired in TradesPage (Sprint 4): Section D uses live B-S probability matrix; Section E fully wired evaluate → verdict → Follow/Take Position → follow-up.
- Security Strategies page: Config drawer removed (Part 11). SMA periods fixed at 8/21/50.

---

## House Style Rules

- **Date format**: ALWAYS mm-dd-yyyy. With time: mm-dd-yyyy hh:mm. Use `formatDate()` from `web/src/utils/formatDate.js`. No other date formatting allowed.
- **Context document timestamps**: Whenever a file in `claude_context/` is created or updated, insert or replace the first line with a heading in this exact format: `# Options Analyzer — [filename.md] (Updated yyyy-mm-dd hh:mm)`. Use the actual filename and current date/time. If the line already exists, replace it; if not, add it as the first line.
- **No `$` in UI**: Display `567.23` not `$567.23`
- **Health pips**: Each pip is its own column — never group in a single cell
- **`getHealthPips` signature**: Always `getHealthPips(trade, systemVars)`
- **Schwab index symbols**: Use `apiSymbol` field for mapping (e.g. `.INX` → `$SPX`)
- **Provider routing**: Never hardcode `"tradier"` — always use `_get_provider()`
- **Prompts in SKILL.md**: Never hardcode prompts in Python or React
- **Position source labels**: Display "Paper" and "Live" (not "PAPER"/"LIVE") in UI
- **Health grades**: Display as letter (A/B/C/D/F) with color: A=green, B=teal, C=yellow, D=orange, F=red

## Known Limitations / Future Work

- No backend tests yet (validation via Swagger UI)
- MCP integration (Phase 4) not started
- Live trading execution (Phase 5) not started — /positions/take records intent only, not wired to Schwab order entry
- Social sentiment, fundamentals providers not yet built
- Watchlist/favorites not yet synced to backend (localStorage only)
- Iron condors section in TradesPage not yet built (coming soon placeholder)
- OptionsTerminal.jsx and SecurityDashboard.jsx are retired but not yet deleted from the codebase