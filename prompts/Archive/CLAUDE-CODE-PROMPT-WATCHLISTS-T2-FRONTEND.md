# Claude Code Prompt — Named Watchlists Frontend (T2)
# Ticket: OTA-446 (Frontend watchlist picker + management UI)
# Terminal: T2 (Frontend)
# Run AFTER T1 backend endpoints are deployed

---

## Step 0 — Read Context

```bash
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
```

Then read these files to understand the existing Security Strategies page:
- `web/src/pages/SecurityStrategiesPage.jsx` — the current scanner page
- `web/src/services/api.js` or equivalent — how API calls are made
- `web/src/components/` — shared component patterns

---

## Step 1 — API Service Layer

Add watchlist API functions to the existing API service file:

```javascript
// Watchlist API
export const getWatchlists = () => api.get('/api/v1/watchlists');
export const createWatchlist = (name) => api.post('/api/v1/watchlists', { name });
export const renameWatchlist = (id, name) => api.put(`/api/v1/watchlists/${id}`, { name });
export const deleteWatchlist = (id) => api.delete(`/api/v1/watchlists/${id}`);
export const getWatchlistSymbols = (id) => api.get(`/api/v1/watchlists/${id}/symbols`);
export const addWatchlistSymbol = (id, symbol) => api.post(`/api/v1/watchlists/${id}/symbols`, { symbol });
export const removeWatchlistSymbol = (id, symbol) => api.delete(`/api/v1/watchlists/${id}/symbols/${symbol}`);
export const getWatchlistSources = () => api.get('/api/v1/watchlists/sources');
```

---

## Step 2 — Replace Source Dropdown on SecurityStrategiesPage

The current page has a `<select>` with options: Watchlist, Positions, All.

Replace it with a **watchlist picker** that:

1. **On page load:** Calls `getWatchlistSources()` to get all watchlists + built-in sources
2. **Renders as:** A styled dropdown (not native `<select>`) showing:
   - User's watchlists (e.g., "My Watchlist (5)", "Dow 30 (30)") — name + symbol count
   - Divider line
   - "All Positions (14)" — built-in source, always present
   - Divider line
   - "+ New Watchlist" — action item at bottom
3. **Selection behavior:** Selecting a source stores the source ID in component state. "Scan now" passes this source to the scan endpoint.
4. **"+ New Watchlist" click:** Shows an inline text input in the dropdown area. Enter to create, Escape to cancel. After creation, auto-selects the new watchlist.

### Dropdown Styling
- Use dark theme CSS variables — `var(--bg1)` for dropdown bg, `var(--text1)` for text
- Dropdown opens below the trigger button
- Selected source shows in the trigger button: `[My Watchlist (5) ▾]`
- Hover: `var(--bg2)` background
- Active/selected: teal left border or teal text
- Symbol count in muted color `var(--text-muted)`

---

## Step 3 — Wire "Add Symbol" Input

The existing "Add symbol..." input on the right side of the filter bar currently does nothing.

Wire it to:
1. On submit (Enter key or click "Add"):
   - Call `addWatchlistSymbol(currentWatchlistId, symbol)`
   - If success: append the new symbol card to the grid (trigger a single-symbol scan, don't rescan everything)
   - If error (symbol not found): show a toast or inline error message in red below the input: "Symbol not found: XXXX"
   - Clear the input after successful add
2. **Disable when "All Positions" is selected** — you can't add symbols to a virtual list. Show tooltip: "Select a watchlist to add symbols"
3. Uppercase the input value before sending

---

## Step 4 — Symbol Card Remove Button

Each strategy scorecard in the scanner grid currently has no remove action.

Add a small `×` button:
- Position: top-right corner of the card
- Visibility: appears on card hover only (CSS `:hover`)
- Style: `var(--text-muted)` color, no background, 16px font size
- Hover state: `var(--text1)` color
- Click: calls `removeWatchlistSymbol(currentWatchlistId, symbol)`, then removes the card from the grid (no full rescan)
- **Hidden when "All Positions" is selected** — can't remove from virtual list

---

## Step 5 — Watchlist Management (Rename / Delete)

Add a `⋯` (three-dot) menu next to each watchlist name in the dropdown:

**Rename:**
- Click "Rename" → watchlist name becomes an editable text input inline
- Enter to save (calls `renameWatchlist(id, newName)`)
- Escape to cancel
- Update the dropdown display after rename

**Delete:**
- Click "Delete" → show confirmation: "Delete '{name}' and its {count} symbols?"
- Two buttons: "Delete" (red) and "Cancel"
- On confirm: calls `deleteWatchlist(id)`
- If deleted watchlist was selected, auto-select "My Watchlist" (default)
- **Hide delete option for default watchlist** (is_default = true)

---

## Step 6 — Auto-Scan on Source Change

When the user selects a different source from the dropdown:
- Do NOT auto-scan (expensive API call for 30+ symbols)
- Keep the "Scan now" button as the trigger
- Clear the previous scan results from the grid
- Show empty state: "Click 'Scan now' to analyze {name}"

---

## House Style Rules (Non-Negotiable)

- Dark theme CSS variables ONLY — never inline hex colors
- `var(--bg2)` restricted to filter bars, pill backgrounds — never card backgrounds
- Buttons sized to content with fixed padding, never full-width
- Buttons must have visible borders/backgrounds in default state
- No `$` prefix on monetary values (not applicable here but enforce habit)
- Dates in `mm-dd-yyyy` format via `formatDate()`

---

## Files to Create/Modify

**Create:**
- `web/src/components/WatchlistPicker.jsx` — the dropdown component
- `web/src/components/WatchlistPicker.css` — styles

**Modify:**
- `web/src/pages/SecurityStrategiesPage.jsx` — replace source `<select>` with WatchlistPicker, wire Add symbol input
- `web/src/services/api.js` (or equivalent) — add watchlist API functions
- Strategy scorecard card component — add × remove button on hover

---

## Acceptance Criteria

1. Source dropdown shows all user watchlists + "All Positions" with symbol counts
2. "+ New Watchlist" creates a new watchlist inline and auto-selects it
3. Selecting a watchlist and clicking "Scan now" scans those symbols
4. "Add symbol..." input adds to the currently selected watchlist and appends the card
5. Invalid symbol shows clear error message
6. Add symbol input disabled when "All Positions" is selected
7. × button on card hover removes symbol from current watchlist
8. ⋯ menu allows rename and delete (delete blocked for default watchlist)
9. Deleting selected watchlist auto-selects default
10. All styling follows dark theme CSS variables — no inline hex

## Commit Message
```
OTA-446: Named watchlists frontend — picker dropdown + management UI

- Replace source <select> with WatchlistPicker component
- Wire "Add symbol" input to watchlist API with validation
- Add × remove button on scorecard cards (hover only)
- Add watchlist rename/delete via ⋯ menu
- Auto-create default watchlist on first load
- Disable add/remove when "All Positions" selected
- Dark theme styling with CSS variables
```
