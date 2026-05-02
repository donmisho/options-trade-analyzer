---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Regression v3 — Navigation Guard + UI Fixes

**Tickets:** OTA-433, OTA-435
**Commit prefix:** `OTA-433 OTA-435 fix: Find Trades symbol guard, option value header, SMA badges, config wiring`

Read `claude_context/UI-GUIDANCE.md` Parts 10 and 12 first.

---

## Fix 1 — "Find trades →" Requires Symbol (OTA-433)

### Step 1: Read StrategyPage
```
cat web/src/pages/StrategyPage.jsx
```
Find the "Find trades →" button onClick handler (~line 519-521).

### Step 2: Read AppContext for activeSymbol
```
grep -rn "activeSymbol" web/src/context/AppContext.jsx | head -10
```
Understand how activeSymbol is set and accessed.

### Step 3: Implement the guard
The button currently navigates unconditionally. Change to:

```jsx
const [showSymbolHint, setShowSymbolHint] = useState(false);

const handleFindTrades = () => {
  if (activeSymbol) {
    navigate(`/trades?strategy=${strategyKey}&symbol=${activeSymbol}`);
  } else {
    setShowSymbolHint(true);
  }
};
```

Below the button, add the guidance message:
```jsx
{showSymbolHint && (
  <span style={{ fontSize: '10px', color: 'var(--muted)', marginLeft: '12px' }}>
    Search for a symbol on the Trades page first, then return here.
  </span>
)}
```

### Step 4: Clear the hint when activeSymbol changes
```jsx
useEffect(() => {
  if (activeSymbol) setShowSymbolHint(false);
}, [activeSymbol]);
```

### Step 5: Verify
```
grep -rn "showSymbolHint\|handleFindTrades" web/src/pages/StrategyPage.jsx
```

---

## Fix 2 — "SPREAD VALUE" → "Option Value" for Single Legs (OTA-435, Part 1)

### Step 1: Read SectionB
```
cat web/src/components/TradeDetail/SectionB.jsx
```
Find the hardcoded `<th>Spread Value</th>` at ~line 91.

### Step 2: Determine how to detect single-leg vs spread
Check what props SectionB receives:
```
grep -rn "<SectionB\|SectionB " web/src/pages/TradesPage.jsx web/src/components/TradeDetail/
```

The trade object should have a `spread_type` or `trade_type` field. Single legs are `long_call` or `long_put`. Spreads have two-word types like `bull_call`, `bear_put`, etc.

### Step 3: Conditionally render the header
```jsx
const isSingleLeg = ['long_call', 'long_put'].includes(tradeType?.toLowerCase());
// ...
<th>{isSingleLeg ? 'Option Value' : 'Spread Value'}</th>
```

If `tradeType` isn't currently passed to SectionB, add it as a prop from the parent.

---

## Fix 3 — Remove SMA Chart On-Chart Period Badges (OTA-435, Part 2)

### Step 1: Read SmaPanel
```
cat web/src/components/SmaPanel.jsx
```
Find lines ~57-59 — the three blocks that render period numbers (20, 50, 200) directly on the chart SVG.

### Step 2: Remove the on-chart badges
Look for JSX blocks like:
```jsx
{lastSmaS && <text x={...} y={...}>20</text>}
{lastSmaM && <text x={...} y={...}>50</text>}
{lastSmaL && <text x={...} y={...}>200</text>}
```
Remove these three blocks entirely. The above-chart legend row (~lines 103-106) already shows "— Fast 20 — Medium 50 — Slow 200" with colored indicators and is fully readable.

### Step 3: Verify the above-chart legend is preserved
```
grep -n "Fast\|Medium\|Slow" web/src/components/SmaPanel.jsx
```
Should still show the above-chart legend row. Only the on-chart SVG text elements should be removed.

---

## Fix 4 — Wire Config Drawer onApply (OTA-435, Part 3)

### Step 1: Read SectionConfigDrawer
```
cat web/src/components/SectionConfigDrawer.jsx
```
Find the Apply button handler. It likely saves to localStorage. Check what key(s) it uses.

### Step 2: Read TradesPage Config drawer usage
```
grep -rn "SectionConfigDrawer\|ConfigDrawer\|vertConfigOpen\|callsConfigOpen" web/src/pages/TradesPage.jsx
```
Find where the drawer is rendered. Confirm no `onApply` prop is passed.

### Step 3: Add onApply callback
In TradesPage.jsx, add an `onApply` handler that:
1. Reads the saved config params from localStorage (same keys the drawer writes to)
2. Calls `fetchVerticals(symbol, configParams)` or `fetchCalls(symbol, configParams)` with the new params
3. Closes the drawer

```jsx
const handleVertConfigApply = () => {
  const savedConfig = JSON.parse(localStorage.getItem('ota_vert_config') || '{}');
  fetchVerticals(symbol, savedConfig);
  setVertConfigOpen(false);
};

// In the JSX:
<SectionConfigDrawer
  open={vertConfigOpen}
  onClose={() => setVertConfigOpen(false)}
  onApply={handleVertConfigApply}
  strategyKeys={VERT_STRATEGY_KEYS}
/>
```

### Step 4: Update fetchVerticals/fetchCalls to accept config params
```
grep -rn "fetchVerticals\|fetchCalls\|const fetch" web/src/pages/TradesPage.jsx | head -20
```
Read the function signatures. If they currently hardcode params, add an optional `config` parameter that overrides defaults:

```javascript
const fetchVerticals = async (sym, config = {}) => {
  const params = {
    min_dte: config.min_dte || 7,
    max_dte: config.max_dte || 45,
    // ... other defaults
    ...config,  // override with user config
  };
  // ... rest of fetch
};
```

### Step 5: Do the same for the Puts & Calls config drawer
Wire `onApply` for the calls section drawer in the same pattern.

---

## Verification

```bash
cd web && npm run build 2>&1 | tail -20
```

Zero errors. Then:
```bash
# Verify no hardcoded "Spread Value" for single legs
grep -n "Spread Value" web/src/components/TradeDetail/SectionB.jsx
# Should show conditional logic, not a hardcoded string

# Verify on-chart badges removed
grep -n "lastSmaS.*text\|lastSmaM.*text\|lastSmaL.*text" web/src/components/SmaPanel.jsx
# Should return zero hits
```

### Manual verification for Don:
- [ ] "Find trades →" with no symbol shows guidance message, does NOT navigate
- [ ] "Find trades →" with activeSymbol navigates and loads results
- [ ] Long Call exit table header says "OPTION VALUE" (not "SPREAD VALUE")
- [ ] Vertical spread exit table header says "SPREAD VALUE"
- [ ] SMA chart has no overlapping period badges on Y-axis
- [ ] Above-chart legend (Fast 20 / Medium 50 / Slow 200) still visible
- [ ] Changing Config drawer params and clicking Apply re-runs the analysis
