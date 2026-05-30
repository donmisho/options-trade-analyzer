# OTA-664 — Diagnose and fix long call evaluate 502

## Problem

Clicking "Evaluate" on a long call trade candidate returns HTTP 502 with no
JSON body. The frontend displays "Evaluation failed: API error: 502".

This affects long call (and possibly long put) candidates only. Vertical spread
evaluations appear to work.

## Symptoms

- Frontend shows: `Evaluation failed: API error: 502`
- No JSON error body is returned (server crash or timeout, not a handled error)
- Schwab is disconnected at the time — but this should not prevent evaluation
  (evaluation uses AI + cached/computed data, not live quotes)

## Relevant Code

### Backend entry point
- `app/api/evaluation_routes.py:500-783` — `evaluate_structured()`
- Line 783: `raise HTTPException(status_code=502, detail=f"AI evaluation failed: {e}")`
  — this is the only 502 raise, but it returns a JSON body. A bare 502 with no
  body suggests the handler never reaches this line (unhandled exception or timeout).

### Evaluation pipeline stages (any could crash)
1. **DTE derivation** (lines 523-532) — parses `dte` from trade dict or expiration
2. **Hard gate evaluation** (lines 537-600+) — gate checks; long calls may hit
   a code path verticals don't (different `spread_type`/`option_type` handling)
3. **Probability matrix** (Black-Scholes computation) — may fail if IV or price
   data is missing from the trade dict for long options
4. **Prompt assembly** — SKILL.md template variable substitution
5. **AI call** (lines 760-783) — `adapter.chat()` via Foundry; could timeout
6. **Response parsing** (`_try_parse_cards()` lines 148-171) — JSON parse of
   Claude output; crash here would be unhandled

### Long option vs vertical differences
Long option trade dicts have `option_type` (call/put) instead of `spread_type`
(bull_put, etc.). Any code that assumes `spread_type` exists without fallback
would crash on long options. Key areas to check:
- Gate evaluation: credit/debit width calculations
- Probability matrix: strike price extraction
- Prompt template: variable substitution expecting vertical-specific fields

## Diagnosis Steps

1. **Check App Service logs** for the 502 request:
   - Azure Portal > App Service > Log stream (or Diagnose and Solve Problems)
   - Look for Python traceback at the time of the failed evaluation
   - The `logger.error` at line 777-782 logs `eval_error_details` — check if
     this log entry exists. If not, the crash is before the try/except block.

2. **Check agent_run_log** table for failed runs:
   ```sql
   SELECT TOP 10 * FROM agent_run_log
   WHERE skill_name = 'claude-trade-agent'
   ORDER BY created_at DESC;
   ```
   If no row exists for the failed call, the crash is before the AI call.

3. **Reproduce locally** with a long call candidate:
   - Start backend with `--reload`
   - Navigate to a symbol with long call candidates
   - Click Evaluate on a long call
   - Check terminal output for the full traceback

4. **Narrow the crash point** by adding temporary logging:
   ```python
   # At the top of evaluate_structured, after gate evaluation:
   logger.info(f"[DEBUG-664] past gates, trade_type={request.trade.get('option_type')}")
   # Before probability matrix:
   logger.info(f"[DEBUG-664] building prob matrix, iv={...}, dte={dte}")
   # Before AI call:
   logger.info(f"[DEBUG-664] calling AI, prompt_len={len(user_message)}")
   ```

## Fix Criteria

- Long call and long put evaluations return structured evaluation cards
  (same as verticals)
- No unhandled exceptions — all error paths return a proper JSON error response
- Agent run log captures the attempt (even if AI call fails)

## Scope

- Backend only (`app/api/evaluation_routes.py`)
- Possibly `app/analysis/black_scholes.py` if the probability matrix crashes
  on single-leg option inputs
- No frontend changes needed (error display already fixed in OTA-663)
