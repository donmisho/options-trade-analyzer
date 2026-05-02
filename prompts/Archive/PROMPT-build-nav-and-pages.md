# Claude Code Prompt — Navigation + Security Strategies + Expansion Panels

## Before You Start

Read these files in this order before writing a single line of code:
1. `CLAUDE.md`
2. `UI-DECISIONS.md`
3. `architecture-plan.md`
4. The current content of every file you are about to modify

The mockup screenshots in `/project-mockups/` are the visual reference.
Match them exactly. Do not improvise layout or color decisions.

---

## Overview

This prompt delivers four changes as one coordinated build:

1. **Nav bar** — add "Security Strategies" tab, remove standalone strategy tabs
2. **Security Strategies page** — new page, primary entry point from watchlist
3. **Verticals expansion** — add strategy scorecard to trade row expansion
4. **Puts & Calls expansion** — same as Verticals but with strategy filtering

These changes share components and must be built in the order listed.
Do not skip ahead. Each step depends on the previous one being correct.

---

## Step 1 — QuoteBar Component Audit

**File**: `web/src/components/QuoteBar.jsx`

First, read the current file. Then verify it renders ALL of these fields
in this exact order with no extras or omissions:

Symbol → SIGNAL badge → Last Analyzed → Price → CHG → CHG% →
Day Range → 52W Range → Volume → Rel Vol → Earnings Date → Dividend Date

Earnings and Dividend rules:
- Only render if the date exists AND is within 60 days from today
- If null or >60 days: do not render the field — no dash, no placeholder
- Earnings within 14 days: wrap in amber badge
  `background: rgba(245,158,11,0.2); color: #f59e0b; padding: 2px 7px; border-radius: 4px`
- No `$` prefix on any value anywhere in this component

Props the component must accept:
```javascript
{
  symbol: string,
  quote: {
    price: number,
    change: number,
    changePct: number,
    dayLow: number,
    dayHigh: number,
    volume: number,
    relVolume: number
  },
  smaSignal: 'BULLISH' | 'BEARISH' | 'MIXED',
  lastAnalyzed: string | null,   // ISO timestamp
  fundamentals: {
    earningsDate: string | null, // ISO date
    dividendDate: string | null  // ISO date
  }
}
```

If QuoteBar is missing any of these fields or renders anything differently,
fix it now before proceeding. Every page depends on this being correct.

---

## Step 2 — Navigation Bar

**File**: `web/src/components/Header.jsx`

### Remove these tabs entirely
- Steady Paycheck
- Weekly Grind
- Trend Rider
- Lottery Ticket
- Directional Compare (if present)

### Final tab order (exact)
```
Dashboard | Security Strategies | Verticals | Puts & Calls | Positions
```

Plus on the right: Settings gear icon · Schwab Connected indicator · Sign out

### Add "Security Strategies" tab behavior
- Route: `/security-strategies`
- When clicked: navigate to `/security-strategies` using the current activeSymbol
- If no activeSymbol is set, navigate to `/security-strategies` and the page
  will handle the empty state

### Watchlist sidebar behavior
**File**: `web/src/components/Watchlist.jsx` (or wherever watchlist items render)

Clicking a symbol in the watchlist must:
1. Set that symbol as activeSymbol in AppContext
2. Navigate to `/security-strategies/:symbol`

This is the primary entry point to Security Strategies.

### App.jsx routing
Add route: `/security-strategies/:symbol?` → renders `<SecurityStrategiesPage />`
Remove routes for any standalone strategy pages that no longer exist.

---

## Step 3 — Security Strategies Page

**File**: `web/src/pages/SecurityStrategiesPage.jsx` (new file)

### Layout (top to bottom, no exceptions)

```
<QuoteBar />                    ← shared component, identical to all pages
<CandlestickChart />            ← same chart component used in OptionsTerminal
<StrategyScorecard />           ← new section, described below
<TradeEvaluationCards />        ← rendered after evaluate, described below
```

### On load behavior
1. Read `:symbol` from route params (or activeSymbol from context if no param)
2. Fetch quote data → pass to QuoteBar
3. Fetch SMA/directional data → pass smaSignal to QuoteBar
4. Fetch fundamentals → pass earningsDate/dividendDate to QuoteBar
5. Call `POST /api/v1/analysis/scorecard` with the symbol → populate scorecard
6. Show loading skeletons while fetching

### Strategy Scorecard section

Header row: "STRATEGY SCORECARD — {SYMBOL}" label left, "Select strategies to evaluate" muted right

For each strategy, one row containing:
- Checkbox (accent-color: #2dd4bf)
- Strategy name (12px bold) + subtitle below (10px muted, e.g. "30-45 DTE credit spread")
- Score bar: flex:1, 8px height, border-radius 4px, colored by score:
  - 70-100: #4ade80 (green)
  - 40-69: #f59e0b (amber)
  - 0-39: #f87171 (red)
- Score number (13px bold, same color as bar)
- Signal summary (right-aligned, muted, from scorecard API response)

Below all rows:
- "Evaluate Selected" button: teal background, disabled until ≥1 checkbox checked
- Selected count: "N strategies selected" (updates as checkboxes change)

Pre-check the highest-scoring strategy by default.

### After Evaluate button clicked

1. Call `POST /api/v1/evaluate/structured` with:
   - symbol
   - current_price, iv, sma_alignment (from already-fetched data)
   - strategy_keys: array of checked strategy keys
   - trade: null (Claude finds the best trade per strategy)

2. Show skeleton loading cards while waiting

3. Render one `<TradeEvaluationCard />` per returned evaluation
   Cards ordered by score descending (highest score first)

### TradeEvaluationCard component
**File**: `web/src/components/TradeEvaluationCard.jsx`

Each card renders:
- Header: strategy name (13px bold) | trade structure found | score | verdict badge
- Verdict badge colors: EXECUTE=green, WAIT=amber, PASS=red
- 6-cell grid (2 rows × 3 cols):
  Row 1: Entry price | Max profit | Max loss
  Row 2: Exit warning price | Take profit level | Stop loss level
- Probability matrix table (see below)
- Claude's read (11px italic muted, 2-3 sentences)
- Action row: [📌 Follow (Paper)] [💰 Take Position]

### Probability Matrix Table

Columns: Price | Exp-9 | Exp-6 | Exp-3 | Expiration
Rows: price levels from +10% to -10% in $10 steps
Current price row: teal tint background, starred label

Cell color by probability:
- >20%: rgba(74,222,128,0.2) green tint
- 10-20%: rgba(245,158,11,0.1) amber tint
- <10%: rgba(248,113,113,0.1) red tint
- Current price row: rgba(45,212,191,0.08) teal tint

### Follow / Take Position actions

Follow button:
- border: 1px solid #2dd4bf, color: #2dd4bf, transparent background
- POST to `/api/v1/positions/follow` with full position data including claude_* fields
- On success: toast "Added to Positions as paper trade" with link to /positions

Take Position button:
- background: #2dd4bf, color: #0d1117
- POST to `/api/v1/positions/take`
- On success: toast "Live position added to Positions" with link to /positions

---

## Step 4 — Verticals Page Expansion

**File**: `web/src/pages/OptionsTerminal.jsx`

Do not change anything about the ranked trade list, QuoteBar, chart, or analyze bar.
Change ONLY the Stage 2 row expansion content.

### Expansion panel layout

Replace the current expansion content with a 2-column CSS grid:

```
Left column (1fr):          Right column (1fr):
Scoring Breakdown           Strategy Fit — this trade
[existing math matrix]      [new StrategyScorecard inline]
```

### Left column — Scoring Breakdown
Keep the existing math matrix exactly as it is. Do not change it.

### Right column — Strategy Scorecard (inline, compact)

Header: "STRATEGY FIT — THIS TRADE" (10px uppercase muted)

For vertical spread trades, show ALL four strategies.
The filter: strategies where `trade_structure === 'credit_spread'` OR
`trade_structure === 'long_option'` — in practice all four qualify for verticals.

Each strategy row (compact version, same layout as Security Strategies scorecard):
- Checkbox
- Strategy name (no subtitle needed in compact mode)
- Score bar
- Score number

Below rows:
- "Evaluate with Claude" button (teal)
- Selected count label

### After Evaluate — inline card

Render `<TradeEvaluationCard />` below the 2-column grid, still inside the
expansion panel. Claude evaluates the pre-selected trade through each chosen
strategy lens. Pass the trade data in the evaluate request body.

---

## Step 5 — Puts & Calls Page Expansion

**File**: `web/src/pages/OptionsTerminal.jsx`
(Same file, different strategy config context — `activeStrategy === 'long-calls'`)

Identical to Step 4 EXCEPT for strategy filtering.

### Strategy filtering — CRITICAL

Filter strategies using the `trade_structure` field from strategy config:

```javascript
// In strategy-configs/*.config.js, each config has trade_structure field
// For Puts & Calls expansion:
const applicableStrategies = allStrategies.filter(
  s => s.trade_structure === 'long_option'
)
const notApplicableStrategies = allStrategies.filter(
  s => s.trade_structure !== 'long_option'
)
```

NEVER hardcode strategy names. The filter must use `trade_structure`.

### Rendering applicable strategies
Same as Verticals — checkbox, name, score bar, score number.
Only Trend Rider and Lottery Ticket will show (both have trade_structure: 'long_option').

### Rendering non-applicable strategies

Show them below a dashed divider — grayed out, no checkbox, no score bar:

```
--- not applicable to this trade type ---
Steady Paycheck     requires credit spread structure
Weekly Grind        requires credit spread structure
```

Styling:
- Divider: `border-bottom: 1px dashed rgba(48,54,61,0.3)` with centered label
  `font-size: 9px; color: rgba(139,148,158,0.4); text-transform: uppercase`
- Non-applicable strategy name: 11px, color: var(--muted), font-style: italic
- Reason text: 10px, color: rgba(139,148,158,0.5), font-style: italic

---

## Validation Checklist

Run through every item before considering this complete.

### Navigation
- [ ] Nav shows exactly: Dashboard | Security Strategies | Verticals | Puts & Calls | Positions
- [ ] No strategy tabs in nav (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket gone)
- [ ] Clicking "Security Strategies" tab navigates to /security-strategies
- [ ] Clicking a watchlist symbol navigates to /security-strategies/:symbol
- [ ] No dead routes in App.jsx

### QuoteBar
- [ ] All 12 fields present in correct order on SecurityStrategiesPage
- [ ] All 12 fields present in correct order on Verticals page
- [ ] All 12 fields present in correct order on Puts & Calls page
- [ ] No `$` prefix anywhere in QuoteBar
- [ ] Earnings date hidden when null or >60 days away
- [ ] Earnings within 14 days shows amber highlight
- [ ] Dividend date hidden when null

### Security Strategies Page
- [ ] Loads for symbol from route param
- [ ] Loads for activeSymbol when no route param
- [ ] All 4 strategy rows show with scores
- [ ] Score bar colors correct (green/amber/red by threshold)
- [ ] Evaluate button disabled until checkbox checked
- [ ] Evaluate button calls /api/v1/evaluate/structured with trade: null
- [ ] TradeEvaluationCards render after evaluate
- [ ] Cards ordered by score descending
- [ ] Follow button POSTs to /api/v1/positions/follow
- [ ] Take Position button POSTs to /api/v1/positions/take
- [ ] Both buttons show success toast with link to Positions

### Verticals Expansion
- [ ] 2-column grid: math matrix left, strategy scorecard right
- [ ] All 4 strategies shown in scorecard
- [ ] Evaluate button calls /api/v1/evaluate/structured with trade pre-populated
- [ ] TradeEvaluationCard renders inline after evaluate

### Puts & Calls Expansion
- [ ] 2-column grid same as Verticals
- [ ] Only Trend Rider and Lottery Ticket shown as applicable (scored)
- [ ] Steady Paycheck and Weekly Grind shown grayed out below divider
- [ ] Divider label: "not applicable to this trade type"
- [ ] Filter uses trade_structure field — no hardcoded strategy names
- [ ] Evaluate button works with long_option strategies only

---

## What NOT To Change

- The ranked trade list on Verticals and Puts & Calls pages
- The analyze bar and symbol input
- The chart component
- The ConfigDrawer
- The Positions page
- The Dashboard page
- Any backend code
- Any strategy config files (they stay, just not in nav)
