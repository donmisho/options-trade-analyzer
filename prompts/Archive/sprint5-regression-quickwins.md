---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 Regression Quick Wins

**Tickets:** OTA-416, OTA-417, OTA-418, OTA-419, OTA-420
**Commit prefix:** `OTA-416 OTA-417 OTA-418 OTA-419 OTA-420`

Read `claude_context/UI-GUIDANCE.md` before starting. Do each fix in order — test after each one.

---

## Fix 1 — Evaluate 422 (OTA-416) — JOURNEY BLOCKER

`TradesPage.jsx:869` — `evaluateStructured()` payload missing `sma_alignment`. Backend requires it, returns 422.

1. Read the evaluate payload construction around line 869
2. Read the backend schema: `grep -rn "sma_alignment" app/schemas/ app/routes/`
3. Add `sma_alignment` to the payload. Source it from the SMA chart state if available, otherwise default: `sma_alignment: smaAlignment || 'mixed'`
4. Test: expand a trade row, click Evaluate — should return a verdict instead of 422

## Fix 2 — StrategyPill colors (OTA-417)

`inferStrategies()` returns hyphenated keys (`trend-rider`) but `STRATEGY_COLORS` uses underscores (`trend_rider`).

1. In `StrategyPill.jsx`, normalize the key before color lookup:
   ```js
   const normalizedKey = (strategyKey || '').replace(/-/g, '_');
   ```
2. Or fix at the source in `inferStrategies()` — use underscores consistently
3. Test: Puts & Calls rows should show TR=blue, LT=purple pills

## Fix 3 — SymbolSearch stale dropdown (OTA-418)

`SymbolSearch.jsx:50-57` — detects `initialValue` change but never calls `setQuery()`.

1. In the useEffect that watches `initialValue`, add:
   ```js
   setQuery(initialValue || '');
   setShowDropdown(false);
   ```
2. Test: navigate from Scan card to `/trades?symbol=GEV` — search should show "GEV" with no dropdown

## Fix 4 — Auto-add to watchlist (OTA-419)

When user selects a symbol in SymbolSearch on TradesPage, auto-add to watchlist.

1. Find `handleSymbolSelect` in TradesPage
2. After setting the active symbol, call `addToWatchlist(symbol)` from AppContext (or equivalent)
3. Add dedup check — don't add if already in watchlist
4. Test: search for a new symbol on Trades, then go to Scan page and click "Scan now" — new symbol should appear

## Fix 5 — Exit scenarios condensed (OTA-420)

`buildExitScenarios()` generates 40+ rows. Default to showing only key rows.

1. Find the component that renders Section B (exit scenario table)
2. The rows already have an `exit_signal` field (MAX PROFIT, BREAKEVEN, STOP, TIME EXIT)
3. Add state: `const [showFullTable, setShowFullTable] = useState(false)`
4. Filter rows: `const displayRows = showFullTable ? allRows : allRows.filter(r => r.exit_signal)`
5. Always show the "Total expected value" footer row
6. Add toggle below the table:
   ```jsx
   <button className="btn-n btn-sm" onClick={() => setShowFullTable(!showFullTable)}>
     {showFullTable ? 'Show key exits ▲' : 'Show full analysis ▼'}
   </button>
   ```
7. Test: expand a trade — should show ~5 key rows. Click toggle — full table appears.

---

## Verification

After all 5 fixes:
1. Evaluate returns a verdict (not 422) ✓
2. Follow/Take Position buttons appear after evaluation ✓
3. Strategy pills show correct colors per strategy ✓
4. Navigating from Scan card populates symbol cleanly (no stale dropdown) ✓
5. Searching a symbol auto-adds to watchlist ✓
6. Exit scenarios show 5 key rows with expand toggle ✓
7. `cd web && npm run dev` — no build errors ✓
