# PHASE-3.6 — Insight Engine (Generic) + Options Domain

## Objective

Build the generic Insight Engine that detects deviations in monitored entities and
uses Claude to craft actionable insights. Deploy it first for the options domain
(monitoring positions). Design it explicitly for reuse in manufacturing, customer health,
and any other monitoring scenario — only the ObservationSource and SKILL.md change.

## Why This Is A Core Pattern, Not Just A Feature

The Insight Engine is the same pattern at every scale:
1. Something is observed
2. It deviates from expectation
3. A practitioner needs to know, and needs to know what to do

The only domain-specific parts are what you're observing and how you frame the insight.
The detection logic, the data model, the dashboard rendering, and the delivery mechanism
are identical whether you're watching options positions or manufacturing equipment.

## Dependencies

- Phase 3.5 complete (Position Monitor Agent running, symbol_context populated)
- insights table created in Azure SQL
- Dashboard page exists (DashboardPage.jsx)

---

## Parallel Streams

### Stream A — Generic Engine (start immediately)
insights table + DeviationDetector + InsightGenerator + InsightRouter

### Stream B — Options Domain Implementation (after Stream A)
Options ObservationSource + options SKILL.md + wire into Position Monitor Agent

### Stream C — Frontend (parallel with B)
InsightCard component + Dashboard feed section

---

## Stream A: Generic Engine

### A1 — insights Table

**File**: `app/models/database.py` (add)

```python
class Insight(Base):
    __tablename__ = "insights"

    insight_id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain              = Column(String(50), nullable=False)     # 'options' | 'manufacturing'
    entity_id           = Column(String(100), nullable=False)    # position_id, machine_id
    entity_label        = Column(String(200), nullable=False)    # human-readable
    observation         = Column(Text, nullable=False)           # JSON
    baseline            = Column(Text, nullable=False)           # JSON
    deviation_score     = Column(Integer, nullable=False)        # 0-100
    deviation_type      = Column(String(50), nullable=False)     # THRESHOLD|TREND|ANOMALY|CORRELATION
    title               = Column(String(200), nullable=False)
    body                = Column(String(1000), nullable=False)
    severity            = Column(String(20), nullable=False)     # INFO|WARNING|CRITICAL
    recommended_actions = Column(Text)                           # JSON array
    status              = Column(String(20), default='ACTIVE')   # ACTIVE|DISMISSED|ACTED_ON
    source_signals      = Column(Text)                           # JSON: which sources triggered
    agent_run_id        = Column(String(36))                     # FK to agent_run_log
    created_at          = Column(DateTime, default=datetime.utcnow)
    dismissed_at        = Column(DateTime)
    acted_on_at         = Column(DateTime)
```

### A2 — DeviationDetector

**File**: `app/agents/deviation_detector.py` (new)

Generic, domain-agnostic deviation detection. Four rule types.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class DeviationResult:
    detected: bool
    deviation_type: Optional[str]   # THRESHOLD | TREND | ANOMALY | CORRELATION
    deviation_score: int            # 0-100 severity
    observation: dict               # what was measured
    baseline: dict                  # what was expected
    description: str                # human-readable description for Claude context

class DeviationDetector:
    """
    Generic deviation detection. Domain-agnostic.
    All methods are pure functions — no database access, no API calls.
    """

    def check_threshold(
        self,
        current_value: float,
        warning_threshold: float,
        stop_threshold: float,
        metric_name: str,
        direction: str = 'below'  # 'below' | 'above'
    ) -> DeviationResult:
        """
        Detect when a value crosses a predefined threshold.
        Used for: exit warning levels, quality control limits.
        """

    def check_trend(
        self,
        values: List[float],        # time series, most recent last
        periods: int = 3,           # how many consecutive periods to look back
        direction: str = 'degrading'  # 'degrading' | 'improving'
    ) -> DeviationResult:
        """
        Detect when a metric has moved consistently in one direction.
        Used for: P&L trending down 3 days, defect rate increasing week-over-week.
        """

    def check_anomaly(
        self,
        current_value: float,
        historical_values: List[float],
        std_dev_threshold: float = 2.0
    ) -> DeviationResult:
        """
        Detect when a value is statistically unusual.
        Used for: unusual volume, abnormal price move, unexpected sensor reading.
        """

    def check_correlation(
        self,
        signals: List[dict],    # list of {name, value, expected_value}
        threshold: int = 2      # how many signals must be adverse simultaneously
    ) -> DeviationResult:
        """
        Detect when multiple signals are moving adversely together.
        Used for: price down + sentiment down + volume spiking simultaneously.
        """
```

### A3 — InsightGenerator

**File**: `app/agents/insight_engine.py` (new)

```python
class InsightEngine:
    """
    Generic insight generation engine. Domain-agnostic.
    The domain is specified by the SKILL.md path and the domain parameter.

    Designed for reuse: instantiate with different domain skill paths
    to get insights for options, manufacturing, customer health, etc.
    """

    def __init__(self, ai_provider, domain: str, skill_path: str):
        self.ai_provider = ai_provider
        self.domain = domain
        self.skill = skill_loader.load(skill_path)
        self.detector = DeviationDetector()

    async def generate(
        self,
        entity_id: str,
        entity_label: str,
        deviation: DeviationResult,
        context_signals: List[dict],
        agent_run_id: Optional[str] = None
    ) -> Insight:
        """
        Given a detected deviation and context, ask Claude to craft an insight.
        Writes the insight to the database. Returns the created Insight.

        Claude returns:
        {
          "title": "8 words max",
          "body": "2-3 sentences: what happened, why it matters, what to consider",
          "severity": "INFO | WARNING | CRITICAL",
          "recommended_actions": [
            {"label": "View Position", "route": "/positions/{entity_id}"},
            {"label": "Dismiss", "action": "dismiss"}
          ]
        }
        """

    async def get_active(
        self,
        domain: str,
        entity_id: Optional[str] = None
    ) -> List[Insight]:
        """Return active (non-dismissed) insights, optionally filtered by entity"""

    async def dismiss(self, insight_id: str) -> None:
        """Mark insight as DISMISSED"""

    async def mark_acted_on(self, insight_id: str) -> None:
        """Mark insight as ACTED_ON (e.g., user navigated to position)"""
```

---

## Stream B: Options Domain

### B1 — Options Domain SKILL.md

**File**: `app/skills/insight-engine/domains/options/SKILL.md` (new)

```markdown
---
name: insight-engine-options
description: Generates insights for options position deviations. Called by the
  Insight Engine when a position health deviation is detected. Returns structured
  insight JSON for display on the trading dashboard.
metadata:
  version: 1.0.0
  domain: options
---

# Options Insight Generator

## Context You Receive
- The position: symbol, strategy, trade structure, entry conditions
- The deviation: what changed, what was expected
- Available signals: price, IV, SMA alignment, any other sources currently connected

## Your Job
Craft a short, actionable insight for an options trader. Be specific — mention the
actual symbol, strategy name, price levels, and what the trader should consider doing.

Do not be generic. "Position is under pressure" is useless. "MSFT Bull Put 415/410
crossed the 412.50 exit warning with IV expanding — consider closing or rolling out
one week" is useful.

## Severity Guide
- INFO: Something noteworthy but not urgent. Position still healthy.
- WARNING: Threshold crossed or thesis weakening. Trader should review.
- CRITICAL: Hard stop approaching or thesis clearly invalidated. Act now.

## Output Format
Return ONLY valid JSON. No preamble.
{
  "title": "max 8 words, states the situation concisely",
  "body": "2-3 sentences. What happened, why it matters for THIS specific position, what to consider.",
  "severity": "INFO | WARNING | CRITICAL",
  "recommended_actions": [
    {"label": "View Position", "route": "/positions/{entity_id}"},
    {"label": "Dismiss", "action": "dismiss"}
  ]
}
```

### B2 — Wire into Position Monitor Agent

**File**: `app/agents/position_monitor.py` (update `_trigger_insights`)

```python
async def _trigger_insights(self, updates: List[PositionHealthUpdate]):
    """
    For each position update where needs_insight=True,
    run the deviation detector to classify the deviation,
    then call insight_engine.generate().
    """
    options_insight_engine = InsightEngine(
        ai_provider=self.ai_provider,
        domain='options',
        skill_path='insight-engine/domains/options'
    )

    for update in updates:
        if not update.needs_insight:
            continue

        # Build deviation result from the agent's insight_context
        deviation = DeviationResult(
            detected=True,
            deviation_type=update.insight_context['deviation_type'],
            deviation_score=self._score_deviation(update),
            observation=update.insight_context['observation'],
            baseline=update.insight_context['baseline'],
            description=update.insight_context.get('description', '')
        )

        await options_insight_engine.generate(
            entity_id=update.position_id,
            entity_label=update.entity_label,
            deviation=deviation,
            context_signals=update.context_signals,
            agent_run_id=update.agent_run_id
        )
```

---

## Stream C: Frontend

### C1 — InsightCard Component

**File**: `web/src/components/InsightCard.jsx` (new)

```javascript
// Renders one insight card on the dashboard feed
// Props: insight (object), onDismiss (fn), onViewEntity (fn)

// Layout:
// ┌─────────────────────────────────────────┐
// │ ⚠️  MSFT position approaching stop level │  ← severity icon + title
// │                                          │
// │  Position has moved 18% against entry   │  ← body text
// │  thesis. Underlying broke below SMA-8   │
// │  with elevated volume...                │
// │                                          │
// │  [View Position]  [Dismiss]              │  ← action buttons from insight
// │  12 minutes ago                          │  ← relative timestamp
// └─────────────────────────────────────────┘

// Severity colors:
// CRITICAL: red left border (#ef4444)
// WARNING: orange left border (#f97316)
// INFO: blue left border (#3b82f6)
```

### C2 — Dashboard Insight Feed

**File**: `web/src/pages/DashboardPage.jsx` (update)

Add an Insights section between the market overview cards and the main content:

```
┌─────────────────────────────────────────────────┐
│  INSIGHTS  (3 active)                    [↻ Refresh] │
│                                                  │
│  [InsightCard - CRITICAL - MSFT]                 │
│  [InsightCard - WARNING - NVDA]                  │
│  [InsightCard - INFO - AAPL]                     │
│                                                  │
│  View all insights →                             │
└─────────────────────────────────────────────────┘
```

Dashboard shows max 3 insights (most severe first). "View all" links to a full
insights list (future page, or filtered Positions view for now).

State:
- Insights polled every 60 seconds while page is active (not push — simple polling)
- Dismissing an insight removes it from the feed immediately (optimistic update)
- Clicking an action button marks the insight as ACTED_ON before navigating

### C3 — Insight Route API

**File**: `web/src/api/client.js` (add)

```javascript
export const getInsights = (domain = 'options') =>
  apiGet(`/api/v1/insights?domain=${domain}&status=ACTIVE`)

export const dismissInsight = (insightId) =>
  apiPatch(`/api/v1/insights/${insightId}/dismiss`, {})
```

**File**: `app/api/insight_routes.py` (new)

```
GET /api/v1/insights
  Query: domain (default 'options'), status (default 'ACTIVE'), entity_id (optional)
  Returns: List[InsightResponse] sorted by severity desc, created_at desc

PATCH /api/v1/insights/{insight_id}/dismiss
  Marks status=DISMISSED, sets dismissed_at=now
  Returns: InsightResponse

PATCH /api/v1/insights/{insight_id}/act
  Marks status=ACTED_ON, sets acted_on_at=now
  Returns: InsightResponse
```

---

## Integration Testing (End of Phase 3.6)

**Test 1 — Insight generated for threshold crossing**
1. Create a paper position on MSFT
2. Manually update the position in SQL to simulate a price move past the exit warning:
   `UPDATE positions SET current_price = [warning_price - 1] WHERE ...`
3. Run position monitor via `POST /api/v1/agents/position-monitor/run`
4. Query insights table — should have a new ACTIVE row for this position
5. Insight body should mention MSFT specifically and reference the exit level

**Test 2 — Dashboard shows insight**
1. Ensure test insight from Test 1 is in the database
2. Navigate to Dashboard page
3. Insight card should appear in the feed
4. Severity badge should match the insight severity

**Test 3 — Dismiss flow**
1. Click Dismiss on an insight card
2. Card should disappear immediately (optimistic update)
3. Query insights table — status should be DISMISSED, dismissed_at should be set
4. Refresh Dashboard — dismissed insight should NOT reappear

**Test 4 — Action button navigation**
1. Click "View Position" on an insight card
2. Should navigate to Positions page filtered to that specific position
3. Query insights table — status should be ACTED_ON

**Test 5 — Generic engine is truly domain-agnostic**
1. Instantiate InsightEngine with domain='test' and a mock SKILL.md path
2. Call generate() with mock deviation and mock signals
3. Insight should be created in insights table with domain='test'
4. The GET /api/v1/insights?domain=options endpoint should NOT return it
5. GET /api/v1/insights?domain=test should return it

**Test 6 — No duplicate insights for same deviation**
1. Run position monitor twice with the same position in a warning state
2. Insights table should have exactly ONE active insight for that position
3. Second run should detect the existing active insight and not create a duplicate

---

## Claude Code Prompts

### Prompt A1 (Stream A — run first)
```
Read CLAUDE.md and architecture-plan.md and PHASE-3.6.md.

Add the Insight SQLAlchemy model to app/models/database.py as specified in
PHASE-3.6.md section A1.

Create app/agents/deviation_detector.py implementing DeviationDetector with all
four methods (check_threshold, check_trend, check_anomaly, check_correlation)
as specified in section A2. All methods are pure functions — no I/O, no side effects.
Each returns a DeviationResult dataclass.

Add DeviationResult dataclass to app/models/schemas.py.
```

### Prompt A2 (Stream A — after A1)
```
Read CLAUDE.md and PHASE-3.6.md.

Create app/agents/insight_engine.py implementing InsightEngine as specified
in PHASE-3.6.md section A3.

The generate() method must:
1. Load the domain SKILL.md using skill_loader
2. Build a prompt with entity details + deviation + context signals
3. Call AI provider with structured output requirement
4. Parse Claude's JSON response into an Insight object
5. Check for existing ACTIVE insight for the same entity_id before creating
   (avoid duplicates — if one exists, update it rather than creating a new row)
6. Write to insights table
7. Write to agent_run_log
8. Return the created/updated Insight

Create app/api/insight_routes.py with the three endpoints specified in section C3.
Register in app/main.py.
```

### Prompt B1 (Stream B — after A2)
```
Read CLAUDE.md and PHASE-3.6.md.

Create app/skills/insight-engine/SKILL.md with the generic pattern.
Create app/skills/insight-engine/domains/options/SKILL.md with the exact
content specified in PHASE-3.6.md section B1.

Update app/agents/position_monitor.py _trigger_insights method as specified
in section B2 to instantiate InsightEngine with the options domain skill path
and call generate() for each position needing an insight.
```

### Prompt C1 (Stream C — run simultaneously with B1)
```
Read CLAUDE.md and PHASE-3.6.md.

Create web/src/components/InsightCard.jsx as specified in section C1.
Use mock data: one CRITICAL insight about MSFT, one WARNING about NVDA.
Implement dismiss and view-entity callbacks as props.
Severity colors: CRITICAL=red, WARNING=orange, INFO=blue left border.

Add getInsights() and dismissInsight() to web/src/api/client.js.

Update web/src/pages/DashboardPage.jsx to include the insights feed section
as specified in section C2. Use mock data initially.
Poll every 60 seconds. Show max 3 cards, most severe first.
```

### Prompt C2 (Stream C — after C1 and A2 are both done)
```
Read CLAUDE.md and PHASE-3.6.md.

Wire DashboardPage.jsx insights feed to use real data from GET /api/v1/insights.
Replace mock insights with real API call.
Implement dismiss action: call dismissInsight(), optimistically remove card,
handle API error by re-adding card.
Implement action button: call PATCH /api/v1/insights/{id}/act, then navigate
to the route specified in the action's route field.
```
