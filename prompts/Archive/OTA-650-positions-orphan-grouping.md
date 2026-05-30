# OTA-650 — Positions surface: eligible-strategies grouping, orphan handling, entry guard

## Terminal context
- This terminal: Terminal A (W4 of routing-fix build schedule; sequenced after OTA-649, before OTA-651)
- Concurrent terminals: none
- Cross-terminal dependencies: OTA-636 and OTA-637 must be committed and deployed. OTA-649 should ideally be committed before this Story for `web/src/client.js` clean sequencing.

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
cat web/src/pages/PositionsPage.jsx
cat app/api/positions_routes.py
cat app/analysis/strategy_routing.py
```

Plus the strategy-page positions panel component and the Trade Detail footer's Follow / Take Position component. Find them in PowerShell: `Get-ChildItem -Recurse web/src -Filter "*.jsx" | Select-String "Follow\|Take Position\|strategy_at_entry"`.

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md → Strategy-Structure Compatibility**
A position's `strategy_at_entry` must be a member of `eligible_strategies(position.spread)`. The current state of production data violates this for some positions (MMM Bear Put under Steady Paycheck, observed 2026-05-11).

**Source: this Story's design — no silent rewrites**
Existing orphaned positions are surfaced in an "Orphaned — strategy mismatch" group, NOT silently re-routed to `best_fit`. The user's audit trail is preserved; one click moves the position to its `best_fit` strategy with a recorded action.

**Source: UI-GUIDANCE.md → Part 1 (Strategy pages — positions panel)**
Each strategy page (`/strategies/{key}`) renders a positions panel filtered to that strategy. After this Story, the filter is `this_strategy ∈ eligible_strategies(position.spread)`, not `position.strategy_at_entry == this_strategy`.

**Source: CLAUDE.md → Async-first Azure rule**
If position-create or re-route writes use any Azure SDK, the calls must use `azure.identity.aio` async variants.

**Source: OTA-637 verdict source unification**
Position cards likely display a verdict on each row. That verdict should already be unified post-OTA-637; this Story does not re-touch verdict source.

## Scope

This Story has three concerns: display grouping on `/positions`, the entry guard on Take Position, and the per-strategy positions panel filter. No DB migration — orphans are surfaced rather than rewritten.

### Phase 1 — Read-only diagnostic (mandatory stop-and-report)

1. `cat` every file in Required Reading.
2. Inspect `web/src/pages/PositionsPage.jsx`. Report:
   - How positions are currently grouped (by `strategy_at_entry`, by symbol, by status?).
   - What component renders each position row.
3. Inspect `app/api/positions_routes.py`. Report:
   - The current `POST /api/v1/positions` (or equivalent) request shape.
   - Whether `strategy_at_entry` is currently validated against anything.
4. Inspect the Trade Detail footer. Find Follow / Take Position. Report:
   - How `strategy_at_entry` is currently chosen on entry (defaulted, user-selected, picked from context, etc.).
5. Find the strategy-page positions panel component. Report its current filter logic.
6. Query the production positions table for any position where `strategy_at_entry ∉ eligible_strategies(position.spread)`. Report the count and a few examples. (If running locally, use the dev DB; if a query script doesn't exist, write one for this diagnostic — a one-off in `/tmp` or `/home/claude/`, do not commit it.)

**STOP at the end of Phase 1.** Report findings to Don. Wait for "proceed to Phase 2" before continuing.

### Phase 2 — Backend implementation

#### 2a. Position-create validation
- In `app/api/positions_routes.py` (or wherever `POST /api/v1/positions` is defined):
  - After resolving the spread reference, compute `eligible_strategies(spread)`.
  - If `request.strategy_at_entry ∉ eligible_strategies(spread)`: return 422 with body `{ "error": "incompatible_strategy", "message": "strategy_at_entry={key} not in eligible_strategies={list} for spread.trade_structure={structure}" }`.
- No fallback. No coercion to `best_fit`. The frontend will not present an incompatible option after Phase 3.

#### 2b. Re-route endpoint (new)
- Add `POST /api/v1/positions/{id}/reroute` that accepts no body.
- Server-side: reads the position, computes `eligible_strategies(position.spread)` and `best_fit(position.spread)`.
- If `best_fit` is non-null: updates `strategy_at_entry = best_fit.key`, records the action (timestamp + previous value + new value) in an audit field if one exists, or in a new audit field added in this Story if needed.
- If `best_fit` is null: returns 409 `{ "error": "no_eligible_strategy", "message": "no compatible strategy for this position's spread" }`.

#### 2c. Orphan-listing endpoint (or response field)
Two options — pick whichever fits the existing positions endpoint shape:
- **Option A** (preferred if positions are returned as a flat list): every position carries `is_orphaned: bool` derived server-side from `strategy_at_entry ∉ eligible_strategies(spread)`.
- **Option B**: a separate `GET /api/v1/positions/orphaned` returns just the orphan list.

Choose based on Phase 1's report on the current positions endpoint. Either way: the frontend can identify orphans without re-running the compatibility check client-side.

### Phase 3 — Frontend implementation

#### 3a. `/positions` page grouping
- At the top of the page: an "Orphaned — strategy mismatch" group (only renders if at least one orphan exists).
- Each orphan row displays:
  - The position details as normal.
  - A red/amber visual marker (per UI-GUIDANCE color tokens — use existing warning/error tokens, no new ones).
  - A `Re-route` button (sized to content per UI-GUIDANCE; not full-width). Clicking it calls `POST /api/v1/positions/{id}/reroute`.
  - If the position's `best_fit` is null: the button is disabled with tooltip "no eligible strategy for this spread".
- Below the orphan group: positions grouped normally by `strategy_at_entry`. No layout change to the non-orphan groups.

#### 3b. Trade Detail footer — Follow / Take Position
When the user is about to Take Position on a spread:
- Compute (client-side, from the spread payload) the eligible-strategies list and `best_fit`.
- **Single eligible**: auto-assign and proceed; show the chosen strategy clearly on the button.
- **Multiple eligible**: dropdown defaulting to `best_fit`. User can override to another eligible strategy.
- **No eligible**: button is disabled with tooltip "no compatible strategy for this spread".
- The button's onClick handler sends `strategy_at_entry` matching the chosen strategy. The 422 from the backend should never fire under normal use; it exists as a server-side guard against malformed requests.

#### 3c. Strategy-page positions panel
- Filter: render positions where `this_strategy ∈ eligible_strategies(position.spread)`, NOT `position.strategy_at_entry == this_strategy`.
- This means: a Bear Put position whose `strategy_at_entry` was incorrectly set to SP appears on the Trend Rider page's positions panel (because TR is the eligible strategy) AND on the orphan group on `/positions`. This is intentional — the position is structurally a TR trade.

### Phase 4 — Manual verification + audit

1. Load `/positions`. Confirm the MMM 146/136 Bear Put (currently grouped under Steady Paycheck per the canonical leak case) appears in the Orphaned group. Confirm the Re-route button shows Trend Rider as the target.
2. Click Re-route. Confirm the position moves to the Trend Rider group; orphan group's count decrements by one.
3. Attempt to Take Position on a Bear Put with the Trade Detail footer. Confirm:
   - The strategy selector defaults to Trend Rider (and shows LT if structurally eligible).
   - Steady Paycheck is not selectable.
4. Manually craft a `POST /api/v1/positions` request via curl/Invoke-RestMethod with `strategy_at_entry=steady_paycheck` and `spread.trade_structure=BEAR_PUT_DEBIT`. Confirm 422 with the documented error body.
5. Load `/strategies/trend-rider`. Confirm the MMM Bear Put (re-routed in step 2) appears in the positions panel.
6. Load `/strategies/steady-paycheck`. Confirm the MMM Bear Put does NOT appear in the positions panel (it didn't before, and shouldn't now).

## Acceptance criteria

- [ ] `POST /api/v1/positions` returns 422 when `strategy_at_entry ∉ eligible_strategies(spread)`.
- [ ] `POST /api/v1/positions/{id}/reroute` exists, sets `strategy_at_entry = best_fit.key`, and returns 409 when `best_fit` is null.
- [ ] Positions endpoint surfaces orphan status (either field or dedicated endpoint).
- [ ] `/positions` renders an Orphaned group at top when orphans exist; Re-route button on each orphan; disabled with tooltip when `best_fit` is null.
- [ ] Trade Detail footer's Take Position: single-eligible auto-assigns, multi-eligible dropdown defaults to `best_fit`, no-eligible disables.
- [ ] Strategy-page positions panel filters by `this_strategy ∈ eligible_strategies(position.spread)`.
- [ ] No DB migration; orphans surfaced not rewritten. Audit trail preserved on re-route.
- [ ] All UI-GUIDANCE conventions honored.

## Out of scope

- Position lifecycle state machine (separate concern, pending Story under OTA-507).
- Re-evaluation of `strategy_at_entry` based on changing market conditions after entry.
- Position close mechanics, OCO bracket management, P&L computation.
- Path B grouped-by-strategy display on Trades — OTA-651.

## Verification steps

1. Backend: `pytest tests/api/test_positions_routes.py -v` (or wherever positions tests live).
2. Run the 6-step manual verification from Phase 4 above.
3. If the dev DB has known orphans, confirm the orphan group count matches the diagnostic-query count from Phase 1.
4. After re-routing a test position, confirm the audit trail (if implemented in 2b) records the previous and new `strategy_at_entry` values.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

OK to continue to **OTA-651-pathb-grouping.md**

## Commit message template

```
OTA-650 feat: positions surface routing with orphan handling and entry guard

- POST /api/v1/positions returns 422 when strategy_at_entry not in
  eligible_strategies(spread)
- New POST /api/v1/positions/{id}/reroute sets strategy_at_entry =
  best_fit.key; 409 when best_fit null
- Positions endpoint surfaces is_orphaned per position
- /positions page renders "Orphaned — strategy mismatch" group at top
  with Re-route button per orphan; disabled when best_fit null
- Trade Detail Take Position: single-eligible auto-assigns,
  multi-eligible dropdown defaults to best_fit, no-eligible disabled
- Strategy-page positions panel filters by
  this_strategy ∈ eligible_strategies(position.spread)

No DB migration; orphans surfaced not rewritten. Audit trail preserved.
Depends on OTA-636 and OTA-637.
```
