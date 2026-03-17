# UI-DECISIONS.md
## Options Analyzer — Canonical UI Decisions

This document records finalized UI decisions that Claude Code must follow exactly.
It is the visual contract for the application. When in doubt, this document wins.
Never deviate from these decisions without explicit approval.

Reference mockups are stored in `/project-mockups/` in the project root.

---

## Navigation Rail

### Layout
The app uses a fixed left navigation rail (220px wide). The top horizontal nav bar has been retired.

### Rail Structure (top to bottom)
- App logo / name — clicking navigates to Dashboard
- Nav items (vertically stacked): Dashboard · Security Strategies · Verticals · Puts & Calls · Positions
- Bottom: Schwab Connected indicator · Settings gear · User / Sign out

### Nav Item Order
Dashboard | Security Strategies | Verticals | Puts & Calls | Positions

### Active State
- 3px solid teal left border (#2dd4bf)
- Teal text (#2dd4bf)
- Background: rgba(45,212,191,0.08)

### Inactive State
- No border (3px solid transparent)
- Muted gray text (#8b949e)
- No background

### Rules
- Exactly these five items. No more, no less.
- Strategy tabs (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket) do NOT appear in the rail. They are scoring lenses inside pages only.
- "Security Strategies" was named deliberately. Do not shorten to "Security".
- Active item: 3px solid teal left border (#2dd4bf) + teal text + rgba(45,212,191,0.08) background.
- Inactive items: muted gray (#8b949e), no border, no background.

### Watchlist Panel
The Watchlist is a collapsible overlay panel triggered by a toggle button in the main content area.
Default state: open. State persists in localStorage.
Toggle button is visible only on analysis pages: Verticals, Puts & Calls, Security Strategies.
Toggle button is `position: fixed`, right edge shifts with the panel (right: 220px when open, 0 when closed).

### Watchlist Symbol Click — Per-Page Behavior
- On Verticals (`/verticals`): sets activeSymbol + runs vertical spread analysis immediately. Does not navigate.
- On Puts & Calls (`/naked-options`): sets activeSymbol + runs analysis immediately. Does not navigate.
- On Positions (`/positions`): sets activeSymbol only. No navigation, no analysis.
- On all other pages (Dashboard, Security Strategies): navigates to `/security-strategies/:symbol`.

---

## QuoteBar — Universal Symbol Header

### This Is A Single Shared Component
File: `web/src/components/QuoteBar.jsx`

EVERY page that shows a symbol uses this exact component. Zero inline reimplementations.
If a page needs a header, it imports `<QuoteBar />`. There is no other option.

### Field Order (left to right, always)
| Field | Format | Notes |
|-------|--------|-------|
| Symbol | 16px bold | e.g. NVDA |
| SIGNAL badge | BULLISH / BEARISH / MIXED | green / red / amber pill |
| Last Analyzed | MM/DD HH:MM | hide if no analysis run yet |
| Price | decimal | e.g. 875.40 |
| CHG | +/- decimal | green if positive, red if negative |
| CHG % | +/- decimal% | green if positive, red if negative |
| Day Range | Low – High | en-dash separator |
| 52W Range | Low – High | en-dash separator |
| Volume | formatted | e.g. 48.2M |
| Rel Vol | decimal + x | e.g. 1.4x |
| Earnings Date | MM/DD/YYYY | ONLY if within 60 days. Amber highlight if within 14 days. |
| Dividend Date | MM/DD/YYYY | ONLY if within 60 days. |

### Rules
- No `$` prefix on any value — ever. House style applies everywhere.
- Earnings and dividend: if null or empty or >60 days away, do not render the
  field at all. No dash, no "N/A", no placeholder.
- Earnings within 14 days: amber badge background (rgba(245,158,11,0.2)),
  amber text. This is a risk signal for options positions.
- Background: var(--bg2) (#161b22)
- Border-bottom: 1px solid var(--border) (#30363d)
- Padding: 10px 16px

### Props Interface
```javascript
<QuoteBar
  symbol="NVDA"
  quote={{
    price: 875.40,
    change: 14.22,
    changePct: 1.65,
    dayLow: 861.10,
    dayHigh: 878.90,
    volume: 48200000,
    relVolume: 1.4
  }}
  smaSignal="BULLISH"        // 'BULLISH' | 'BEARISH' | 'MIXED'
  lastAnalyzed="2026-03-13T18:04:00"  // ISO string or null
  fundamentals={{
    earningsDate: "2026-04-23",   // ISO date string or null
    dividendDate: null
  }}
/>
```

---

## Security Strategies Page

### Route
`/security-strategies/:symbol` or `/security-strategies` (uses activeSymbol)

### Layout (top to bottom)
1. QuoteBar (shared component, identical to all pages)
2. Candlestick chart with SMA 8/21/50 overlays — same chart component as OptionsTerminal
3. Strategy Scorecard section

### Strategy Scorecard
Shows all four strategies scored 0-100 simultaneously.

Each strategy row contains (left to right):
- Checkbox (for selection before Evaluate)
- Strategy name (bold) + subtitle (muted, e.g. "30-45 DTE credit spread")
- Score bar (colored gradient: red < 40, amber 40-69, green 70+)
- Score number (colored same as bar)
- Signal summary (right-aligned, muted, e.g. "IV rank 67 · bullish SMA")

Below all rows:
- "Evaluate Selected" button (teal, disabled until ≥1 checked)
- Selected count label (e.g. "2 strategies selected")

### After Evaluate — TradeEvaluationCards
One card per selected strategy, rendered below the scorecard.
Cards appear in order of score (highest first).
Each card contains: strategy name, trade structure found, score, verdict badge,
6-cell trade detail grid, probability matrix table, Claude's read, Follow + Take Position buttons.

### Claude's Role on This Page
Claude finds the BEST trade for each selected strategy automatically.
No trade is pre-selected by the user on this page.

---

## Verticals Page — Trade Row Expansion

### Unchanged
The ranked trade list, QuoteBar, chart, and analyze bar are unchanged.

### Expansion Panel Layout (2-column grid)
Left column: Scoring Breakdown (existing math matrix)
Right column: Strategy Fit scorecard for this specific trade

### Strategy Fit — Verticals
Show ALL four strategies (all are structurally compatible with vertical spreads).
Filter is: `trade_structure === 'credit_spread' || trade_structure === 'long_option'`
In practice for verticals: all four show.

Each strategy row: checkbox · name · score bar · score number
Below rows: "Evaluate with Claude" button · selected count

### After Evaluate — TradeEvaluationCard
Renders inline below the 2-column grid within the same expansion panel.
Claude evaluates the pre-selected trade through each chosen strategy lens.

### Follow / Take Position
Buttons on the TradeEvaluationCard, not on the expansion panel itself.
Follow = Paper position. Take Position = Live position.
Both POST to position endpoints and show a success toast.

---

## Puts & Calls Page — Trade Row Expansion

### Identical to Verticals EXCEPT for strategy filtering

### Strategy Fit — Puts & Calls
ONLY show strategies where `trade_structure === 'long_option'`:
- ✅ Trend Rider — show, scored
- ✅ Lottery Ticket — show, scored

Non-applicable strategies are shown grayed out below a divider:
- ❌ Steady Paycheck — shown dimmed with reason "requires credit spread structure"
- ❌ Weekly Grind — shown dimmed with reason "requires credit spread structure"

### Why Show Non-Applicable Strategies At All
Transparency. The user can see why those strategies don't apply to this trade type,
rather than wondering where they went. The grayed-out section is clearly separated
by a dashed divider labeled "not applicable to this trade type".

### Filtering Rule
Filtering MUST be driven by the `trade_structure` field in strategy config files.
NEVER hardcode strategy names in the filter logic. A new `long_option` strategy
added in the future must automatically appear here without code changes.

---

## Color System

```
Background:    #0d1117  (--bg)
Surface:       #161b22  (--bg2)
Elevated:      #21262d  (--bg3)
Border:        #30363d  (--border)
Teal accent:   #2dd4bf  (--teal)   — primary brand, active states, CTAs
Green:         #4ade80  (--green)  — bullish, positive, high scores (70+)
Amber:         #f59e0b  (--amber)  — warning, mixed signal, mid scores (40-69)
Red:           #f87171  (--red)    — bearish, negative, low scores (<40), losses
Blue:          #60a5fa  (--blue)   — informational
Purple:        #c084fc  (--purple) — AI/Claude-related elements
Text primary:  #e6edf3  (--text)
Text muted:    #8b949e  (--muted)
```

### Score Color Rules
- Score 70-100: var(--green)
- Score 40-69: var(--amber)
- Score 0-39: var(--red)
- Score bar fill matches score color

### Verdict Badge Colors
- EXECUTE: green background (rgba(74,222,128,.15)), green text
- WAIT: amber background (rgba(245,158,11,.15)), amber text
- PASS: red background (rgba(248,113,113,.15)), red text

---

## Typography
- Font family: monospace (matches trading terminal aesthetic)
- Nav tabs: 12px
- QuoteBar symbol: 16px bold
- QuoteBar field labels: 9px uppercase, letter-spacing 0.4px, muted
- QuoteBar field values: 12px
- Table headers: 10px uppercase, letter-spacing 0.4px, muted
- Table cells: 11px
- Strategy names in scorecard: 12px bold
- Score numbers: 13px bold
- Claude read text: 10px normal (non-italic), color #c9d1d9, line-height 1.65
- Section titles: 10px uppercase, letter-spacing 0.6px, muted

---

## Interaction Patterns

### Expanding a Trade Row
- Click anywhere on the row to expand/collapse
- Chevron in first cell: ▶ collapsed, ▼ expanded
- Expanded row has subtle teal background tint (rgba(45,212,191,.03))
- Expansion panel has teal top border (rgba(45,212,191,.2))
- Only one row expanded at a time (collapsing previous on new expand is acceptable
  but not required — multiple expansions are fine)

### Evaluate Button
- Disabled (dimmed, not clickable) until at least one strategy checkbox is checked
- On click: shows loading state, then renders TradeEvaluationCard(s)
- Loading state: skeleton placeholder cards with pulse animation
- If already evaluated and user clicks again: re-fetches and replaces cards

### Follow / Take Position
- Both show a confirmation toast: "Position added to Positions page"
- Toast links to Positions page
- Buttons remain visible after action (user may want to follow multiple strategies)

### Watchlist Sidebar
- Clicking a symbol: sets activeSymbol AND navigates to Security Strategies for that symbol
- Active symbol has teal left border and subtle teal background

---

## Verticals Page — Expansion Panel (Revised)

The expansion panel has been redesigned. Replace the previous 2-column layout
description with this 4-column layout. This is the canonical spec.

### Layout: 4-Column Grid

The expansion panel is a single horizontal row divided into four equal columns
(25% each), separated by 1px solid #21262d vertical dividers. A teal top border
(2px solid rgba(45,212,191,0.35)) visually connects it to the selected trade row.

**Column 1 — Score Breakdown**
Shows the five scoring metrics. For each metric:
- Colored dot (matches metric color) + metric name + weight badge (e.g. "35%")
- Formula in 9px italic muted text below the name
- 3px horizontal bar showing the normalized score value (0–1), colored to match
  the metric dot

Metric colors (consistent everywhere, never change):
- Expected Value: #60a5fa (blue)
- Reward:Risk: #2dd4bf (teal)
- Probability: #f59e0b (amber)
- Liquidity: #c084fc (purple)
- Theta Efficiency: #f87171 (red)

**Column 2 — Actual Calculation**
For each of the five metrics, shows:
- 9px muted label (metric name)
- The actual numbers plugged into the formula, rendered in a dark inset box
  (background #161b22, left border 2px solid #30363d), with the result value
  colored in the metric color
- A "norm" label + progress bar showing the normalized 0–1 value + the weighted
  contribution to the composite score (e.g. "+0.333") in the metric color

At the bottom, a total row showing how the contributions sum to the composite
score (e.g. "0.332 + 0.196 + ... → 88").

**Column 3 — Strategy Fit**
Shows all four strategies as single-select radio rows. Only one strategy can
be active at a time. Each row:
- Radio indicator: a small colored left border or filled dot on the active row
  (teal, #2dd4bf) — no border on inactive rows
- Strategy name (10px)
- Colored score bar (green ≥70 / amber 40–69 / red <40)
- Score number colored to match bar

Clicking any strategy row immediately selects it (deselects the previous).
The active row has a subtle teal tint (background rgba(45,212,191,0.06)) and
a 2px left border in teal (#2dd4bf). Inactive rows have no background or
left border.

Below each strategy row, a single line of 9px italic muted text explaining
WHY the trade scored that way for that strategy (e.g. "IV rank 67 · bullish
SMA · 30-45 DTE ✓" or "DTE 35 exceeds 7-14 window").

The highest-scoring strategy is selected by default when the panel opens.

At the bottom of column 3:
- "Evaluate with Claude →" button (see Button Standards below)
- Button is always enabled once a strategy is selected (which it always is,
  since the top strategy is pre-selected on open)
- No "N strategies selected" count needed — single select is self-evident

**Column 4 — Strategy Explanation**
Shows the explanation for the currently selected strategy. Updates immediately
when the user clicks a different strategy row in column 3. Contains:
- Strategy name in 12px bold teal
- Subtitle in 9px muted (e.g. "30-45 DTE credit spread · income objective")
- Parameter grid (2 columns): each param shows a 9px uppercase muted key and
  11px value — green with ✓ if the trade meets the parameter, plain white if
  neutral, red with ✗ if it fails
- Signal check box (background #161b22, border-radius 4px): lists 3-4 signal
  items each with a colored dot (green/amber/red) and 9px description

Column 4 is purely informational — no buttons, no inputs. It answers "why
does this strategy score this way for this trade" before the user commits
to evaluating with Claude.

### After Evaluate — Verdict Card

When the user clicks "Evaluate with Claude →", a loading state appears
(animated dots, 9px muted text showing which strategy and trade are being
evaluated), then the verdict card slides in below the 4-column panel with
a smooth max-height transition (0 → visible, ~0.4s ease).

The verdict card has:
- Background: #0a0f15 (slightly darker than page background)
- Top border: 2px solid rgba(74,222,128,0.4) for EXECUTE,
  rgba(245,158,11,0.4) for WAIT, rgba(248,113,113,0.4) for PASS

**Verdict Header** (flex row, items aligned center, border-bottom 1px #21262d):
- Verdict badge: EXECUTE / WAIT / PASS — see Verdict Badge Colors in Color System
- Strategy tag: purple tinted pill (background rgba(192,132,252,0.12),
  color #c084fc, border rgba(192,132,252,0.3))
- Trade reference: symbol · type · strikes · expiry · credit (10px muted)
- Timestamp: 9px, far right, color #444d56

**Verdict Body** (3-column grid: 1.4fr · 1fr · 1fr, border-left 1px #21262d
between columns):

Column 1 — Claude's Read:
- 9px uppercase muted section label
- 10px normal (non-italic) #c9d1d9 prose, line-height 1.65
- Two paragraphs separated by 8px margin

Column 2 — Exit Plan:
- 9px uppercase muted section label
- Four exit level rows, each with a label+sub on the left and price on the right:
  - TAKE PROFIT — price in green
  - WARNING LEVEL — price in amber
  - HARD STOP — price in red
  - EARNINGS WATCH (only if earnings fall within expiry window) — date in purple
- Rows separated by 1px dashed #21262d dividers

Column 3 — Pre-Screen Checks:
- 9px uppercase muted section label
- List of check items: green dot = pass, amber dot = caution, red dot = fail
- Each item: 6px colored dot + 9px description text
- Risk budget box at bottom (background #161b22, border-radius 4px): shows
  max loss dollar amount and % of portfolio, confirms within position limit

**Verdict Action Row** (flex row, border-top 1px #21262d, margin-top 16px):
- "Follow (Paper)" button — teal outlined style
- "Take Position (Live)" button — green filled style, bold
- Follow-up text input (flex: 1, placeholder "Ask a follow-up about this
  trade…") — pressing Enter sends the follow-up with trade context appended
- "Discard ✕" button — neutral outlined style, far right, collapses verdict

If the user selects a different strategy in column 3 while a verdict is
visible, the verdict card collapses automatically. The user must click
"Evaluate with Claude →" again to get a verdict for the newly selected
strategy. This prevents stale verdicts from being misread as applying to
the current selection.

---

## Button Standards

Buttons must NEVER stretch to fill their container or the full width of the
screen. Every button is sized to fit its text content plus fixed internal
padding. This is a hard rule with no exceptions.

### Sizing
- Padding: 6px 14px for small buttons, 7px 18px for standard buttons
- Width: auto (shrinks to content) — never 100%, never flex-grow, never stretch
- The only exception is a button explicitly labeled as a "full-width submit"
  in a form context (e.g. a login form's submit button)

### Button Styles (use exactly these — do not invent new variants)

**Teal outlined** (primary action, non-destructive):
```css
background: rgba(45,212,191,0.1);
border: 1px solid rgba(45,212,191,0.4);
color: #2dd4bf;
padding: 7px 16px;
border-radius: 4px;
font-size: 11px;
font-family: monospace;
cursor: pointer;
width: auto;
```

**Green filled** (positive/confirm action, e.g. Take Position):
```css
background: rgba(74,222,128,0.12);
border: 1px solid rgba(74,222,128,0.45);
color: #4ade80;
font-weight: 700;
padding: 7px 16px;
border-radius: 4px;
font-size: 11px;
font-family: monospace;
cursor: pointer;
width: auto;
```

**Neutral outlined** (secondary/discard actions):
```css
background: transparent;
border: 1px solid #30363d;
color: #8b949e;
padding: 7px 14px;
border-radius: 4px;
font-size: 11px;
font-family: monospace;
cursor: pointer;
width: auto;
```

**Disabled state** (applies to all button types):
```css
opacity: 0.35;
cursor: default;
pointer-events: none;
```

### Visibility Rule
Buttons must be visually distinct at all times — including before hover.
A button that is only visible on hover is not a button, it is a hidden
control. Every button must have a visible border or background in its
default (non-hover) state so the user can see it exists without mousing
over it.

### Button Groupings
When two or more buttons appear together (e.g. Follow + Take Position):
- Arrange horizontally in a flex row with gap: 10px
- Do NOT stretch either button to fill remaining space
- Buttons sit left-aligned within their container unless explicitly
  specified otherwise (e.g. a modal's confirm/cancel pair may be
  right-aligned)

---

## Evaluate Button — Loading and State Management

The "Evaluate with Claude →" button in the expansion panel has three states:

**Default** (strategy selected, no verdict showing):
- Label: "Evaluate with Claude →"
- Teal outlined style (see Button Standards)
- Full opacity, clickable

**Loading** (after click, waiting for Claude response):
- Label: "Evaluating…" with animated ellipsis (CSS pulse on each dot,
  staggered 0.2s delays)
- Background: rgba(45,212,191,0.06) — slightly dimmer than default
- Color: #8b949e (muted — visually signals in-progress)
- Not clickable during loading (pointer-events: none)
- Below the button: 9px muted text identifying what is being evaluated,
  e.g. "Steady Paycheck · AMZN 200/195 Apr 17"

**Re-evaluate** (verdict already showing for current strategy):
- Label: "Re-evaluate →"
- Same teal outlined style
- Clicking replaces the existing verdict with loading state, then new verdict

**Strategy switched while verdict visible**:
- Verdict card collapses immediately on strategy row click
- Button returns to default "Evaluate with Claude →" label
- This ensures the user always knows which strategy the visible verdict
  belongs to

---

## ResultsTable — Column Configuration Contract

`ResultsTable` is a pure display component. It never knows what page it is on.
It accepts a `columns` prop array and renders whatever columns are defined.
Column definitions live in `web/src/config/`.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `results` | `array` | Trade objects to display |
| `columns` | `array` | Column config array (see below) |
| `context` | `object` | Passed as 2nd arg to each `col.render(trade, ctx)` |
| `expandedRowId` | `string` | Controlled by parent — id of open expansion row |
| `onRowClick` | `fn(id)` | Called with row id on click; `null` = collapse |
| `renderExpansionRow` | `fn(trade)` | Renders the expansion `<tr>` contents |
| `getRowId` | `fn(trade, idx)` | Optional; defaults to `String(idx)` |
| `defaultSortKey` | `string` | Initial sort column (default: `'composite_score'`) |
| `defaultSortDir` | `'asc'\|'desc'` | Initial sort direction (default: `'desc'`) |

### Column Config Shape

```javascript
{
  key: string,          // unique key; also the sort field unless sortKey overrides
  sortKey: string,      // optional — override which trade field is sorted on
  label: string,        // header text
  title: string,        // optional — tooltip on header and cell
  width: number,        // px width hint for <th>
  align: string,        // 'left' | 'center' | 'right' (default 'right')
  sortable: boolean,    // default true; set false to disable sort on click
  render: (trade, ctx) => ReactNode,  // cell renderer; ctx includes context + idx
}
```

### Sorting Behavior
- Click any sortable header → sort descending by that column
- Click again → toggle to ascending
- Active sort column shown with ▼ (desc) or ▲ (asc) indicator in teal
- Clicking a sort header calls `onRowClick(null)` to collapse any open expansion row
- Sort state is managed internally; parent does not need to track it

### Verticals Column Set
`web/src/config/verticals-columns.jsx`
`#` · TYPE · SPREAD · EXPIRATION · DELTA · IV · THETA · NET · R:R · PROB · SCORE · [R:R pip] · [PROB pip] · [SCR pip]
Default sort: SCORE descending.

IV column: short leg implied volatility, stored as decimal (0.2616), displayed as percentage (26.2%).
Format: `(val * 100).toFixed(1) + '%'`. Shows '—' if null.

Pip thresholds (from `ctx.systemVars`, with defaults):
- R:R pip: green ≥1.5, amber ≥1.0
- Prob pip: green ≥55%, amber ≥45%
- Score pip: green ≥0.65, amber ≥0.45

### Puts & Calls Column Set
`web/src/config/long-options-columns.jsx`
TYPE · STRIKE · EXPIRATION · DELTA · IV · THETA/DAY · PREMIUM · BREAKEVEN · vs ITM · SCORE · [Δ pip] · [IV pip] · [Run pip]
Default sort: SCORE descending.

IV column: contract implied volatility, stored as decimal (0.2616), displayed as percentage (26.2%).
Format: `(val * 100).toFixed(1) + '%'`. Shows '—' if null.

Pip thresholds (from `ctx.systemVars`, with defaults):
- Delta pip: green 0.30–0.65, amber ±0.05 of edges
- IV pip: green ≤0.30 (30%), amber ≤0.50 (50%) — thresholds are decimal fractions, not percentages
- Runway pip: green ≥30d, amber ≥15d

### vs ITM Column
- `key: '_vs_itm'`, `sortKey: 'vs_itm_dollars'`
- Requires parent to pre-compute `trade.vs_itm_dollars = (call: price − strike, put: strike − price)`
- Displays as `+12.34 / +1.4%` (positive = ITM, negative = OTM)
- Color: green when ITM (distance > 0), amber when within 5% of money, muted gray otherwise
- Parent must pass `ctx.currentPrice` for the computation

---

## What Does NOT Exist In The Nav

These items are explicitly NOT in the navigation bar:
- Steady Paycheck (tab)
- Weekly Grind (tab)
- Trend Rider (tab)
- Lottery Ticket (tab)
- Directional Compare (tab)
- Any other strategy as a standalone tab

Strategy configs remain in `web/src/strategy-configs/` and are used by the
scoring engine. They do not drive navigation.
