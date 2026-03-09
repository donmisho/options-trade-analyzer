# OTA Agentic Architecture Plan
## Options Trade Analyzer — Phase 2.6 and Forward

---

## What This Document Is

This is the architectural specification for how AI agents are built, deployed, observed,
and governed in the Options Trade Analyzer. It is the companion to two SKILL.md files:

- `app/skills/ota-agentic-strategy/SKILL.md` — reusable master pattern (save this in your project forever)
- `app/skills/claude-trade-agent/SKILL.md` — the trade evaluation agent specifically

Read this document to understand **why** the pattern is designed the way it is.
Read the SKILL.md files when you're actually building.

---

## The Core Problem Being Solved

The current Ask Claude panel is a dead end architecturally:
- One trade in, one response out, nothing stored
- No way to know if Claude's recommendations were good over time
- If you add a second agent (portfolio risk, market scanning), you'd build it separately
  with no connection to the first
- When Agent 365 arrives, there's nothing to plug in

The redesign solves all four problems simultaneously.

---

## The Three-Layer Architecture

Think of agents in this project as living across three layers, like floors of a building.
You build from the bottom up, but the design considers all three from the start.

### Layer 1 — Execution (what you build now)
Your FastAPI backend, Python agent code, and SKILL.md prompt files.
Each agent is a focused specialist that does one thing well.

The trade evaluation agent lives here. It knows how to triage trades, do a deep dive,
and answer follow-up questions. It doesn't know about portfolio risk or market scanning —
those will be separate specialists.

### Layer 2 — Orchestration (what you add as you grow)
Azure AI Foundry Agent Service. This is where agents are registered, where multi-agent
workflows are defined, and where handoffs between agents are managed.

Right now, the FastAPI backend calls the trade agent directly. As you add more agents,
you'll add an **orchestrator** in Foundry that receives requests and routes them to the
right specialist. The orchestrator is thin — it routes and coordinates, it doesn't analyze.

### Layer 3 — Management (what arrives with Agent 365)
Microsoft is building Agent 365 as the enterprise management surface for all agents
running in your tenant. It's currently in public preview as part of Foundry's M365
integration (one-click publish to Teams / Copilot Chat). The full governance surface
is coming.

By building correctly in Layers 1 and 2 — with Foundry-registered agents, Entra identities,
and standard OpenTelemetry traces — everything you build today will appear in Agent 365
automatically when it becomes generally available. You won't rebuild; you'll just log in.

---

## How Observability Works

Every time Claude evaluates a trade, two things happen in parallel:

**The telemetry trace** flows to Application Insights via OpenTelemetry. This is the
real-time monitoring story. You can see in the Foundry portal: which agent ran, how long
it took, how many tokens it used, whether it succeeded or threw an error. Traces are
structured with parent-child spans, so you can drill from "this triage session" into
"this specific model call" and see the token counts, latency, and verdict.

**The business record** is written to Azure SQL. This is the historical audit story.
Every single agent invocation writes a row to `agent_run_log` containing the full
prompt text, the full model response, the market snapshot at call time, and a link
back to the Application Insights trace via the OTel trace ID. This row never expires.

Why both? Application Insights is excellent for monitoring but retains data for 90 days
by default and isn't structured for relational queries. Azure SQL gives you the permanent,
queryable record that can answer: "For every EXECUTE recommendation this agent made in Q1,
what was the underlying price movement over the next 30 days?" That question — measuring
whether Claude's recommendations actually made money — is only answerable if you store
the full context of every call, forever.

When Power BI and Microsoft Fabric are connected (a future milestone), this same SQL data
becomes your trading performance dashboard. The agent observability data and the trade
outcome data live in the same database, so you can correlate them directly.

---

## The Prompt Architecture and Why It Matters

Every prompt lives in a SKILL.md file. Python has a utility (`skill_loader.py`) that
reads those files and fills in the variable slots before sending to the model.

This is not just organizational neatness. It has two practical effects:

**You can tune the agent without deploying code.** If Claude's triage rankings feel too
aggressive, you edit the `BATCH_TRIAGE_SYSTEM` section in SKILL.md, restart the backend,
and the new behavior is live. No Python changes, no React changes, no Git PR required.

**The prompt version travels with every recommendation.** The SKILL.md frontmatter has a
`version` field. That version is written into `agent_run_log.prompt_version` with every
call. Six months from now, if you want to know whether recommendations made with version 1.0
were better than version 1.3, that field lets you segment the data. Prompt engineering
becomes a measurable, auditable practice rather than a black box.

---

## The Multi-Agent Future: How Agents Connect

Today: one agent, called directly by FastAPI.

In the near future (when you build the Portfolio Risk agent or Market Scan agent):
each new agent gets its own SKILL.md, its own Foundry registration, and its own Entra
Agent ID. They're independent specialists.

When you want them to coordinate — for example, "flag the trades where Claude's EXECUTE
recommendation overlaps with a portfolio risk alert" — you add an **orchestrator** in
Foundry's multi-agent workflow builder. The orchestrator doesn't know about options;
it knows how to route requests and collect results. The specialists handle the domain logic.

The connection protocol between agents is Agent2Agent (A2A), which Microsoft supports
natively in Foundry. You don't write custom handoff code. You define which agents the
orchestrator can call, and the orchestrator figures out the routing based on context.

---

## Agent 365 Readiness: What You're Doing Now vs. Later

You are making specific choices today that make Agent 365 adoption a configuration step:

**Using Foundry to deploy agents** — Agent 365 manages Foundry-hosted agents natively.
If your agents live in Foundry, they show up in Agent 365 automatically.

**Entra Agent IDs** — Agent 365 governance is identity-based. Each agent gets a distinct
identity so policies, permissions, and audit trails are per-agent, not per-app.

**Standard OpenTelemetry** — Agent 365 monitoring is built on the same Application Insights
feed. The traces you're already emitting are the ones it reads.

**Foundry model endpoints (not direct API)** — When Agent 365 adds model governance policies
(content filters, rate limits, approval gates for certain model calls), those policies apply
at the Foundry endpoint level. Your agent code doesn't change.

What you defer: publishing agents to Teams/Copilot Chat, tenant-wide governance policies,
and using the M365 Admin Center for fleet management. Those are Agent 365 features you
enable when the platform is generally available, not things you build.

---

## Azure Resources Summary

| Resource | Name | New? | Purpose |
|----------|------|------|---------|
| AI Foundry | `ota-foundry` | Existing | Agent deployment, model gateway, observability portal |
| Application Insights | `ota-insights` | **New** | OTel trace sink for all agent telemetry |
| Log Analytics Workspace | `ota-logs` | **New** | Backend store for Application Insights |
| Azure SQL table | `agent_run_log` | **New** | Permanent per-call audit record |
| Azure SQL table | `trade_recommendations` | **New** | Stored verdicts queryable by trade |

All new resources follow `ota-` naming and carry the standard four tags.
`ota-insights` and `ota-logs` use `component=ai`.

---

## Build Sequence for Phase 2.6

1. Create `app/skills/` directory structure, copy SKILL.md files in
2. Build `skill_loader.py` utility (~80 lines)
3. Add `agent_run_log` and `trade_recommendations` tables to Azure SQL schema
4. Create `ota-insights` Application Insights resource, wire to `ota-foundry`
5. Add `init_agent_telemetry()` call to `main.py` startup
6. Build `agent_routes.py` with all 7 endpoints
7. Wire OTel tracing into agent routes using `invoke_with_tracing()` wrapper
8. Register `ota-trade-evaluation-agent` in Foundry portal, note Entra Agent ID
9. Build React components: `TriageResults`, `DeepDiveView`, `FollowUpThread`, `RecommendationBadge`, `TradeAgentPanel`
10. Add multi-select + "Ask Claude (N)" to VerticalsPage and LongCallsPage
11. Deprecate old AskClaudePanel and evaluate endpoints

The first four steps are pure infrastructure and can be done in a single session before
writing any agent logic. Getting telemetry flowing early means you have observability
data from the first real test call.
