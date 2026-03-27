# Claude Code Prompt — OTA-292 OTA-297
## Phase 2.11 Backend Stream A: Exit Scenario Engine + Structured Evaluation Endpoint

### Tickets
- OTA-292: Exit Scenario Computation Engine and API Endpoint (`POST /api/v1/evaluate/exit-scenario`)
- OTA-297: TradeVerdictResponse Pydantic Schema and `/evaluate/structured` Endpoint

---

### Before You Start

```bash
cat app/routers/evaluation_routes.py
cat app/models/schemas.py | grep -n "Trade\|Verdict\|Evaluate" | head -40
cat app/engines/black_scholes.py
cat app/providers/base.py | head -60
```

Read all four before writing any code. The exit scenario endpoint must use the existing BS engine — do not rewrite probability math.

---

## Part 1 — OTA-292: Exit Scenario Computation Engine

### New endpoint
```
POST /api/v1/evaluate/exit-scenario
```

### Request schema (add to `schemas.py`):
```python
class ExitScenarioRequest(BaseModel):
    spread_type: str          # BEAR_PUT_DEBIT, BULL_CALL_DEBIT, BULL_PUT_CREDIT, BEAR_CALL_CREDIT
    long_strike: float
    short_strike: float
    expiry: str               # ISO date string e.g. "2026-05-15"
    entry_price: float        # per share (e.g. 8.80)
    underlying_price: float
    iv: float                 # implied volatility as decimal (e.g. 0.28)
    risk_free_rate: float     # e.g. 0.05
```

### Computation sequence:
1. Calculate `spread_width = abs(long_strike - short_strike)`
2. Calculate `dte` from today to `expiry`
3. Calculate `max_profit` and `max_loss` using the same formulas as `vertical_engine.py` (debit vs credit)
4. Generate price range: from `min(long_strike, short_strike) - 5` to `max(long_strike, short_strike) + 5`, in **5-dollar steps**
5. For each price in range, calculate:
   - `spread_value`: intrinsic value of the spread at that underlying price
   - `pl_per_contract`: `(spread_value - entry_price) * 100` for debits; `(entry_price - spread_value) * 100` for credits
   - `pl_pct`: `pl_per_contract / (max_loss)` as a percentage
   - `probability`: BS cumulative probability of underlying reaching that price by expiry — use `black_scholes.py`
   - `expected_value`: `pl_per_contract * probability`
   - `zone`: one of `max_profit`, `profit`, `entry`, `warning`, `max_loss` (based on price relative to breakeven and strikes)
   - `exit_signal`: label for key rows — `MAX PROFIT`, `BREAKEVEN`, `ENTRY`, `STOP`, `TIME EXIT`, or empty string

6. Add a **TIME EXIT** row at expiry minus 7 calendar days (use today's price for that row — it's an approximate marker, not a computed value)
7. Return an array of row objects + summary fields: `breakeven`, `max_profit_price`, `max_loss_price`, `total_ev`

### Response schema (add to `schemas.py`):
```python
class ExitScenarioRow(BaseModel):
    underlying_price: float
    spread_value: float
    pl_per_contract: float
    pl_pct: float
    probability: float
    expected_value: float
    zone: str
    exit_signal: str

class ExitScenarioResponse(BaseModel):
    rows: List[ExitScenarioRow]
    breakeven: float
    max_profit_price: float
    max_loss_price: float
    total_ev: float
    dte: int
    time_exit_date: str       # mm-dd-yyyy format
```

### Acceptance criteria:
- `BEAR_PUT_DEBIT` 370/345 at 8.80: entry row shows `pl_per_contract = 0.00`, at 345 row shows `pl_per_contract = 1620.00`
- `BEAR_CALL_CREDIT` 395/420 at 5.40: entry row shows `pl_per_contract = 540.00`, at 420 row shows `pl_per_contract = -1960.00`
- No Claude/AI involvement — pure math
- No `$` prefix on any value

---

## Part 2 — OTA-297: TradeVerdictResponse Schema + `/evaluate/structured` Endpoint

### New Pydantic models (add to `schemas.py`):

```python
class KeyLevel(BaseModel):
    price: float
    description: str

class TradeVerdictResponse(BaseModel):
    ev_commentary: str
    key_level: KeyLevel
    iv_context: str
    verdict: Literal["EXECUTE", "WATCH", "PASS"]
    verdict_rationale: str
```

All five fields are **required** — any missing field raises 422, never a partial render.

### New endpoint:
```
POST /api/v1/evaluate/structured
```

**Request:** Accept the full `ExitScenarioResponse` payload (the output of `/evaluate/exit-scenario`) plus spread economics:

```python
class StructuredEvaluationRequest(BaseModel):
    # Spread identity
    spread_type: str
    long_strike: float
    short_strike: float
    expiry: str
    entry_price: float
    # Pre-computed from exit scenario
    max_profit: float
    max_loss: float
    breakeven: float
    dte: int
    total_ev: float
    ev_pct_of_risk: float     # total_ev / max_loss * 100
    p_max_profit: float       # probability at max profit price row
    p_breakeven_or_better: float
    p_max_loss: float
    iv: float
```

**Logic:**
1. Load the SKILL.md prompt from `app/skills/claude-trade-agent/SKILL.md` using `skill_loader.py`
2. Call the AI provider via the provider factory (never hardcode provider)
3. Parse the JSON response and validate against `TradeVerdictResponse`
4. Return the structured object
5. Fire-and-forget async write to `agent_run_log` (do not block response)

**Provider routing rule:** Azure Foundry in `production`, Anthropic direct in `development` — enforced by provider factory, never hardcoded in this route.

**Error handling:**
- If AI returns malformed JSON → return 422 with clear message
- If provider unavailable → return 503
- agent_run_log write failure must never propagate to caller

---

### After Building

Verify via Swagger at `https://127.0.0.1:8000/docs`:
1. Call `/evaluate/exit-scenario` with the MSFT BEAR_PUT_DEBIT 370/345 anchor values
2. Confirm row at strike 345 shows `pl_per_contract = 1620.00`
3. Call `/evaluate/structured` with those values — confirm it returns a valid `TradeVerdictResponse`
4. Check `agent_run_log` has a new row

---

### Commit Message
```
OTA-292 OTA-297 feat: exit scenario engine and structured evaluation endpoint
```
