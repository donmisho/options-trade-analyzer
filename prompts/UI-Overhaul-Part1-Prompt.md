# Claude Code Prompt — UI Overhaul Part 1
## Finish Expansion Panels + Bugs + Shared Infrastructure

---

## Before you do anything else

**Check whether this work is already done.**

Run the following and report back before touching any file:

```bash
# 1. Check if a shared Toast component exists
find web/src -name "Toast.jsx" -o -name "Toast.tsx" -o -name "toast.jsx" 2>/dev/null

# 2. Check if verdict auto-collapse is wired in OptionsTerminal
grep -n "auto.*collapse\|strategy.*switch\|setVerdict.*null\|clearVerdict\|onStrategyChange" web/src/pages/OptionsTerminal.jsx 2>/dev/null | head -20

# 3. Check if Column 4 (Strategy Explanation) exists in the expansion panel
grep -n "StrategyExplanation\|strategy.*explanation\|column.*4\|col4\|paramGrid\|signal.*check" web/src/pages/OptionsTerminal.jsx 2>/dev/null | head -20

# 4. Check if loading animation exists
grep -n "Evaluating\|pulse\|animated\|ellipsis\|loadingText" web/src/pages/OptionsTerminal.jsx 2>/dev/null | head -20

# 5. Check if Puts & Calls strategy filter uses trade_structure
grep -n "trade_structure\|tradeStructure\|long_option\|credit_spread" web/src/pages/OptionsTerminal.jsx web/src/strategy-configs/index.js 2>/dev/null | head -20

# 6. Check AskClaudePanel stale results fix
grep -n "useEffect\|trade\.id\|selectedTrade\|clearResult\|resetPanel" web/src/components/AskClaudePanel.jsx 2>/dev/null | head -20

# 7. Check if watchlist prices are wired
grep -n "quote\|price\|fetch.*quote\|useEffect" web/src/components/Watchlist.jsx 2>/dev/null | head -30
```

For each check: if the feature is already present and working, tell me and skip that task. Only build what is genuinely missing.

---

## Context

Read these files in full before writing any code:

```bash
cat UI-DECISIONS.md
cat CLAUDE.md
cat web/src/pages/OptionsTerminal.jsx
cat web/src/components/AskClaudePanel.jsx
cat web/src/components/Watchlist.jsx
cat web/src/components/QuoteBar.jsx
cat web/src/components/FormulaBreakdown.jsx
cat web/src/strategy-configs/index.js
cat web/src/api/client.js
```

The UI-DECISIONS.md file is the visual contract. It wins over all other sources. Never deviate from the specs it defines.

---

## Scope of This Session

This session completes Groups 1 through 4 from the UI Overhaul Completion Plan. Work in this exact order.

---

## Group 1 — Bugs & Shared Infrastructure

### Task 2.5.1 — Fix AskClaudePanel Stale Results

The `AskClaudePanel` does not reset its evaluation state when the user selects a different trade from the results table. The user sees a stale Claude verdict that belongs to the previously selected trade.

**Fix:**

In `AskClaudePanel.jsx`, add a `useEffect` that clears `result` and `followupResult` state when the trade identity changes. The dependency array must watch specific trade properties — **not** `trade.id` or the whole `trade` object (those don't fire reliably on row switch). Watch these:

```javascript
useEffect(() => {
  setResult(null);
  setFollowupResult(null);
  setFollowupInput('');
}, [trade?.symbol, trade?.buyStrike, trade?.sellStrike, trade?.expiration]);
```

Verify with: open AskClaude for Trade A → receive verdict → click a different trade → AskClaude panel shows blank (no stale content).

---

### Task 2.5.2 — Watchlist Live Prices

**Part A — Proactive token refresh (backend)**

In `app/providers/schwab_token_manager.py`, add a background refresh loop:

```python
# On startup, start a background task that checks token expiry every 5 minutes
# If time_until_expiry < 600 seconds (10 minutes), call refresh_token()
# Log refresh attempts and outcomes
# Do not raise on failure — log the error and continue
```

Wire this into the FastAPI lifespan in `app/main.py` so it starts when the app starts and cancels on shutdown.

**Part B — Watchlist quote fetch (frontend)**

In `web/src/components/Watchlist.jsx`:

1. On component mount, call `GET /api/v1/market/quote/{symbol}` for each symbol in the watchlist. Populate prices from the response.
2. When `activeSymbol` changes, fetch the quote for the new symbol if not already cached.
3. Show a loading state (dim the price field) while fetching. On error, show `—` and do not crash.
4. Cache fetched quotes in component state keyed by symbol. Do not re-fetch a symbol that was fetched within the last 60 seconds.

---

### Task G-1 — Shared Toast Component

Create `web/src/components/Toast.jsx`. It must be a single reusable component — not ad hoc inline toasts.

**Spec:**

- Position: bottom-right, fixed, `z-index: 1000`
- Background: `#21262d` (--bg3), border: `1px solid #30363d` (--border)
- Text: 11px, `#e6edf3` (--text), monospace font
- Animation: slide in from right (200ms ease), auto-dismiss after 3000ms
- Optional link: if `href` prop provided, render a teal-colored clickable link as a second line
- Dismiss: clicking the toast closes it immediately
- Props interface:
  ```javascript
  <Toast
    message="Position added."
    href="/positions"
    linkLabel="View Positions →"
    onDismiss={() => {}}
  />
  ```

Wire it into `App.jsx` or a `ToastContext` so any component can trigger it without prop drilling. Provide a `useToast()` hook that exposes `showToast({ message, href, linkLabel })`.

---

### Tasks G-2 and G-3 — QuoteBar Audit

Read `web/src/components/QuoteBar.jsx` carefully, then:

**G-2 — Earnings/dividend conditional render:**
- Earnings field must NOT render at all when `earningsDate` is null, undefined, or more than 60 days from today
- When within 60 days: renders normally
- When within 14 days: amber badge background `rgba(245,158,11,0.2)`, amber text `#f59e0b`
- Same rule for dividendDate
- Test: pass `earningsDate: null` — field is absent. Pass a date 90 days away — field is absent. Pass a date 10 days away — amber. Pass a date 30 days away — renders normally.

**G-3 — No $ prefix:**
- Audit every rendered value in QuoteBar: price, change, day range, 52-week range
- Remove any `$` prefix anywhere it exists
- House style: display `567.23` not `$567.23`
- This is a hard rule with no exceptions

---

## Group 2 — Finish the Verticals Expansion Panel

Read `web/src/pages/OptionsTerminal.jsx` fully before making any changes. The expansion panel is inline in this file.

### Task V-1 — Column 3: Per-Strategy 'Why' Text

Below each strategy row in Column 3, add a single line of 9px italic muted text explaining why the trade scored that way for that strategy.

**Source:** This text comes from the strategy scorer output. If the backend does not yet return a `why` field per strategy, add a placeholder that reads from `trade.strategyScores[strategyKey].summary` — use whatever field the scorer is actually returning. Do not fabricate text; read what the data actually provides.

**Style:**
```css
font-size: 9px;
font-style: italic;
color: #8b949e;  /* --muted */
margin-top: 3px;
line-height: 1.4;
```

Example content: `"IV rank 67 · bullish SMA · 30-45 DTE ✓"` or `"DTE 35 exceeds 7-14 window"`

---

### Task V-2 — Column 4: Strategy Explanation Panel

Column 4 is the rightmost column of the expansion panel. It is purely informational — no buttons, no inputs. It updates immediately when the user clicks a different strategy row in Column 3.

**Content (top to bottom):**

1. Strategy name — 12px bold teal (`#2dd4bf`)
2. Subtitle — 9px muted (e.g. `"30-45 DTE credit spread · income objective"`)
3. **Parameter grid** — 2-column layout, each row shows:
   - 9px uppercase muted key on the left
   - 11px value on the right: green with ✓ if trade meets the parameter, plain white if neutral, red with ✗ if it fails
   - Source: compare `trade` fields against the strategy config's parameter thresholds
4. **Signal check box** — background `#161b22`, border-radius 4px, padding 8px. Lists 3-4 signal items, each with a colored dot (green/amber/red) and 9px description. Source: SMA alignment, IV rank, volume signal from trade data.

Read `web/src/strategy-configs/steady-paycheck.config.js` (and the others) to understand what parameters and thresholds each strategy defines. Use those config values to drive the ✓/✗ logic.

---

### Task V-3 — Loading State: Animated Dots + Context Text

When "Evaluate with Claude →" is clicked, while waiting for the API response:

**Button label:** `"Evaluating…"` — the three dots pulse individually with staggered CSS animation:
```css
/* Apply to each dot span with animation-delay: 0s, 0.2s, 0.4s */
@keyframes pulse {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}
```

**Button style during loading:**
- Background: `rgba(45,212,191,0.06)` (dimmer than default)
- Color: `#8b949e` (muted)
- `pointer-events: none`

**Context text below button:**
- 9px muted text showing what is being evaluated
- Format: `"[Strategy Name] · [Symbol] [strikes] [expiry]"`
- Example: `"Steady Paycheck · AMZN 200/195 Apr 17"`
- Appears only during loading state; disappears when verdict arrives

---

### Task V-4 — Verdict Auto-Collapse on Strategy Switch

When the user clicks a different strategy row in Column 3 while a verdict card is currently visible:

1. Collapse the verdict card immediately (set verdict state to null / hide the card)
2. Reset the Evaluate button to its default label: `"Evaluate with Claude →"`
3. Update Column 4 to show the newly selected strategy's explanation

This prevents stale verdicts from being misread as applying to the currently selected strategy.

**Implementation note:** The strategy selection state and the verdict state must be connected. When `selectedStrategy` changes, `setVerdict(null)`.

---

### Task V-5 — Button width:auto Audit

Scan all buttons in the expansion panel and the verdict card. Apply this rule strictly:

```css
width: auto;        /* never 100%, never flex-grow: 1 */
flex-shrink: 0;     /* prevent shrinking in flex row */
```

Check: Follow (Paper), Take Position (Live), Evaluate with Claude →, Re-evaluate →, Discard ✕, and any icon buttons. None may stretch to fill their container.

---

### Task V-6 — useEffect Fix for Stale Verdict on Trade Change

The same root cause as Task 2.5.1 applies to the expansion panel itself: if a verdict is showing for Trade A and the user expands Trade B, the verdict from Trade A must not leak into Trade B's panel.

In the expansion panel state management, add:

```javascript
useEffect(() => {
  setExpandedVerdict(null);
  setSelectedStrategy(null);  // or reset to top scorer
}, [trade?.symbol, trade?.buyStrike, trade?.sellStrike, trade?.expiration]);
```

---

## Group 3 — Finish Puts & Calls Expansion Panel

### Task P-1 — Strategy Fit Filtered by trade_structure

The Puts & Calls expansion panel must only show strategies where the strategy config's `tradeStructure` (or `trade_structure`) field matches `'long_option'`.

**Rule:** This filtering MUST read from the strategy config files — never hardcode strategy names.

Read `web/src/strategy-configs/index.js`. Each config has a `tradeStructure` or `payoffType` field. Use that field:

```javascript
// Get all strategies
const allStrategies = getStrategies(); // from strategy-configs/index.js

// For Puts & Calls: show only long_option compatible strategies
const applicable = allStrategies.filter(s => s.tradeStructure === 'long_option');
const notApplicable = allStrategies.filter(s => s.tradeStructure !== 'long_option');
```

If the config files do not yet have a `tradeStructure` field, **add it to each config file now**:
- `steady-paycheck.config.js`: `tradeStructure: 'credit_spread'`
- `weekly-grind.config.js`: `tradeStructure: 'credit_spread'`
- `trend-rider.config.js`: `tradeStructure: 'long_option'`
- `lottery-ticket.config.js`: `tradeStructure: 'long_option'`

This field is required for the filter to work correctly and must exist before Phase 2.9 builds the strategy scoring system.

---

### Task P-2 — Grayed-Out Non-Applicable Strategies

Below the applicable strategy rows, render the non-applicable strategies with:

1. A dashed divider: `border-top: 1px dashed #30363d`
2. A label above the grayed section: `"not applicable to this trade type"` — 9px muted, italic
3. Each non-applicable row rendered at `opacity: 0.35`, `pointer-events: none`
4. A reason string below each grayed strategy name: `"requires credit spread structure"` — 9px muted italic

These rows are visual only. They cannot be selected. They cannot be evaluated.

---

### Task P-3 — Verdict Card for Long Option Context

Verify (do not rebuild) that the TradeEvaluationCard / verdict card renders correctly for a long option trade. Check:

- The trade reference in the verdict header formats correctly for a single-leg trade (no sell strike)
- The exit plan rows make sense for a long option (no credit received to reference)
- Pre-screen checks reference the correct fields for a long call/put

If any field shows undefined or renders incorrectly for long option data, fix the rendering logic. Report what you find.

---

## Group 4 — Formula Transparency with Real Scoring Data

### Task G-4 — Wire FormulaBreakdown to Real Data

Read `web/src/components/FormulaBreakdown.jsx` and `app/analysis/vertical_engine.py` (or whichever engine produced the trade's score).

The FormulaBreakdown component must render real values — not hardcoded mock data.

**What to show per metric (5 metrics):**

1. **Raw metric value** — the actual number computed (e.g. expected value = 0.42)
2. **Normalization** — show the min-max normalization formula applied: `(raw - min) / (max - min)` with actual min/max used
3. **Normalized score** — the 0–1 result (e.g. 0.74)
4. **Weighted contribution** — normalized × weight (e.g. 0.74 × 0.35 = 0.259)

At the bottom: sum all weighted contributions → show how they total to the composite score.

**Data source:** The backend analysis response already returns scoring data. Check what fields are present in the trade object that comes back from `POST /api/v1/analyze/verticals`. If a `scoreBreakdown` or `metricScores` field is not present, add it to the API response:

In `app/analysis/vertical_engine.py`, when building the result object, add:
```python
score_breakdown={
    "expected_value":   {"raw": ev, "normalized": ev_norm, "weight": 0.35, "contribution": ev_norm * 0.35},
    "reward_risk":      {"raw": rr, "normalized": rr_norm, "weight": 0.25, "contribution": rr_norm * 0.25},
    "probability":      {"raw": prob, "normalized": prob_norm, "weight": 0.20, "contribution": prob_norm * 0.20},
    "liquidity":        {"raw": liq, "normalized": liq_norm, "weight": 0.15, "contribution": liq_norm * 0.15},
    "theta_efficiency": {"raw": theta, "normalized": theta_norm, "weight": 0.05, "contribution": theta_norm * 0.05},
}
```

Pass this through the API response schema (`schemas.py`) and into the frontend trade object. The FormulaBreakdown component reads from `trade.scoreBreakdown`.

---

## Delivery Order

Complete tasks in this order. Do not skip ahead:

1. `2.5.1` — AskClaudePanel stale results fix
2. `2.5.2` — Watchlist token refresh (backend) + quote fetch (frontend)
3. `G-1` — Toast component
4. `G-2/G-3` — QuoteBar audit
5. `V-1` — Column 3 why text
6. `V-2` — Column 4 Strategy Explanation
7. `V-3` — Loading state
8. `V-4` — Verdict auto-collapse
9. `V-5` — Button width:auto audit
10. `V-6` — Stale verdict useEffect
11. `P-1` — Puts & Calls trade_structure filter + add field to strategy configs
12. `P-2` — Grayed non-applicable strategies
13. `P-3` — Verdict card long option check
14. `G-4` — FormulaBreakdown wired to real scoring data

After each task, briefly confirm what was done and whether it required a change or was already complete.

---

## Do Not

- Do not modify `UI-DECISIONS.md` — it is read-only reference in this session
- Do not change the color system, button styles, or typography without explicit approval
- Do not refactor any component that is not explicitly listed above
- Do not start Phase 2.9 work (StrategyScorecard, SecurityDashboard, strategy_scorer.py)
- Do not remove AskClaudePanel imports — that happens in Phase 2.11
- Do not add any `$` prefix to price values anywhere in the UI
