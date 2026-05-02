# PHASE-2.11 — Claude Structured Evaluation + Probability Matrix

## Objective

Replace the open-ended AskClaudePanel with a structured analytical engine. Claude
returns consistent, comparable evaluation cards per strategy. The probability matrix
is computed by Black-Scholes (backend math), not Claude. Claude's role is judgment
and qualitative commentary, not arithmetic.

## Why This Phase Third

Depends on Phase 2.9 (strategy scorecard — need strategies to evaluate) and Phase 2.10
(positions — evaluation output gets attached to positions via Follow/Take Position).
The probability matrix computation was built in Phase 2.9 (black_scholes.py) and is
ready to use here.

## Dependencies

- Phase 2.9 complete (StrategyScorecard, black_scholes.py working)
- Phase 2.10 complete (positions table exists, Follow/Take Position wired)
- Azure Foundry connected (FOUNDRY_API_KEY set in .env)

---

## What Changes

### Retired
- `AskClaudePanel.jsx` — removed from all routing and imports
- `POST /api/v1/evaluate/trade` — deprecated, returns 410 Gone
- `POST /api/v1/evaluate/followup` — deprecated

### New
- `POST /api/v1/evaluate/structured` — single endpoint, returns structured cards
- `TradeEvaluationCard.jsx` — renders one strategy evaluation card
- `ProbabilityMatrix.jsx` — renders the B-S probability table
- `app/skills/claude-trade-agent/SKILL.md` — updated for structured output format

---

## The Structured Evaluation Output Contract

This is the exact JSON shape Claude must return. It is enforced via Pydantic on the
backend before returning to the frontend. If Claude's output doesn't parse, the
backend retries once with an explicit correction prompt.

```python
class TradeEvaluationCard(BaseModel):
    strategy_key: str
    strategy_label: str
    trade_structure: str            # "Sell 415P / Buy 410P, Dec 19"
    entry_price: float
    max_profit: float
    max_loss: float
    exit_warning_price: float       # underlying price that triggers warning
    exit_warning_pnl: float         # position P&L at warning (negative = loss)
    exit_target_debit: float        # debit to close that represents ~50% profit
    exit_stop_debit: float          # debit to close that represents 2× credit
    probability_matrix: ProbabilityMatrix   # pre-computed, passed in from B-S
    score: int                      # 0-100 from strategy scorer
    verdict: str                    # EXECUTE | WAIT | PASS
    claude_read: str                # 2-3 sentences on fit with current conditions
    key_risks: List[str]            # 2-3 bullet points
    thesis_invalidators: List[str]  # conditions that would make this wrong
```

---

## Parallel Streams

### Stream A — Backend (start immediately)
Updated evaluation endpoint + SKILL.md + structured output parsing

### Stream B — Frontend (start with mock data)
TradeEvaluationCard + ProbabilityMatrix components + integration into SecurityDashboard

---

## Stream A: Backend Work

### A1 — Updated SKILL.md for Structured Output

**File**: `app/skills/claude-trade-agent/SKILL.md`

The SKILL.md must be updated to instruct Claude to return ONLY valid JSON matching
the TradeEvaluationCard schema. Key instructions:

```markdown
## Output Format

Return ONLY a JSON array. No preamble, no markdown fences, no explanation outside
the JSON structure. Each element of the array is one TradeEvaluationCard.

For verdict:
- EXECUTE: score ≥ 70, IV rank favorable, SMA alignment matches trade direction,
  probability matrix shows price staying within profitable zone
- WAIT: score 50-69 OR conditions not fully aligned but thesis is valid
- PASS: score < 50 OR conditions actively unfavorable for this strategy

For claude_read: 2-3 sentences maximum. State what's working, what's not,
and one specific thing to watch. No generic statements.

For key_risks: exactly 2-3 items, each under 15 words.
For thesis_invalidators: exactly 2-3 items. These are specific price/event
conditions — not general risk statements.
```

### A2 — Structured Evaluation Endpoint

**File**: `app/api/evaluation_routes.py` (update)

```
POST /api/v1/evaluate/structured
  Request: {
    symbol: str,
    current_price: float,
    iv: float,
    sma_alignment: dict,
    strategy_keys: List[str],     # which strategies to evaluate
    trade: Optional[dict]          # pre-populated trade or null (Claude finds best)
  }
  Response: {
    evaluations: List[TradeEvaluationCard],
    evaluated_at: str,
    agent_run_id: str
  }
```

Implementation steps:
1. For each strategy_key, compute probability matrix (black_scholes.py)
2. Build structured prompt using SKILL.md template
3. Include probability matrix as context in prompt
4. Call Foundry endpoint
5. Parse JSON response into List[TradeEvaluationCard] via Pydantic
6. If parse fails, retry once with correction prompt
7. Write to agent_run_log
8. Return evaluations

### A3 — Deprecate Old Endpoints

```python
@router.post("/trade")
async def evaluate_trade_deprecated():
    return JSONResponse(
        status_code=410,
        content={"detail": "Deprecated. Use POST /api/v1/evaluate/structured"}
    )
```

---

## Stream B: Frontend Work

### B1 — ProbabilityMatrix Component

**File**: `web/src/components/ProbabilityMatrix.jsx` (new)

Renders the B-S probability table as a grid.

Columns: price levels (440, 430, 420, ... current price highlighted, ... 360)
Rows: dates (Exp-9, Exp-6, Exp-3, Expiration)
Cells: probability percentage, colored by intensity (higher prob = darker green)

Current price row is highlighted with a different background.
The "profitable zone" for a credit spread (between the short strikes) is
subtly highlighted to show where the trade makes money vs loses money.

```javascript
props: {
  matrix: ProbabilityMatrix,   // from API
  tradeStructure: dict,        // to highlight profitable zone
  currentPrice: float
}
```

### B2 — TradeEvaluationCard Component

**File**: `web/src/components/TradeEvaluationCard.jsx` (new)

Renders one strategy's full evaluation. Layout:

```
┌──────────────────────────────────────────────────┐
│  Steady Paycheck                    Score: 84     │
│  EXECUTE                                          │
├──────────────────────────────────────────────────┤
│  Sell 415P / Buy 410P, Dec 19                    │
│  Entry: 2.45 credit  Max Profit: 245  Max Loss: 255 │
│  Exit Warning: MSFT below 412.50 (P&L: -$85)     │
│  Exit Target: Buy back at 1.23 debit (50% profit) │
│  Exit Stop: Buy back at 4.90 debit (2× credit)   │
├──────────────────────────────────────────────────┤
│  PROBABILITY MATRIX                              │
│  [ProbabilityMatrix component]                    │
├──────────────────────────────────────────────────┤
│  Claude's Read                                   │
│  "MSFT is well-positioned for this trade given..." │
│                                                  │
│  Key Risks:                                      │
│  • Earnings in 18 days could spike IV            │
│  • Support at 410 has been tested twice          │
│                                                  │
│  This trade is wrong if:                         │
│  • MSFT breaks below 408 on heavy volume         │
│  • Fed announcement causes broad market selloff  │
├──────────────────────────────────────────────────┤
│           [📌 Follow]    [💰 Take Position]       │
└──────────────────────────────────────────────────┘
```

Follow and Take Position buttons call the position_routes.py endpoints from Phase 2.10,
now including the full claude_* fields from the evaluation.

### B3 — SecurityDashboard Evaluate Flow

**File**: `web/src/pages/SecurityDashboard.jsx` (update)

After user selects strategies and clicks "Evaluate Selected":
1. Call `POST /api/v1/evaluate/structured`
2. Show loading state (skeleton cards)
3. Render one `TradeEvaluationCard` per strategy below the scorecard
4. Cards appear in order of score (highest first)

### B4 — OptionsTerminal Integration

**File**: `web/src/pages/OptionsTerminal.jsx` (update Stage 2 and Stage 3)

Stage 2 expansion now shows:
1. StrategyScorecard (from Phase 2.9)
2. Evaluate button
3. On evaluate: TradeEvaluationCard(s) rendered inline in the expansion

Stage 3 (side drawer) is retired. AskClaudePanel import removed.

---

## Integration Testing (End of Phase 2.11)

**Test 1 — Structured output parses correctly**
1. Call `POST /api/v1/evaluate/structured` via Swagger for MSFT, strategy=steady-paycheck
2. Response must be valid JSON matching TradeEvaluationCard schema
3. All required fields must be present and non-null
4. Verdict must be EXECUTE, WAIT, or PASS — no other values

**Test 2 — Probability matrix is mathematically consistent**
1. In the returned evaluation card, check probability_matrix
2. For any given date column, probabilities should sum to ~1.0
3. Probabilities should decrease as price moves further from current
4. Current price cell should have the highest probability for near-term dates

**Test 3 — Follow from evaluation card attaches Claude data**
1. Evaluate a strategy from SecurityDashboard
2. Click Follow on the evaluation card
3. Navigate to Positions page
4. Find the created position — expand detail view
5. claude_verdict, claude_exit_levels, claude_probability_matrix should all be populated

**Test 4 — Multiple strategy evaluation in one call**
1. Select 3 strategies on SecurityDashboard
2. Click Evaluate
3. Verify exactly ONE call to /api/v1/evaluate/structured (not three)
4. Three TradeEvaluationCards should render

**Test 5 — AskClaudePanel is fully retired**
1. Search codebase for AskClaudePanel imports
2. Should find zero active imports (only the deprecated file itself)
3. Old endpoints /evaluate/trade should return 410

**Test 6 — agent_run_log entry created**
1. Run any evaluation
2. Query agent_run_log table in Azure SQL (or SQLite in dev)
3. Row should exist with prompt_text, response_text, prompt_version, created_at

---

## Claude Code Prompts

### Prompt A1 (Stream A)
```
Read CLAUDE.md and architecture-plan.md and PHASE-2.11.md.

Update app/skills/claude-trade-agent/SKILL.md as specified in PHASE-2.11.md
section A1. The skill must instruct Claude to return ONLY a JSON array of
TradeEvaluationCard objects with no preamble or markdown fences.

Add the TradeEvaluationCard Pydantic model to app/models/schemas.py with all
fields specified in the output contract section. Include a validator that ensures
verdict is one of EXECUTE | WAIT | PASS.

Then create the structured evaluation endpoint in app/api/evaluation_routes.py
as specified in section A2. The endpoint must:
1. Compute probability matrix for each strategy using black_scholes.py
2. Build prompt from SKILL.md via skill_loader.py
3. Call Foundry adapter
4. Parse response as List[TradeEvaluationCard]
5. Retry once if JSON parsing fails
6. Write to agent_run_log
7. Return structured response

Deprecate the old /evaluate/trade and /evaluate/followup endpoints with 410 responses.
```

### Prompt B1 (Stream B — run simultaneously with A1)
```
Read CLAUDE.md and PHASE-2.11.md.

Create web/src/components/ProbabilityMatrix.jsx as specified in section B1.
Use mock data: current price 415, range 370-460 in $10 steps, 4 date columns.
Color cells by probability intensity using green opacity (0.1 to 0.9).
Highlight the current price row. Add a subtle highlight for a mock profitable
zone between 410-420.

Create web/src/components/TradeEvaluationCard.jsx as specified in section B2.
Use mock data showing a complete evaluation card for Steady Paycheck on MSFT.
Include all sections: header, trade structure, probability matrix, Claude read,
key risks, thesis invalidators, and Follow/Take Position buttons (disabled for now).
```

### Prompt B2 (Stream B — after both A1 and B1 are done)
```
Read CLAUDE.md and PHASE-2.11.md.

Wire the evaluation flow end-to-end:

1. Add evaluateStrategies(payload) to web/src/api/client.js calling
   POST /api/v1/evaluate/structured

2. Update SecurityDashboard.jsx to call evaluateStrategies when "Evaluate Selected"
   is clicked and render TradeEvaluationCard components for each result

3. Update OptionsTerminal.jsx Stage 2 to include the evaluate flow and render
   TradeEvaluationCard inline in the expansion

4. Wire Follow and Take Position buttons in TradeEvaluationCard to call the
   position endpoints from Phase 2.10, passing the full claude_* data

5. Remove AskClaudePanel from all imports. Remove Stage 3 drawer from OptionsTerminal.
   Verify no broken references.
```
