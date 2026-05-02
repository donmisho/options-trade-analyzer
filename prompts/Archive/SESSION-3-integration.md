OTA-340 OTA-348 OTA-350

## SESSION 3 — Integration
### Run AFTER Sessions 1 and 2 are both committed

## IMPORTANT — Read First
Read UI-GUIDANCE.md. Sessions 1 and 2 have completed. This session wires everything together.

---

### Step 1 — Wire ResultsTable to Sections (OTA-340)

Update TradesPage.jsx to render ResultsTable inside each trade-structure section:

1. Vertical spreads section (when expanded):
   - Import ResultsTable from web/src/components/ResultsTable.jsx
   - Update web/src/config/verticals-columns.js to match v3 column order:
     [chevron] [Score] [Spread] [Type] [Expiration] [Delta] [IV] [Theta] [Net] [R:R] [Prob] [Strategies]
   - Score column uses <ScoreCell score={row.score} /> from web/src/components/ScoreCell.jsx
   - Type column uses <TradeTypeBadge type={row.type} /> from web/src/components/TradeTypeBadge.jsx
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

1. Import all sections:
   import { SectionA, SectionB, SectionC, SectionD, SectionE } from '../components/TradeDetail';

2. When row clicked → expand inline below it (full colspan)

3. Render inside the expansion:
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

4. Only one row expanded at a time — clicking another row collapses the current one
5. Expanded row gets className "expanded" with bg rgba(45,212,191,0.03)
6. Map existing analysis response data to Section component props:
   - SectionA needs the trade object with strikes, expiry, entry, maxProfit, maxLoss, etc.
   - SectionB needs scenarios array (price increments with P&L calculations)
   - SectionC needs outcome summary (probabilities and EV)
   - SectionE evaluation starts as null (pre-evaluation state shows Evaluate button)

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
   - Remove the line about "Five fixed nav tabs" — replace with the new 4-item description
   - Update timestamp to current date

2. Update project-hierarchy.md:
   - Add TradesPage.jsx, StrategyPage.jsx under pages/
   - Add TradeDetail/ directory under components/ with SectionA.jsx through SectionE.jsx
     and index.js
   - Add StrategyPill.jsx, TradeTypeBadge.jsx, ScoreCell.jsx under components/
   - Mark VerticalsPage.jsx as "(deprecated — migrated to TradesPage)"
   - Mark LongCallsPage.jsx as "(deprecated — migrated to TradesPage)"
   - Update timestamp

3. Add superseded header to UI-DECISIONS.md as the first two lines:
   ```
   # SUPERSEDED — This file is replaced by UI-GUIDANCE.md v3.1 (03-31-2026)
   # Retained for historical reference only. Do not use for implementation.
   ```

---

### Final Commit

Verify the full flow works:
- Navigate to /trades
- Enter a symbol → QuoteBar loads, chart shows
- Vertical spreads section expanded with ResultsTable
- Click a row → trade detail expands with Sections A-E
- Section E shows Evaluate button (pre-evaluation state)
- Click Discard → expansion collapses
- Click another row → previous collapses, new expands
- Puts & calls section can be expanded with its own table
- Strategy pills show on the last column with tooltips
- Trade type badges show clean names with directional colors
- Score cells show bar + number with threshold colors
- Nav rail shows 4 items + strategy sub-nav
- /strategies/steady-paycheck shows placeholder
- /verticals redirects to /trades
- CLAUDE.md updated, UI-DECISIONS.md has superseded header

Commit message: OTA-340 OTA-348 OTA-350 feat: wire ResultsTable + trade detail expansion + doc updates

Recommended QA level: 2 (full regression — touches multiple components, integration points across both parallel sessions)
