# Options Analyzer — architecture-plan.md (Updated 2026-04-11 22:00)
# Epic: OTA-477 | Feature: OTA-481

## Table of Contents

- [What This Document Is](#what-this-document-is)
- [Core Architectural Patterns](#core-architectural-patterns)
  - [Pattern 1: Provider Adapter Pattern](#pattern-1-provider-adapter-pattern)
  - [External Credential Management](#external-credential-management)
  - [Pattern 2: Skill-Driven Prompt Architecture](#pattern-2-skill-driven-prompt-architecture)
  - [Pattern 3: Two-Track Observability](#pattern-3-two-track-observability)
  - [Pattern 4: Unified Position Model](#pattern-4-unified-position-model)
  - [Pattern 5: Generic Insight Engine](#pattern-5-generic-insight-engine)
  - [Pattern 6: Backend-for-Frontend Identity](#pattern-6-backend-for-frontend-identity)
  - [Pattern 7: Unified Deployment](#pattern-7-unified-deployment)
- [The Three-Layer Architecture](#the-three-layer-architecture)
  - [Layer 1 — Execution](#layer-1--execution)
  - [Layer 2 — Orchestration](#layer-2--orchestration)
  - [Layer 3 — Management (Agent 365)](#layer-3--management-agent-365)
- [System Structure](#system-structure)
  - [Backend Structure](#backend-structure)
  - [Frontend Structure](#frontend-structure)
- [Data Models (Azure SQL)](#data-models-azure-sql)
- [Key API Endpoints](#key-api-endpoints)
- [End-to-End Data Flow](#end-to-end-data-flow)
- [The Strategy System](#the-strategy-system)
  - [What a Strategy Is](#what-a-strategy-is)
  - [Strategy Config Schema Pattern](#strategy-config-schema-pattern)
- [The Positions System](#the-positions-system)
  - [Position Lifecycle](#position-lifecycle)
  - [Health Grade Computation](#health-grade-computation)
- [The Insight Engine](#the-insight-engine)
  - [Architecture](#architecture)
  - [Insight Data Model](#insight-data-model)
  - [SKILL.md Structure](#skillmd-structure)
  - [Dashboard Feed](#dashboard-feed)
- [The Market Intelligence Aggregator](#the-market-intelligence-aggregator)
  - [Symbol Context Store](#symbol-context-store)
  - [Position Monitor Agent](#position-monitor-agent)
- [Black-Scholes Probability Matrix](#black-scholes-probability-matrix)
- [Claude Structured Evaluation](#claude-structured-evaluation)
  - [Evaluation Flow](#evaluation-flow)
  - [Entry Points](#entry-points)
- [Observability](#observability)
- [Agent Inventory](#agent-inventory)
  - [Agent CLAUDE.md Convention](#agent-claudemd-convention)
- [The Multi-Agent Future](#the-multi-agent-future)
- [Agent 365 Readiness](#agent-365-readiness)
- [Azure Resources Summary](#azure-resources-summary)
- [Phase History](#phase-history)

---

## What This Document Is

This is the architectural specification for the Options Trade Analyzer. It describes
why the system is designed the way it is, how data flows through it, and how agents
are built, deployed, observed, and governed.

Read this document to understand **why** the pattern is designed the way it is.
Read `CLAUDE.md` for **how** to work in the repo.
Read `business-rules.md` for **what** the system calculates and enforces.
Read `UI-GUIDANCE.md` for **what the UI looks like** and user journeys.
Read `auth-process.md` for **how auth works** (flows, sessions, security).

---

## Core Architectural Patterns

These patterns are permanent foundations. ALL new features must follow them.

### Pattern 1: Provider Adapter Pattern

All external data sources — market data, AI models, brokerages, and signal
sources — implement a standard interface. Adding a new source requires writing one
adapter class. Zero changes to engines, routes, or frontend.

**Established adapters**: SchwabMarketData, AnthropicAdapter, FoundryAdapter
**Future adapters**: SocialSentimentProvider, FundamentalsProvider, AlternateBrokerageProvider

Every adapter implements:
```python
class ContextSource(ABC):
    source_id: str          # unique identifier e.g. "schwab_quotes"
    signal_type: str        # PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS
    async def fetch(self, symbol: str) -> dict
    def normalize(self, raw: dict) -> ContextSignal
    def ttl_seconds(self) -> int   # how long this signal stays fresh
```

### External Credential Management

Each provider adapter owns its credential lifecycle. The calling code (engines,
routes, agents) calls `provider.fetch()` and never knows how the credential was
obtained. OAuth, federation, API key, service account — the adapter chooses
whatever is appropriate for its source. All credentials are stored and managed
server-side.

| Credential | Auth Method | Where Stored | Managed By |
|------------|------------|-------------|------------|
| Schwab market data | OAuth 2.0 (authorization code) | In-memory (dev) / Key Vault (prod) | `SchwabTokenManager` |
| Azure AI Foundry | API key | Key Vault | `SecretsManager` |
| Future brokerage (Fidelity, etc.) | OAuth or API key (source-dependent) | Key Vault | New provider adapter |
| Future data (Bloomberg, Census, etc.) | Federation, API key, or service account | Key Vault | New provider adapter |

Adding a new external credential = one Key Vault secret + one provider adapter.
The connectivity layer is uniform; the auth method is source-specific.

### Pattern 2: Skill-Driven Prompt Architecture

Every AI prompt lives in a SKILL.md file under `app/skills/{skill_name}/SKILL.md`.
Python loads these via `skill_loader.py`. No prompts are hardcoded in Python or React.

This means:
- Prompts can be tuned without code changes
- Prompt version is recorded with every AI call in `agent_run_log`
- Prompt engineering is measurable and auditable

### Pattern 3: Two-Track Observability

Every AI agent invocation produces two records simultaneously:
- **OpenTelemetry trace** → Application Insights (`ota-insights`) — real-time monitoring
- **Business record** → Azure SQL `agent_run_log` — permanent audit, never expires

The SQL record links back to the OTel trace via `trace_id`. This allows correlating
"what did Claude recommend" with "what actually happened to the position."

### Pattern 4: Unified Position Model

Paper follows and live trades share an identical data model. The only distinguishing
fields are `source` (PAPER | LIVE) and `status` (FOLLOWING | LIVE | CLOSED).
The Positions page, monitoring agent, and aggregate analytics work identically
for both. Live execution flips `source` from PAPER to LIVE without touching any
other infrastructure.

### Pattern 5: Generic Insight Engine

The Insight Engine is a domain-agnostic pattern for detect → score → communicate
anomalies. It is deployed first in the options domain but is designed to be reused
in manufacturing, customer health, and any other monitoring scenario.

The domain-specific parts are:
1. The `ObservationSource` adapter (what to watch)
2. The SKILL.md prompt template (how to frame the insight for that domain)

Everything else — deviation detection, insight data model, dashboard rendering,
dismissal flow — is generic and reused across domains.

### Pattern 6: Backend-for-Frontend Identity

FastAPI is the OIDC confidential client. The browser never holds tokens — only
HttpOnly session cookies. Multi-IdP support via a provider registry. Certificate-based
credentials (tenant blocks secrets).

See `auth-process.md` for full implementation details including session lifecycle,
security controls, and Entra app registration.

### Pattern 7: Unified Deployment

FastAPI serves both the API (`/api/v1/*`) and the React SPA (from `static/`
directory) from a single App Service on a single domain (`oa.tmtctech.ai`).
Cloudflare provides CDN and edge caching. One GitHub Actions workflow handles build
and deploy.

In development, the frontend and backend run as separate processes: FastAPI on port
8000 and Vite dev server on port 5173. The static mount in FastAPI only activates when
`static/index.html` exists (production builds only).

---

## The Three-Layer Architecture

Agents live across three layers. Build from the bottom up, but design for all three.

### Layer 1 — Execution
FastAPI backend, Python agent code, and SKILL.md prompt files. Each agent is a
focused specialist that does one thing well.

### Layer 2 — Orchestration
Azure AI Foundry Agent Service. Agents are registered here, multi-agent workflows
are defined, and handoffs between agents are managed.

### Layer 3 — Management (Agent 365)
Microsoft Agent 365 is the enterprise management surface for agents running in a
tenant. By building correctly in Layers 1 and 2 — with Foundry-registered agents,
Entra identities, and standard OpenTelemetry traces — everything built today
appears in Agent 365 automatically when it becomes generally available.

---

## System Structure

### Backend Structure

```
app/
├── main.py                          # FastAPI entry point, lifespan context, CORS
├── core/
│   ├── config.py                   # Pydantic Settings (from .env)
│   └── secrets.py                  # SecretsManager (Azure Key Vault + .env fallback)
├── auth/
│   ├── service.py                  # BFF auth: OIDC, sessions, token exchange
│   └── dependencies.py             # require_tier1/2/3 FastAPI dependencies
├── models/
│   ├── database.py                 # SQLAlchemy models
│   ├── session.py                  # Async DB engine and session factory
│   └── schemas.py                  # Pydantic request/response schemas
├── providers/
│   ├── base.py                     # Abstract interfaces (MarketData, ContextSource)
│   ├── tradier.py                  # Tradier adapter (fallback)
│   ├── schwab.py                   # Schwab adapter (primary)
│   ├── schwab_token_manager.py     # OAuth token lifecycle
│   ├── factory.py                  # ProviderFactory
│   └── ai.py                       # AnthropicAdapter + FoundryAdapter
├── analysis/
│   ├── vertical_engine.py          # Bull call / bear put spread scoring
│   ├── long_call_engine.py         # Naked calls/puts scoring
│   ├── directional_engine.py       # SMA momentum + directional scoring
│   ├── black_scholes.py            # Probability matrix computation
│   ├── strategy_scorer.py          # Multi-strategy scorecard engine
│   └── strategy_definitions.py     # Strategy parameter definitions (thresholds, weights)
├── agents/
│   ├── position_monitor.py         # Daily position health agent
│   ├── insight_engine.py           # Generic insight detection + generation
│   └── skill_loader.py             # Loads SKILL.md files, fills variables
├── skills/
│   ├── claude-trade-agent/
│   │   └── SKILL.md
│   ├── position-monitor/
│   │   └── SKILL.md
│   └── insight-engine/
│       ├── SKILL.md                # Generic pattern
│       └── domains/
│           └── options/
│               └── SKILL.md        # Options-specific vocabulary
└── api/
    ├── auth_routes.py              # BFF auth endpoints (login, callback, session, logout)
    ├── market_routes.py
    ├── config_routes.py
    ├── analysis_routes.py
    ├── schwab_auth_routes.py
    ├── evaluation_routes.py        # Structured output
    ├── dashboard_routes.py         # Dashboard layout GET/PUT + media SAS URLs
    ├── position_routes.py          # Position CRUD, follow, take-position
    └── insight_routes.py           # Insight feed, dismiss
```

### Frontend Structure

```
web/
├── .env.production                      # Production API base URL (HTTPS)

web/src/
├── App.jsx                              # Routes + activeStrategy state
├── main.jsx                             # React root
├── context/
│   └── AppContext.jsx                   # activeSymbol, watchlist, favorites, prices
├── api/
│   └── client.js                        # API client functions (uses cookie auth)
├── strategy-configs/                    # Strategy plugin system
│   ├── index.js                         # Registry: maps key → config object
│   ├── verticals.config.js
│   ├── long-calls.config.js
│   ├── steady-paycheck.config.js
│   ├── weekly-grind.config.js
│   ├── trend-rider.config.js
│   └── lottery-ticket.config.js
├── components/
│   ├── Layout.jsx                       # Left rail + watchlist toggle + Outlet
│   ├── Watchlist.jsx
│   ├── QuoteBar.jsx
│   ├── ConfigDrawer.jsx                 # Strategy-aware config schema
│   ├── StrategyScorecard.jsx            # Multi-strategy score display
│   ├── TradeEvaluationCard.jsx          # Structured Claude output card
│   ├── ProbabilityMatrix.jsx            # B-S probability table
│   ├── PositionHealthBadge.jsx          # A-F grade indicator
│   ├── InsightCard.jsx                  # Dashboard insight feed card
│   └── ...
└── pages/
    ├── TradesPage.jsx                   # Unified trades terminal — Sections A-E
    ├── SecurityStrategiesPage.jsx       # Scan screen
    ├── StrategyPage.jsx                 # Per-strategy detail
    ├── PositionsPage.jsx                # Positions with health grades
    └── DashboardPage.jsx                # Insight feed + widgets
```

---

## Data Models (Azure SQL)

All tables use UNIQUEIDENTIFIER PKs and DATETIME2 timestamps.

### positions

```sql
CREATE TABLE positions (
    position_id           UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    user_id               UNIQUEIDENTIFIER NOT NULL,
    symbol                NVARCHAR(20) NOT NULL,
    strategy_key          NVARCHAR(50) NOT NULL,       -- 'steady-paycheck', 'trend-rider'
    trade_structure       NVARCHAR(MAX) NOT NULL,      -- JSON: legs, strikes, expiry
    source                NVARCHAR(10) NOT NULL,       -- 'PAPER' | 'LIVE'
    status                NVARCHAR(20) NOT NULL,       -- 'FOLLOWING'|'LIVE'|'CLOSED'
    entry_price           DECIMAL(10,4),
    entry_date            DATETIME2 NOT NULL,
    entry_greeks          NVARCHAR(MAX),               -- JSON: delta, gamma, theta, vega
    entry_iv_rank         DECIMAL(5,2),
    entry_sma_alignment   NVARCHAR(MAX),               -- JSON: SMA values + signal
    entry_underlying_price DECIMAL(10,4),
    claude_probability_matrix NVARCHAR(MAX),           -- JSON: B-S matrix at entry
    claude_exit_levels    NVARCHAR(MAX),               -- JSON: warning, scale_out, stop
    claude_verdict        NVARCHAR(MAX),               -- JSON: full evaluation card
    claude_score          INT,                         -- 0-100
    health_grade          NVARCHAR(2),                 -- 'A'|'B'|'C'|'D'|'F'
    current_price         DECIMAL(10,4),               -- updated by monitor agent
    current_pnl           DECIMAL(10,4),               -- updated by monitor agent
    last_monitored_at     DATETIME2,
    exit_price            DECIMAL(10,4),
    exit_date             DATETIME2,
    exit_reason           NVARCHAR(50),                -- TARGET|WARNING|STOP|EXPIRED|MANUAL
    outcome_pnl           DECIMAL(10,4),
    created_at            DATETIME2 DEFAULT GETUTCDATE(),
    updated_at            DATETIME2 DEFAULT GETUTCDATE()
)
```

### symbol_context

```sql
CREATE TABLE symbol_context (
    context_id    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    symbol        NVARCHAR(20) NOT NULL,
    source_id     NVARCHAR(50) NOT NULL,
    signal_type   NVARCHAR(50) NOT NULL,
    signal_value  NVARCHAR(MAX) NOT NULL,
    captured_at   DATETIME2 DEFAULT GETUTCDATE(),
    expires_at    DATETIME2 NOT NULL
)
```

### insights

```sql
CREATE TABLE insights (
    insight_id          UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    domain              NVARCHAR(50) NOT NULL,
    entity_id           NVARCHAR(100) NOT NULL,
    entity_label        NVARCHAR(200) NOT NULL,
    observation         NVARCHAR(MAX) NOT NULL,
    baseline            NVARCHAR(MAX) NOT NULL,
    deviation_score     INT NOT NULL,
    deviation_type      NVARCHAR(50) NOT NULL,
    title               NVARCHAR(200) NOT NULL,
    body                NVARCHAR(1000) NOT NULL,
    severity            NVARCHAR(20) NOT NULL,
    recommended_actions NVARCHAR(MAX),
    status              NVARCHAR(20) DEFAULT 'ACTIVE',
    source_signals      NVARCHAR(MAX),
    agent_run_id        UNIQUEIDENTIFIER,
    created_at          DATETIME2 DEFAULT GETUTCDATE(),
    dismissed_at        DATETIME2,
    acted_on_at         DATETIME2
)
```

### agent_run_log

Every AI agent invocation writes one row. Never deleted. Contains full prompt text,
full model response, market snapshot, prompt version, and OTel `trace_id`.

### user_sessions

See `auth-process.md` for schema and session lifecycle.

---

## Key API Endpoints

### Strategy Scoring
- `POST /api/v1/analyze/scorecard` — runs all strategies for a symbol, returns 0-100 per strategy
- `POST /api/v1/analyze/probability-matrix` — Black-Scholes matrix for a trade

### Structured Evaluation
- `POST /api/v1/evaluate/structured` — Claude deep dive, returns structured cards

### Positions
- `POST /api/v1/positions/follow` — create paper position from evaluation
- `POST /api/v1/positions/take` — create live position (records intent, not yet wired to Schwab)
- `GET /api/v1/positions` — list with filters: status, source, symbol, strategy
- `PATCH /api/v1/positions/{id}/close` — close position, record outcome
- `GET /api/v1/positions/aggregate` — stats by strategy group

### Position Monitor
- `POST /api/v1/agents/position-monitor/run` — on-demand trigger (also runs on schedule)

### Insights
- `GET /api/v1/insights` — active insights feed, filtered by domain='options'
- `PATCH /api/v1/insights/{id}/dismiss` — dismiss insight

### Auth (BFF)
- `GET /api/v1/auth/entra/login` — initiate OIDC login
- `GET /api/v1/auth/entra/callback` — handle OIDC callback
- `GET /api/v1/auth/session` — session info (from cookie)
- `POST /api/v1/auth/logout` — destroy session

---

## End-to-End Data Flow

```
User pulls up MSFT
    ↓
Security Strategies page loads
    ├── Fetches current quote + SMA data (Schwab)
    ├── Runs all strategy scoring engines (backend)
    ├── Reads active insights for MSFT (insight feed)
    └── Renders strategy scorecard (0-100 per strategy)
    ↓
User selects strategies and clicks "Evaluate"
    ↓
Claude structured evaluation runs
    ├── Black-Scholes probability matrix (backend math, not Claude)
    ├── Claude deep dive per strategy (Foundry endpoint)
    ├── Returns: probability matrix + trade card + exit levels
    └── Writes to agent_run_log
    ↓
User clicks "Follow" or "Take Position"
    ↓
Position created in Azure SQL
    ├── Full entry snapshot: trade, Greeks, IV, SMA, Claude output
    ├── source = PAPER or LIVE
    └── status = FOLLOWING or LIVE
    ↓
Position Monitor Agent runs daily (after market close)
    ├── Reads all open positions
    ├── Reads current context from symbol_context (all sources)
    ├── Computes health grade A-F
    ├── Detects threshold crossings
    └── If deviation detected → Insight Engine runs
            ↓
        Insight Engine
            ├── Builds observation + baseline + deviation context
            ├── Calls Claude with domain SKILL.md prompt
            ├── Receives structured insight (title, body, severity, actions)
            ├── Writes to insights table
            └── Insight appears on Dashboard feed
```

---

## The Strategy System

### What a Strategy Is

A strategy is a named configuration of trade structure, DTE window, scoring weights,
filter thresholds, config schema (user-adjustable parameters), and Greek targets.

See `business-rules.md` for the complete strategy definitions including DTE ranges,
delta targets, exit rules, and scoring weight formulas per strategy.

### Strategy Config Schema Pattern

Each strategy defines a `configSchema` in its config file. ConfigDrawer renders
whatever schema the active strategy defines — a dynamic, strategy-aware parameter set.

```javascript
configSchema: [
  { key: 'dte_min', label: 'Min DTE', type: 'slider', min: 1, max: 60, default: 30 },
  { key: 'delta_max', label: 'Max Short Delta', type: 'slider', min: 0.10, max: 0.50, default: 0.30 },
  { key: 'iv_rank_min', label: 'Min IV Rank', type: 'slider', min: 0, max: 100, default: 40 },
  { key: 'exit_profit_pct', label: 'Take Profit %', type: 'slider', min: 25, max: 90, default: 50 },
]
```

---

## The Positions System

### Position Lifecycle

See `business-rules.md` for the full position lifecycle state machine, exit reasons,
and aggregate analysis rules.

```
CREATED (Follow or Take Position action)
    ↓
ACTIVE (monitoring begins)
    ↓
ALERTED (health grade degraded, insight generated)
    ↓
CLOSED (user action or expiration)
    ├── exit_reason: TARGET | WARNING | STOP | EXPIRED | MANUAL
    └── outcome recorded for aggregate analysis
```

### Health Grade Computation

See `business-rules.md` for grade definitions and computation rules. Grades are
computed by the Position Monitor Agent daily using deterministic math against
Claude's exit levels stored at position entry. Not a Claude call.

---

## The Insight Engine

### Architecture

```
InsightEngine
    ├── ObservationSource (interface — domain-specific implementations)
    ├── DeviationDetector (generic)
    │   ├── ThresholdRule
    │   ├── TrendRule (degrading N consecutive periods)
    │   ├── AnomalyRule (N standard deviations from baseline)
    │   └── CorrelationRule (two signals moving together unusually)
    ├── InsightGenerator (Claude call, domain SKILL.md)
    └── InsightRouter
        ├── dashboard_feed
        ├── notification (future)
        └── escalation_log → agent_run_log
```

### Insight Data Model

See [Data Models (Azure SQL)](#data-models-azure-sql) for the `insights` table schema.

### SKILL.md Structure

```
app/skills/
    insight-engine/
        SKILL.md              ← generic insight pattern
        domains/
            options/
                SKILL.md      ← options vocabulary, exit levels, position context
            manufacturing/
                SKILL.md      ← production metrics, quality thresholds (future)
```

### Dashboard Feed

Active insights appear on the home Dashboard page, most severe first.
Each card shows: severity icon, title, body (2-3 sentences), two action buttons.
Actions are defined by Claude in the insight's `recommended_actions` field —
typically "View Position" (navigates to Positions page filtered to that entity)
and "Dismiss" (marks status=DISMISSED, removes from feed).

---

## The Market Intelligence Aggregator

### Symbol Context Store

All signal sources write to a single normalized table (`symbol_context`). See
[Data Models](#data-models-azure-sql) for the schema.

Freshness windows by signal type:
- PRICE: 5 minutes
- TECHNICAL (SMA, IV): 1 hour
- SENTIMENT: 4 hours
- FUNDAMENTAL: 7 days
- NEWS/EVENTS: 24 hours

### Position Monitor Agent

First consumer of the symbol context store. Runs as a scheduled FastAPI background task
after market close (4:15pm ET). Also callable on-demand from the Positions page.

Responsibilities:
1. Read all ACTIVE positions from SQL
2. For each position, load current context from `symbol_context`
3. Compute health grade against enriched context
4. Detect threshold crossings using DeviationDetector rules
5. For each detected deviation, invoke Insight Engine
6. Write health grade updates and insight records to SQL
7. Log full run to `agent_run_log`

This agent has its own SKILL.md, its own Foundry registration, and its own Entra
Agent ID. It is the first of what will become a fleet of monitoring specialists.

---

## Black-Scholes Probability Matrix

The probability matrix shown in Claude's structured evaluation is computed by the
backend using Black-Scholes, NOT by Claude. Claude receives the pre-computed matrix
as context and uses it for qualitative commentary.

Backend endpoint: `POST /api/v1/analyze/probability-matrix`

Inputs: current price, IV, DTE, risk-free rate, price range (±10% in $10 steps)
Output: probability of price being at each level on dates: expiry-3, expiry-6, expiry-9, expiry

The matrix must be consistent, auditable, and fast.
Claude's role is judgment and communication, not arithmetic.

---

## Claude Structured Evaluation

Claude is a structured analytical engine that returns consistent, comparable output
cards. Each strategy returns a structured card:

### Evaluation Flow

1. User selects strategies on Security Strategies page or expands a trade row
2. Single "Evaluate" button triggers one Claude call per selected strategy
3. Each strategy returns:

```json
{
  "strategy": "Steady Paycheck",
  "trade_structure": "Sell 415P / Buy 410P, Dec 19",
  "entry_price": 2.45,
  "max_profit": 245,
  "max_loss": 255,
  "exit_warning_price": 412.50,
  "exit_price_debit": 4.90,
  "probability_matrix": { ... },
  "score": 84,
  "verdict": "EXECUTE | WAIT | PASS",
  "claude_read": "2-3 sentences on fit with current conditions",
  "recommended_actions": [
    {"label": "Follow", "action": "follow"},
    {"label": "Take Position", "action": "take_position"}
  ]
}
```

### Entry Points

The same evaluation flow is accessible from two places:
- **Security Strategies page**: trade is null, Claude finds best trade per strategy
- **Trade row expansion** (TradesPage): trade is pre-populated, Claude evaluates it through each strategy lens

Same component (`StrategyScorecard`), same Claude output format, two contexts.

---

## Observability

Every time Claude evaluates a trade, two things happen in parallel:

**The telemetry trace** flows to Application Insights via OpenTelemetry.

**The business record** is written to Azure SQL `agent_run_log` containing the full
prompt text, full model response, market snapshot, prompt version, and OTel trace ID.
This row never expires.

When Power BI and Microsoft Fabric are connected (future milestone), `agent_run_log`
joined with the `positions` table answers: "For every EXECUTE recommendation,
what was the actual outcome?" That question is only answerable because both records
are stored permanently.

---

## Agent Inventory

| Agent | Directory | Trigger | Purpose |
|-------|-----------|---------|---------|
| QA-UX | `agents/qa-ux/` | Post-build (Level 1-2) | Visual regression against ticket acceptance criteria |
| QA-Data | `agents/qa-data/` | Post-build (Level 2) | Data accuracy across 64-config matrix |
| Identity & Security | `agents/identity-security/` | Post-auth-change | Auth flow validation, session lifecycle |
| Position Monitor | `app/agents/position_monitor.py` | Daily (4:15pm ET) + on-demand | Health grades, threshold crossings, insight generation |
| Trade Evaluation | `app/skills/claude-trade-agent/` | User-initiated | Structured Claude analysis per strategy |

### Agent CLAUDE.md Convention

Every agent directory contains its own `CLAUDE.md` with agent-specific instructions,
thresholds, and behavioral rules. These are subordinate to the root `CLAUDE.md` and
must stay in sync with QA gate levels defined there. When modifying QA behavior,
update all five files: root `CLAUDE.md`, `qa-ux/CLAUDE.md`, `qa-data/CLAUDE.md`,
`fe-dev/CLAUDE.md`, `be-dev/CLAUDE.md`.

---

## The Multi-Agent Future

Today: Position Monitor Agent, Trade Evaluation Agent.

Near future: Portfolio Risk Agent (looks across all positions for correlation, sector
concentration, total delta exposure), Market Scan Agent (proactively surfaces
opportunities from watchlist without user initiating analysis).

All agents share the same observability infrastructure, the same SKILL.md pattern,
and the same Foundry registration approach. The orchestrator in Foundry routes
requests to the right specialist. Agents communicate via Agent2Agent (A2A) protocol.

---

## Agent 365 Readiness

Choices made now that make Agent 365 adoption a configuration step:
- Foundry-hosted agents → appear in Agent 365 automatically
- Entra Agent IDs → per-agent identity, policies, and audit trails
- Standard OpenTelemetry → Agent 365 monitoring reads the same feed
- Foundry model endpoints → model governance policies apply at endpoint level

---

## Azure Resources Summary

| Resource | Name | Purpose |
|----------|------|---------|
| App Service | `options-analyzer-api` | API + SPA hosting |
| AI Foundry | `ota-foundry-resource` | Agent deployment, model gateway |
| Application Insights | `ota-insights` | OTel trace sink |
| Log Analytics Workspace | `ota-logs` | Backend for App Insights |
| Azure SQL | `options-analyzer-db` | All persistent data |
| Key Vault | `options-analyzer` | All secrets |
| Storage | `otaunstructured` | Dashboard media, documents, backtest exports |

SQL tables: `agent_run_log`, `trade_recommendations`, `strategy_configs`, `positions`,
`symbol_context`, `insights`, `user_sessions`.

---

## Phase History

- **Phase 0**: Security & Authentication ✅
- **Phase 1**: Configuration & Market Data ✅
- **Phase 2.1-2.4**: Analysis Engines + AI Evaluation ✅
- **Phase 2.5**: Frontend Completion (partial) ✅
- **Phase 2.6**: Claude Trade Agent Redesign ✅
- **Phase 2.7**: Options Decision Terminal ✅
- **Phase 2.8**: Configurable System Variables, Dashboard, Schwab Routing ✅
- **Phase 2.9**: Security Dashboard + Strategy Scorecard ✅
- **Phase 2.10**: Positions Page + Follow/Take Position ✅
- **Phase 2.11**: Claude Structured Evaluation + Probability Matrix ✅
- **Phase 3**: Azure Deployment ✅ (live 2026-03-04 — App Service, unified deployment)
- **Phase 3.5**: Market Intelligence Aggregator + Position Monitor Agent ✅
- **Phase 3.6**: Insight Engine (Generic) + Options Domain ✅
- **Sprint 4**: Trades page unification, SecurityStrategiesPage v3 ✅
- **Sprint 5**: Regression cycle, startup visibility, MSAL fix ✅
- **Identity Management Foundation**: BFF identity, MSAL removal, certificate auth ✅
- **Unified Deployment**: SWA removed, FastAPI serves API + SPA, Cloudflare CDN ✅
- **Phase 4**: MCP Integration 🔲
- **Phase 5**: Live Trading Execution 🔲
