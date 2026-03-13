---
name: ota-agentic-strategy
description: >
  Master architecture pattern for every AI agent in the Options Trade Analyzer
  project. Defines how agents are structured, deployed through Azure AI Foundry,
  observed via OpenTelemetry + Application Insights, and wired for future Agent 365
  management. Use this skill whenever designing a new agent, wiring observability,
  adding an orchestration workflow across agents, or preparing for Agent 365 migration.
  Always consult this skill before writing any agent code or adding new Azure AI resources.
---

# OTA Agentic Strategy — Master Architecture Pattern

This skill defines the reusable patterns every agent in this project must follow.
Individual agent SKILL.md files define **what** the agent does and **what prompts it uses**.
This file defines **how every agent is built, deployed, observed, and governed**.

---

## Why This Pattern Exists

The Options Trade Analyzer will eventually run several specialized agents:
- **Trade Evaluation Agent** (Phase 2.6) — triage, deep-dive, follow-up
- **Portfolio Risk Agent** (future) — monitors open positions against thresholds
- **Market Scan Agent** (future) — proactive watchlist screening
- **Order Pre-Flight Agent** (future) — validates orders before execution

These agents will eventually need to hand off work to each other, share context,
and be managed from a single governance surface. That surface is **Agent 365**
(Microsoft's planned enterprise agent management layer, currently in public preview
as part of Microsoft Foundry's M365 integration).

Building each agent correctly from the start — with Foundry deployment, OpenTelemetry
tracing, and the right identity pattern — means Agent 365 management is a configuration
step, not a rebuild.

---

## The Three-Layer Stack

Every agent in this project is built across three layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3 — MANAGEMENT PLANE                                     │
│  Agent 365 (future) · Foundry Control Plane · Power BI/Fabric   │
│  "Where you monitor, govern, and eventually manage from M365"   │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2 — ORCHESTRATION PLANE                                  │
│  Foundry Agent Service · Multi-Agent Workflows                  │
│  Microsoft Agent Framework (Semantic Kernel + AutoGen runtime)  │
│  "Where agents talk to each other and workflows are defined"    │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1 — EXECUTION PLANE                                      │
│  FastAPI (ota-api) · Python agent code · SKILL.md prompt files  │
│  "Where individual agents run, call models, and persist data"   │
└─────────────────────────────────────────────────────────────────┘
```

Your code today lives entirely in Layer 1. The work in Phase 2.6 adds Layer 2.
Layer 3 is already partially enabled (Foundry Control Plane exists) and will expand
as Agent 365 matures.

---

## Azure Resources for the Agent Layer

These are the Azure resources used by agents, in addition to the existing `ota-*` stack.

| Resource | Name | Purpose |
|----------|------|---------|
| AI Foundry Project | `ota-foundry` (existing) | Agent deployment, model routing, observability portal |
| Application Insights | `ota-insights` | OpenTelemetry trace sink for all agents |
| Log Analytics Workspace | `ota-logs` | Backend store for Application Insights (and Azure SQL logs) |
| Entra Agent ID | auto-assigned per agent | Each Foundry-hosted agent gets an Entra identity for secure M365 access |

All resources follow the `ota-` naming convention (see `azure-naming-conventions.md`)
and must carry the standard four tags: `project`, `environment`, `component`, `owner`.

For Application Insights and Log Analytics, use `component=ai`.

---

## Agent Identity Pattern

Every agent deployed to Foundry gets a **Microsoft Entra Agent ID** — this is an
identity assigned by Foundry automatically when you register the agent. It is distinct
from the App Service Managed Identity used by the FastAPI backend.

This matters because:
1. It enables future Agent 365 governance (policies apply per-agent-identity)
2. It provides an audit trail: "this action was taken by the Trade Evaluation Agent" vs. "by the app"
3. When agents call each other (Agent2Agent / A2A protocol), they authenticate via these identities

In your code, you never manage these identities manually. Foundry handles the lifecycle.
You reference them in observability data and in future A2A wiring.

---

## Observability Architecture

Every agent step must be observable. The goal is to answer these questions at any time:

- What input did this agent receive?
- What did it send to the model?
- What did the model return?
- How long did each step take?
- What was the token cost?
- For a specific recommendation, what was the exact chain of reasoning that produced it?

This is accomplished through **OpenTelemetry (OTel)** traces flowing to **Application Insights**,
visualized in the **Foundry Observability portal** and queryable via **Azure Monitor / Log Analytics**.

### Trace Anatomy for a Single Agent Call

```
Trace: trade-evaluation-agent / deep-dive
│
├── Span: agent.invoke (root)
│   ├── attributes: agent.name, agent.id, user.id, trade_key, stage
│   │
│   ├── Span: prompt.build
│   │   ├── attributes: prompt_section, template_vars (no PII in prod), prompt_version
│   │
│   ├── Span: gen_ai.chat (LLM call)
│   │   ├── attributes: gen_ai.system, gen_ai.request.model, gen_ai.usage.input_tokens
│   │   ├── attributes: gen_ai.usage.output_tokens, gen_ai.response.finish_reason
│   │   ├── events: gen_ai.user.message (if ENABLE_SENSITIVE_DATA=true)
│   │   └── events: gen_ai.assistant.message (if ENABLE_SENSITIVE_DATA=true)
│   │
│   ├── Span: verdict.parse
│   │   └── attributes: verdict, rank, confidence
│   │
│   └── Span: recommendation.persist
│       └── attributes: trade_key, verdict, db.operation
```

### Custom Attributes to Emit on Every Agent Span

These are beyond the standard OTel GenAI conventions — they're specific to this app:

```python
# Add to every agent span root
span.set_attribute("ota.agent.name", agent_name)          # e.g. "trade-evaluation-agent"
span.set_attribute("ota.agent.stage", stage)               # "triage" | "deep_dive" | "followup"
span.set_attribute("ota.trade.key", trade_key)             # "{symbol}:{spread}:{expiration}"
span.set_attribute("ota.trade.symbol", symbol)
span.set_attribute("ota.session.id", session_id)           # links triage → deep_dive → followup
span.set_attribute("ota.verdict", verdict)                 # populated after LLM call
span.set_attribute("ota.prompt.version", prompt_version)   # from SKILL.md frontmatter
span.set_attribute("ota.prior_recommendation", had_prior)  # true/false
```

### Python Instrumentation Boilerplate (copy into every agent module)

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.trace import SpanKind
import os

# Called once at app startup (in main.py)
def init_agent_telemetry():
    configure_azure_monitor(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
        enable_live_metrics=True,
    )

# Used in every agent call
tracer = trace.get_tracer("ota.agents")

async def invoke_with_tracing(agent_name: str, stage: str, trade_key: str, fn, **kwargs):
    with tracer.start_as_current_span(
        f"{agent_name}/{stage}",
        kind=SpanKind.INTERNAL
    ) as span:
        span.set_attribute("ota.agent.name", agent_name)
        span.set_attribute("ota.agent.stage", stage)
        span.set_attribute("ota.trade.key", trade_key)
        try:
            result = await fn(**kwargs)
            span.set_attribute("ota.verdict", result.get("verdict", "unknown"))
            return result
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            raise
```

### Sensitive Data Policy

| Environment | `ENABLE_SENSITIVE_DATA` | What's logged |
|-------------|------------------------|---------------|
| Local dev   | `true` | Full prompts, model responses, function args |
| Azure dev   | `false` | Metadata only (tokens, latency, verdict, trade_key) |
| Production  | `false` | Metadata only — never log full prompt/response text |

The full prompt text is always stored separately in the `agent_run_log` table in Azure SQL
(see Data Persistence section below). OpenTelemetry carries the structural trace; SQL carries
the full content for auditability.

---

## Data Persistence — Full Audit Trail

OpenTelemetry traces expire after 90 days (Application Insights default) and are not
queryable with the full relational structure needed for recommendation analysis.

The solution is a two-track persistence model:

**Track A — Telemetry (Foundry / Application Insights)**
- Purpose: real-time monitoring, debugging, performance analysis
- Retention: 90 days (configurable in Log Analytics)
- Query via: Foundry Observability portal, Azure Monitor, KQL queries

**Track B — Business Record (Azure SQL)**
- Purpose: full audit trail, recommendation history, effectiveness measurement
- Retention: indefinite
- Query via: Azure SQL, Power BI, Microsoft Fabric (future)

### Azure SQL Tables for Agent Audit Trail

```sql
-- Every agent invocation, every stage, every run
CREATE TABLE agent_run_log (
    id                  BIGINT IDENTITY PRIMARY KEY,
    run_id              UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),  -- links multi-stage sessions
    agent_name          NVARCHAR(100) NOT NULL,
    stage               NVARCHAR(50) NOT NULL,      -- triage | deep_dive | followup
    trade_key           NVARCHAR(255),              -- "{symbol}:{spread}:{expiration}"
    symbol              NVARCHAR(20),
    user_id             INT REFERENCES users(id),
    
    -- Full inputs (what was sent to the model)
    prompt_system       NVARCHAR(MAX),
    prompt_user         NVARCHAR(MAX),
    prompt_version      NVARCHAR(50),
    market_snapshot     NVARCHAR(MAX),              -- JSON: price, SMAs, VIX at call time
    trade_snapshot      NVARCHAR(MAX),              -- JSON: trade metrics at call time
    
    -- Full outputs
    model_response_raw  NVARCHAR(MAX),              -- raw model text
    verdict             NVARCHAR(20),               -- EXECUTE | WAIT | PASS | STRONG | MEDIUM | WEAK
    verdict_summary     NVARCHAR(MAX),
    
    -- Telemetry linkage
    otel_trace_id       NVARCHAR(64),               -- links to Application Insights trace
    
    -- Performance
    input_tokens        INT,
    output_tokens       INT,
    latency_ms          INT,
    model_name          NVARCHAR(100),
    
    -- Timestamps
    created_at          DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

-- Persisted recommendations (the "what Claude said" record, queryable by trade)
-- This is the same table defined in the trade agent SKILL.md — reproduced here for completeness
CREATE TABLE trade_recommendations (
    id                  INT IDENTITY PRIMARY KEY,
    trade_key           NVARCHAR(255) NOT NULL UNIQUE,
    symbol              NVARCHAR(20) NOT NULL,
    spread_label        NVARCHAR(100) NOT NULL,
    expiration          NVARCHAR(20) NOT NULL,
    verdict             NVARCHAR(20) NOT NULL,
    rank                NVARCHAR(20),
    verdict_summary     NVARCHAR(MAX) NOT NULL,
    market_snapshot     NVARCHAR(MAX) NOT NULL,
    trade_snapshot      NVARCHAR(MAX) NOT NULL,
    run_id              UNIQUEIDENTIFIER,           -- links back to agent_run_log
    prompt_version      NVARCHAR(50),
    evaluated_at        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at          DATETIME2
);
```

The `run_id` column links a stored recommendation back to its full input/output record
in `agent_run_log`. That means for any recommendation you can always answer:
"what exactly did the model see, what did it say, and what did the market look like?"

---

## Prompt Loading Pattern

All prompts live in SKILL.md files under `app/skills/{agent-name}/SKILL.md`.
A shared loader utility parses and serves them. No prompt text ever appears in Python code.

```
app/
└── skills/
    ├── skill_loader.py               ← shared utility (build once, used by all agents)
    ├── claude-trade-agent/
    │   └── SKILL.md
    └── (future agents)/
        └── SKILL.md
```

### `skill_loader.py` — Prompt Loader Utility

```python
"""
Loads named prompt sections from a SKILL.md file.
Sections are delimited by ### headers followed by a fenced code block.

Usage:
    loader = SkillLoader("claude-trade-agent")
    system = loader.get("DEEP_DIVE_SYSTEM")
    user = loader.render("DEEP_DIVE_USER", symbol="QQQ", current_price=459.44, ...)
"""

import re
from pathlib import Path
from functools import lru_cache


class SkillLoader:
    SKILLS_DIR = Path(__file__).parent

    def __init__(self, skill_name: str):
        skill_path = self.SKILLS_DIR / skill_name / "SKILL.md"
        self._sections = self._parse(skill_path.read_text())
        # extract prompt_version from frontmatter if present
        self.prompt_version = self._extract_version(skill_path.read_text())

    def get(self, section_name: str) -> str:
        """Return the raw text of a named prompt section."""
        if section_name not in self._sections:
            raise KeyError(f"Prompt section '{section_name}' not found in SKILL.md")
        return self._sections[section_name]

    def render(self, section_name: str, **kwargs) -> str:
        """Render a prompt template, filling {{variable}} slots."""
        template = self.get(section_name)
        # Handle {{#if var}}...{{/if}} blocks
        template = self._process_conditionals(template, kwargs)
        # Fill {{variable}} slots
        for key, value in kwargs.items():
            template = template.replace(f"{{{{{key}}}}}", str(value) if value is not None else "")
        return template

    def _parse(self, text: str) -> dict:
        """Extract named fenced code blocks from markdown.
        Looks for pattern:  ### Section Name (`SECTION_KEY`)\n```\n...\n```
        """
        pattern = r"###.*?\(`([A-Z_]+)`\)\n```[a-z]*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        return {name: content.strip() for name, content in matches}

    def _process_conditionals(self, template: str, ctx: dict) -> str:
        """Remove {{#if var}}...{{/if}} blocks when var is falsy."""
        pattern = r"\{\{#if (\w+)\}\}(.*?)\{\{/if\}\}"
        def replace(m):
            var, block = m.group(1), m.group(2)
            return block if ctx.get(var) else ""
        return re.sub(pattern, replace, template, flags=re.DOTALL)

    def _extract_version(self, text: str) -> str:
        match = re.search(r"^version:\s*(.+)$", text, re.MULTILINE)
        return match.group(1).strip() if match else "unversioned"


@lru_cache(maxsize=16)
def get_skill(skill_name: str) -> SkillLoader:
    """Cached loader — reads file once per process lifecycle."""
    return SkillLoader(skill_name)
```

---

## Multi-Agent Orchestration Pattern (Foundry Agent Service)

When the project grows to multiple agents, they are coordinated via
**Foundry Agent Service multi-agent workflows**. The pattern is:

```
Orchestrator Agent (Foundry-managed)
│
├── calls → Trade Evaluation Agent  (handles triage, deep-dive, followup)
├── calls → Portfolio Risk Agent    (future)
└── calls → Market Scan Agent       (future)
```

The orchestrator is a thin routing layer. It:
1. Receives the user intent from the FastAPI backend
2. Decides which specialist agent(s) to invoke
3. Passes results back, optionally chaining agents together
4. Is the single entity that Agent 365 sees as "the Options Analyzer agent"

**Why this matters now**: each specialist agent you build today should be registered in
Foundry as an individual agent with its own ID and SKILL.md. When the orchestrator is added,
it connects to them via the Agent2Agent (A2A) protocol — a standard Microsoft supports natively.
You don't have to rebuild anything. You add the orchestrator and wire connections.

### Foundry Registration Checklist (per agent)

When registering an agent in the Foundry portal:
- [ ] Give the agent a clear name: `ota-trade-evaluation-agent`
- [ ] Paste the `DEEP_DIVE_SYSTEM` prompt as the agent instructions
- [ ] Connect the Claude model deployment (`ota-foundry` → Claude endpoint)
- [ ] Enable tracing → connect `ota-insights` Application Insights resource
- [ ] Note the assigned Entra Agent ID — record it in the agent's SKILL.md frontmatter
- [ ] Apply tags: `project=options-trade-analyzer`, `environment=dev`, `component=ai`, `owner=don`

---

## Agent 365 Readiness Checklist

Agent 365 is Microsoft's forthcoming enterprise agent management surface, currently in
public preview as "deploy agents to Microsoft 365 and Agent 365" from Foundry.
It will eventually be the place to manage, monitor, and govern all agents across your tenant.

**What you're doing now that makes Agent 365 migration a configuration step, not a rebuild:**

| What you're doing now | Why it matters for Agent 365 |
|-----------------------|------------------------------|
| Registering each agent in Foundry with its own ID | Agent 365 manages Foundry-registered agents natively |
| Assigning Entra Agent IDs | Agent 365 governance is identity-based |
| Emitting standard OTel traces | Agent 365 monitoring consumes the same Application Insights feed |
| Using Foundry's model endpoints (not direct API) | Agent 365 can apply model policies centrally |
| Structured SKILL.md prompts with version tracking | Agent 365 will support prompt governance/approval workflows |
| A2A-compatible agent boundaries | Agent 365 can compose multi-agent workflows from the M365 surface |

**What you defer until Agent 365 is generally available:**
- Publishing agents to Microsoft Teams or Copilot Chat
- Setting tenant-wide governance policies on agent behavior
- Using Agent 365's approvals/human-in-the-loop controls
- Managing agent fleet from the M365 Admin Center

---

## Adding a New Agent — Checklist

When building any new agent in this project, follow this sequence:

1. **Create `app/skills/{agent-name}/SKILL.md`** — define all prompts, I/O schemas,
   and the agent's stage flow. Follow the format established in `claude-trade-agent/SKILL.md`.

2. **Add `version:` to the SKILL.md frontmatter** — increment this when prompts change
   significantly. It flows into `agent_run_log.prompt_version` for historical tracing.

3. **Build the route module** in `app/api/{agent_name}_routes.py`. Use `get_skill()`
   from `skill_loader.py` — no prompt text in Python.

4. **Instrument every agent call** using the `invoke_with_tracing()` wrapper defined in
   this skill. Emit the custom `ota.*` span attributes.

5. **Write to `agent_run_log`** for every completed stage — full inputs and outputs.

6. **Register in Foundry portal** — follow the registration checklist above.
   Connect Application Insights. Note the Entra Agent ID and add it to the SKILL.md frontmatter.

7. **Add to the milestone table** in `030126_-_PROJECT-PLAN.md` with phase and dependencies.

8. **Update `azure-naming-conventions.md`** if any new Azure resources are created.

---

## References

- Azure AI Foundry Agent Service: https://azure.microsoft.com/en-us/products/ai-foundry/agent-service/
- Microsoft Agent Framework (Semantic Kernel + AutoGen): https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/
- Foundry Observability / Tracing: https://learn.microsoft.com/en-us/azure/foundry/concepts/observability
- OTel trace setup: https://learn.microsoft.com/en-us/azure/ai-foundry/observability/how-to/trace-agent-setup
- Agent 365 preview: Foundry portal → Agent Service → Publish to Microsoft 365
- Multi-agent workflows: Foundry portal → Agent Service → Workflows
