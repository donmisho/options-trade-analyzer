# Session Prompt — Phase 2.6 Part 1: Claude Trade Agent (Backend)

## Who You Are Talking To
I am an experienced Microsoft AI consultant building a personal options trading analyzer.
I have strong conceptual programming understanding but limited hands-on coding experience.
Always explain the "why" behind each step. I work on Windows with PowerShell.

## The Project
**Options Trade Analyzer** — React + FastAPI options analysis app.
- GitHub: `https://github.com/donmisho/options-trade-analyzer`
- Backend: Python 3.13 FastAPI at `options-analyzer/app/`
- Frontend: React + Vite at `options-analyzer/web/`
- Local dev root: `C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer`
- Venv: `venv` (not `.venv`)
- Azure SQL: `options-analyzer-sql.database.windows.net` / `options-analyzer-db`
  — Entra ID auth only, no SQL credentials
- Azure Key Vault: `ota-kv`
- Azure AI Foundry: `ota-foundry` (Claude deployed here)
- Application Insights: `ota-insights` (for agent telemetry)

## Prerequisites for This Session
**Phase 3 Azure deployment must be complete before starting this session.** Specifically:
- Azure SQL is live and the app is connecting to it successfully
- `agent_run_log` and `trade_recommendations` tables exist in Azure SQL
  (schema is in `app/skills/ota-agentic-strategy/SKILL.md`)
- `ota-insights` Application Insights resource exists and its connection string is in Key Vault
- Key Vault is wired to the backend via `SecretsManager`

If any of the above are not done, stop and complete Phase 3 first.

## What We Built in Prior Sessions That Directly Relates to This
Two SKILL.md files were written and are in project knowledge (and should be in the repo at
`app/skills/`):
- `app/skills/ota-agentic-strategy/SKILL.md` — master architecture pattern for all agents.
  Contains: three-layer stack diagram, OpenTelemetry boilerplate, SQL table schemas,
  `skill_loader.py` full code, Foundry registration checklist, Agent 365 readiness checklist.
  **Read this first.**
- `app/skills/claude-trade-agent/SKILL.md` — the trade evaluation agent's prompt library.
  Contains: all three stage system prompts and user message templates, exit level calculations,
  recall/prior-context logic, storage schema, backend endpoint table.

The design decisions recorded in the project plan (ADR-001 through ADR-004) explain why the
architecture is built this way. The most important one for this session: **all AI prompts live
in SKILL.md files — zero hardcoded prompt text in Python.**

## What We Are Building This Session: Phase 2.6 Backend

This is a backend-only session. The frontend (TradeAgentPanel) is built in a separate session
after this one is working and tested.

### Step 1 — Create the skills directory and copy SKILL.md files
```
app/
└── skills/
    ├── skill_loader.py           ← build this (code is in ota-agentic-strategy SKILL.md)
    ├── ota-agentic-strategy/
    │   └── SKILL.md              ← already written, copy from project knowledge
    └── claude-trade-agent/
        └── SKILL.md              ← already written, copy from project knowledge
```
The `skill_loader.py` utility parses SKILL.md files, extracts named fenced code blocks
by section header key (e.g., `BATCH_TRIAGE_SYSTEM`), and renders `{{variable}}` template slots.
The full implementation is in the ota-agentic-strategy SKILL.md — copy it verbatim.

### Step 2 — Wire OpenTelemetry telemetry into main.py
- Install: `azure-monitor-opentelemetry` (add to requirements.txt)
- Add `init_agent_telemetry()` call to app startup in `main.py`
- The boilerplate is in ota-agentic-strategy SKILL.md — copy the `init_agent_telemetry()`
  and `invoke_with_tracing()` functions into a new `app/agents/telemetry.py` module
- `APPLICATIONINSIGHTS_CONNECTION_STRING` comes from Key Vault via `SecretsManager`

### Step 3 — Build agent_routes.py
Build `app/api/agent_routes.py` with these 7 endpoints:

| Endpoint | Method | Stage | max_tokens | Notes |
|----------|--------|-------|------------|-------|
| `/api/v1/agent/triage` | POST | 1 | 800 | Returns JSON rankings |
| `/api/v1/agent/deep-dive` | POST | 2 | 1200 | Full analysis + verdict |
| `/api/v1/agent/followup` | POST | 3 | 600 | Contextual follow-up |
| `/api/v1/agent/recommendations` | GET | — | — | List by symbol |
| `/api/v1/agent/recommendations/{key}` | GET | — | — | Single recommendation |
| `/api/v1/agent/recommendations/{key}` | PUT | — | — | Save/update verdict |
| `/api/v1/agent/recommendations/{key}` | DELETE | — | — | Clear recommendation |

Key implementation details:
- Use `get_skill("claude-trade-agent")` from skill_loader to load prompts — never hardcode prompt text
- Wrap every AI call with `invoke_with_tracing()` from telemetry.py
- Every completed call writes a row to `agent_run_log` (full inputs + outputs + otel_trace_id)
- The `deep-dive` endpoint checks `trade_recommendations` for a prior record with the same
  `trade_key` ("{symbol}:{spread_label}:{expiration}"). If found, inject the prior verdict
  and `change_summary` into the `{{#if prior_recommendation}}` block in the DEEP_DIVE_USER template
- After a successful `deep-dive`, write/update the record in `trade_recommendations`
- All endpoints require Tier 1 JWT auth (use existing `require_read` dependency)

### Step 4 — Register agent in Foundry portal
After the routes are working and tested locally:
1. Open Azure AI Foundry portal → `ota-foundry` → Agent Service
2. Create new agent named `ota-trade-evaluation-agent`
3. Paste the `DEEP_DIVE_SYSTEM` prompt section as agent instructions
4. Select the Claude model deployment
5. Enable tracing → connect `ota-insights`
6. Apply tags: `project=options-trade-analyzer`, `environment=dev`, `component=ai`, `owner=don`
7. Copy the assigned Entra Agent ID and add it to `claude-trade-agent/SKILL.md` frontmatter

### Step 5 — Test end to end
Test each endpoint via FastAPI's built-in docs at `https://127.0.0.1:8000/docs`:
1. POST to `/triage` with a sample batch of 2-3 trades — verify JSON rankings come back
2. POST to `/deep-dive` with one trade — verify full analysis and verdict
3. GET `/recommendations/{key}` — verify the recommendation was saved to SQL
4. POST to `/deep-dive` with the same trade key again — verify prior context is injected
5. POST to `/followup` — verify contextual response
6. Check Foundry portal → Observability → Traces — verify traces are appearing

## What Not To Touch This Session
- `AskClaudePanel.jsx` and old evaluate endpoints — leave them running, they get removed in the frontend session
- Frontend code of any kind
- The existing `FoundryAdapter` / `AnthropicAdapter` pattern — the new agent routes use these same adapters

## Patterns to Follow
- **Entra ID auth** for Azure SQL — DefaultAzureCredential, no passwords
- **SecretsManager** for all secrets — `await secrets.get("applicationinsights-connection-string")`
- **skill_loader** for all prompts — `get_skill("claude-trade-agent").render("DEEP_DIVE_USER", **context)`
- **invoke_with_tracing** wrapper on every AI call — never call the model without it
- Explain the "why" behind each file and function as we build

## Start Here
Before writing any code, confirm:
1. Do `app/skills/ota-agentic-strategy/SKILL.md` and `app/skills/claude-trade-agent/SKILL.md`
   exist in the repo? (If not, we need to create them from project knowledge first)
2. Do `agent_run_log` and `trade_recommendations` tables exist in Azure SQL?
3. Is `APPLICATIONINSIGHTS_CONNECTION_STRING` in Key Vault?

Then start with Step 1.
