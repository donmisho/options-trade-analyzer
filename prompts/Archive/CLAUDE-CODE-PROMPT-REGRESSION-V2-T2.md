---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Regression v3 — Data Integrity Fixes

**Tickets:** OTA-432, OTA-434
**Commit prefix:** `OTA-432 OTA-434 fix: debit spread context label, credit spread P&L formula`

Read `claude_context/UI-GUIDANCE.md` Part 10 (Screen 2, Trade Detail Expansion) first.

---

## Fix 1 — Section A Context Label (OTA-432) — P0

### Step 1: Read the current code
```
cat web/src/components/TradeDetail/SectionA.jsx
```
Find `getContextLabel` or equivalent function that produces the "(bearish — you receive credit)" text.

### Step 2: Understand the bug
The function checks `upper.includes('DEBIT')` to detect debit spreads, but spread_type values from the backend are:
- `bull_call` (BULL_CALL_DEBIT — debit)
- `bear_put` (BEAR_PUT_DEBIT — debit)
- `bull_put` (BULL_PUT_CREDIT — credit)
- `bear_call` (BEAR_CALL_CREDIT — credit)
- `long_call` (single leg — debit/premium)
- `long_put` (single leg — debit/premium)

The word "DEBIT" never appears in the value, so `isDebit` is always false, and all trades show "you receive credit."

### Step 3: Fix using the spread direction matrix
Replace the string-matching logic with a deterministic map:

```javascript
const SPREAD_INFO = {
  bull_call:  { direction: 'bullish', entry: 'you pay debit' },
  bear_put:   { direction: 'bearish', entry: 'you pay debit' },
  bull_put:   { direction: 'bullish', entry: 'you receive credit' },
  bear_call:  { direction: 'bearish', entry: 'you receive credit' },
  long_call:  { direction: 'bullish', entry: 'you pay premium' },
  long_put:   { direction: 'bearish', entry: 'you pay premium' },
};

function getContextLabel(spreadType) {
  const key = (spreadType || '').toLowerCase().replace(/-/g, '_');
  const info = SPREAD_INFO[key];
  if (!info) return '';
  return `(${info.direction} — ${info.entry})`;
}
```

### Step 4: Find where getContextLabel is called and update
The function likely receives the spread_type or trade_type prop. Make sure the prop value matches the keys above (lowercase with underscores). If the prop uses hyphens, normalize with `.replace(/-/g, '_')`.

### Step 5: Verify
```
grep -rn "getContextLabel\|you receive\|you pay\|context.*label" web/src/components/TradeDetail/
```
Confirm no residual string-matching logic remains.

---

## Fix 2 — Credit Spread P&L Formula (OTA-434) — Latent P0

### Step 1: Read the exit scenario builder
```
grep -rn "buildExitScenarios\|spreadValue\|isBull\|isCredit" web/src/pages/TradesPage.jsx web/src/components/TradeDetail/
```
Then `cat` the relevant file to see the full `buildExitScenarios` function.

### Step 2: Understand the bug
The current code uses an `isBull` flag to choose the spread value formula:
- If bull: `spreadValue = max(0, min(price - loStrike, width))` (value increases with price)
- If bear: `spreadValue = max(0, min(hiStrike - price, width))` (value decreases with price)

This is correct for DEBIT spreads where bull=call and bear=put. But for CREDIT spreads:
- BULL_PUT_CREDIT is bullish but uses put legs → spread value should DECREASE with price (bear formula)
- BEAR_CALL_CREDIT is bearish but uses call legs → spread value should INCREASE with price (bull formula)

### Step 3: Fix — base formula on option type, not direction
The spread value formula depends on whether the legs are CALLS or PUTS, not whether the trade is bullish or bearish:

```javascript
// Spread value depends on option type (put vs call), not bull vs bear
const isCallSpread = ['bull_call', 'bear_call'].includes(spreadType);
const isPutSpread = ['bear_put', 'bull_put'].includes(spreadType);

// For each price level:
let spreadValue;
if (isCallSpread) {
  spreadValue = Math.max(0, Math.min(price - loStrike, width));
} else if (isPutSpread) {
  spreadValue = Math.max(0, Math.min(hiStrike - price, width));
}

// P&L depends on credit vs debit
const isCredit = ['bull_put', 'bear_call'].includes(spreadType);
let pnl;
if (isCredit) {
  pnl = (entry - spreadValue) * 100;  // credit: profit when spread value shrinks
} else {
  pnl = (spreadValue - entry) * 100;  // debit: profit when spread value grows
}
```

### Step 4: Verify existing debit spreads unchanged
After the fix, trace through manually:
- **BEAR_PUT_DEBIT 330/320, entry=4.85:**
  - isPutSpread=true → spreadValue = max(0, min(330 - price, 10))
  - At price=265: sv = max(0, min(65, 10)) = 10.00 → pnl = (10 - 4.85) × 100 = +515 ✓
  - At price=340: sv = max(0, min(-10, 10)) = 0 → pnl = (0 - 4.85) × 100 = -485 ✓

- **BULL_CALL_DEBIT 320/330, entry=5.15:**
  - isCallSpread=true → spreadValue = max(0, min(price - 320, 10))
  - At price=340: sv = max(0, min(20, 10)) = 10.00 → pnl = (10 - 5.15) × 100 = +485 ✓
  - At price=310: sv = 0 → pnl = (0 - 5.15) × 100 = -515 ✓

### Step 5: Verify credit spreads will work correctly
- **BULL_PUT_CREDIT 320/310, entry=2.50 (credit received):**
  - isPutSpread=true → spreadValue = max(0, min(320 - price, 10))
  - At price=330 (above both strikes, OTM): sv = max(0, min(-10, 10)) = 0 → pnl = (2.50 - 0) × 100 = +250 ✓ (keep full credit)
  - At price=305 (below both strikes, ITM): sv = max(0, min(15, 10)) = 10 → pnl = (2.50 - 10) × 100 = -750 ✓ (max loss)

### Step 6: Also check the key row labeling for credit spreads
For credit spreads, the exit signal ordering should flip:
- MAX PROFIT at the price where spread value = 0 (favorable end)
- STOP at the price where spread value = width (unfavorable end)

Read the key row assignment logic and verify it handles credit spreads correctly. If it uses P&L direction (positive = profit), it should work automatically after the formula fix.

---

## Verification

```bash
cd web && npm run build 2>&1 | tail -20
```

Zero errors. Then verify no residual bugs:
```bash
grep -rn "includes.*DEBIT\|includes.*CREDIT" web/src/components/TradeDetail/
```
Should return zero hits (replaced by deterministic map).

### Manual verification for Don:
- [ ] Bear Put expansion shows "(bearish — you pay debit)"
- [ ] Bull Call expansion shows "(bullish — you pay debit)"
- [ ] Long Call expansion shows "(bullish — you pay premium)"
- [ ] Long Put expansion shows "(bearish — you pay premium)"
- [ ] Bear Put P&L numbers unchanged from before this fix
- [ ] Bull Call P&L numbers unchanged from before this fix
