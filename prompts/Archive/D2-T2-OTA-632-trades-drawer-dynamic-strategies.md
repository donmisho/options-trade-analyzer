# OTA-632 — Trades page Configuration drawer — show all strategies dynamically

## Deployment context
- Deployment: **D2**
- This terminal: **T2**
- Concurrent terminals: T1 (`OTA-627` strategies declare compatible structures) — already committed before T2's Phase 2 begins
- Cross-terminal dependencies: **T2 cannot start Phase 2 (code change) until T1 (OTA-627) has committed.** T2 may run Phase 1 (read-only discovery) concurrently with T1.

## ⚠️ Hard gate at start of this prompt

Before any code changes, verify T1's commit is present locally:

```
git log --oneline -10 | grep "OTA-627"
```

- **If OTA-627 commit is present:** proceed with Phase 1 and Phase 2.
- **If OTA-627 commit is NOT present:** Phase 1 (read-only discovery) may proceed. **STOP at the end of Phase 1** and wait for Don's signal that T1 has committed. Do not begin Phase 2.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/business-rules.md
```

Plus:

```
cat web/src/pages/TradesPage.jsx                     # Configuration drawer caller + STRATEGY_KEY_MAP at lines 34-37
cat web/src/strategy-configs/index.js                # post-OTA-627 derived helpers
cat web/src/strategy-configs/steady-paycheck.config.js   # confirm short_code is or is not present
grep -rn "STRATEGY_KEY_MAP" web/src/                 # locate every consumer; there may be parallel copies
grep -rn "'SP'\\|'WG'\\|'TR'\\|'LT'" web/src/ | head -30  # find hardcoded short codes
grep -rn "'steady-paycheck'\\|'weekly-grind'\\|'trend-rider'\\|'lottery-ticket'" web/src/ | head -30
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md § Strategy vs trade structure (post-OTA-627)**
A strategy is configurable independent of which trade structure is currently being displayed. The Configuration drawer must expose all strategies regardless of the current Trades view (verticals, calls, etc.). Filtering by visible trade type is wrong; the user may want to configure a strategy that doesn't currently have results showing.

**Source: architecture-plan.md § Single source of truth for strategy metadata**
Strategy metadata (key, short_code, label, compatible_structures, scoring weights, parameter ranges) lives in `web/src/strategy-configs/*.config.js`. The registry derives all maps. No consumer hardcodes strategy keys or short codes.

**Source: UI-GUIDANCE.md § Strategy pills**
Pills display the short_code (SP/WG/TR/LT) with hover tooltips showing the full label. Current short codes remain until the strategy taxonomy rename (separate future epic).

**Source: CLAUDE.md § OTA-512 pattern**
Per-strategy edits persist in localStorage via the existing pattern from OTA-512 (cached-results regression fix). Reuse that pattern; do not invent a new localStorage shape.

**Source: CLAUDE.md § House style**
- Buttons sized to content, never full-width
- `var(--bg2)` restricted to filter bars, QuoteBar, and pill badge backgrounds
- Dark theme CSS variables only — no inline hex

---

## Phase 1 — Discovery (read-only, OK to run concurrent with T1)

1. Inventory every file that has a hardcoded copy of `STRATEGY_KEY_MAP`, hardcoded `'SP'|'WG'|'TR'|'LT'`, or hardcoded `'steady-paycheck'|'weekly-grind'|'trend-rider'|'lottery-ticket'` outside test fixtures. Likely candidates:
   - `web/src/pages/TradesPage.jsx`
   - `web/src/pages/ScanCard.jsx`
   - `web/src/pages/TradeEvaluationCard.jsx` (or the components folder equivalent)
   - `web/src/pages/StrategyPage.jsx`
   - `web/src/pages/PositionsPage.jsx`
   - `web/src/pages/StrategyProfilePage.jsx`
2. Confirm the Configuration drawer body (the component called from `TradesPage.jsx`) already iterates over whatever `strategyKeys` prop it receives.
3. Confirm `web/src/strategy-configs/index.js` post-OTA-627 exposes a derived "all strategies" map suitable for `SCORECARD_STRATEGIES` iteration.
4. Identify whether each strategy config already exports a `short_code` field; if not, this Story adds it.
5. Report findings to Don if anything surprising surfaces (e.g., a strategy config without a label).

**STOP HERE if OTA-627 has not yet committed.** Phase 2 cannot start until T1 commits and you pull/rebase off the new state.

---

## Phase 2 — Implementation (run only after OTA-627 commit is in)

### 1. Add `short_code` field to each strategy config

In each `web/src/strategy-configs/*.config.js`:

- `steady-paycheck.config.js` → `short_code: 'SP'`
- `weekly-grind.config.js` → `short_code: 'WG'`
- `trend-rider.config.js` → `short_code: 'TR'`
- `lottery-ticket.config.js` → `short_code: 'LT'`

### 2. Uniqueness check at registry load

In `web/src/strategy-configs/index.js`, add a build-time / startup uniqueness check across the registry:

```javascript
const seenShortCodes = new Set();
for (const strat of SCORECARD_STRATEGIES) {
  if (seenShortCodes.has(strat.short_code)) {
    throw new Error(`Duplicate strategy short_code: ${strat.short_code}`);
  }
  seenShortCodes.add(strat.short_code);
}
```

This runs at module-load time and prevents misconfigurations from shipping.

### 3. Remove hardcoded `STRATEGY_KEY_MAP` everywhere it exists

Phase 1 located every copy. Replace each with a derived map computed from `SCORECARD_STRATEGIES`:

```javascript
// In web/src/strategy-configs/index.js — single SoT
export const STRATEGY_KEY_MAP = Object.fromEntries(
  SCORECARD_STRATEGIES.map(s => [s.short_code, s.key])
);
export const SHORT_CODE_MAP = Object.fromEntries(
  SCORECARD_STRATEGIES.map(s => [s.key, s.short_code])
);
```

Every consumer imports from `strategy-configs/index.js`. No local copies.

### 4. Drop the `trade_structure` filter from the Configuration drawer caller

In `web/src/pages/TradesPage.jsx`:

- The Configuration drawer caller currently passes a `trade_structure`-filtered subset as `strategyKeys`. Change to pass the full `SCORECARD_STRATEGIES.map(s => s.key)`.
- The drawer body iterates this prop; result is tabs for SP, WG, TR, LT regardless of the current Trades view.
- The existing "tabs only shown when multiple strategies apply" gate at `TradesPage.jsx:527` still applies for single-strategy edge cases. Preserve it.

### 5. Default active tab on drawer open

When the drawer opens, the active tab defaults to the strategy whose results are currently displayed (preserves current behavior). User can switch tabs and edit; edits persist per-strategy in localStorage via the existing OTA-512 pattern.

If no specific strategy is "currently displayed" (e.g., empty Trades view), default to the first strategy in `SCORECARD_STRATEGIES`.

### 6. Verify all six surfaces use the derived maps

For each file in Phase 1's inventory:

- Replace any local hardcoded short-code or strategy-key reference with an import from `strategy-configs/index.js`.
- For badge display, import `SHORT_CODE_MAP[strategy.key]` instead of inlining `'SP'`.
- For lookups by short code, use `STRATEGY_KEY_MAP[short_code]`.

---

## Acceptance criteria

1. Each scorecard config exports a `short_code` field; the registry's startup uniqueness check passes.
2. `web/src/strategy-configs/index.js` exports `STRATEGY_KEY_MAP` and `SHORT_CODE_MAP` derived from `SCORECARD_STRATEGIES` with no hardcoded enumeration.
3. No file outside `web/src/strategy-configs/` declares its own copy of `STRATEGY_KEY_MAP`. `grep -rn "STRATEGY_KEY_MAP" web/src/` returns matches only as imports from `strategy-configs/index.js`.
4. The Configuration drawer at TradesPage.jsx exposes the full `SCORECARD_STRATEGIES` set as tabs (SP, WG, TR, LT) regardless of the current Trades view.
5. The "tabs only shown when multiple strategies apply" gate at line 527 still applies (preserved).
6. The drawer's active tab on open defaults to the strategy whose results are currently displayed.
7. Per-strategy edits persist across page reload via the existing OTA-512 localStorage pattern.
8. **Renaming or adding a strategy requires zero edits to `TradesPage.jsx`, `ScanCard.jsx`, `TradeEvaluationCard.jsx`, `StrategyPage.jsx`, `PositionsPage.jsx`, or `StrategyProfilePage.jsx`.** Verify post-change: `grep -rn "'SP'\\|'WG'\\|'TR'\\|'LT'\\|'steady-paycheck'\\|'weekly-grind'\\|'trend-rider'\\|'lottery-ticket'" web/src/` outside test fixtures returns no matches.
9. **Regression smoke:** open Trades page on verticals view → open Configuration drawer → SP, WG, TR, LT tabs all present. Switch to TR tab → change DTE window → Apply → reload page → setting persists → setting is reflected when TR scores cards on Security Strategies page.

---

## Out of scope

- The `compatible_structures` field on configs (OTA-627, already shipped in T1's commit).
- The structural fit gate on the agent prompt (OTA-618, shipped in D1).
- Pipeline-layer credit-spread generation (OTA-451).
- Strategy taxonomy rename (cute names → mechanics-based names is a future epic).
- New scoring weights or signal definitions.

---

## Verification steps (run before commit)

1. **OTA-627 commit confirmed present** via `git log --oneline -10 | grep "OTA-627"` (re-verify; do not commit if T1's work isn't in your tree).
2. **Hardcoded short-code grep clean** (acceptance criteria 8) — no matches outside test fixtures and `strategy-configs/`.
3. **Manual smoke (dev frontend):**
   - Open Trades page on verticals view → open Configuration drawer → see SP, WG, TR, LT tabs.
   - Switch to TR tab → change DTE window → Apply.
   - Reload page → reopen drawer → switch to TR tab → confirm DTE window persisted.
   - Navigate to Security Strategies page → TR-scored cards reflect the edited DTE window.
4. **Adding-strategy thought experiment:** add a hypothetical fifth strategy config locally (do not commit). Open Trades page → drawer should now show 5 tabs without any edit to `TradesPage.jsx`. Roll back the local edit.
5. **Console clean:** no errors or warnings related to strategy keys or registry initialization on page load.
6. **Pytest:** any tests that referenced `STRATEGY_KEY_MAP` import from `strategy-configs/index.js`. All existing tests pass.

If any verification fails, stop and report.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers OTA-632.

## Push instruction

**DO NOT push. Single push for Deployment 2 will be coordinated by Don after both D2 terminals (T1, T2) have committed.**

## Coordination footer

**Independent — no downstream dependency.** This terminal closes after committing. Don pushes both D2 commits together.

## Commit message template

```
OTA-632 feat: Trades drawer shows all strategies dynamically; short_code on configs; STRATEGY_KEY_MAP derived from registry
```
