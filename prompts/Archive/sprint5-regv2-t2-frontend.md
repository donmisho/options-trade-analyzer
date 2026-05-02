---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 Regression v2 — Terminal 2: Frontend Fixes

**Tickets:** OTA-424, OTA-425
**Commit prefix:** `OTA-424 OTA-425`

Read `claude_context/UI-GUIDANCE.md` before starting.

---

## Fix 1 — "Find trades →" empty page (OTA-424, P1)

StrategyPage navigates `/trades?strategy=X` with no symbol. TradesPage guard exits on empty symbol.

1. Read: `grep -rn "Find trades\|findTrades\|navigate.*trades" web/src/pages/StrategyPage.jsx`
2. Read: `grep -rn "useContext\|AppContext\|activeSymbol" web/src/pages/StrategyPage.jsx`
3. Fix: Import `useContext` + `AppContext` if not already. In the "Find trades →" onClick:
   ```js
   const { activeSymbol } = useContext(AppContext);
   const params = new URLSearchParams({ strategy: strategyKey });
   if (activeSymbol) params.set('symbol', activeSymbol);
   navigate(`/trades?${params.toString()}`);
   ```
4. If no activeSymbol is set, still navigate but show guidance. In TradesPage, when `strategy` param exists but no symbol: show an inline message above the sections: "Enter a symbol above to see {strategyName} trade candidates."

## Fix 2 — Evaluate guard for zero price (OTA-424, P1)

evaluateStructured can 422 if underlying price is 0 (not loaded yet).

1. Read: find the Evaluate button render in TradesPage or the expansion component
2. Add guard: disable the button when `!quote?.price || quote.price === 0`
3. Show tooltip or muted text: "Loading price data..." when disabled
4. This prevents the 422 entirely — the user can't click Evaluate until data is ready

## Fix 3 — SymbolSearch dropdown re-opens (OTA-424, P2)

The first fix attempt set `setQuery()` in the initialValue effect, but that triggers the search effect which re-opens the dropdown.

1. Read: `cat web/src/components/SymbolSearch.jsx`
2. Add a `isProgrammatic` ref:
   ```js
   const isProgrammatic = useRef(false);
   ```
3. In the initialValue useEffect:
   ```js
   useEffect(() => {
     if (initialValue) {
       isProgrammatic.current = true;
       setQuery(initialValue);
       setShowDropdown(false);
     }
   }, [initialValue]);
   ```
4. In the search/filter effect that opens the dropdown:
   ```js
   if (isProgrammatic.current) {
     isProgrammatic.current = false;
     return; // skip opening dropdown for programmatic changes
   }
   ```

## Fix 4 — Wire real SMA values to evaluate (OTA-424, P2)

sma_alignment in the evaluate payload is hardcoded to N/A values. SmaPanel computes the real alignment but it never reaches the evaluate handler.

1. Read: `grep -rn "sma_alignment\|smaAlignment\|makeTradeHandlers" web/src/pages/TradesPage.jsx`
2. Find where `smaAlignment` state is set (likely from the SMA chart component callback)
3. Find where `makeTradeHandlers` is called — it builds the evaluate handler
4. Pass `smaAlignment` as a parameter to `makeTradeHandlers` and use it in the payload:
   ```js
   sma_alignment: smaAlignment || { alignment: 'mixed', sma_8: 'N/A', sma_21: 'N/A', sma_50: 'N/A' }
   ```

## Fix 5 — Add symbol input on Scan page (OTA-425)

No UI to add symbols to the watchlist. Add inline on the Scan page filter bar.

1. In SecurityStrategiesPage.jsx, in the filter bar, add after the existing controls:
   ```jsx
   <input
     type="text"
     placeholder="Add symbol..."
     value={newSymbol}
     onChange={e => setNewSymbol(e.target.value.toUpperCase())}
     onKeyDown={e => e.key === 'Enter' && handleAddSymbol()}
     style={{ width: '120px' }}
     className="fu-input"
   />
   <button className="btn-n btn-sm" onClick={handleAddSymbol}>Add</button>
   ```
2. `handleAddSymbol`: call `addToWatchlist(newSymbol)` from AppContext, clear input, show success Toast
3. Add dedup check — if symbol already in watchlist, show info Toast "Already in scan list"

## Fix 6 — Cleanup (OTA-425)

1. Replace `alert()` in Layout.jsx with Toast:
   ```
   grep -rn "alert(" web/src/components/Layout.jsx
   ```
   Replace with `showToast({ type: 'error', message: '...' })`. Import useToast if Toast exists, or use a simple inline notification div.

2. Delete dead files:
   ```
   rm web/src/components/AskClaudePanel_v2.jsx
   rm web/src/components/Watchlist.jsx
   ```
   Search for and remove any remaining imports: `grep -rn "AskClaudePanel_v2\|Watchlist" web/src/`

3. Remove inline RefreshConfirmDialog from StrategyPage.jsx (lines ~155-203). Use the shared `web/src/components/RefreshConfirmDialog.jsx` import instead.

---

## Verification

After all fixes:
1. "Find trades →" with activeSymbol → Trades loads with data ✓
2. "Find trades →" without activeSymbol → guidance message shown ✓
3. Evaluate button disabled while price loads, enabled once ready ✓
4. Scan card navigation → no dropdown re-open ✓
5. Evaluate payload shows real SMA values (check network tab) ✓
6. "Add symbol" input on Scan page works ✓
7. No alert() calls remain ✓
8. No dead files on disk ✓
9. `cd web && npm run dev` — no build errors ✓
