# Claude Code Prompt — OTA-291 OTA-293 OTA-294 OTA-295 OTA-298
## Phase 2.11 Frontend Stream B: Trade Evaluation Components

### Tickets
- OTA-291: TradeIdentityHeader component
- OTA-293: ExitScenarioTable component with zone color coding
- OTA-294: OutcomeSummaryCard component with EV status indicator
- OTA-295: ProbabilityMatrix enhancements (zone colors, cumulative column, time exit column)
- OTA-298: ClaudesRead component with verdict badge

### Prerequisite
These components use **mock data** — the backend from OTA-292/297 does not need to be complete before running this prompt. Each component receives its data as props from the parent TradeEvaluationView (built in the next session, OTA-299).

---

### Before You Start

```bash
cat web/src/components/AskClaudePanel.jsx | head -60
grep -rn "formatDate\|formatScore\|formatPct" web/src/utils/ | head -20
grep -rn "tokens\|--color\|--bg" web/src/index.css | head -30
cat web/src/config/verticals-columns.js | head -30
```

Read these before writing any component. Use the existing formatDate utility for all dates. Use existing CSS variables — never hardcode colors.

---

### Design System Reminders (non-negotiable)
- Background: `#0D1117` (Void Charcoal)
- Bullish/execute: `#00C896` (Emerald Teal)
- Warning/wait: `#F5A623` (Apricot Amber)
- Danger/max-loss: `#F85149`
- AI/actions: `#8B5CF6` (Amethyst Violet)
- **No `$` prefix anywhere**
- **No full-width buttons** — always sized to content with fixed padding
- Scores/values: `##.00` format
- Probabilities: `##.00%` format
- Dates: `mm-dd-yyyy` via `formatDate()`

---

## Component 1 — OTA-291: TradeIdentityHeader

**File:** `web/src/components/TradeIdentityHeader.jsx`

**Props:**
```js
{
  spread_type,        // e.g. "BEAR_PUT_DEBIT"
  long_strike,
  short_strike,
  expiry,             // ISO date → formatDate() for display
  entry_price,        // per share
  entry_price_contract, // entry_price * 100
  max_profit,
  max_loss,
  breakeven,
  dte,
  reward_risk,        // e.g. 1.84
  profit_trigger,     // price label shown in teal
  stop_trigger,       // price label shown in amber
  time_exit_date      // ISO date → formatDate()
}
```

**Layout:** Compact two-row header bar at top of the evaluation panel.

- Row 1: Spread type label (enum name + plain-English direction), strikes, expiry, DTE
- Row 2: Entry / Max Profit / Max Loss / Breakeven / R:R / Profit Trigger / Stop Trigger / Time Exit

**Display rules:**
- Spread type shows both: `BEAR_PUT_DEBIT (bearish — you pay to enter)`
- Entry shows: `8.80 debit per share (880 per contract)`
- Max Profit: `1620 if MSFT at or below 345 at expiry`
- Max Loss: `880 if MSFT at or above 370 at expiry`
- R:R: `1.84:1`
- Profit trigger label: Emerald Teal `#00C896`
- Stop trigger label: Apricot Amber `#F5A623`
- Component is **stateless** — pure display

---

## Component 2 — OTA-293: ExitScenarioTable

**File:** `web/src/components/ExitScenarioTable.jsx`

**Props:** `{ rows: ExitScenarioRow[], totalEV: number }`

**Columns:** Underlying Price | Spread Value | P&L per Contract | P&L % | Probability | Expected Value | Exit Signal

**Row color coding via CSS class (set by `row.zone` field):**
- `profit-zone` → Emerald Teal `#00C896` tinted row background
- `entry` → neutral
- `warning-zone` → Apricot Amber `#F5A623` tinted row background
- `max-loss` → Danger `#F85149` tinted row background

**Key rows** (MAX PROFIT, BREAKEVEN, ENTRY, STOP, TIME EXIT) — show label in Exit Signal column in bold.

**Table footer:** "Total Expected Value" row = sum of all EV column values.

**Formatting:**
- P&L per contract: `##.00` with sign (e.g. `+1620.00` / `-880.00`)
- Probability: `##.00%`
- EV: with sign
- No `$` in any cell

**Acceptance criteria:**
- `BEAR_PUT_DEBIT` 370/345 at entry row: `pl_per_contract = 0.00`; at 345 row: `pl_per_contract = +1620.00`
- `BEAR_CALL_CREDIT` 395/420 at entry row: `pl_per_contract = +540.00`; at 420 row: `pl_per_contract = -1960.00`

---

## Component 3 — OTA-294: OutcomeSummaryCard

**File:** `web/src/components/OutcomeSummaryCard.jsx`

**Props:**
```js
{
  p_max_profit,             // ##.00%
  p_breakeven_or_better,    // ##.00%
  p_max_loss,               // ##.00%
  expected_value,           // with sign, ##.00
  ev_pct_of_risk            // ##.00%
}
```

**Computed client-side:**
- `p_partial_profit = p_breakeven_or_better - p_max_profit`

**Layout:** Compact card showing all six metrics.

**EV status indicator:**
- Negative EV → badge labeled `Negative Expected Value` in Apricot Amber `#F5A623`
- Positive EV → indicator in Emerald Teal `#00C896`

**Rules:**
- No `$` anywhere
- Card background `#0D1117`
- Stateless — all values come as props

---

## Component 4 — OTA-295: ProbabilityMatrix Enhancements

**File:** `web/src/components/ProbabilityMatrix.jsx` (existing — enhance, do not recreate)

```bash
cat web/src/components/ProbabilityMatrix.jsx
```

Read the existing component fully before making changes.

**Three enhancements to add:**

### 4a — Zone color coding
Apply CSS class to each row based on `underlying_price` relative to breakeven, short strike, and long strike:
- `profit-zone`: price in profit territory → Emerald Teal `#00C896` tinted
- `partial-profit`: between breakeven and full profit → light teal tinted
- `loss-zone`: price in loss territory → Apricot Amber `#F5A623` tinted
- `max-loss`: at or beyond max loss strike → Danger `#F85149` tinted

### 4b — Cumulative probability column
Add a column showing the probability of underlying reaching that price **or further** in the profit direction. The cumulative value at the long strike must equal `p_max_profit` from `OutcomeSummaryCard` within 1% tolerance.

### 4c — Time exit column
Add a column for `expiry minus 7 calendar days`. Column header shows that date in `mm-dd-yyyy` format via `formatDate()`.

**Rows to visually highlight** with a left border or bold font:
- Breakeven row
- Profit target row
- Stop-loss row (from exit scenario table)

**No changes to the existing Black-Scholes probability calculation.**

---

## Component 5 — OTA-298: ClaudesRead

**File:** `web/src/components/ClaudesRead.jsx`

**Props:**
```js
{
  onEvaluate: Function,     // called when Evaluate button is clicked
  loading: boolean,
  error: string | null,
  result: {                 // null until evaluated
    ev_commentary,
    key_level: { price, description },
    iv_context,
    verdict,                // "EXECUTE" | "WATCH" | "PASS"
    verdict_rationale
  } | null
}
```

**Layout:**
1. **Evaluate button** (Amethyst Violet `#8B5CF6`, content-sized, never full-width) — triggers `onEvaluate()`; disabled while `loading === true`
2. **Loading state:** skeleton placeholder while awaiting response
3. **Error state:** if `error` is set, show error message in Danger red
4. **Result state** (when `result` is not null):
   - Verdict badge prominent at top — `EXECUTE` = Emerald Teal background, `WATCH` = Apricot Amber, `PASS` = muted gray
   - Badge sized to text content with fixed horizontal padding — **never full-width**
   - `ev_commentary` text below badge
   - `key_level` as a highlighted price callout with description
   - `iv_context` as a secondary paragraph
   - `verdict_rationale` as a muted supporting line

**Rules:**
- No `$` anywhere
- Background `#0D1117`
- Stateless — all state managed by parent

---

### Mock Data for Development

Since the backend isn't wired yet, each component should render using this mock at the top of each file (wrapped in a `if (process.env.NODE_ENV === 'development')` guard or simply as a default prop comment):

```js
// MOCK — remove when wired via TradeEvaluationView
const mockResult = {
  ev_commentary: "Positive expected value of 312 suggests this trade has statistical edge, though it's modest relative to max risk.",
  key_level: { price: 361.20, description: "Breakeven — must stay below for any profit" },
  iv_context: "IV at 28% is elevated — premiums are rich, slightly favouring this bear put debit.",
  verdict: "EXECUTE",
  verdict_rationale: "P(Breakeven or Better) at 58.40% exceeds breakeven threshold. EV is positive at 312."
}
```

---

### After Building

Visually verify each component renders in isolation by temporarily importing it into an existing page (e.g. the Verticals page) with mock props. Then remove the import before committing.

```bash
npm run lint
```

Fix any lint errors before committing.

---

### Commit Message
```
OTA-291 OTA-293 OTA-294 OTA-295 OTA-298 feat: trade evaluation frontend components
```
