# UI Overhaul Completion Plan

## Regression Fixes

Items restored after the left nav migration and expansion panel rebuild.

- ✅ **Fix 1 — Watchlist Symbol Click: Per-Page Routing**
  Watchlist click now checks current route. On Verticals/Puts & Calls: stays on page, re-runs analysis for new symbol (via `activeSymbol` effect in OptionsTerminal). On Positions: sets activeSymbol only. On Dashboard/Security Strategies: navigates to `/security-strategies/:symbol`.

- ✅ **Fix 2 — Sortable Column Headers**
  Column headers in the trade results table are clickable. Clicking sorts by that column (descending first). Clicking again reverses direction. Active column shows ▲/▼ indicator. Default sort: SCORE (composite_score) descending. Expanding a row then clicking a sort header collapses the row before sorting.

- ✅ **Fix 3 — Watchlist Toggle Button Positioning**
  Toggle button changed from `position: absolute` (overlapping the watchlist panel) to `position: fixed` with dynamic `right` value: 220px when panel is open, 0px when closed. State and localStorage persistence were already in place.
