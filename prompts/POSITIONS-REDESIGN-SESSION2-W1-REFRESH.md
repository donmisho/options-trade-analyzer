---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Positions Redesign — Session 2, Window 1: Refresh Endpoint + SKILL.md
# Jira: OTA-264, OTA-266
# Prerequisites: Session 1 Window 1 complete (position_assessments table exists)

## Context

You are building the Position Refresh endpoint — the core feature that lets a user
click ↻ on a position and get a fresh Claude evaluation with current market data.
The evaluation is stored as a new versioned assessment row. Claude must also
generate a 5-7 word synopsis for the version header.

**Read these files first:**
```
cat CLAUDE.md
cat app/api/evaluation_routes.py
cat app/api/position_routes.py
cat app/providers/ai/prompts.py
cat app/providers/ai/base.py
cat app/skills/claude-trade-agent/SKILL.md
cat app/models/database.py | grep -A 30 "class PositionAssessment"
cat app/models/database.py | grep -A 30 "class Position"
```

## Task 1: Position Refresh Endpoint (OTA-264)

Add to `app/api/position_routes.py`:

### POST /api/v1/positions/{id}/refresh

**Flow:**
1. Read position from DB (validate it exists and is ACTIVE — not ARCHIVED/CLOSED)
2. Read all existing assessments for this position (for Claude's history context)
3. Extract trade structure: symbol, legs, strikes, expiry from `trade_structure` JSON
4. Fetch current Schwab data:
   - Current quote for underlying (price, volume, etc.)
   - Current option chain to get the specific legs' current Greeks and marks
   - Calculate current spread mark from the chain data
5. Build Claude prompt context including:
   - Original entry snapshot (from position fields)
   - All prior assessments (verdict, score, synopsis, claude_read — so Claude sees its own history)
   - Current market data
   - Strategy definition (from strategy_definitions.py for the position's strategy_key)
6. Call Claude via the existing AI provider (respect APP_ENV routing: development → Claude Pro, production → Foundry)
7. Parse structured response: verdict, score, synopsis, claude_read, exit_levels
8. Write new row to `position_assessments` with:
   - `assessment_type = 'UPDATE'`
   - `version_number = max(existing versions) + 1`
   - `market_snapshot = JSON of current underlying price, IV, delta, spread mark`
9. Write to `agent_run_log` (fire-and-forget async — never block)
10. Update position table: `current_price`, `current_pnl`, `last_monitored_at`
11. Return the new `PositionAssessmentResponse`

**Pydantic request/response:**
```python
class PositionRefreshResponse(BaseModel):
    assessment: PositionAssessmentResponse
    current_premium: float
    current_pnl: float
    pnl_pct: float
    perf_status: str  # 'green' | 'amber' | 'red'
```

**Error handling:**
- Position not found: 404
- Position is ARCHIVED or CLOSED: 400 "Cannot refresh an archived/closed position"
- Schwab not connected: 503 "Market data unavailable"
- Claude call fails: 502, return partial data with null assessment

## Task 2: Synopsis Generation in SKILL.md (OTA-266)

Update `app/skills/claude-trade-agent/SKILL.md` to support position refresh mode.

Add a new section or conditional block that activates when the prompt includes
prior assessment history. The key addition:

```
## Position Refresh Mode

When you receive prior_assessments in the context, you are updating an existing
position evaluation. Your response MUST include a `synopsis` field.

### Synopsis Rules
- Exactly 5-7 words
- Summarize whether the original thesis holds or what materially changed
- Reference specific data points when possible (IV, SMA, price levels)
- This appears as a one-line header in the UI — make it scannable

### Synopsis Examples (good)
- "IV expanding, thesis strengthening slightly"
- "Bullish rally pressuring thesis, hold for now"
- "SMA 8 test approaching, volume contracting"
- "Approaching take profit, theta accelerating"
- "Hard stop breached, recommend immediate exit"

### Synopsis Examples (bad — too vague)
- "No significant changes observed"
- "Position still looks good"
- "Market is moving"

### Exit Level Updates
When refreshing, recalculate exit levels based on current conditions.
Exit levels MAY change between assessments — e.g., a hard stop may tighten
if the thesis is weakening, or a calendar exit may be added as DTE shrinks.
Always include: take_profit, warning_level, hard_stop.
Optionally include: calendar_exit (when DTE < 14 and breakeven not touched).
```

Update the `TradeVerdict` Pydantic model in `app/providers/ai/base.py` to include:
```python
synopsis: Optional[str] = None  # 5-7 word summary, populated on refresh
```

Update the prompt builder in `app/providers/ai/prompts.py` to include
prior assessment history when provided:
```python
def build_refresh_prompt(position, assessments, current_market_data, strategy_def):
    """Build prompt for position refresh with assessment history."""
    # Include: original entry data, all prior assessments, current data
    # Claude should see its own prior analysis to maintain continuity
```

## Validation

```bash
# After backend is running:
# 1. Create a position via POST /positions/follow with evaluation data
# 2. Call POST /positions/{id}/refresh
# 3. Verify response contains: verdict, score, synopsis, claude_read, exit_levels
# 4. Verify synopsis is 5-7 words
# 5. GET /positions/{id}/assessments — should show 2 rows (ORIGINAL + UPDATE)
# 6. Call refresh again — should show 3 rows
# 7. Verify each assessment has incrementing version_number
# 8. Verify agent_run_log has a new row for each refresh call
```

## House Rules
- SKILL.md is the ONLY place prompt text lives — never hardcode in Python
- AI provider routing: development → Claude Pro, production → Foundry
- Fire-and-forget async for agent_run_log writes
- All scores 0-100, format ##.00
- Dates mm-dd-yyyy in responses
