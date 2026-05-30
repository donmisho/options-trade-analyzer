# OTA-649 — Security Strategies grid cell scores with N/A semantics

## Terminal context
- This terminal: Terminal A (W4 of routing-fix build schedule; sequenced with OTA-650 and OTA-651 to avoid web/src/client.js merge conflicts)
- Concurrent terminals: none (sequenced, not parallel — see BUILD-SCHEDULE-routing-fix.md for rationale)
- Cross-terminal dependencies: OTA-636 and OTA-637 must be committed and deployed. This Story builds on the `eligible_strategies` and `best_fit` contracts.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
```

Plus, before editing:

```
cat web/src/pages/SecurityDashboard.jsx
cat web/src/components/StrategyScorecard.jsx
cat app/api/analysis_routes.py
cat app/analysis/strategy_routing.py
```

If the Security Strategies page filename differs from `SecurityDashboard.jsx`, find it with PowerShell: `Get-ChildItem -Recurse web/src/pages -Filter "*.jsx" | Select-String "Security Strateg"`.

## Relevant Context — Do Not Deviate Without Escalation

**Source: 031526 - UI-Overhaul-Completion-Plan.docx → Security Strategies Page section**
The scorecard endpoint `/api/v1/analysis/scorecard` may not yet exist. Check before assuming. If missing, this Story includes its creation as a backend prerequisite (Phase 2.9 work folded in here).

**Source: business-rules.md → Strategy-Structure Compatibility**
The corrected cell-score definition:

```
Cell(symbol, strategy) =
  max score(spread, strategy)
  over spreads where:
    spread.underlying = symbol
    AND strategy ∈ eligible_strategies(spread)

When that set is empty: cell displays N/A.
```

**Source: UI-GUIDANCE.md → Part 4 (Formatting)**
Score format `##.00`. Probability `##.00%`. No `$` prefix on monetary values.

**Source: UI-GUIDANCE.md → Part 3 (Color tokens)**
N/A cells use the existing muted-text variable. No new color tokens for this Story.

**Source: OTA-636 backend contract**
`/api/v1/analysis/scorecard` MUST reuse the predicates from `app/analysis/strategy_routing.py`. No duplicate compatibility logic in the scorecard endpoint.

**Source: OTA-637 frontend behavior**
Pill rendering on Security Strategies cards is already null-aware after OTA-637. This Story is about the *cell* score, not the per-spread pill rendering — different concept on the same page.

## Scope

The Security Strategies grid displays a cell per (symbol, strategy). Each cell summarizes "is there a trade for me here under this strategy?". Today's cells score every pair regardless of structural compatibility; corrected behavior is to display N/A when no eligible candidate exists.

### Phase 1 — Read-only diagnostic (mandatory stop-and-report)

1. `cat` every file in Required Reading.
2. Confirm whether `/api/v1/analysis/scorecard` exists. If yes: report its current request/response shape and the cell-score logic. If no: report which endpoint the Security Strategies page currently calls.
3. Inspect the Security Strategies page component. Report:
   - What data shape does it expect from the backend?
   - How does it render cells today — score-bar with number, raw number, color-coded, etc.?
   - What is the click-through behavior on a cell?
4. Identify the `argmax` requirement: for click-through to land on the right spread, the backend must return *which spread* produced the cell's max score. Report whether the current response carries this reference.

**STOP at the end of Phase 1.** Report findings. Wait for "proceed to Phase 2" before continuing.

### Phase 2 — Backend implementation

#### 2a. Endpoint shape — `/api/v1/analysis/scorecard`
- If missing, create it. If present, modify.
- Request: `{ symbols: List[str] }` or per-symbol; match the page's current call pattern.
- Response shape per (symbol, strategy):

```json
{
  "symbol": "MMM",
  "strategy": "steady_paycheck",
  "score": null,
  "argmax_spread_ref": null,
  "reason": "no eligible BULL_PUT_CREDIT/BEAR_CALL_CREDIT candidates passed SP gates"
}
```

Populated case:

```json
{
  "symbol": "MMM",
  "strategy": "trend_rider",
  "score": 78.40,
  "argmax_spread_ref": { "spread_id": "...", "structure": "BEAR_PUT_DEBIT", "strikes": "146/136", "expiry": "2026-05-29" },
  "reason": null
}
```

#### 2b. Cell computation logic
- Reuse `eligible_strategies()` and per-strategy scoring from `app/analysis/strategy_routing.py` and `app/analysis/strategy_scorer.py` (both delivered by OTA-636).
- For each (symbol, strategy):
  1. Fetch the candidate spread universe for the symbol.
  2. Filter to spreads where `strategy ∈ eligible_strategies(spread)`.
  3. Score each filtered spread against `strategy`.
  4. `score = max(scores)` if any survived; `null` otherwise.
  5. `argmax_spread_ref` carries the spread that produced the max.
  6. `reason` is null when score is non-null, populated string when score is null.
- No duplication of the compatibility matrix in the scorecard endpoint. Always go through the helpers.

### Phase 3 — Frontend implementation

#### 3a. Cell rendering
- Populated cell: score `##.00` per UI-GUIDANCE Part 4, with score-bar color per Part 3.
- N/A cell: muted-gray "N/A" text. No score bar. The cell has the same height/border as populated cells — no layout shift between states.
- Tooltip on N/A cell shows the `reason` string from the backend.

#### 3b. Click-through behavior
- Click on populated cell → `/trades?symbol={symbol}` with the `argmax_spread_ref` expanded.
   - Carry the spread reference via URL param or router state so the Trades page knows which row to expand on mount.
- Click on N/A cell → no-op. Tooltip remains visible if hovered.

#### 3c. Visual regression check
For MMM specifically (the canonical leak case):
- SP cell: N/A
- WG cell: N/A
- TR cell: populated, score derived from best Bear Put
- LT cell: per single-leg-long-put availability — N/A or populated

### Phase 4 — Tests

- Backend: a unit test on the scorecard endpoint that asserts MMM (with mocked candidate data) returns N/A for SP/WG and a populated TR cell.
- Frontend: if a test setup exists (`web/src/__tests__/` or similar), add a test that renders the grid with a mix of populated/null cells and asserts the N/A cells render correctly with their tooltips. If no frontend test setup exists, skip and document in the manual verification.

## Acceptance criteria

- [ ] `/api/v1/analysis/scorecard` returns per-cell `{ score | null, argmax_spread_ref | null, reason | null }` with the contract above.
- [ ] Cell computation reuses helpers from `app/analysis/strategy_routing.py`; no duplicate compatibility logic.
- [ ] Populated cells render `##.00` with score-bar color per UI-GUIDANCE.
- [ ] N/A cells render muted-gray "N/A" with tooltip showing the backend `reason`. No layout shift between populated and N/A states.
- [ ] Click on populated cell navigates to `/trades?symbol={symbol}` with the argmax spread expanded.
- [ ] Click on N/A cell is a no-op.
- [ ] For MMM: SP and WG cells show N/A, TR cell is populated, LT per compatibility.
- [ ] No grid cell can show a score for a (symbol, strategy) pair where no eligible spread exists.

## Out of scope

- Security Strategies page layout, filter bar, card sort.
- Symbol-list management or watchlist mechanics on the page.
- Consolidating pill-rendering utilities between Security Strategies and Trades (TODO from OTA-637).
- Path B grouped-by-strategy display on Trades (OTA-651 covers; this Story only handles the cell click-through landing on a specific spread).

## Verification steps

1. Run backend tests: `pytest tests/api/test_analysis_routes.py -v` (or wherever the scorecard endpoint test lives).
2. Hard refresh the Security Strategies page in the browser.
3. Confirm the MMM card displays SP=N/A, WG=N/A, TR=populated, LT=per compatibility.
4. Hover the N/A cells; confirm the tooltip surfaces the backend `reason` string.
5. Click the populated TR cell; confirm navigation to `/trades?symbol=MMM` with a Bear Put expanded.
6. Click an N/A cell; confirm no navigation.
7. Find a known-bullish symbol with healthy IV; load Security Strategies. Confirm SP and WG cells are populated, TR may be populated for any Bull Call debits, LT per compatibility.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

OK to continue to **OTA-650-positions-orphan-grouping.md**

## Commit message template

```
OTA-649 feat: Security Strategies grid cell scores with N/A semantics

- /api/v1/analysis/scorecard returns per-cell {score|null,
  argmax_spread_ref|null, reason|null}
- Cell computation: max score(spread, strategy) over spreads where
  strategy ∈ eligible_strategies(spread); else null
- Frontend cells: populated render ##.00 + score-bar color;
  N/A renders muted "N/A" + tooltip with backend reason
- Click on populated cell navigates to /trades?symbol=X with the
  argmax spread expanded; N/A click is a no-op
- For MMM: SP/WG cells now N/A, TR populated with best Bear Put score

Reuses app/analysis/strategy_routing.py helpers from OTA-636.
Depends on OTA-636 and OTA-637.
```
