---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Regression v2 Fixes — CSS Custom Properties, Column Order & Exit Row Labels

**Tickets:** OTA-427, OTA-428, OTA-429
**Commit prefix:** `OTA-427 OTA-428 OTA-429 fix: strategy pill CSS vars, column order, exit scenario labels`

Read `claude_context/UI-GUIDANCE.md` Parts 8 and 10 first. Then execute the three fixes below in order.

---

## Fix 1 — Strategy Pill CSS Custom Properties (OTA-427)

### Step 1: Read current files
```
cat web/src/index.css | head -80
cat web/src/strategyColors.js
cat web/src/components/StrategyPill.jsx
grep -rn "var(--amber)\|var(--green)\|var(--blue)\|var(--purple)" web/src/
```

### Step 2: Add CSS custom properties to index.css
Find the `:root` block in `web/src/index.css` and add these properties (group them with a comment):

```css
/* Strategy pill colors — canonical source for all strategy color references */
--strategy-sp: #f59e0b;   /* amber — Steady Paycheck */
--strategy-wg: #4ade80;   /* green — Weekly Grind */
--strategy-tr: #60a5fa;   /* blue  — Trend Rider */
--strategy-lt: #c084fc;   /* purple — Lottery Ticket */
```

### Step 3: Update strategyColors.js
Replace every `var(--amber)` → `var(--strategy-sp)`, `var(--green)` → `var(--strategy-wg)`, `var(--blue)` → `var(--strategy-tr)`, `var(--purple)` → `var(--strategy-lt)` in both `text` and `bg` (background) color references.

### Step 4: Verify no stale references remain
```
grep -rn "var(--amber)\|var(--green)\|var(--blue)\|var(--purple)" web/src/components/StrategyPill.jsx web/src/strategyColors.js web/src/components/ScanCard.jsx
```
Should return zero hits. If ScanCard.jsx has hardcoded strategy colors, update those too.

### Step 5: Verify StrategyPill.jsx uses strategyColors.js
```
cat web/src/components/StrategyPill.jsx
```
Confirm it imports from strategyColors.js (or equivalent) and doesn't have its own hardcoded color map.

---

## Fix 2 — Move Strategies Column Adjacent to Score (OTA-428)

### Step 1: Read current column order
```
cat web/src/config/verticals-columns.js
cat web/src/config/long-options-columns.js
```

### Step 2: Identify the Strategies column entry
Find the column object with key/header "Strategies" or "Strategy" — note its current array index position.

### Step 3: Move it
In both files, move the Strategies column entry to index 1 (immediately after the Score column at index 0). The new order should be:

```
Score → Strategies → [remaining columns in their current order]
```

Do NOT change any column's internal definition — only its position in the array.

### Step 4: Verify
```
grep -n "key\|header" web/src/config/verticals-columns.js | head -15
grep -n "key\|header" web/src/config/long-options-columns.js | head -15
```
Confirm Strategies is at position 1 in both files.

---

## Fix 3 — Update Exit Scenario Key Row Labels (OTA-429)

### Step 1: Find the exit scenario logic
```
grep -rn "buildExitScenarios\|exit_signal\|key_row\|keyRow\|MAX.PROFIT\|BREAKEVEN\|STOP\|TIME.EXIT" web/src/pages/TradesPage.jsx web/src/components/ExitScenarioTable.jsx
```

### Step 2: Read the full component
```
cat web/src/components/ExitScenarioTable.jsx
```
Or wherever the exit scenario rendering lives. Understand how the 5 key rows are currently identified and filtered.

### Step 3: Update the 5 key row labels
The current labels (from OTA-420) are likely: MAX PROFIT, BREAKEVEN, STOP, TIME EXIT, current price.

Replace with these exact 5 labels:
1. **STOP** — the stop-loss trigger price level
2. **MONITOR LOSS** — loss monitoring threshold (a price between stop and breakeven)
3. **BREAK EVEN** — P&L = 0 crossing point
4. **MONITOR PROFIT** — profit monitoring threshold (a price between breakeven and max profit)
5. **MAX PROFIT** — maximum profit scenario

### Step 4: Update the row identification logic
Each label needs a price-level identification rule:
- **STOP**: Use the trade's stop price / trigger level from Section A data
- **MONITOR LOSS**: Midpoint between STOP and BREAK EVEN, rounded to nearest $5
- **BREAK EVEN**: The breakeven price from trade data
- **MONITOR PROFIT**: Midpoint between BREAK EVEN and MAX PROFIT, rounded to nearest $5
- **MAX PROFIT**: The max profit price level (short strike for credits, long strike for debits)

If the current logic uses `exit_signal` tags on the scenario rows, update the tag names to match.

### Step 5: Verify the expanded view
When "Show full analysis ▼" is toggled, the 5 key rows should appear in-place among the full $5-increment rows — they are NOT duplicated, they ARE the rows at those price levels, just visually highlighted (e.g., bold text, or a left-border accent).

### Step 6: Verify color coding
- STOP and MONITOR LOSS rows: loss zone tinting `rgba(248,113,113,0.03)`
- BREAK EVEN row: neutral (no tinting)
- MONITOR PROFIT and MAX PROFIT rows: profit zone tinting (green equivalent)

---

## Verification

```bash
cd web && npm run build 2>&1 | tail -20
```

Confirm zero errors, zero warnings about missing variables. If warnings exist, fix them.

### Visual spot-check list (for Don to verify manually):
- [ ] StrategyPill colors: SP=amber, WG=green, TR=blue, LT=purple
- [ ] Strategies column immediately after Score in both Verticals and Puts & Calls sections
- [ ] Exit scenario table shows 5 key rows by default with correct labels
- [ ] Expanded exit table shows all rows with key rows anchored in sequence
