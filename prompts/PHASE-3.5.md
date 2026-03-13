# PHASE-3.5 — Market Intelligence Aggregator + Position Monitor Agent

## Objective

Build the autonomous position monitoring infrastructure. The Position Monitor Agent
runs daily after market close, reads all open positions, evaluates their health
against current context from all available signal sources, and feeds the Insight
Engine when deviations are detected. This is built agent-first — it has its own
SKILL.md, Foundry registration, and Entra Agent ID from day one.

## Why Agent-First

A naive implementation would be a cron job that loops positions and updates P&L.
That works but it is a dead end — it can't reason, escalate, or grow.

Built agent-first means:
- The agent reads from a standardized context store, not directly from APIs
- New signal sources (social sentiment, fundamentals) plug in without changing the agent
- Every run is observable in Application Insights and auditable in agent_run_log
- When Portfolio Risk Agent and Market Scan Agent are added, they follow the same pattern
  and share the same infrastructure

## Dependencies

- Phase 2.10 complete (positions table exists and populated)
- Phase 3 Azure deployment complete (Azure SQL, App Service running)
- Application Insights wired (ota-insights resource exists)
- OpenTelemetry configured in main.py

---

## Parallel Streams

### Stream A — Infrastructure (start first, others depend on it)
symbol_context table + ContextSource interface + Schwab price source adapter

### Stream B — Agent Logic (after Stream A)
Position Monitor Agent + SKILL.md + scheduled trigger + on-demand endpoint

### Stream C — Foundry Registration (parallel with B)
Register agent in Foundry portal + note Entra Agent ID

Streams B and C can run in parallel. Both depend on Stream A.

---

## Stream A: Infrastructure

### A1 — symbol_context Table

**File**: `app/models/database.py` (add)

```python
class SymbolContext(Base):
    __tablename__ = "symbol_context"

    context_id  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol      = Column(String(20), nullable=False, index=True)
    source_id   = Column(String(50), nullable=False)
    signal_type = Column(String(50), nullable=False)
    signal_value = Column(Text, nullable=False)   # JSON
    captured_at = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime, nullable=False)

    # Composite index for fast lookup: symbol + source + not expired
    __table_args__ = (
        Index('ix_symbol_context_lookup', 'symbol', 'source_id', 'expires_at'),
    )
```

### A2 — ContextSource Abstract Interface

**File**: `app/providers/base.py` (add to existing)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ContextSignal:
    source_id: str
    signal_type: str    # PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS
    symbol: str
    value: dict         # normalized signal data
    ttl_seconds: int    # how long this signal stays fresh

class ContextSource(ABC):
    """
    Abstract interface for all signal sources.
    Implement this to add any new data source — market data, sentiment,
    fundamentals, alternative brokerages, etc.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier e.g. 'schwab_quotes', 'social_sentiment'"""
        pass

    @property
    @abstractmethod
    def signal_type(self) -> str:
        """One of: PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS"""
        pass

    @abstractmethod
    async def fetch(self, symbol: str) -> dict:
        """Fetch raw data for the symbol from this source"""
        pass

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """
        Normalize raw data into a consistent signal_value JSON blob.
        The normalized format must be stable — downstream consumers depend on it.
        """
        pass

    @abstractmethod
    def ttl_seconds(self) -> int:
        """How long this signal stays fresh before re-fetching"""
        pass
```

### A3 — Schwab Price Context Source

**File**: `app/providers/schwab_context_source.py` (new)

First implementation of ContextSource. Fetches current price + Greeks + IV from Schwab.

```python
class SchwabPriceContextSource(ContextSource):
    source_id = "schwab_quotes"
    signal_type = "PRICE"

    def ttl_seconds(self) -> int:
        return 300  # 5 minutes

    async def fetch(self, symbol: str) -> dict:
        # Use existing SchwabMarketData to get quote
        pass

    def normalize(self, raw: dict) -> dict:
        # Return consistent shape:
        return {
            "price": raw["lastPrice"],
            "change": raw["netChange"],
            "change_pct": raw["percentChange"],
            "volume": raw["totalVolume"],
            "iv": raw.get("volatility"),
            "iv_rank": raw.get("ivRank"),  # computed if not in response
            "bid": raw["bidPrice"],
            "ask": raw["askPrice"],
        }
```

### A4 — Context Store Service

**File**: `app/agents/context_store.py` (new)

```python
class ContextStore:
    """
    Reads and writes symbol context. Handles TTL expiry.
    Used by: Position Monitor Agent, future agents.
    """

    async def get(self, symbol: str, source_id: str) -> Optional[dict]:
        """Return non-expired signal value or None"""

    async def set(self, signal: ContextSignal) -> None:
        """Write signal to symbol_context table"""

    async def get_all_for_symbol(self, symbol: str) -> List[dict]:
        """Return all non-expired signals for a symbol, all sources"""

    async def refresh_if_stale(
        self,
        symbol: str,
        source: ContextSource
    ) -> dict:
        """
        Check if signal is fresh. If expired, fetch and store new signal.
        Returns current (possibly just-refreshed) signal value.
        """
```

---

## Stream B: Agent Logic

### B1 — Position Monitor SKILL.md

**File**: `app/skills/position-monitor/SKILL.md` (new)

```markdown
---
name: position-monitor
description: Monitors open options positions daily. Reads current context signals,
  computes health grades, detects threshold crossings. Escalates to insight engine
  when deviation is detected. Use when evaluating open position health after market close.
metadata:
  version: 1.0.0
  agent: position-monitor
  domain: options
---

# Position Monitor Agent

## Role
You are a position health analyst. You review open options positions daily and
determine whether each position is tracking as expected, degrading, or in need
of immediate attention.

## Input Context
For each position you receive:
- Entry conditions: trade structure, entry price, entry Greeks, Claude's original exit levels
- Current conditions: current price, current Greeks (if available), SMA alignment
- Available signals: all non-expired signals from symbol_context for this symbol

## Your Job
For each position, determine:
1. Is the underlying price within the range Claude's probability matrix projected?
2. Has any exit level been crossed since entry?
3. Are any signals indicating the original thesis may be wrong?
4. What is the appropriate health grade (A/B/C/D/F)?

## Escalation Criteria
Escalate to the Insight Engine (set needs_insight=true) when:
- Exit warning level has been crossed
- Underlying price is outside the 1-standard-deviation range from Claude's matrix
- Two or more signals are moving adversely simultaneously
- Position is within 3 days of expiration with significant unrealized loss

## Output Format
Return ONLY valid JSON. Array of PositionHealthUpdate objects.
{
  "position_id": "...",
  "health_grade": "A|B|C|D|F",
  "current_pnl": float,
  "needs_insight": boolean,
  "insight_context": {  // only if needs_insight=true
    "deviation_type": "THRESHOLD|TREND|ANOMALY",
    "observation": "what happened",
    "baseline": "what was expected"
  }
}
```

### B2 — Position Monitor Agent

**File**: `app/agents/position_monitor.py` (new)

```python
class PositionMonitorAgent:
    """
    Autonomous agent that monitors all open positions.
    Runs on schedule (daily after close) or on-demand.

    This agent is designed to scale to any number of signal sources —
    new ContextSource implementations are picked up automatically
    without changes to this agent.
    """

    def __init__(self, context_store, insight_engine, ai_provider):
        self.context_store = context_store
        self.insight_engine = insight_engine
        self.ai_provider = ai_provider
        self.skill = skill_loader.load("position-monitor")

    async def run(self, user_id: Optional[str] = None) -> AgentRunResult:
        """
        Main entry point. Processes all open positions.
        If user_id is provided, processes only that user's positions.
        Writes to agent_run_log. Returns summary of run.
        """
        with telemetry.span("position_monitor.run") as span:
            positions = await self._load_open_positions(user_id)
            span.set_attribute("position_count", len(positions))

            updates = []
            for position in positions:
                update = await self._process_position(position)
                updates.append(update)

            await self._write_updates(updates)
            await self._trigger_insights(updates)

            return AgentRunResult(
                agent="position-monitor",
                positions_processed=len(positions),
                insights_triggered=sum(1 for u in updates if u.needs_insight),
                run_at=datetime.utcnow()
            )

    async def _process_position(self, position: Position) -> PositionHealthUpdate:
        """
        1. Load context for this symbol (all sources, refresh if stale)
        2. Build Claude prompt with position + context
        3. Get health grade + escalation decision from Claude
        4. Return update object
        """

    async def _trigger_insights(self, updates: List[PositionHealthUpdate]):
        """
        For each update with needs_insight=True, call insight_engine.generate()
        """
```

### B3 — Scheduled Trigger

**File**: `app/main.py` (add to lifespan)

Use APScheduler to trigger the agent after market close:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def start_scheduler():
    # Run position monitor at 4:15pm ET Monday-Friday
    scheduler.add_job(
        run_position_monitor,
        'cron',
        day_of_week='mon-fri',
        hour=16,
        minute=15,
        timezone='America/New_York'
    )
    scheduler.start()
```

Add `apscheduler` to requirements.txt.

### B4 — On-Demand Endpoint

**File**: `app/api/` (add to a new agents_routes.py)

```
POST /api/v1/agents/position-monitor/run
  Query param: user_id (optional, admin-only if provided)
  Triggers agent run immediately, returns run summary
  Requires Tier 2 auth

GET /api/v1/agents/position-monitor/status
  Returns: last_run_at, positions_processed, insights_triggered, next_run_at
  Requires Tier 1 auth
```

---

## Stream C: Foundry Registration

Do this manually in the Azure portal while Stream B is being built.

1. Navigate to `ota-foundry-resource` in Azure AI Foundry portal
2. Create a new Agent: name=`ota-position-monitor-agent`
3. Note the Entra Agent ID — add to `.env` as `POSITION_MONITOR_AGENT_ID`
4. Assign appropriate model (claude-sonnet-4-6)
5. Tag: project=options-trade-analyzer, component=ai, environment=dev

---

## Integration Testing (End of Phase 3.5)

**Test 1 — Context store populates**
1. Start backend, ensure Schwab connected
2. Call `POST /api/v1/agents/position-monitor/run` via Swagger
3. Query `symbol_context` table in SQL
4. Should have rows for each symbol in open positions with expires_at in the future

**Test 2 — Health grades computed for all open positions**
1. Ensure you have at least 2 open paper positions from Phase 2.10
2. Run the position monitor
3. Query `positions` table — health_grade and last_monitored_at should be updated
4. Grades should reflect current price vs entry

**Test 3 — Context freshness respected**
1. Run position monitor twice in quick succession
2. Check APScheduler logs — second run should use cached context (not re-fetch from Schwab)
3. `symbol_context.captured_at` should not change on second run within TTL window

**Test 4 — Scheduled trigger fires**
1. Set scheduler time to 2 minutes in the future for testing
2. Wait for it to fire
3. Verify agent_run_log has a new entry
4. Revert scheduler to 4:15pm ET

**Test 5 — New source adapter picked up automatically**
1. Create a mock ContextSource in tests/mock_sentiment_source.py
2. Register it in ProviderFactory
3. Run position monitor
4. Verify symbol_context has rows from the mock source
5. Verify health grade computation considers the mock signal

---

## Claude Code Prompts

### Prompt A1 (Stream A — run first, everything depends on this)
```
Read CLAUDE.md and architecture-plan.md and PHASE-3.5.md.

Add the SymbolContext SQLAlchemy model to app/models/database.py as specified
in PHASE-3.5.md section A1 including the composite index.

Add the ContextSource abstract base class to app/providers/base.py as specified
in section A2.

Create app/providers/schwab_context_source.py implementing SchwabPriceContextSource
as specified in section A3. It should use the existing SchwabMarketData provider
to fetch quote data, then normalize it to the standardized shape.

Create app/agents/context_store.py implementing ContextStore with all four methods
as specified in section A4. The refresh_if_stale method must check expires_at
before fetching — only re-fetch if the cached signal is expired or missing.
```

### Prompt B1 (Stream B — after A1)
```
Read CLAUDE.md and PHASE-3.5.md.

Create app/skills/position-monitor/SKILL.md with the exact content specified
in PHASE-3.5.md section B1.

Create app/agents/position_monitor.py implementing PositionMonitorAgent as
specified in section B2. The agent must:
1. Load open positions from SQL
2. For each position, call context_store.refresh_if_stale for each registered source
3. Build prompt from SKILL.md using skill_loader
4. Call AI provider with structured output requirement
5. Parse PositionHealthUpdate objects from response
6. Write health grade updates back to positions table
7. Return AgentRunResult with summary stats
8. Write full run to agent_run_log

Wrap the entire run in an OpenTelemetry span.
```

### Prompt B2 (Stream B — after B1)
```
Read CLAUDE.md and PHASE-3.5.md.

Add APScheduler to requirements.txt and configure the scheduled trigger in
app/main.py as specified in PHASE-3.5.md section B3. The job must run at
4:15pm ET Monday-Friday.

Create app/api/agents_routes.py with the two endpoints specified in section B4:
- POST /api/v1/agents/position-monitor/run (Tier 2 auth)
- GET /api/v1/agents/position-monitor/status (Tier 1 auth)

Register the router in app/main.py.

The /run endpoint must await the agent run and return the AgentRunResult as JSON.
It must not time out — use a background task if the run takes more than 30 seconds.
```
