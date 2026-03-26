---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Positions Redesign — Session 1, Window 1: Backend Foundation
# Jira: OTA-263, OTA-265
# Prerequisites: None — this is the foundation session

## Context

You are building the backend infrastructure for versioned position assessments.
The Positions page is being redesigned so that each position can have multiple
Claude evaluations stacked over time (Original + Updates). This requires a new
table and several API endpoints.

**Read these files first:**
```
cat CLAUDE.md
cat architecture-plan.md | head -100
cat app/models/database.py
cat app/api/position_routes.py
```

## Task 1: Create position_assessments table (OTA-263)

Add a new SQLAlchemy model `PositionAssessment` to `app/models/database.py`:

```sql
CREATE TABLE position_assessments (
    assessment_id         UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    position_id           UNIQUEIDENTIFIER NOT NULL,  -- FK to positions
    version_number        INT NOT NULL,               -- auto-increment per position
    assessment_type       NVARCHAR(20) NOT NULL,      -- 'ORIGINAL' | 'UPDATE'
    verdict               NVARCHAR(20) NOT NULL,      -- 'EXECUTE' | 'WAIT' | 'PASS'
    score                 INT NOT NULL,               -- 0-100
    synopsis              NVARCHAR(200),              -- 5-7 word Claude summary
    claude_read           NVARCHAR(MAX) NOT NULL,     -- full analysis text
    exit_levels           NVARCHAR(MAX),              -- JSON: take_profit, warning, hard_stop, calendar_exit
    market_snapshot       NVARCHAR(MAX),              -- JSON: underlying_price, iv, delta, spread_mark
    agent_run_id          UNIQUEIDENTIFIER,           -- FK to agent_run_log
    created_at            DATETIME2 DEFAULT GETUTCDATE()
)
```

Create the corresponding Pydantic schemas in `app/models/schemas.py`:
- `PositionAssessmentCreate` — used by the refresh endpoint
- `PositionAssessmentResponse` — returned by the list endpoint

**Migration of existing data on position create:**
Update the Follow and Take Position endpoints (`POST /api/v1/positions/follow`
and `POST /api/v1/positions/take`) to also create the first `position_assessments`
row with `assessment_type='ORIGINAL'`, copying from the evaluation data that was
passed in. The existing `claude_verdict`, `claude_exit_levels`, `claude_score`
fields on the positions table stay for backward compatibility.

## Task 2: Assessment List, Archive, and Current Pricing endpoints (OTA-265)

Add these endpoints to `app/api/position_routes.py`:

### GET /api/v1/positions/{id}/assessments
Returns all assessments for a position ordered by `created_at DESC`.
Response: list of `PositionAssessmentResponse` objects.

### PATCH /api/v1/positions/{id}/archive
Sets position `status` to `'ARCHIVED'`. This is a new status value alongside
FOLLOWING, LIVE, and CLOSED. Archived = expired or manually shelved.
Closed = explicit exit with recorded P&L. Different semantics.

Update the `GET /api/v1/positions` list endpoint to exclude ARCHIVED positions
by default. Add an `include_archived` query parameter (default false).

### GET /api/v1/positions/current-prices
Accepts query parameter `position_ids` (comma-separated UUIDs).
For each position:
1. Read the position's `trade_structure` JSON to get the symbol and legs
2. Fetch current Schwab quote for the underlying via existing market data provider
3. If it's a spread, fetch current option chain and calculate spread mark
4. Return: `{ position_id, current_premium, current_pnl, pnl_pct, perf_status }`
5. Update `current_price` and `current_pnl` on the positions table

`perf_status` logic:
- `'green'` if current_pnl > 0 and not within 10% of warning level
- `'amber'` if current_pnl < 0 OR within 10% of warning level from exit_levels
- `'red'` if hard stop breached (current underlying beyond hard stop price)

## Validation

After completing both tasks, verify:
```bash
# Start backend
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --ssl-keyfile key.pem --ssl-certfile cert.pem

# Test via Swagger UI at https://127.0.0.1:8000/docs
# 1. Create a position via POST /positions/follow — verify assessment row created
# 2. GET /positions/{id}/assessments — verify returns the ORIGINAL assessment
# 3. PATCH /positions/{id}/archive — verify status changes to ARCHIVED
# 4. GET /positions — verify archived position excluded by default
# 5. GET /positions?include_archived=true — verify it appears
```

## House Rules
- All dates use DATETIME2
- All UUIDs use UNIQUEIDENTIFIER with DEFAULT NEWID()
- Pydantic models for all request/response schemas
- No hardcoded provider names — use `_get_provider()`
- Schwab is the sole market data provider
