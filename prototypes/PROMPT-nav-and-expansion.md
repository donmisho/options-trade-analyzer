# Claude Code Prompt — Nav Simplification + Terminal Expansion + QuoteBar Unification

Read `CLAUDE.md`, `architecture-plan.md`, and `PHASE-2.9.md` before making any changes.
Then read the actual current content of every file you are about to modify before touching it.

---

## What This Prompt Does

Four related changes that must be delivered together:

1. Remove strategy tabs from top-level navigation
2. Unify QuoteBar as a single shared component used identically on every page
3. Update OptionsTerminal (Verticals) trade row expansion to show StrategyScorecard
4. Update OptionsTerminal (Puts & Calls) trade row expansion to show StrategyScorecard
   with strategy filtering by trade structure

---

## Change 1 — Nav Simplification

### File: `web/src/components/Header.jsx`

Remove the following strategy tabs from the navigation completely:
- Steady Paycheck
- Weekly Grind
- Trend Rider
- Lottery Ticket
- Directional Compare (if present as a top-level tab)

The nav bar after this change must contain exactly:
**Dashboard | Verticals | Puts & Calls | Positions**

Plus the existing Settings gear icon and Schwab Connected indicator on the right.

The strategy config files (`steady-paycheck.config.js`, `weekly-grind.config.js`,
`trend-rider.config.js`, `lottery-ticket.config.js`) are NOT deleted. They stay in
`web/src/strategy-configs/` — they now feed the StrategyScorecard component instead
of driving their own pages.

Any routes in `App.jsx` that pointed to standalone strategy pages should be removed
or redirected to SecurityDashboard. Do not leave dead routes.

---

## Change 2 — QuoteBar Unification

### Context

There are currently two different header implementations:
- SecurityDashboard has a minimal inline header (price, day range, 52w range, volume only)
- OptionsTerminal has a fuller inline header (symbol, signal badge, last analyzed,
  price, chg, chg%, day range, 52w range, volume, rel vol)

Neither is complete. Both are missing earnings date and dividend date.

### File: `web/src/components/QuoteBar.jsx`

This is the SINGLE source of truth for the symbol header. All other inline header
implementations must be removed and replaced with this component.

Ensure QuoteBar renders ALL of the following fields in this order:

| Field | Format | Notes |
|-------|--------|-------|
| Symbol | Large bold | e.g. AMZN |
| SIGNAL badge | BULLISH / BEARISH / MIXED | Color: green/red/yellow |
| Last Analyzed | MM/DD/YYYY HH:MM | Only shown after first analysis |
| Price | Decimal | e.g. 207.38 |
| CHG | +/- decimal | Red if negative, green if positive |
| CHG % | +/- decimal% | Red if negative, green if positive |
| Day Range | Low – High | |
| 52W Range | Low – High | |
| Volume | Formatted | e.g. 35.6M |
| Rel Vol | Decimal + x | e.g. 0.8x |
| Earnings Date | MM/DD/YYYY | Only render if data exists AND within 60 days. Amber highlight if within 14 days. |
| Dividend Date | MM/DD/YYYY | Only render if data exists AND within 60 days. |

Rules:
- No `$` prefix on any value — house style applies everywhere
- Earnings and dividend: if the data field is null or empty, do not render
  the field at all — no dash, no placeholder, no "N/A"
- Earnings within 14 days: wrap in an amber highlight badge — this is a
  risk signal that matters for options positions
- QuoteBar accepts these props:
  ```javascript
  {
    symbol: string,
    quote: object,        // price, chg, chgPct, dayLow, dayHigh, volume, relVolume
    smaSignal: string,    // 'BULLISH' | 'BEARISH' | 'MIXED'
    lastAnalyzed: string, // ISO timestamp or null
    fundamentals: object  // earningsDate, dividendDate — both optional
  }
  ```

### Files to update after fixing QuoteBar:

**`web/src/pages/SecurityDashboard.jsx`**
- Remove any inline header implementation
- Import and render `<QuoteBar />` with all available props
- Pass `fundamentals` data if the SecurityDashboard fetches it; if not, add
  a call to fetch fundamentals for the active symbol on load

**`web/src/pages/OptionsTerminal.jsx`**
- Remove any inline header implementation
- Import and render `<QuoteBar />` with all available props
- Pass `smaSignal` from the existing SMA/directional engine result
- Pass `lastAnalyzed` from the analysis run timestamp

After this change, searching the codebase for any component other than `QuoteBar.jsx`
that renders price + day range + 52w range inline should return zero results.

---

## Change 3 — OptionsTerminal Expansion (Verticals)

### Context

The Verticals page (`OptionsTerminal` with `activeStrategy='verticals'`) shows a
ranked list of vertical spread trades. Each row is expandable (Stage 2). The expansion
currently shows the math matrix and payoff diagram.

### File: `web/src/pages/OptionsTerminal.jsx`

In the Stage 2 row expansion for vertical spread trades, add the following BELOW
the existing math matrix and payoff diagram:

**Section: Strategy Fit**

Render `<StrategyScorecard />` in a compact read-only mode showing how this specific
trade scores across all four strategies.

For vertical spread trades, all four strategies are potentially compatible.
Filter using the strategy's `trade_structure` field from `strategy_definitions.py`
(or equivalent frontend config):
- Show strategies where `trade_structure === 'credit_spread'` OR `trade_structure === 'long_option'`
- For vertical spreads specifically: show ALL four strategies

Pass the expanded trade's data to the scorecard so scores reflect this specific
trade, not a generic symbol-level score.

Below the scorecard, render:
- Checkboxes to select which strategies to evaluate (pre-checked on highest scorer)
- **"Evaluate with Claude"** button — disabled until at least one strategy selected

When Evaluate is clicked:
- Call `POST /api/v1/evaluate/structured` with the trade pre-populated
- Render `<TradeEvaluationCard />` for each returned evaluation, inline in the expansion
- Each card includes Follow and Take Position buttons wired to position endpoints

---

## Change 4 — OptionsTerminal Expansion (Puts & Calls)

### Context

The Puts & Calls page (`OptionsTerminal` with `activeStrategy='long-calls'` or similar)
shows ranked naked call and put trades. Same expansion pattern as Verticals but with
strategy filtering.

### File: `web/src/pages/OptionsTerminal.jsx`

In the Stage 2 row expansion for naked call/put trades, add the same Strategy Fit
section as Change 3, BUT with strategy filtering:

**Only show strategies where `trade_structure === 'long_option'`**

From the initial four strategies:
- ✅ Trend Rider (`trade_structure: 'long_option'`) — show
- ✅ Lottery Ticket (`trade_structure: 'long_option'`) — show
- ❌ Steady Paycheck (`trade_structure: 'credit_spread'`) — hide
- ❌ Weekly Grind (`trade_structure: 'credit_spread'`) — hide

The scorecard for a naked call/put expansion therefore shows exactly 2 strategies.
The filtering must be driven by `trade_structure` in the strategy config, not
hardcoded strategy names. Adding a new `long_option` strategy in the future should
automatically include it here without code changes.

---

## Validation Checklist

After completing all four changes, verify:

- [ ] Nav bar shows exactly: Dashboard | Verticals | Puts & Calls | Positions
- [ ] No strategy tabs (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket) in nav
- [ ] No dead routes in App.jsx
- [ ] SecurityDashboard header is identical to OptionsTerminal header — same component
- [ ] Both headers show earnings date when within 60 days
- [ ] Both headers show dividend date when within 60 days
- [ ] Earnings within 14 days shows amber highlight on both pages
- [ ] No `$` prefix anywhere in either header
- [ ] Expanding a vertical spread trade shows all 4 strategy scores
- [ ] Expanding a naked call/put trade shows exactly 2 strategy scores (Trend Rider, Lottery Ticket)
- [ ] Strategy filtering is driven by `trade_structure` field, not hardcoded names
- [ ] Evaluate button present in both expansions, disabled until strategy selected
- [ ] TradeEvaluationCard renders inline after evaluation
- [ ] Follow and Take Position buttons on evaluation cards work
- [ ] Strategy config files still exist in `strategy-configs/` (not deleted)
