# Claude Code Prompt — OTA-264 OTA-266
## Position Assessment Versioning: Refresh Endpoint + Synopsis SKILL.md

### Tickets
- OTA-264: Position Refresh endpoint — re-run analysis with current data, create new assessment version
- OTA-266: Add synopsis generation to evaluation SKILL.md for position refresh

---

### Before You Start

```bash
cat app/routers/evaluation_routes.py
cat app/routers/position_routes.py
cat app/models/schemas.py | grep -n "Position\|Assessment\|Verdict" | head -40
cat app/skills/claude-trade-agent/SKILL.md
cat app/skill_loader.py
```

Read all five before writing code. The refresh endpoint must follow the same Claude call pattern as the existing evaluation routes.

---

## Part 1 — OTA-266: Add Synopsis to SKILL.md (do this first)

**File:** `app/skills/claude-trade-agent/SKILL.md`

Add a new section titled **"Position Refresh Assessment"**.

This prompt is used when re-evaluating an existing position with current market data. It differs from the initial structured evaluation in that it:
1. Receives all prior assessments so Claude can reference its own analysis history
2. Must output a `synopsis` field: a 5–7 word summary of whether the original thesis holds or what changed

**Section to add:**

```markdown
## Position Refresh Assessment

### System Prompt (static — cache this section)

You are a professional options trade analyst reviewing an existing position. You have access to the original trade entry context and all prior assessments you have made on this position. Your job is to assess whether the original thesis still holds given current market data.

Rules:
- Return ONLY a valid JSON object. No preamble, no markdown fences, no explanation outside the JSON.
- All six fields are required. Never omit a field.
- synopsis: 5–7 words summarizing thesis status. Examples: "IV expanding, thesis strengthening slightly", "Bullish rally pressuring thesis, hold for now", "Thesis intact, theta decay on track". Be direct. No filler words.
- verdict: One of exactly: EXECUTE, WATCH, or PASS.
- score: Integer 0–100 reflecting current position health.
- claude_read: 2–3 sentences of detailed analysis referencing current vs. entry data.
- exit_levels: Object with profit_target (price) and stop_loss (price) given current conditions.
- assessment_type: Always "UPDATE" for this prompt.

### User Prompt Template (dynamic — do not cache)

Review this position:

**Original Entry:**
Spread: {spread_type}
Strikes: {long_strike} / {short_strike}
Expiry: {expiry}
Entry Price: {entry_price}
Entry Date: {entry_date}
Max Profit: {max_profit} | Max Loss: {max_loss}
Original Thesis: {original_thesis}

**Current Market Data:**
Underlying Price: {current_price}
Current Spread Value: {current_spread_value}
Current P&L: {current_pl} ({current_pl_pct}%)
DTE Remaining: {dte_remaining}
Current IV: {current_iv}

**Prior Assessment History:**
{prior_assessments}

Based on how conditions have changed since entry and your prior assessments, provide your update.

Return this exact JSON structure:
{
  "synopsis": "5-7 word summary",
  "verdict": "EXECUTE" | "WATCH" | "PASS",
  "score": integer 0-100,
  "claude_read": "2-3 sentence analysis",
  "exit_levels": { "profit_target": float, "stop_loss": float },
  "assessment_type": "UPDATE"
}
```

**After editing, verify:**
```bash
grep -n "Position Refresh Assessment" app/skills/claude-trade-agent/SKILL.md
grep -n "synopsis" app/skills/claude-trade-agent/SKILL.md
```

---

## Part 2 — OTA-264: Position Refresh Endpoint

**New endpoint:**
```
POST /api/v1/positions/{id}/refresh
```

**Logic sequence:**
1. Fetch the position from DB by `id` — return 404 if not found
2. Fetch all prior `position_assessments` rows for this position, ordered by `created_at ASC`
3. Fetch current market data via Schwab provider: `quote(symbol)` + `get_chain(symbol, ...)`
4. Calculate current spread value and P&L from the chain data
5. Load the "Position Refresh Assessment" section from SKILL.md via `skill_loader.py`
6. Build the prompt with all prior assessments formatted as a readable history block
7. Call AI provider via provider factory (Foundry in prod, Anthropic direct in dev)
8. Parse JSON response and validate against a new `PositionRefreshResponse` Pydantic model
9. Write a new row to `position_assessments` table with `assessment_type = "UPDATE"`
10. Write to `agent_run_log` (fire-and-forget async — must not block response)
11. Return the `PositionRefreshResponse`

**New Pydantic model (add to `schemas.py`):**
```python
class PositionRefreshResponse(BaseModel):
    position_id: int
    synopsis: str
    verdict: Literal["EXECUTE", "WATCH", "PASS"]
    score: int
    claude_read: str
    exit_levels: dict  # { "profit_target": float, "stop_loss": float }
    assessment_type: str  # "UPDATE"
    assessment_id: int    # new row ID from position_assessments
```

**Prior assessments format block** (pass to prompt as `{prior_assessments}`):
```
Assessment 1 (mm-dd-yyyy):
  Verdict: WATCH | Score: 72
  Synopsis: IV expanding, thesis strengthening slightly
  Claude's Read: [claude_read text]

Assessment 2 (mm-dd-yyyy):
  Verdict: EXECUTE | Score: 81
  ...
```
If no prior assessments exist, pass `"No prior assessments — this is the first review."`.

---

### Error Handling
- Position not found → 404
- Schwab market data unavailable → 503 with message
- AI provider error → 502 with message
- `agent_run_log` write failure → log only, never propagate to caller

---

### Verify via Swagger

1. Create or identify an existing position with a known ID
2. `POST /api/v1/positions/{id}/refresh`
3. Confirm response includes `synopsis`, `verdict`, `score`, `claude_read`
4. Check `position_assessments` table has a new row with `assessment_type = "UPDATE"`
5. Call refresh again — confirm second call includes the first assessment in prior history

---

### Commit Message
```
OTA-264 OTA-266 feat: position refresh endpoint with assessment versioning and synopsis
```
