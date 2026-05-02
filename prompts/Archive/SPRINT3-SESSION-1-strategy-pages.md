OTA-351 OTA-369 OTA-370 OTA-371

## SESSION 1 — Sprint 2 Fixes + Strategy Page Full Build
### Run in Claude Code Terminal 1 (parallel with Session 2)

## IMPORTANT — Read First
Read UI-GUIDANCE.md (the ENTIRE file) before making any changes. It is the single source
of truth. Also review ota-experience-mockups-v3.html Screen 3 (Strategy Page) and
architecture-plan.md "Strategy Scorecard — Scoring Engine Data Inputs" section.

This session covers the Sprint 2 integration fixes (prerequisite) then the full Strategy
Page build. Do NOT modify PositionsPage.jsx — that's being built by Terminal 2.

---

### Step 1 — Sprint 2 Integration Fixes (OTA-351)

Fix the 5 gaps from Sprint 1 on the Trades page:

**1a. Import SMA chart into TradesPage**
The SMA chart component works on Security Strategies page (candlestick with 8/21/50 day
SMAs and chart range selector). Find that component and import it into TradesPage.jsx,
replacing the gray placeholder div. Pass the active symbol so it loads correct data.

**1b. Wire StrategyPill into ResultsTable Strategies column**
Open web/src/config/verticals-columns.js. Find the "Strategies" column definition.
Update its render function to map over the trade's strategy array and render
StrategyPill for each. Check what field name the backend uses (strategies,
strategy_tags, matched_strategies). Do the same for long-options-columns.js.

**1c. Render SectionC in trade detail expansion**
Open TradesPage.jsx. Find where SectionA, SectionB, SectionD, SectionE are rendered
in the expansion. Add SectionC between SectionB and SectionD:
```jsx
<SectionC outcome={selectedTrade.outcome || {}} />
```
Import SectionC from TradeDetail if not already imported.

**1d. Populate SectionB with scenario data**
SectionB renders headers but no rows. Check what data the analysis endpoint returns.
Map the trade's P&L scenarios to the scenarios array prop. Each scenario needs:
price, spreadValue, pnl, pnlPct, probability, expectedValue, exitSignal.
If the backend doesn't return pre-computed scenarios, compute them from the trade data
at $5 price increments around current price.

**1e. Verify Puts & calls and Iron condors sections render**
Scroll below Vertical spreads on the Trades page. Confirm "Puts & calls" section
renders (collapsed by default) and "Iron condors" renders grayed out with "coming soon".
If missing, check TradesPage.jsx for the section rendering code.

**Verify:** /trades?symbol=SPY shows real SMA chart, strategy pills in table rows,
Section C outcome bar in expansion, Section B with data rows.

---

### Step 2 — Strategy Header + Parameter Cards (OTA-369)

Replace the placeholder in web/src/pages/StrategyPage.jsx:

1. Read :key from useParams (e.g., "steady-paycheck"). Convert to lookup key
   (e.g., "steady_paycheck").

2. Create a STRATEGY_DATA map (or separate file web/src/config/strategy-data.js):

   **steady_paycheck:**
   - name: "Steady Paycheck"
   - description: "25-50 DTE credit spreads, high IV rank, income focus"
   - dteRange: "25 – 50 DTE", structure: "Credit spread"
   - requirement: "Requires credit spread structure"
   - parameters: [
       { key: 'dte_min', label: 'Min DTE', value: '25 days', range: '15 – 45' },
       { key: 'dte_max', label: 'Max DTE', value: '50 days', range: '30 – 60' },
       { key: 'delta_max', label: 'Max short delta', value: '0.3 Δ', range: '0.1 – 0.45' },
       { key: 'iv_rank_min', label: 'Min IV rank', value: '40%', range: '0 – 100' },
       { key: 'exit_profit', label: 'Take profit at', value: '50%', range: '25 – 90' },
       { key: 'stop_loss', label: 'Stop loss (credit ×)', value: '2×', range: '1.5 – 4' }
     ]

   **weekly_grind:**
   - name: "Weekly Grind"
   - description: "5-16 DTE credit spreads, theta/gamma optimization"
   - dteRange: "5 – 16 DTE", structure: "Credit spread"
   - requirement: "Requires credit spread structure"
   - parameters: [
       { key: 'dte_min', label: 'Min DTE', value: '5 days', range: '1 – 10' },
       { key: 'dte_max', label: 'Max DTE', value: '16 days', range: '10 – 21' },
       { key: 'delta_max', label: 'Max short delta', value: '0.25 Δ', range: '0.1 – 0.35' },
       { key: 'iv_rank_min', label: 'Min IV rank', value: '30%', range: '0 – 100' },
       { key: 'exit_profit', label: 'Take profit at', value: '65%', range: '40 – 90' },
       { key: 'stop_loss', label: 'Stop loss (credit ×)', value: '1.5×', range: '1 – 3' }
     ]

   **trend_rider:**
   - name: "Trend Rider"
   - description: "25-65 DTE long calls on strong uptrends"
   - dteRange: "25 – 65 DTE", structure: "Long call"
   - requirement: "Requires bullish SMA alignment"
   - parameters: [
       { key: 'dte_min', label: 'Min DTE', value: '25 days', range: '15 – 45' },
       { key: 'dte_max', label: 'Max DTE', value: '65 days', range: '45 – 90' },
       { key: 'delta_target', label: 'Target delta', value: '0.60 Δ', range: '0.40 – 0.80' },
       { key: 'iv_rank_max', label: 'Max IV rank', value: '50%', range: '0 – 100' }
     ]

   **lottery_ticket:**
   - name: "Lottery Ticket"
   - description: "1-8 DTE deep OTM calls, asymmetric payout"
   - dteRange: "1 – 8 DTE", structure: "Deep OTM call"
   - requirement: "Catalyst present"
   - parameters: [
       { key: 'dte_max', label: 'Max DTE', value: '8 days', range: '1 – 14' },
       { key: 'delta_max', label: 'Max delta', value: '0.15 Δ', range: '0.05 – 0.25' },
       { key: 'payout_min', label: 'Min payout ratio', value: '5:1', range: '3 – 20' }
     ]

3. Strategy header card:
   - Border: 1px solid var(--border), border-radius 4px, padding 20px, margin-bottom 16px
   - Name: 18px bold monospace
   - Description: 11px muted, margin-bottom 12px
   - Metadata row: flex, gap 24px — DTE range, Structure, Requirement
     Each as stacked label (9px uppercase muted) / value (12px)

4. Parameters section:
   - Section label: "PARAMETERS" — 10px uppercase, letter-spacing 0.6px, muted,
     margin 16px 0 8px
   - Grid: display grid, grid-template-columns repeat(4, 1fr), gap 10px, margin-bottom 16px
   - Each parameter card: border 1px solid var(--border), border-radius 4px, padding 12px
     - Label: 9px uppercase, letter-spacing 0.4px, muted, margin-bottom 4px
     - Value: 18px bold
     - Range: 9px muted, margin-top 2px (e.g., "Range: 15 – 45")
   - Config % formatted as ##% (no decimals). Multipliers as #×.
   - If a strategy has fewer than 4 params in the last row, use repeat(2, 1fr) for that row

---

### Step 3 — Scoring Weights (OTA-370)

Add below parameters section in StrategyPage.jsx:

1. Section label: "SCORING WEIGHTS"

2. Container: border 1px solid var(--border), border-radius 4px, padding 14px,
   margin-bottom 16px

3. Add weights data to STRATEGY_DATA:

   **steady_paycheck weights:**
   - Theta Margin Ratio: 30%
   - Probability of Profit: 25%
   - Expected Value: 20%
   - Reward Risk: 15%
   - IV Rank: 10%

   **weekly_grind weights:**
   - Theta Gamma Ratio: 35%
   - Probability of Profit: 25%
   - Credit Width %: 20%
   - Expected Value: 15%
   - Liquidity: 5%

   **trend_rider weights:**
   - SMA Alignment Score: 30%
   - Delta Quality: 25%
   - Expected Value: 20%
   - IV Percentile Cost: 15%
   - Runway Score: 10%

   **lottery_ticket weights:**
   - Payout Ratio: 45%
   - Delta OTM Score: 25%
   - Bid Ask Tightness: 20%
   - Open Interest: 10%

4. Each weight row:
   - Flex row, align-items center, gap 8px, margin-bottom 10px (last: 0)
   - Metric name: 10px muted, width 140px
   - Bar background: flex 1, height 3px, var(--bg3), border-radius 2px
   - Bar fill: height 100%, border-radius 2px, width = weight%
     Use strategy-appropriate colors rotating through var(--teal), var(--purple),
     var(--blue), var(--amber) — or match the mockup colors
   - Weight percentage: 10px bold, width 30px, text-align right, var(--green)

---

### Step 4 — "Find trades" + Strategy Positions (OTA-371)

Add below scoring weights:

1. "Find trades →" + helper text:
   - Flex row, gap 10px, align-items center, margin-bottom 24px
   - Teal outlined button: "Find trades →"
   - onClick: navigate('/trades?strategy=' + key)
   - Helper: "Opens Trades page filtered to {name} parameters" (10px muted)

2. Strategy positions section:
   - Section label: "{Name} positions" (e.g., "Steady Paycheck positions")
   - Filter bar: var(--bg2) bg, 1px var(--border), border-radius 4px, padding 8px 14px
     - Status: Active (dropdown, 10px)
     - Type: All / Paper / Live (dropdown, 10px)
     - Position count + last refreshed (9px muted, margin-left auto)
     - "↻ Refresh all" (teal outlined small)

3. Import RefreshConfirmDialog from web/src/components/RefreshConfirmDialog.jsx
   (being built by Terminal 2 — if it doesn't exist yet, create an inline stub that
   renders the confirmation UI).
   Show dialog when Refresh all is clicked AND >1 position.
   Single position refresh: no confirmation.

4. Positions table (filtered to this strategy):
   - Fetch positions from existing positions endpoint, filter by strategy
   - Columns: [chevron] [Score] [Symbol] [Type] [Strike/Spread] [Expiration]
     [Premium] [Current] [P&L] [DTE] [Health]
   - Use ScoreCell for score column
   - Type column: "Paper" blue badge / "Live" green badge
   - Health: A-F letter badge (A/B green, C/D amber, F red)
   - P&L: ±##.00 (±##.00%), green positive, red negative

5. Below table: placeholder card
   - Border 1px var(--border), border-radius 4px, padding 20px, text-align center
   - Text: "Backtest data available in Phase 3.3" (11px muted)

---

### Commit Checkpoint

Verify:
- /trades?symbol=SPY shows real SMA chart (not placeholder)
- Strategy pills appear in Strategies column of trade results
- Trade detail expansion shows Sections A, B (with data), C, D, E in order
- /strategies/steady-paycheck shows header, parameters, weights, "Find trades", positions
- /strategies/weekly-grind renders with different data
- /strategies/trend-rider and /strategies/lottery-ticket render correctly
- "Find trades →" navigates to /trades?strategy=steady-paycheck
- Refresh all on positions shows confirmation when >1

Recommended QA level: 2 (multi-page changes)

Commit message: OTA-351 OTA-369 OTA-370 OTA-371 feat: sprint 2 fixes + strategy page full build
