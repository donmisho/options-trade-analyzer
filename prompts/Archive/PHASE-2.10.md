# PHASE-2.10 — Positions Page + Follow/Take Position

## Objective

Build the unified position tracking system. Paper follows and live positions share
an identical data model and the same Positions page UI. This phase creates the
infrastructure that every downstream feature (monitoring agent, insight engine,
aggregate analytics) depends on.

## Why This Phase Second

The Positions page is mostly independent of Claude's structured evaluation (Phase 2.11).
You can Follow a trade using data that already exists from the scorecard (Phase 2.9).
The Claude evaluation card gets added to the position snapshot in Phase 2.11 — but
the position data model and page can be built and tested now.

## Dependencies

- Phase 2.9 complete (StrategyScorecard, SecurityDashboard working)
- Azure SQL accessible (positions table needs to be created)
- Schwab connected for live price fetching

---

## Parallel Streams

### Stream A — Backend (start immediately)
Database schema + position CRUD API

### Stream B — Frontend (start with mock data)
PositionsPage + health grade component + filter bar

Streams integrate when both are done.

---

## Stream A: Backend Work

### A1 — Database Schema

**File**: `app/models/database.py` (add Position model)

Create the `positions` table as specified in CLAUDE.md data models section.
Also create a SQLAlchemy ORM model:

```python
class Position(Base):
    __tablename__ = "positions"

    position_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    strategy_key = Column(String(50), nullable=False)
    trade_structure = Column(Text, nullable=False)   # JSON
    source = Column(String(10), nullable=False)      # PAPER | LIVE
    status = Column(String(20), nullable=False, default="FOLLOWING")
    entry_price = Column(Numeric(10, 4))
    entry_date = Column(DateTime, nullable=False)
    entry_greeks = Column(Text)                      # JSON
    entry_iv_rank = Column(Numeric(5, 2))
    entry_sma_alignment = Column(Text)               # JSON
    entry_underlying_price = Column(Numeric(10, 4))
    claude_probability_matrix = Column(Text)         # JSON — null until Phase 2.11
    claude_exit_levels = Column(Text)                # JSON — null until Phase 2.11
    claude_verdict = Column(Text)                    # JSON — null until Phase 2.11
    claude_score = Column(Integer)
    health_grade = Column(String(2))                 # A|B|C|D|F
    current_price = Column(Numeric(10, 4))
    current_pnl = Column(Numeric(10, 4))
    last_monitored_at = Column(DateTime)
    exit_price = Column(Numeric(10, 4))
    exit_date = Column(DateTime)
    exit_reason = Column(String(50))
    outcome_pnl = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### A2 — Position Schemas

**File**: `app/models/schemas.py` (add)

```python
class FollowPositionRequest(BaseModel):
    symbol: str
    strategy_key: str
    trade_structure: dict       # legs, strikes, expiration
    entry_price: float
    entry_greeks: dict
    entry_iv_rank: float
    entry_sma_alignment: dict
    entry_underlying_price: float
    claude_score: Optional[int] = None
    # claude_* fields added in Phase 2.11

class TakePositionRequest(FollowPositionRequest):
    pass  # identical for now — source will be set to LIVE by the route

class ClosePositionRequest(BaseModel):
    exit_price: float
    exit_reason: str    # TARGET | WARNING | STOP | EXPIRED | MANUAL

class PositionResponse(BaseModel):
    position_id: str
    symbol: str
    strategy_key: str
    strategy_label: str
    source: str
    status: str
    entry_price: float
    entry_date: str
    entry_underlying_price: float
    current_price: Optional[float]
    current_pnl: Optional[float]
    health_grade: Optional[str]
    claude_score: Optional[int]
    days_held: int
    dte_at_entry: Optional[int]
    trade_structure: dict

class PositionListResponse(BaseModel):
    positions: List[PositionResponse]
    total: int
    aggregate: dict     # win_rate, avg_pnl, avg_hold_days, by strategy
```

### A3 — Position Routes

**File**: `app/api/position_routes.py` (new file)

```
POST /api/v1/positions/follow
  Body: FollowPositionRequest
  Creates position with source=PAPER, status=FOLLOWING
  Returns: PositionResponse

POST /api/v1/positions/take
  Body: TakePositionRequest
  Creates position with source=LIVE, status=LIVE
  Returns: PositionResponse

GET /api/v1/positions
  Query params: status, source, symbol, strategy_key
  All params optional, composable filters
  Returns: PositionListResponse with aggregate stats

GET /api/v1/positions/{position_id}
  Returns: PositionResponse (full detail)

PATCH /api/v1/positions/{position_id}/close
  Body: ClosePositionRequest
  Sets status=CLOSED, records exit data, computes outcome_pnl
  Returns: PositionResponse

GET /api/v1/positions/aggregate
  Query params: same filters as GET /positions
  Returns aggregate stats only (win_rate, avg_pnl, by_strategy breakdown)
```

All routes require Tier 1 auth minimum. Close requires Tier 2 (write action).

### A4 — Health Grade Computation

**File**: `app/analysis/health_grade.py` (new file)

Pure math function — no Claude call needed.

```python
def compute_health_grade(position: Position, current_price: float) -> str:
    """
    Computes A-F health grade from position state vs. Claude's exit levels.
    Called by position_routes.py on GET and by position_monitor agent.

    If claude_exit_levels is null (Phase 2.11 not yet run), grade based on
    simple P&L percentage relative to entry credit/debit.
    """
```

Grade thresholds:
- **A**: Current P&L ≥ 0, underlying within probability matrix range, no levels threatened
- **B**: P&L slightly negative OR nearing exit warning but not breached
- **C**: Within 20% of exit warning level
- **D**: Exit warning level breached
- **F**: Hard stop hit OR position at max loss

---

## Stream B: Frontend Work

### B1 — PositionsPage

**File**: `web/src/pages/PositionsPage.jsx` (new, replaces FavoritesPage)

**Filter bar** (top of page, horizontal):
```
Status: [All ▼]  Type: [All ▼]  Symbol: [Search...▼]  Strategy: [All ▼]
```

All four filters are composable. Changing any filter re-fetches positions.

**Layout within each strategy group**:
```
━━━ Steady Paycheck ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4 active · Win rate 67% · Avg P&L +340 · Avg hold 18d

SYMBOL  TYPE    GRADE  ENTRY    CURRENT  P&L      DTE  ACTIONS
MSFT    Paper   A      415.00   417.30   +42      12   [Close] [View]
NVDA    Paper   C      480.00   471.20   -28      8    [Close] [View]
AAPL    Live    B      185.50   186.90   +18      21   [Close] [View]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ Trend Rider ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2 closed · Win rate 100% · Avg P&L +189

SYMBOL  TYPE    GRADE  ENTRY    EXIT     P&L       HOLD  REASON
TSLA    Paper   A      245.00   259.00   +312      14d   TARGET
```

### B2 — PositionHealthBadge Component

**File**: `web/src/components/PositionHealthBadge.jsx` (new)

```javascript
// Renders letter grade with color
// A = green (#22c55e)
// B = teal (#14b8a6)
// C = yellow (#eab308)
// D = orange (#f97316)
// F = red (#ef4444)
// null = gray dash

export function PositionHealthBadge({ grade }) { ... }
```

Also renders a tooltip on hover explaining what the grade means for this position.

### B3 — Follow/Take Position Actions

These actions are triggered from two places:
1. SecurityDashboard "Evaluate Selected" flow (after Claude evaluation in Phase 2.11)
2. Trade row expansion in OptionsTerminal

For Phase 2.10, wire the actions to create positions with the data available NOW
(before Claude evaluation). The claude_* fields will be null until Phase 2.11.

**In OptionsTerminal Stage 2 expansion**, add two buttons below the scorecard:
```
[📌 Follow (Paper)]    [💰 Take Position (Live)]
```

Both buttons open a confirmation modal showing the trade structure and entry price.
Confirm → POST to the appropriate endpoint → toast notification → position created.

### B4 — Navigation Update

- Rename "Favorites" tab in Header to "Positions"
- Route `/favorites` redirects to `/positions`
- `/positions` renders `PositionsPage`
- FavoritesPage.jsx retained but commented out of routing

---

## Integration Testing (End of Phase 2.10)

**Test 1 — Follow a trade creates a position**
1. Navigate to Verticals page, run analysis for MSFT
2. Expand the top-scoring trade
3. Click "Follow (Paper)"
4. Navigate to Positions page
5. Position should appear in the correct strategy group with source=Paper
6. Health grade should show (even without Claude evaluation — uses P&L fallback)

**Test 2 — Filters compose correctly**
1. Create paper positions for 2 different symbols and 2 different strategies
2. Filter by Status=Active — all 4 should show
3. Filter by Type=Live — should show 0 (none are Live)
4. Filter by Symbol=MSFT — should show only MSFT positions
5. Combined filter (Active + Paper + MSFT) should narrow correctly

**Test 3 — Health grade updates on price change**
1. Create a paper position on MSFT at current price
2. Call `PATCH /api/v1/positions/{id}` via Swagger to simulate a price update
3. Grade should reflect the new price vs entry

**Test 4 — Close a position**
1. Navigate to an active paper position on Positions page
2. Click Close, select exit_reason=TARGET, enter exit price
3. Position should move to Historical section
4. Outcome P&L should be computed correctly (exit price vs entry price × contract multiplier)

**Test 5 — Aggregate stats update with filters**
1. Close several positions with positive and negative outcomes
2. Filter to Strategy=Steady Paycheck
3. Aggregate bar should show correct win rate and average P&L for that strategy only

---

## Claude Code Prompts

### Prompt A1 (Stream A — run first)
```
Read CLAUDE.md and architecture-plan.md and PHASE-2.10.md.

Add the Position SQLAlchemy model to app/models/database.py as specified in
PHASE-2.10.md section A1. The model must match the positions table schema
exactly from CLAUDE.md.

Add the Pydantic schemas (FollowPositionRequest, TakePositionRequest,
ClosePositionRequest, PositionResponse, PositionListResponse) to
app/models/schemas.py as specified in section A2.

Then create app/analysis/health_grade.py implementing compute_health_grade()
as specified in section A4. When claude_exit_levels is null, fall back to
P&L percentage: positive P&L = A, 0 to -10% = B, -10 to -25% = C,
-25 to -50% = D, > -50% = F.
```

### Prompt A2 (Stream A — after A1)
```
Read CLAUDE.md and PHASE-2.10.md.

Create app/api/position_routes.py implementing all 5 endpoints specified in
PHASE-2.10.md section A3:
- POST /api/v1/positions/follow
- POST /api/v1/positions/take
- GET /api/v1/positions (with composable filters)
- PATCH /api/v1/positions/{id}/close
- GET /api/v1/positions/aggregate

All endpoints require Tier 1 auth minimum. Close requires Tier 2.
Register the router in app/main.py.

GET /api/v1/positions aggregate stats must compute:
- win_rate: closed positions where outcome_pnl > 0 / total closed
- avg_pnl: mean outcome_pnl across closed positions
- avg_hold_days: mean days between entry_date and exit_date
- by_strategy: same stats broken down per strategy_key
```

### Prompt B1 (Stream B — run simultaneously with A1)
```
Read CLAUDE.md and PHASE-2.10.md.

Create web/src/components/PositionHealthBadge.jsx as specified in section B2.

Create web/src/pages/PositionsPage.jsx as specified in section B1. Use mock data
for now — hardcode an array of 4-5 positions with different strategies, sources,
statuses, symbols, and health grades. The page must render positions grouped by
strategy with aggregate stats per group and a filter bar with all four filters.

Update Header.jsx to rename "Favorites" to "Positions" and point the route to
/positions.
```

### Prompt B2 (Stream B — after B1 and after A2 is ready)
```
Read CLAUDE.md and PHASE-2.10.md.

Wire PositionsPage.jsx to use real data:
1. Add getPositions(filters), followTrade(data), takeTrade(data), closePosition(id, data)
   to web/src/api/client.js
2. Replace mock data in PositionsPage with real API calls
3. Implement filter bar state — changing any filter triggers re-fetch
4. Add loading states and empty states

Then add Follow and Take Position buttons to the OptionsTerminal Stage 2 expansion
as specified in section B3. Include confirmation modal before creating position.
Show toast on success with link to Positions page.
```
