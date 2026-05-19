# Phase 3b.4 — Query Fixes Cutover Log

**Date:** 2026-05-19
**Ticket:** OTA-670
**Commit:** `OTA-670 feat: phase 3b.4 - query fixes`

---

## Actions Applied

### Actions 1 + 2 — `canonicalize()` on remaining backend sites

**Deviation from §7.3b.4 literal wording:** The audit says "Add `.upper()` normalization." This prompt uses `canonicalize()` instead, for consistency with 3b.2's pattern across the same files, and because the target columns have FK constraints to `symbol_reference.symbol` which requires canonical form (no `$`, uppercased). `canonicalize()` is idempotent — no risk of double-normalization.

**`app/api/trade_evaluation_routes.py` — audit lines 516, 616: NO CHANGES NEEDED.**
Both sites were already wired to `canonicalize(request.symbol)` by 3b.2 (OTA-668). Confirmed at current lines 517 and 617. No action taken.

**`app/api/evaluation_routes.py` — 2 sites changed:**

| Line | Context | Before | After |
|------|---------|--------|-------|
| 567 | `GateTradeContext(symbol=...)` | `request.symbol` | `canonicalize(request.symbol)` |
| 751 | `market_snapshot = {"symbol": ...}` | `request.symbol` | `canonicalize(request.symbol)` |

### Action 3 — `ValidationAssessment.ticker → .symbol` call-site sweep

**Result: zero references outside `database.py` that need rewriting.**

Grep searched all files in `app/` and `tests/` for `.ticker` attribute access and `ticker=` constructor kwargs. Findings:
- `app/models/database.py` — ORM model already renamed by 3b.1 (out of scope)
- `app/models/schemas.py:542` — `ValidationAssessmentCreate` Pydantic schema declares `ticker: str`. This is the API request/response contract, not an ORM attribute reference. Renaming it would be an API-breaking change. **Left unchanged.**
- No route, service, agent, or test file references `ValidationAssessment.ticker` as an attribute, filter, or constructor kwarg.

### Action 4 — Frontend `.toUpperCase()`

**File:** `web/src/components/TradeEvaluationView.jsx`

| Line | Before | After |
|------|--------|-------|
| 186 | `symbol: spread.symbol \|\| ''` | `symbol: (spread.symbol \|\| '').toUpperCase()` |

No other frontend file was touched.

---

## Test Results

### Import check
```
python -c "from app.api import trade_evaluation_routes, evaluation_routes; from app.services import symbol_normalization; print('imports OK')"  → PASS
```

### pytest
```
pytest --ignore=scratch --ignore=dev-agents -q
503 passed, 2 skipped, 0 failures in 42.80s
```

Same scope and pass count as 3b.2 and 3b.3.

### npm run build
```
npm run build
✓ built in 17.57s
```
Pre-existing chunk size warning only (>500 kB). No new errors.

### Smoke-test queries (Section 5)

Not re-run for 3b.4. Changes are application-code normalization (2 Python call sites + 1 JS call site). No schema, FK, or ORM model changes. Prior sub-phase smoke tests remain valid.

---

## Deviations from Audit

1. **`canonicalize()` instead of `.upper()`** for Actions 1 + 2, per prompt's explicit deviation guidance. Reasoning: FK constraints on target columns require canonical form; consistency with 3b.2's pattern in the same files.
2. **Actions 1 + 2 only applied to `evaluation_routes.py`** — the two `trade_evaluation_routes.py` sites (audit lines 516, 616) were already covered by 3b.2's commit. This is reconciliation, not a deviation.
3. **`ValidationAssessmentCreate.ticker` in `schemas.py` left unchanged** — it's a Pydantic API schema field, not an ORM attribute. Renaming would be an API-breaking change outside this prompt's scope.

## Findings Not in Audit

- `evaluation_routes.py` line 685 has `"symbol": request.symbol` in a dict literal on the auto_pass path's `market_snapshot=` kwarg. This is the same pattern as line 751 but wasn't called out in audit §2.2. Left unchanged to stay within the audit's enumerated scope — it's not a DB column write, it's a JSON value inside `market_snapshot`.

---

## File Inventory

| Status | File |
|--------|------|
| MODIFIED | `app/api/evaluation_routes.py` |
| MODIFIED | `web/src/components/TradeEvaluationView.jsx` |

**No files in `app/models/`, `app/services/`, `app/agents/`, or other `web/src/` files were modified.**

---

## Banner: SUCCESS

**Phase 3b is structurally complete.** All four sub-phase cutover logs (3b.1, 3b.2, 3b.3, 3b.4) show SUCCESS.
