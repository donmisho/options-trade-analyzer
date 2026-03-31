OTA-336 OTA-337 OTA-338 OTA-339 OTA-341 OTA-342 OTA-349

## SESSION 1 — Nav + Routes + Page Shell + Shared Components
### Run in Claude Code Terminal 1 (parallel with Session 2)

## IMPORTANT — Read First
Read UI-GUIDANCE.md (the ENTIRE file) before making any changes. It is the single source
of truth and supersedes UI-DECISIONS.md and all prior specs. Also open
ota-experience-mockups-v3.html in a browser or read the HTML source for visual reference
(Screens 1 and 2 especially).

This session covers 7 subtasks. Execute them in order. Do NOT modify any files under
web/src/components/TradeDetail/ — that directory is being built by a parallel session.

---

### Step 1 — Shared Components (OTA-341, OTA-342, OTA-349)

Build these three independent components first. They have no dependencies on each other
or on the nav/route changes.

**1a. Create web/src/components/StrategyPill.jsx (OTA-341)**

Props: strategy (string — "steady_paycheck", "SP", etc.)

Abbreviation + color mapping:
- steady_paycheck / SP → abbr "SP", bg rgba(245,158,11,0.12), text var(--amber)
- weekly_grind / WG → abbr "WG", bg rgba(74,222,128,0.12), text var(--green)
- trend_rider / TR → abbr "TR", bg rgba(96,165,250,0.12), text var(--blue)
- lottery_ticket / LT → abbr "LT", bg rgba(192,132,252,0.12), text var(--purple)

Pill styling: font-size 9px, font-weight 700, padding 2px 5px, border-radius 3px,
margin 0 1px, display inline-block, cursor default, position relative.

Tooltip on hover (CSS-only, no JS state):
- Shows full name (e.g., "Steady Paycheck")
- Position absolute, bottom 100%, left 50%, transform translateX(-50%)
- bg var(--bg3), border 1px solid var(--border), font-size 9px, font-weight 400,
  padding 3px 8px, border-radius 3px, white-space nowrap, margin-bottom 4px, z-index 10
- display: none by default → display: block on .pill:hover .tooltip

Export a STRATEGY_COLORS constant object for reuse by other components:
```js
export const STRATEGY_COLORS = {
  steady_paycheck: { abbr: 'SP', bg: 'rgba(245,158,11,0.12)', text: 'var(--amber)', fullName: 'Steady Paycheck' },
  weekly_grind: { abbr: 'WG', bg: 'rgba(74,222,128,0.12)', text: 'var(--green)', fullName: 'Weekly Grind' },
  trend_rider: { abbr: 'TR', bg: 'rgba(96,165,250,0.12)', text: 'var(--blue)', fullName: 'Trend Rider' },
  lottery_ticket: { abbr: 'LT', bg: 'rgba(192,132,252,0.12)', text: 'var(--purple)', fullName: 'Lottery Ticket' },
};
```

Accept both key formats ("steady_paycheck" and "SP") — normalize on input.

**1b. Create web/src/components/TradeTypeBadge.jsx (OTA-342)**

Props: type (string — raw enum like "BEAR_PUT_DEBIT")

Display name transform (at render time): replace underscores with spaces, title case.
"BULL_CALL_DEBIT" → "Bull Call Debit"

Color: first word determines direction.
- BULL → bg rgba(74,222,128,0.15), text var(--green)
- BEAR → bg rgba(248,113,113,0.15), text var(--red)
- Future types follow same rule: first word = direction = color

Styling: font-size 9px, font-weight 700, padding 2px 6px, border-radius 3px, white-space nowrap.

Search the existing codebase for anywhere trade types are displayed and replace with
<TradeTypeBadge type={...} />. Check: VerticalsPage.jsx, LongCallsPage.jsx, ResultsTable
column configs, any expansion panels.

**1c. Create web/src/components/ScoreCell.jsx (OTA-349)**

Props: score (number 0-100)

Layout: flex row, align-items center, gap 6px.
- Bar bg: width 50px, height 4px, bg var(--bg3), border-radius 2px, overflow hidden
- Bar fill: height 100%, width = {score}%, border-radius 2px, color by threshold
- Number: font-size 11px, font-weight 700, min-width 36px

Color thresholds (same color for bar fill AND number):
- 70-100: var(--green)
- 40-69: var(--amber)
- 0-39: var(--red)

Format: always ##.00 via .toFixed(2).

---

### Step 2 — Nav Rail Update (OTA-336)

Update web/src/components/Layout.jsx (or wherever the sidebar nav renders):

Replace the current 5 primary nav items with exactly 4:
- Dashboard → /dashboard
- Security Strategies → /security-strategies
- Trades → /trades
- Positions → /positions

Remove "Verticals" and "Puts & Calls" from the nav entirely.

Add "STRATEGIES" section header below primary items:
- font-size 9px, text-transform uppercase, letter-spacing 0.6px, color var(--muted)
- padding 20px 16px 6px 16px

Add 4 strategy sub-nav links below the header:
- Steady Paycheck → /strategies/steady-paycheck
- Weekly Grind → /strategies/weekly-grind
- Trend Rider → /strategies/trend-rider
- Lottery Ticket → /strategies/lottery-ticket
- font-size 11px, color var(--muted), padding 7px 16px 7px 24px
- Hover: color var(--text)
- Active: color var(--teal), border-left 3px solid var(--teal), padding-left 21px,
  background rgba(45,212,191,0.08)

Primary item active state:
- border-left 3px solid var(--teal), color var(--teal), bg rgba(45,212,191,0.08)

Primary item inactive:
- border-left 3px solid transparent, color var(--muted), no bg

Bottom section (margin-top auto, padding 16px, border-top 1px solid var(--border)):
- Schwab Connected: font-size 10px, color var(--green), with 6px green dot
- Settings gear: font-size 11px, color var(--muted)

Rail width: 200px fixed (NOT 220px — v3 supersedes prior).

---

### Step 3 — Routes (OTA-337)

Update web/src/App.jsx:

1. Add route: /trades → TradesPage (create the file in step 4)
2. Add route: /strategies/:key → StrategyPage (create placeholder)
3. Remove routes for /verticals and /puts-calls (or /long-calls)
4. Add redirects: /verticals → /trades, /puts-calls → /trades

Create web/src/pages/StrategyPage.jsx as a placeholder:
- Read :key from useParams
- Render: "Strategy: {key} — under construction" (16px bold monospace)
- Export default

Do NOT delete VerticalsPage.jsx or LongCallsPage.jsx files.

---

### Step 4 — TradesPage Shell (OTA-338)

Build out web/src/pages/TradesPage.jsx:

1. Symbol search at top: use existing SymbolSearch component.
   If URL has ?symbol=XXX, pre-populate. On selection, update URL param.
2. Import and render <QuoteBar /> below search. Use the shared component from
   web/src/components/QuoteBar.jsx. Do NOT reimplement.
3. SMA chart area: import existing chart component if available, otherwise render
   placeholder div: height 160px, border 1px solid var(--border), border-radius 4px,
   centered text "SMA chart — configurable moving averages", color var(--muted), 10px.
4. Below chart: render the collapsible sections (step 5).
5. Read URL params: ?symbol=XXX and ?strategy=XXX on mount.

---

### Step 5 — Collapsible Trade Structure Sections (OTA-339)

Add to TradesPage.jsx below the chart area:

Three collapsible sections, each with a section header:
- Header: flex row, align-items center, padding 10px 0, cursor pointer,
  border-bottom 1px solid var(--border), gap 8px
- Chevron: ▼ expanded, ▶ collapsed (9px muted, width 14px)
- Title: 12px bold
- Count: 10px muted (e.g., "· 20 results")
- Config button on right: neutral outlined small ("⚙ Config"), padding 4px 10px, 10px font

Sections in order:
a. "Vertical spreads" — expanded by default
b. "Puts & calls" — collapsed by default
c. "Iron condors" — collapsed, opacity 0.5, count text "· coming soon" (italic),
   NOT clickable, no Config button

When expanded, render placeholder text for now: "Loading vertical spreads..." etc.
The ResultsTable wiring happens in the integration session (Session 3).

Do NOT render the purple dashed annotation boxes from mockups (those are design notes only).

---

### Commit Checkpoint

After completing all 5 steps, verify:
- Nav shows 4 primary items + strategy sub-nav
- /trades renders the TradesPage with search, QuoteBar, chart, 3 sections
- /strategies/steady-paycheck renders the placeholder
- /verticals redirects to /trades
- StrategyPill, TradeTypeBadge, ScoreCell all render correctly in isolation

Wait for Session 2 to complete before running Session 3 (integration).

Recommended QA level: 1 (targeted — Layout.jsx + TradesPage + new components)

Commit message: OTA-336 OTA-337 OTA-338 OTA-339 OTA-341 OTA-342 OTA-349 feat: v3 nav rail, trades page shell, shared components
