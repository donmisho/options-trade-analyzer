# OTA Agentic Architecture Plan
## Options Trade Analyzer — Phase 2.6 and Forward

---

## Strategy Scorecard — Scoring Engine Data Inputs (Phase 2.9)

`POST /api/v1/analyze/scorecard` — single chain fetch, four scores returned.

All four scores are calculated live from the options chain for the requested symbol.
There are no hardcoded values. Scores are 0–100, normalized with min-max scaling
across all candidates per strategy.

### Chain fetch
- `provider.get_chain(symbol, min_dte=0, max_dte=70, strike_range_pct=20)`
- Returns: `contracts[]`, `underlying_price`
- One fetch per scorecard call regardless of strategy count.

### Steady Paycheck — 25–50 DTE credit spreads
| Metric | Weight | Source |
|---|---|---|
| `theta_margin_ratio` | 30% | `abs(net_theta) / max_loss` — theta collected per dollar at risk |
| `probability_of_profit` | 25% | Delta-derived PoP from VerticalSpreadEngine |
| `expected_value` | 20% | `(credit × PoP) - (max_loss × (1-PoP))` |
| `reward_risk` | 15% | `credit / max_loss` |
| `iv_rank` | 10% | Proxy: `atm_iv / 0.60` clamped 0–1 (ATM IV from nearest 5 calls) |

### Weekly Grind — 5–16 DTE credit spreads
| Metric | Weight | Source |
|---|---|---|
| `theta_gamma_ratio` | 35% | `abs(net_theta) / max_loss` proxy (true gamma not in ScoredSpread) |
| `probability_of_profit` | 25% | Delta-derived PoP |
| `credit_width_pct` | 20% | `(credit / spread_width) × 100` — premium quality |
| `expected_value` | 15% | EV from VerticalSpreadEngine |
| `liquidity` | 5% | `long_volume + short_volume + long_oi + short_oi` |

### Trend Rider — 25–65 DTE long calls
| Metric | Weight | Source |
|---|---|---|
| `sma_alignment_score` | 30% | Client-supplied float 0–1 via `user_config.sma_alignment_score`; defaults to 0.5 |
| `delta_quality` | 25% | Proximity to 0.50–0.70 delta target range |
| `expected_value` | 20% | `delta × underlying × 0.05 - mid_price` |
| `iv_percentile_cost` | 15% | `1 - (iv_decimal / 1.0)` — lower IV = cheaper options for buyers |
| `runway_score` | 10% | `theta_runway_days` from LongCallEngine |

### Lottery Ticket — 1–8 DTE deep OTM calls
| Metric | Weight | Source |
|---|---|---|
| `payout_ratio` | 45% | `(delta × price × 0.10 × 100) / premium_dollars` — return on 10% move |
| `delta_otm_score` | 25% | `1 - (delta / 0.25)` — lower delta = more OTM = higher score |
| `bid_ask_tightness` | 20% | `1 - (bid_ask_spread_pct / 100)` — fill quality |
| `open_interest` | 10% | Raw OI on the contract |

### Why scores differ meaningfully per symbol
- **High-IV symbols** (SQQQ, leveraged ETFs): more premium available → higher Steady Paycheck / Weekly Grind scores
- **Trending symbols** with clean SMA stacks: `sma_alignment_score` driven by frontend SMA state → higher Trend Rider
- **Low-price / illiquid symbols**: fewer candidates in DTE windows → scores may be 0 (no candidates)
- **ATM IV proxy**: computed from the actual chain, so a symbol with 15% IV scores very differently from one with 60% IV

---

## What This Document Is

This is the architectural specification for how AI agents are built, deployed, observed,
and governed in the Options Trade Analyzer. It is the companion to SKILL.md files under
`app/skills/`.

Read this document to understand **why** the pattern is designed the way it is.
Read the SKILL.md files when you're actually building.

---

## Critical Shared UI Components

These components must be implemented ONCE and reused identically across every page.
Never reimplement them inline. See `UI-DECISIONS.md` for the complete visual contract.

### Navigation Bar — Final Tab Order

```
Dashboard | Security Strategies | Verticals | Puts & Calls | Positions
```

"Security Strategies" is named deliberately — "Security" alone is ambiguous with
login/firewall security. Clicking a watchlist symbol navigates to Security Strategies
for that symbol. The nav tab uses the currently active symbol.

Strategy tabs (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket) do NOT
appear as top-level navigation. They are scoring lenses, not pages.

### QuoteBar — Universal Symbol Header

**Used on**: SecurityStrategies, OptionsTerminal (Verticals), OptionsTerminal (Puts & Calls),
and any future page that displays a symbol context.

**File**: `web/src/components/QuoteBar.jsx`

**Required fields in this exact order**:
| Field | Notes |
|-------|-------|
| Symbol | Large, bold |
| SIGNAL badge | BULLISH / BEARISH / MIXED — from SMA alignment |
| Last Analyzed | Timestamp of last analysis run |
| Price | Current last price |
| CHG | Dollar change, red if negative |
| CHG % | Percent change, red if negative |
| Day Range | Low – High |
| 52W Range | 52-week Low – High |
| Volume | Formatted (35.6M) |
| Rel Vol | Relative volume (0.8x) |
| Earnings Date | Show if within 60 days, highlight if within 14 days. Hide if none known. |
| Dividend Date | Show if within 60 days. Hide if none known. |

**Rules**:
- No `$` prefix on any value — house style applies everywhere
- Earnings and dividend: if null or >60 days away, do not render the field at all
- Earnings within 14 days: amber highlight badge — risk signal for options positions
- This component is the ONLY place QuoteBar rendering logic lives
- Every page that needs it imports `<QuoteBar />` — zero inline reimplementations

**Why this keeps getting lost**: Each new page build tends to create a simplified inline
version of the header rather than importing the shared component. Both `UI-DECISIONS.md`
and `CLAUDE.md` call this out explicitly to prevent it.

---

## The Core Problem Being Solved

The original Ask Claude panel was a dead end architecturally:
- One trade in, one response out, nothing stored
- No way to know if Claude's recommendations were good over time
- No connection between evaluations, positions, and outcomes
- When Agent 365 arrives, there's nothing to plug in

The redesign (Phases 2.6 onward) solves all of these simultaneously by building
a coherent system from symbol lookup → strategy scoring → follow/trade → outcome tracking
→ aggregate validation.

---

## The Three-Layer Architecture

Think of agents in this project as living across three layers, like floors of a building.
You build from the bottom up, but the design considers all three from the start.

### Layer 1 — Execution (what you build now)
Your FastAPI backend, Python agent code, and SKILL.md prompt files.
Each agent is a focused specialist that does one thing well.

### Layer 2 — Orchestration (what you add as you grow)
Azure AI Foundry Agent Service. This is where agents are registered, where multi-agent
workflows are defined, and where handoffs between agents are managed.

### Layer 3 — Management (what arrives with Agent 365)
Microsoft is building Agent 365 as the enterprise management surface for all agents
running in your tenant. By building correctly in Layers 1 and 2 — with Foundry-registered
agents, Entra identities, and standard OpenTelemetry traces — everything you build today
will appear in Agent 365 automatically when it becomes generally available.

---

## Core Architectural Patterns

These patterns are established principles that ALL new features must follow.
They are not phase-specific — they are permanent foundations.

### Pattern 1: Provider Adapter Pattern

All external data sources — market data, AI models, brokerages, and future signal
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
This means the Positions page, monitoring agent, and aggregate analytics work
identically for both. Live execution in Phase 5 flips `source` from PAPER to LIVE
without touching any other infrastructure.

### Pattern 5: Generic Insight Engine

The Insight Engine is a domain-agnostic pattern for detect → score → communicate
anomalies. It is deployed first in the options domain but is explicitly designed
to be reused in manufacturing, customer health, and any other monitoring scenario.

The domain-specific parts are:
1. The `ObservationSource` adapter (what to watch)
2. The SKILL.md prompt template (how to frame the insight for that domain)

Everything else — deviation detection, insight data model, dashboard rendering,
dismissal flow — is generic and reused across domains.

---

## The Full Data Flow (End to End)

```
User pulls up MSFT
    ↓
Security Dashboard loads
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

A strategy is a named configuration of:
- **Trade structure**: vertical spread, long call, iron condor, etc.
- **DTE window**: 0-7, 7-14, 30-45, etc.
- **Scoring weights**: which metrics matter most for this objective
- **Filter thresholds**: what gets excluded before scoring
- **Config schema**: the parameters the user can adjust in ConfigDrawer
- **Greek targets**: delta range, theta/gamma ratio, IV rank thresholds

### Initial Four Strategies

**1. Steady Paycheck** — Income, 30-45 DTE credit spreads
- Primary objective: maximize theta per dollar at risk
- Key metrics: Theta/Margin ratio, IV Rank (min 40), Probability of Profit
- Short strike delta: 0.20-0.30
- Exit at 50% of max profit, stop at 2x credit received

**2. Weekly Grind** — Income, 7-14 DTE credit spreads
- Primary objective: high-frequency theta capture
- Key metrics: Theta/Gamma ratio (critical — Gamma explodes near expiry), credit/width %
- Short strike delta: 0.20-0.25 (tighter — less room for error)
- Requires more active management than Steady Paycheck

**3. Trend Rider** — Directional, 30-60 DTE long calls or bull call spreads
- Primary objective: capture directional move with defined risk
- Key metrics: Delta, SMA alignment score, runway vs expected move
- Long strike delta: 0.50-0.70
- Entry requires bullish SMA alignment (8 > 21 > 50)

**4. Lottery Ticket** — Speculative, 1-7 DTE deep OTM
- Primary objective: asymmetric payout on a credible catalyst
- Key metrics: Cost/max payout ratio (min 5:1), catalyst presence
- Delta range: 0.05-0.15
- Scoring formula is inverted — optimizes for payout ratio, not probability

### Strategy Config Schema Pattern

Each strategy defines a `configSchema` in its config file. ConfigDrawer renders
whatever schema the active strategy defines. This replaces the static 14-field
system variables approach with a dynamic, strategy-aware parameter set.

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

Computed by Position Monitor Agent daily. NOT a Claude call — pure math.

| Grade | Meaning |
|-------|---------|
| A | Within projected range, P&L at or above expected pace |
| B | Slightly outside range, no warnings triggered |
| C | Approaching exit warning level |
| D | Exit warning breached or significant adverse move |
| F | Hard stop hit or thesis completely invalidated |

For closed positions, grade reflects actual vs projected outcome at entry.

### Positions Page Filters

Four composable filters:
- **Status**: Active | Historical | All
- **Type**: Paper | Live | All
- **Symbol**: typeahead from watchlist
- **Strategy**: all or select one

Aggregate stats bar recalculates against active filter combination.

---

## The Insight Engine (Generic Pattern)

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

```sql
CREATE TABLE insights (
    insight_id        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    domain            NVARCHAR(50) NOT NULL,      -- 'options' | 'manufacturing'
    entity_id         NVARCHAR(100) NOT NULL,     -- position_id, machine_id, etc.
    entity_label      NVARCHAR(200) NOT NULL,     -- human-readable label
    observation       NVARCHAR(MAX) NOT NULL,     -- JSON: what was measured
    baseline          NVARCHAR(MAX) NOT NULL,     -- JSON: what was expected
    deviation_score   INT NOT NULL,              -- 0-100
    deviation_type    NVARCHAR(50) NOT NULL,     -- THRESHOLD|TREND|ANOMALY|CORRELATION
    title             NVARCHAR(200) NOT NULL,
    body              NVARCHAR(1000) NOT NULL,
    severity          NVARCHAR(20) NOT NULL,     -- INFO|WARNING|CRITICAL
    recommended_actions NVARCHAR(MAX),           -- JSON array of action objects
    status            NVARCHAR(20) DEFAULT 'ACTIVE', -- ACTIVE|DISMISSED|ACTED_ON
    source_signals    NVARCHAR(MAX),             -- JSON: which sources triggered
    agent_run_id      UNIQUEIDENTIFIER,          -- FK to agent_run_log
    created_at        DATETIME2 DEFAULT GETUTCDATE(),
    dismissed_at      DATETIME2,
    acted_on_at       DATETIME2
)
```

### SKILL.md Structure for Insight Engine

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

All signal sources write to a single normalized table:

```sql
CREATE TABLE symbol_context (
    context_id     UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    symbol         NVARCHAR(20) NOT NULL,
    source_id      NVARCHAR(50) NOT NULL,       -- 'schwab_quotes', 'social_sentiment'
    signal_type    NVARCHAR(50) NOT NULL,        -- PRICE|SENTIMENT|FUNDAMENTAL|TECHNICAL|NEWS
    signal_value   NVARCHAR(MAX) NOT NULL,       -- normalized JSON blob
    captured_at    DATETIME2 DEFAULT GETUTCDATE(),
    expires_at     DATETIME2 NOT NULL            -- source-specific freshness window
)
```

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

This is built agent-first: it has its own SKILL.md, its own Foundry registration,
and its own Entra Agent ID. It is the first of what will become a fleet of
monitoring specialists.

---

## Black-Scholes Probability Matrix

The probability matrix shown in Claude's structured evaluation is computed by the
backend using Black-Scholes, NOT by Claude. Claude receives the pre-computed matrix
as context and uses it for qualitative commentary.

Backend endpoint: `POST /api/v1/analysis/probability-matrix`

Inputs: current price, IV, DTE, risk-free rate, price range (+/- 10% in $10 steps)
Output: probability of price being at each level on dates: expiry-3, expiry-6, expiry-9, expiry

Why backend math, not Claude? The matrix must be consistent, auditable, and fast.
Claude's role is judgment and communication, not arithmetic.

---

## Claude Structured Evaluation (Replaces AskClaudePanel)

### What Changed

`AskClaudePanel` is retired. Claude is no longer a chat interface. Claude is a
structured analytical engine that returns consistent, comparable output cards.

### Evaluation Flow

1. User selects strategies on Security Dashboard or expands a trade row
2. Single "Evaluate" button triggers one Claude call per selected strategy
3. Each strategy returns a structured card:

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
- **Security Dashboard**: trade is null, Claude finds best trade per strategy
- **Trade row expansion** (OptionsTerminal): trade is pre-populated, Claude evaluates it through each strategy lens

Same component (`StrategyScorecard`), same Claude output format, two contexts.

---

## How Observability Works

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

| Resource | Name | Status | Purpose |
|----------|------|--------|---------|
| AI Foundry | `ota-foundry-resource` | Existing | Agent deployment, model gateway |
| Application Insights | `ota-insights` | New (Phase 2.6) | OTel trace sink |
| Log Analytics Workspace | `ota-logs` | New (Phase 2.6) | Backend for App Insights |
| Azure SQL | `options-analyzer-db` | Existing | All persistent data |
| Key Vault | (existing) | Existing | All secrets |

New SQL tables by phase:
- Phase 2.6: `agent_run_log`, `trade_recommendations`
- Phase 2.9: `strategy_configs`
- Phase 2.10: `positions`
- Phase 3.5: `symbol_context`
- Phase 3.6: `insights`

---

## Phase History

- **Phase 0**: Security & Authentication ✅
- **Phase 1**: Configuration & Market Data ✅
- **Phase 2.1-2.4**: Analysis Engines + AI Evaluation ✅
- **Phase 2.5**: Frontend Completion (partial) 🔶
- **Phase 2.6**: Claude Trade Agent Redesign 🔶
- **Phase 2.7**: Options Decision Terminal ✅
- **Phase 2.8**: Configurable System Variables, Dashboard, Schwab Routing ✅
- **Phase 2.9**: Security Dashboard + Strategy Scorecard 🔲
- **Phase 2.10**: Positions Page + Follow/Take Position 🔲
- **Phase 2.11**: Claude Structured Evaluation + Probability Matrix 🔲
- **Phase 3**: Azure Deployment 🔲
- **Phase 3.5**: Market Intelligence Aggregator + Position Monitor Agent 🔲
- **Phase 3.6**: Insight Engine (Generic) + Options Domain 🔲
- **Phase 4**: MCP Integration 🔲
- **Phase 5**: Live Trading Execution 🔲
