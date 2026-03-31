# Sprint 1 — Parallel Claude Code Session Prompts

## How to Run

Open two Claude Code terminals. Paste Session 1 into Terminal 1, Session 2 into Terminal 2.
Run simultaneously — they touch completely independent files.

**After both complete:** Commit, then run Session 3 (integration) in a single terminal.

---

## SESSION 1 — Nav + Routes + Page Shell + Shared Components
### Covers: OTA-336, OTA-337, OTA-338, OTA-339, OTA-341, OTA-342, OTA-349

Paste this entire block into Claude Code Terminal 1:

```
OTA-336 OTA-337 OTA-338 OTA-339 OTA-341 OTA-342 OTA-349

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
The ResultsTable wiring happens in the integration session.

Do NOT render the purple dashed annotation boxes from mockups (those are design notes only).

---

### Commit Checkpoint

After completing all 5 steps, verify:
- Nav shows 4 primary items + strategy sub-nav
- /trades renders the TradesPage with search, QuoteBar, chart, 3 sections
- /strategies/steady-paycheck renders the placeholder
- /verticals redirects to /trades
- StrategyPill, TradeTypeBadge, ScoreCell all render correctly in isolation

Wait for Session 2 to complete before running the integration session.

Recommended QA level: 1 (targeted — Layout.jsx + TradesPage + new components)

Commit message: OTA-336 OTA-337 OTA-338 OTA-339 OTA-341 OTA-342 OTA-349 feat: v3 nav rail, trades page shell, shared components
```

---

## SESSION 2 — Trade Detail Section Components
### Covers: OTA-343, OTA-344, OTA-345, OTA-346, OTA-347

Paste this entire block into Claude Code Terminal 2:

```
OTA-343 OTA-344 OTA-345 OTA-346 OTA-347

## IMPORTANT — Read First
Read UI-GUIDANCE.md (the ENTIRE file) before making any changes. It is the single source
of truth. Also open ota-experience-mockups-v3.html and study Screen 2's trade detail
expansion (the .td-exp section with Sections A through E).

This session creates all files under web/src/components/TradeDetail/.
Do NOT modify Layout.jsx, App.jsx, TradesPage.jsx, or any files outside TradeDetail/ —
those are being built by a parallel session.

Create the directory: web/src/components/TradeDetail/

---

### Step 1 — SectionA.jsx (OTA-343) — Trade Header

Create web/src/components/TradeDetail/SectionA.jsx

Props: trade (object with type, strikes, expiry, dte, entry, maxProfit, maxLoss,
breakeven, rewardRisk, profitTrigger, stopTrigger, timeExit)

The outermost wrapper has the teal top border (this goes on the parent container that
wraps ALL sections, but define the styling here as a CSS class for the parent to use):
- border-top: 2px solid rgba(45,212,191,0.35)
- padding: 16px 0

Section A content card:
- border: 1px solid var(--border), border-radius 4px, padding 10px 14px
- display flex, flex-wrap wrap, gap 14px, margin-bottom 12px

Contents left to right:
1. Import and render <TradeTypeBadge type={trade.type} /> — at 12px font-weight 700
   NOTE: TradeTypeBadge is being built in the parallel session. Import it but if it
   doesn't exist yet, create a local inline fallback that renders the type as text.
2. Context label: derive from trade type.
   - If type contains "DEBIT" → "(bearish — you pay to enter)" or "(bullish — you pay to enter)"
   - If type contains "CREDIT" → "(bearish — you receive credit)" or "(bullish — you receive credit)"
   - Bull/Bear determined by first word
   - Style: 10px, color var(--muted)
3. Metadata fields as stacked label/value pairs:
   Each field: label on top (9px uppercase, letter-spacing 0.4px, muted),
   value below (12px bold)

   Fields:
   - Strikes: e.g., "630 / 620"
   - Expiry: use formatDate() from web/src/utils/formatDate.js → mm-dd-yyyy
   - DTE: e.g., "17d"
   - Entry: e.g., "3.66 debit (366.00 / contract)" — NO $ prefix
   - Max profit: green, ##.00
   - Max loss: red, ##.00
   - Breakeven: ##.00
   - R:R: #.##:1 format
   - Profit trigger: green
   - Stop trigger: red
   - Time exit: formatDate()

Export default SectionA.

---

### Step 2 — SectionB.jsx (OTA-344) — Exit Scenario Table

Create web/src/components/TradeDetail/SectionB.jsx

Props: scenarios (array of { price, spreadValue, pnl, pnlPct, probability,
expectedValue, exitSignal })

Section label above table: "EXIT SCENARIO ANALYSIS"
- font-size 10px, text-transform uppercase, letter-spacing 0.6px, color var(--muted)
- margin: 16px 0 8px

Table columns:
Underlying price | Spread value | P&L / contract | P&L % | Probability | Expected value | Exit signal

Table styling:
- width 100%, border-collapse collapse
- th: font-size 9px, text-transform uppercase, letter-spacing 0.4px, color var(--muted),
  padding 6px 8px, text-align right (first col left), font-weight 400,
  border-bottom 1px solid var(--border)
- td: font-size 11px, padding 6px 8px, text-align right (first col left),
  border-bottom 1px solid rgba(48,54,61,0.3)

Loss zone: rows where pnl < 0 get background rgba(248,113,113,0.03)

P&L formatting:
- Positive: color var(--green), "+634.00", "+173.22%"
- Negative: color var(--red), "-366.00", "-100.00%"
- Sign ALWAYS shown. Format ##.00.

Probability: ##.00% format

Exit signal badges (9px bold, letter-spacing 0.3px):
- "MAX PROFIT" → var(--green)
- "BREAKEVEN" → var(--amber)
- "STOP" → var(--red)
- "TIME EXIT" → var(--muted)

Footer row:
- td colspan 5: "Total expected value" font-weight 700, text-align left
- td: EV value, font-weight 700, colored green if positive, red if negative

Also accept a totalEV prop for the footer.

Export default SectionB.

---

### Step 3 — SectionC.jsx (OTA-345) — Outcome Summary

Create web/src/components/TradeDetail/SectionC.jsx

Props: outcome (object with pMaxProfit, pBreakeven, pPartial, pMaxLoss,
expectedValue, evPctRisk)

Section label: "OUTCOME SUMMARY" (same style as SectionB label)

Container: display flex, gap 1px, border 1px solid var(--border), border-radius 4px,
overflow hidden, margin-bottom 12px.

Six cells, each separated by border-left 1px solid var(--border) (except first):
- flex 1, padding 12px 14px

Cell internals:
- Label: font-size 9px, text-transform uppercase, letter-spacing 0.3px,
  color var(--muted), margin-bottom 4px
- Value: font-size 16px, font-weight 700

Cells:
1. "P(MAX PROFIT)" → value in var(--green), format ##.00%
2. "P(BREAKEVEN OR BETTER)" → value in var(--green), format ##.00%
3. "P(PARTIAL PROFIT)" → default text color, format ##.00%
4. "P(MAX LOSS)" → value in var(--red), format ##.00%
5. "EXPECTED VALUE" → colored by sign (green +, red -), format ±##.00
6. "EV % OF RISK" → default text color, format ##.00%
   Below value: badge div
   - "POSITIVE EV" if evPctRisk > 0: bg rgba(74,222,128,0.1), color var(--green)
   - "NEGATIVE EV" if evPctRisk <= 0: bg rgba(248,113,113,0.1), color var(--red)
   - font-size 9px, font-weight 700, padding 3px 8px, border-radius 3px,
     display inline-block, margin-top 4px

Export default SectionC.

---

### Step 4 — SectionD.jsx (OTA-347) — Probability Matrix Placeholder

Create web/src/components/TradeDetail/SectionD.jsx

Props: none

Section label: "PROBABILITY MATRIX" (same style)

Placeholder card:
- border 1px solid var(--border), border-radius 4px, padding 20px, text-align center
- Text: "Probability matrix — available when Phase 2.11 backend is complete"
- font-size 11px, color var(--muted)

Export default SectionD.

---

### Step 5 — SectionE.jsx (OTA-346) — Claude's Read

Create web/src/components/TradeDetail/SectionE.jsx

Props: evaluation (object with verdict, bestStrategy, summaryText, analysis,
keyLevelPrice, keyLevelExplanation), tradeContext (string like "SPY · BEAR PUT · 630/620 · 04-16"),
onEvaluate, onFollow, onTakePosition, onFollowUp, onDiscard

Two states: pre-evaluation (evaluation is null) and post-evaluation.

**Pre-evaluation state:**
Just render the Evaluate button (teal outlined: bg rgba(45,212,191,0.1),
border 1px solid rgba(45,212,191,0.4), color var(--teal), padding 7px 16px,
border-radius 4px, font-size 11px, font-family monospace, width auto).
onClick → onEvaluate()

**Post-evaluation state:**
Container: border 1px solid var(--border), border-radius 4px, padding 14px 16px,
margin-top 12px

Header row: display flex, align-items center, gap 10px, flex-wrap wrap, margin-bottom 10px
1. Label "CLAUDE'S READ": font-size 9px, text-transform uppercase,
   letter-spacing 0.6px, color var(--muted)
2. Verdict badge: font-size 10px, font-weight 700, padding 3px 10px, border-radius 3px
   - "EXECUTE" → bg rgba(74,222,128,0.15), color var(--green)
   - "WAIT" → bg rgba(245,158,11,0.15), color var(--amber)
   - "PASS" → bg rgba(248,113,113,0.15), color var(--red)
3. Claude summary advice badge — THIS IS A WHITE OUTLINED BADGE, NOT PURPLE:
   - background rgba(255,255,255,0.06)
   - border 1px solid rgba(255,255,255,0.35)
   - color #e6edf3
   - font-size 9px, font-weight 700, padding 3px 10px, border-radius 3px
   - display inline-flex, align-items center, gap 4px
   - Text format: "Best fit: " in #e6edf3 + strategy name in strategy color
   - Import STRATEGY_COLORS from StrategyPill.jsx (or define locally if not available yet)
     to get the correct color for the strategy name
4. Trade context: font-size 9px, color var(--muted), margin-left auto
5. Evaluate button (teal outlined small: padding 4px 10px, 10px font)

Analysis text: font-size 10px, color #c9d1d9, line-height 1.65, margin-bottom 8px.
NON-italic. Multiple paragraphs (map over analysis array or split by \n\n).

Key level callout:
- background var(--bg2), border-left 2px solid var(--amber)
- padding 6px 10px, font-size 10px, margin 8px 0, border-radius 0 4px 4px 0
- Price in var(--amber) font-weight 700, followed by explanation text in default color

Actions row: display flex, gap 10px, margin-top 12px, align-items center
1. "Follow (Paper)" — teal outlined button (padding 7px 16px)
2. "Take Position (Live)" — green filled button: bg rgba(74,222,128,0.12),
   border 1px solid rgba(74,222,128,0.45), color var(--green), font-weight 700
3. Follow-up input: flex 1, bg var(--bg), border 1px solid var(--border),
   color var(--text), font-family monospace, font-size 10px, padding 7px 12px,
   border-radius 4px, placeholder "Ask a follow-up about this trade..."
4. "Discard ✕" — neutral outlined: bg transparent, border 1px solid var(--border),
   color var(--muted)

ALL buttons: width auto (never full-width stretch), font-family monospace, font-size 11px.

Wire callbacks: Follow → onFollow(), Take Position → onTakePosition(),
follow-up submit (Enter key) → onFollowUp(text), Discard → onDiscard()

Export default SectionE.

---

### Step 6 — Index file

Create web/src/components/TradeDetail/index.js:
```js
export { default as SectionA } from './SectionA';
export { default as SectionB } from './SectionB';
export { default as SectionC } from './SectionC';
export { default as SectionD } from './SectionD';
export { default as SectionE } from './SectionE';
```

---

### Commit Checkpoint

After completing all steps, verify each component renders without errors when imported
individually. Test with mock data if needed.

Wait for Session 1 to complete before running the integration session.

Recommended QA level: 1 (targeted — TradeDetail components only)

Commit message: OTA-343 OTA-344 OTA-345 OTA-346 OTA-347 feat: trade detail Sections A-E components
```

---

## SESSION 3 — Integration (run AFTER Sessions 1 and 2 are both committed)
### Covers: OTA-340, OTA-348, OTA-350

Paste this into a single Claude Code terminal after both sessions above are done:

```
OTA-340 OTA-348 OTA-350

## IMPORTANT — Read First
Read UI-GUIDANCE.md. Sessions 1 and 2 have completed. This session wires everything together.

---

### Step 1 — Wire ResultsTable to Sections (OTA-340)

Update TradesPage.jsx to render ResultsTable inside each trade-structure section:

1. Vertical spreads section (when expanded):
   - Import ResultsTable from web/src/components/ResultsTable.jsx
   - Update web/src/config/verticals-columns.js to match v3 column order:
     [chevron] [Score] [Spread] [Type] [Expiration] [Delta] [IV] [Theta] [Net] [R:R] [Prob] [Strategies]
   - Score column uses <ScoreCell score={row.score} />
   - Type column uses <TradeTypeBadge type={row.type} />
   - Strategies column renders array of <StrategyPill strategy={s} /> per trade
   - NO row numbers

2. Puts & calls section (when expanded):
   - Use long-options-columns.js, adapt column order to match v3

3. Port data fetching logic from VerticalsPage.jsx and LongCallsPage.jsx:
   - Each section fetches independently when expanded
   - Show loading indicator while fetching
   - Show error message inline on failure

4. Row click toggles expanded state (wired in Step 2)

---

### Step 2 — Assemble Trade Detail Expansion (OTA-348)

Update TradesPage.jsx to render Sections A-E when a row is expanded:

1. When row clicked → expand inline below it (full colspan)
2. Render inside the expansion:
   <div style={{ borderTop: '2px solid rgba(45,212,191,0.35)', padding: '16px 0' }}>
     <SectionA trade={selectedTrade} />
     <SectionB scenarios={selectedTrade.scenarios || []} totalEV={selectedTrade.totalEV} />
     <SectionC outcome={selectedTrade.outcome || {}} />
     <SectionD />
     <SectionE
       evaluation={selectedTrade.evaluation}
       tradeContext={`${symbol} · ${selectedTrade.type} · ${selectedTrade.spread} · ${selectedTrade.expiry}`}
       onEvaluate={() => console.log('Evaluate', selectedTrade)}
       onFollow={() => console.log('Follow paper', selectedTrade)}
       onTakePosition={() => console.log('Take position', selectedTrade)}
       onFollowUp={(text) => console.log('Follow-up:', text, selectedTrade)}
       onDiscard={() => setExpandedRow(null)}
     />
   </div>

3. Only one row expanded at a time
4. Expanded row gets className "expanded" with bg rgba(45,212,191,0.03)
5. Map existing analysis response data to Section component props

---

### Step 3 — Document Updates (OTA-350)

1. Update CLAUDE.md:
   - Change "UI-DECISIONS.md" references to "UI-GUIDANCE.md"
   - Update nav description: "Nav: Left rail (200px fixed). Items: Dashboard ·
     Security Strategies · Trades · Positions. Strategy sub-nav: Steady Paycheck /
     Weekly Grind / Trend Rider / Lottery Ticket."
   - Remove "Verticals" and "Puts & Calls" as separate nav items
   - Add: "Verticals and Puts & Calls merged into Trades page per UI-GUIDANCE.md v3.1"
   - Add TradeTypeBadge, StrategyPill, ScoreCell to shared components list
   - Add: "Claude summary advice badge: white outlined (not purple)"
   - Remove "Five fixed nav tabs" line
   - Update timestamp

2. Update project-hierarchy.md:
   - Add TradesPage.jsx, StrategyPage.jsx under pages/
   - Add TradeDetail/ directory under components/ with SectionA.jsx through SectionE.jsx
   - Add StrategyPill.jsx, TradeTypeBadge.jsx, ScoreCell.jsx under components/
   - Mark VerticalsPage.jsx, LongCallsPage.jsx as "(deprecated — migrated to TradesPage)"
   - Update timestamp

3. Add superseded header to UI-DECISIONS.md (first line):
   "# SUPERSEDED — This file is replaced by UI-GUIDANCE.md v3.1 (03-31-2026)"
   "# Retained for historical reference only. Do not use for implementation."

---

### Final Commit

Commit message: OTA-340 OTA-348 OTA-350 feat: wire ResultsTable + trade detail expansion + doc updates

Recommended QA level: 2 (full regression — touches multiple components, integration points)
```
