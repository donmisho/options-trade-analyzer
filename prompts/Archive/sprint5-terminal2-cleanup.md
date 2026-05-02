---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 — Terminal 2: Deprecated Code Removal + Trade Detail & Layout Cleanup

**Tickets:** OTA-406, OTA-407
**Commit prefix:** `OTA-406 OTA-407`

Read `claude_context/UI-GUIDANCE.md` Parts 7, 8, 10, 11 before starting.

## House style (enforce everywhere)
- No `$` prefix on monetary values. Format `##.00` via `.toFixed(2)`
- Dates: `mm-dd-yyyy` via `formatDate()`
- Scores: 0-100, `##.00`, green 70+ / amber 40-69 / red 0-39
- Dark theme CSS variables only — never inline hex
- Buttons: auto-width, never full-width
- Trade type badges: clean title case display names, bull=green bear=red

---

## Step 1 — Delete deprecated files (OTA-406)

1. Read each file first to confirm it's safe to delete:
   ```
   cat web/src/components/AskClaudePanel.jsx | head -5
   cat web/src/pages/FavoritesPage.jsx | head -5
   cat web/src/pages/OptionsTerminal.jsx | head -5
   ```

2. Delete deprecated files:
   ```
   rm web/src/components/AskClaudePanel.jsx
   rm web/src/pages/FavoritesPage.jsx
   rm web/src/pages/OptionsTerminal.jsx
   ```

3. Search for and remove all imports:
   ```
   grep -rn "AskClaudePanel" web/src/
   grep -rn "FavoritesPage" web/src/
   grep -rn "OptionsTerminal" web/src/
   ```
   Remove every import, lazy load, and route reference found.

4. In `web/src/App.jsx`, add redirect for /favorites:
   ```jsx
   <Route path="/favorites" element={<Navigate to="/positions" replace />} />
   ```
   Import `Navigate` from react-router-dom if not already imported.

5. Verify: `cd web && npm run dev` — no build errors

## Step 2 — Remove ProbabilityMatrix from trade detail (OTA-407 part 1)

The v3 mockup shows trade detail as A → B → C → E. No Section D (ProbabilityMatrix) in the display. The backend endpoint stays — it feeds scoring. Only remove the frontend render.

1. `cat web/src/pages/TradesPage.jsx` — find where ProbabilityMatrix is rendered in the expansion
2. Also check: `grep -rn "ProbabilityMatrix" web/src/` to find all references
3. In the trade detail expansion (TradeDetailExpansion component or inline in TradesPage):
   - Remove the `<ProbabilityMatrix>` component render
   - Remove the `getProbabilityMatrix()` API call that fires on row expansion
   - Remove any `matrixData` state variable
   - Keep the import of ProbabilityMatrix.jsx file itself (don't delete the file — Positions page might use it later)
4. Verify the expansion now shows: Section A (trade header) → Section B (exit scenarios) → Section C (outcome summary) → Section E (Claude's Read)
5. No build errors

## Step 3 — Remove Watchlist sidebar panel (OTA-407 part 2)

The Watchlist sidebar panel on the right side of the main content area must be removed. Positions page is the watchlist now.

1. `cat web/src/components/Layout.jsx` — find the Watchlist panel render
2. Remove from Layout.jsx:
   - The Watchlist component import
   - The collapsible panel that renders the Watchlist (likely a `<div>` with conditional display)
   - The toggle button/icon that shows/hides the Watchlist
   - Any Watchlist-related state: `showWatchlist`, `watchlistOpen`, etc.
3. DO NOT delete `web/src/components/Watchlist.jsx` itself — the Scan page may reference `getWatchlist()` from the API client
4. The main content area should now occupy the full width (no sidebar)
5. Verify: no build errors, no visual regression on any page

## Step 4 — Fix trade type badge display names (OTA-407 part 3)

1. `cat web/src/components/TradeTypeBadge.jsx` — check current formatting
2. The component should convert raw enum values to clean title case:
   ```
   BEAR_PUT_DEBIT    → "Bear Put Debit"
   BULL_PUT_CREDIT   → "Bull Put Credit"
   BEAR_CALL_CREDIT  → "Bear Call Credit"
   BULL_CALL_DEBIT   → "Bull Call Debit"
   LONG_CALL         → "Long Call"
   LONG_PUT          → "Long Put"
   ```
3. Implementation: replace underscores with spaces, apply title case:
   ```js
   const formatTypeName = (raw) =>
     raw.replace(/_/g, ' ')
        .toLowerCase()
        .replace(/\b\w/g, c => c.toUpperCase());
   ```
4. Badge coloring: bull trades (BULL_*) = green (`var(--green)`), bear trades (BEAR_*) = red (`var(--red)`), long call = blue, long put = red
5. Also check TradesPage Section A (trade header) — the type badge there should use the same formatted name
6. Verify: expand a trade row, confirm badge shows clean name with correct color

## Verification

After all steps:
1. `/security-strategies` renders (empty shell or with scan cards if T1 is done)
2. `/favorites` redirects to `/positions`
3. No AskClaudePanel, FavoritesPage, or OptionsTerminal imports remain
4. Expanding a trade row shows A → B → C → E (no ProbabilityMatrix)
5. No Watchlist sidebar panel visible on any page
6. Trade type badges show clean title case names
7. No build errors, no console errors
