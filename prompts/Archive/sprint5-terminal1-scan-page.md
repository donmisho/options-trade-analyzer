---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 — Terminal 1: Scan Page v3 Rebuild

**Tickets:** OTA-401, OTA-402, OTA-403, OTA-404, OTA-405
**Commit prefix:** `OTA-401 OTA-402 OTA-403 OTA-404 OTA-405`

Read `claude_context/UI-GUIDANCE.md` Part 10 Screen 1, Part 11, and Part 3a before starting. Reference `ota-experience-mockups-v3.html` Screen 1 for the visual spec.

## House style (enforce everywhere)
- No `$` prefix on monetary values. Format `##.00` via `.toFixed(2)`
- Dates: `mm-dd-yyyy` via `formatDate()`
- Scores: 0-100, `##.00`, green 70+ / amber 40-69 / red 0-39
- Probabilities: `##.00%`
- IV rank: `##.00%`
- Config %: `##%` (no decimals)
- Dark theme CSS variables only — never inline hex
- `var(--bg2)` only on filter bars, QuoteBar, pill badge backgrounds
- Buttons: auto-width, never full-width
- Strategy pills: SP (amber), WG (green), TR (blue), LT (purple)

---

## Step 1 — Gut SecurityStrategiesPage (OTA-401)

1. `cat web/src/pages/SecurityStrategiesPage.jsx` — understand current structure
2. Remove from the component:
   - `QuoteBar` import and render
   - `CandlestickChart` / `ComposedChart` / SMA chart + all chart state (`candles`, `smaData`, `chartRange`, `smaPeriods`)
   - `StrategyScorecard` import and render with checkboxes
   - `TradeEvaluationCard` import and render
   - `EvalSkeleton` / loading states for evaluation
   - `handleEvaluate` function and evaluation state
   - `SymbolSearch` input (single-symbol entry)
   - All single-symbol state: `quote`, `activeSymbol` from this page, `selectedKeys`, `evaluations`, `evalLoading`
3. Keep: component function, export, route, page layout wrapper, page title "Security Strategies", any reusable CSS imports
4. Verify: `cd web && npm run dev` — no build errors, `/security-strategies` shows empty shell

## Step 2 — Build ScanCard component (OTA-402)

1. Create `web/src/components/ScanCard.jsx`
2. Card structure per mockup:
   ```
   ┌─────────────────────────────────────┐
   │ AAPL  [BULLISH]  [NEW]             │
   │ 178.50 · +2.30 (+1.31%) · 45.2M   │
   │                                     │
   │ Steady Paycheck ████████░░  82.00  │
   │ Weekly Grind    █████░░░░░  55.00  │
   │ Trend Rider     ███████░░░  75.00  │
   │ Lottery Ticket  ███░░░░░░░  33.00  │
   │                                     │
   │ Clean uptrend · IV rank 28.00%     │
   └─────────────────────────────────────┘
   ```
3. Props: `{ symbol, price, change, changePercent, volume, relVolume, signal, isNew, strategies: [{key, label, score, best_trade}], signalSummary, ivRank, onClick }`
4. Signal badge: BULLISH (green bg), BEARISH (red bg), MIXED (amber bg), NEUTRAL (muted)
5. NEW badge: teal bg, 8px text
6. Score bars: 3px height, strategy color fill, score ##.00 with threshold coloring
7. Strategy names: 10px muted, 90px width
8. Signal summary: 10px italic muted, IV rank as ##.00%
9. Card: `border: 1px solid var(--border)`, hover: `border-color: rgba(45,212,191,0.3)`, `cursor: pointer`
10. Also add the card grid to SecurityStrategiesPage: `display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;`

## Step 3 — Build filter bar (OTA-403)

1. Add filter bar above the card grid in SecurityStrategiesPage
2. Controls:
   - Source dropdown: Watchlist / Positions / All (default: Watchlist)
   - Signal dropdown: All / Bullish / Bearish / Mixed
   - Min score: number input (0-100)
   - Sort: Score (high first) / Symbol (A-Z) / Signal
   - "Scan now" button (teal outlined, `btn-t` class)
3. Filter bar: `background: var(--bg2); padding: 12px 16px; border-radius: 4px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;`
4. Filters apply client-side to the scan results state array
5. "Scan now" triggers the orchestration in Step 4

## Step 4 — Wire scan orchestration (OTA-404)

1. In `web/src/api/client.js`, verify `getWatchlist()` and `getStrategyScorecard(symbol)` exist
2. In SecurityStrategiesPage, wire "Scan now":
   ```
   handleScan:
     1. Set scanning = true, results = []
     2. Fetch symbol list based on Source filter:
        - Watchlist: getWatchlist()
        - Positions: getPositions() → extract unique symbols
        - All: merge both, deduplicate
     3. Fan out scorecard calls with max 5 concurrent:
        - Use a semaphore pattern or chunked Promise.allSettled
        - As each resolves, append to results state (progressive render)
     4. Set scanning = false when all complete
   ```
3. While scanning: show skeleton cards (pulsing border, muted text "Loading...")
4. Progress: "Scanning 3 of 10 symbols..." above the grid
5. Failed symbols: show card with red border and "Failed to load" text
6. Empty state (no watchlist): centered text "Add symbols to your watchlist to scan" with muted styling

## Step 5 — Wire card click + cleanup (OTA-405)

1. Wire `ScanCard` `onClick` → `navigate(\`/trades?symbol=\${symbol}\`)` using `useNavigate()`
2. Verify TradesPage reads `symbol` from URL query params and loads that symbol
3. Delete dead files:
   - `rm web/src/pages/SecurityDashboard.jsx`
   - `rm web/src/components/SecurityDashboard.jsx`
4. `grep -r "SecurityDashboard" web/src/` — remove any remaining imports
5. Verify no build errors

## Verification

After all 5 steps:
1. Navigate to `/security-strategies` — page shows filter bar + empty state
2. Add symbols to watchlist if needed, click "Scan now" — cards render progressively
3. Verify score bars, signal badges, IV rank formatting
4. Click a card — navigates to `/trades?symbol=X` and loads that symbol
5. No build errors, no console errors
