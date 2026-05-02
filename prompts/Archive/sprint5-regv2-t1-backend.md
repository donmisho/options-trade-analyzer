---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 Regression v2 — Terminal 1: Backend Fixes

**Tickets:** OTA-422, OTA-423
**Commit prefix:** `OTA-422 OTA-423`

---

## Fix 1 — Enrich ScorecardResponse (OTA-422)

Scan cards show "—" for prices and NEUTRAL for all signals because the scorecard endpoint doesn't return quote data or SMA signal.

1. Read the scorecard endpoint:
   ```
   cat app/routes/analysis_routes.py
   ```
   Find the POST /api/v1/analyze/scorecard handler and its response schema.

2. Read the existing quote + SMA logic:
   ```
   grep -rn "getQuote\|get_quote\|sma_signal\|sma_alignment\|compute_sma" app/
   ```

3. In the scorecard handler, AFTER computing strategy scores, add:
   - Call the quote provider to get current price data: `{ price, change, change_percent, volume, rel_volume }`
   - Compute or retrieve SMA signal alignment (the same logic used on the Trades page SMA panel)
   - Add both to the response:
     ```python
     response = {
         "symbol": symbol,
         "underlying_price": ...,  # already exists
         "quote": {
             "price": quote.price,
             "change": quote.change,
             "change_percent": quote.change_percent,
             "volume": quote.volume,
             "rel_volume": quote.rel_volume
         },
         "sma_signal": sma_result.get("alignment", "mixed"),
         "strategies": [...]  # already exists
     }
     ```

4. Update the Pydantic response schema if one exists to include the new fields as Optional.

5. Test: `curl -X POST http://localhost:8000/api/v1/analyze/scorecard -H "Content-Type: application/json" -d '{"symbol":"AAPL"}'` — response should include quote and sma_signal.

## Fix 2 — Consolidate watchlist to backend only (OTA-423)

Watchlist has split-brain: Scan page calls backend API, AppContext uses localStorage. Backend is source of truth.

1. Read current state:
   ```
   grep -rn "watchlist" web/src/context/AppContext.jsx
   grep -rn "watchlist" web/src/api/client.js
   cat app/routes/watchlist_routes.py
   ```

2. Verify backend endpoints exist:
   - `GET /api/v1/watchlist` — returns symbol list
   - `POST /api/v1/watchlist` — adds a symbol
   - `DELETE /api/v1/watchlist/{symbol}` — removes a symbol
   If any are missing, create them (simple CRUD against the watchlist table).

3. In AppContext.jsx:
   - Remove localStorage read/write for watchlist
   - Replace with backend API calls: `getWatchlist()`, `addToWatchlist(symbol)`, `removeFromWatchlist(symbol)`
   - Keep React state as in-memory cache, hydrate from backend on mount
   - One-time migration: on mount, if localStorage has watchlist items AND backend is empty, POST each to backend, then clear localStorage

4. In SecurityStrategiesPage.jsx:
   - Empty-state check should use the same backend-sourced state (not a separate localStorage check)

5. Test: add a symbol via Trades page search → verify it appears in Scan page on next "Scan now"

---

## Verification

1. Scan page cards show real prices (not "—")
2. Scan page cards show correct signal badges (not all NEUTRAL)
3. Adding a symbol on Trades auto-adds to backend watchlist
4. Scan page empty state works correctly when backend watchlist is empty
5. No localStorage watchlist references remain in AppContext
