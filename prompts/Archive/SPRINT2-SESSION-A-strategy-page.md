OTA-359 OTA-360 OTA-361

## Sprint 2 Session A — Strategy Page Build
### Run in Claude Code Terminal 1 (parallel with Session B — Positions Page)

Read UI-GUIDANCE.md (the ENTIRE file) and review ota-experience-mockups-v3.html Screen 3 (Steady Paycheck example) before starting. Also read architecture-plan.md for the strategy scoring tables (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket weight/metric definitions).

This session ONLY modifies web/src/pages/StrategyPage.jsx and any new strategy config files. Do NOT modify PositionsPage.jsx — that's being built in the parallel session.

---

### Step 1 — Strategy Header (OTA-359)

Replace the placeholder in web/src/pages/StrategyPage.jsx with the full strategy page layout:

1. Read :key from useParams (e.g., "steady-paycheck"). Map to strategy config.
2. Strategy header card (border 1px solid var(--border), border-radius 4px, padding 20px, margin-bottom 16px):
   - Strategy name: 18px bold
   - Description: 11px muted, margin-bottom 12px (e.g., "25-50 DTE credit spreads, high IV rank, income focus")
   - Metadata row (flex, gap 24px): DTE range, Structure, Requirement — each as stacked label/value pair (same .qf styling as QuoteBar fields)

3. Define strategy configs for all 4 strategies. Use web/src/strategy-configs/ if they exist, otherwise define inline. Data from architecture-plan.md:

   **Steady Paycheck:** 25-50 DTE credit spreads, high IV rank, income focus. DTE 25-50, Structure: Credit spread, Requirement: Requires credit spread structure.
   **Weekly Grind:** 5-16 DTE credit spreads, high theta-gamma ratio, fast decay. DTE 5-16, Structure: Credit spread, Requirement: Requires credit spread structure.
   **Trend Rider:** 25-65 DTE long calls on strong trends, SMA alignment. DTE 25-65, Structure: Long call, Requirement: Requires bullish SMA alignment.
   **Lottery Ticket:** 1-8 DTE deep OTM calls, asymmetric payout. DTE 1-8, Structure: Long call (deep OTM), Requirement: High payout ratio on small move.

**Verify:** All 4 strategy URLs (/strategies/steady-paycheck, /weekly-grind, /trend-rider, /lottery-ticket) show correct strategy-specific headers.

---

### Step 2 — Parameters + Weights + Find Trades (OTA-360)

Add to StrategyPage.jsx below the header:

1. Section label "PARAMETERS" (10px uppercase, letter-spacing 0.6px, muted)
2. Parameter card grid (display grid, 4 columns, gap 10px, margin-bottom 16px):
   Each card: border 1px solid var(--border), border-radius 4px, padding 12px
   - Label: 9px uppercase, letter-spacing 0.4px, muted, margin-bottom 4px
   - Value: 18px bold
   - Range note: 9px muted, margin-top 2px (e.g., "Range: 15 – 45")

   Parameters per strategy from architecture-plan.md:

   **Steady Paycheck:** Min DTE (25 days, range 15-45), Max DTE (50 days, range 30-60), Max short delta (0.3 Δ, range 0.1-0.45), Min IV rank (40%, range 0-100), Take profit at (50%, range 25-90), Stop loss (2×, range 1.5-4)
   **Weekly Grind:** Min DTE (5 days, range 3-10), Max DTE (16 days, range 10-21), Max short delta (0.25 Δ, range 0.1-0.40), Min credit width (15%, range 5-30), Take profit at (65%, range 40-90), Stop loss (2×, range 1.5-3)
   **Trend Rider:** Min DTE (25 days, range 15-40), Max DTE (65 days, range 45-90), Target delta (0.50-0.70 Δ), Min SMA alignment (0.5, range 0-1), Take profit at (100%, range 50-200), Time stop (10 days before expiry)
   **Lottery Ticket:** Min DTE (1 day, range 0-3), Max DTE (8 days, range 5-14), Max delta (0.25 Δ, range 0.05-0.30), Min payout ratio (5×, range 3-20), Max premium (50.00, range 10-200)

   Format: configuration % as ##% (no decimals), multipliers as #×, deltas as 0.# Δ

3. Section label "SCORING WEIGHTS" below parameters
4. Weights display (border 1px solid var(--border), border-radius 4px, padding 14px):
   Each weight as a horizontal bar row: metric name (10px muted, width 140px), bar bg (flex 1, 3px, var(--bg3)), fill (height 100%, strategy color from STRATEGY_COLORS), percentage (10px bold, 30px, right-aligned)

   Weights from architecture-plan.md:
   **Steady Paycheck:** Theta Margin Ratio 30%, Probability of Profit 25%, Expected Value 20%, Reward Risk 15%, IV Rank 10%
   **Weekly Grind:** Theta Gamma Ratio 35%, Probability of Profit 25%, Credit Width % 20%, Expected Value 15%, Liquidity 5%
   **Trend Rider:** SMA Alignment Score 30%, Delta Quality 25%, Expected Value 20%, IV Percentile Cost 15%, Runway Score 10%
   **Lottery Ticket:** Payout Ratio 45%, Delta OTM Score 25%, Bid Ask Tightness 20%, Open Interest 10%

   Import STRATEGY_COLORS from StrategyPill.jsx. Use each strategy's color for bar fill.

5. "Find trades →" button (teal outlined) + helper text (10px muted: "Opens Trades page filtered to {strategy} parameters"). onClick → navigate to /trades?strategy={key}

**Verify:** Parameter cards in 4-column grid with correct values. Scoring weight bars with correct percentages and strategy colors. "Find trades →" navigates correctly.

---

### Step 3 — Filtered Positions (OTA-361)

Add filtered positions list to StrategyPage.jsx below the "Find trades" button:

1. Section label: "{Strategy Name} positions" (e.g., "Steady Paycheck positions")
2. Filter bar (var(--bg2) bg): Status dropdown (Active/All/Closed), Type dropdown (All/Paper/Live), position count + last refreshed timestamp (9px muted), "↻ Refresh all" button (teal outlined small)
3. Positions table using existing positions data from GET /api/v1/positions?strategy={key}. Column order: chevron, Score (ScoreCell), Symbol (bold), Type badge (Paper=blue, Live=green), Strike/Spread, Expiration (formatDate), Premium, Current, P&L (±##.00 with sign and color), DTE, Health (grade badge A-F)
4. Cost guardrail: "Refresh all" on >1 position shows confirmation dialog per UI-GUIDANCE.md Part 9:
   - Overlay: rgba(0,0,0,0.6), 1px var(--border), border-radius 6px, 20px padding
   - Title: "Refresh {n} positions?" (12px bold)
   - Body: explanation text (10px #c9d1d9, line-height 1.5)
   - Actions: "Confirm refresh" (teal outlined) + "Cancel" (neutral outlined)
   Single-position refresh runs without confirmation.
5. Use existing position data and components. Health grade badges from PositionHealthBadge.jsx if it exists.

**Verify:** Strategy positions section renders below "Find trades". Filtered to current strategy. Cost guardrail works. All formatting correct.

---

### Commit

Commit message: OTA-359 OTA-360 OTA-361 feat: strategy page — header, parameters, weights, find trades, filtered positions

Recommended QA level: 1 (targeted — StrategyPage.jsx only)
