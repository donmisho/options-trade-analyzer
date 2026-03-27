# Claude Code Prompt — OTA-304 OTA-306 OTA-307
## Symbol Type-Ahead Search Component

### Tickets
- OTA-304: Build SymbolSearch component with two-tier results and company names
- OTA-306: Fetch active position symbols endpoint for Tier 1 highlighting
- OTA-307: Symbol selection triggers immediate analysis — remove Analyze button

---

### Before You Start

```bash
grep -rn "Analyze\|analyzeSymbol\|onAnalyze\|handleAnalyze" web/src/ | grep -v node_modules | head -40
grep -rn "watchlist\|symbol\|SymbolInput\|SymbolSearch" web/src/ | grep -v node_modules | head -40
cat web/src/context/AppContext.jsx | head -80
cat app/routers/position_routes.py | grep -n "def\|route\|@router" | head -30
```

Read all before writing. You need to know the current symbol entry mechanism on each page before replacing it.

---

## Part 1 — OTA-306: Active Position Symbols Endpoint (backend — do this first)

**New endpoint:**
```
GET /api/v1/positions/symbols
```

**Returns:**
```json
[
  { "symbol": "AAPL", "position_count": 2 },
  { "symbol": "MSFT", "position_count": 1 }
]
```

Only include symbols with **active** positions (not closed/historical).
Deduplicated — if a symbol has 3 active positions, return count = 3 but only one entry.
Empty array if no active positions.

Add to `position_routes.py`. No auth requirement beyond standard Tier 1.

---

## Part 2 — OTA-304: SymbolSearch Component (frontend)

**File:** `web/src/components/SymbolSearch.jsx`

**Two-tier type-ahead:**
- **Tier 1** (symbols with active positions): Bold, Emerald Teal `#00C896`, position count badge (e.g. `AAPL — Apple Inc. — 2 positions`)
- **Tier 2** (all market symbols): Muted color, no badge (e.g. `LLY — Eli Lilly & Co.`)

**Behavior:**
- Typing opens dropdown
- Arrow keys navigate, Enter selects, Escape closes
- On selection: call `onSelect(symbol)` prop and close dropdown
- Page load: show placeholder text (the `placeholder` prop), **not** a stale symbol
- Company names fetched from Schwab or a static lookup — use whatever company name source is already in the codebase; if none exists, use a lightweight static map for common tickers

**Props (framework-portable pattern):**
```js
{
  onSelect: Function,          // called with selected symbol string
  placeholder: string,         // e.g. "Search symbol..."
  searchFn: Function,          // async (query) => [{ symbol, companyName }] — injected, not hardcoded
  positionSymbols: Array,      // [{ symbol, position_count }] from AppContext
  initialValue: string | null  // optional — pre-populate field
}
```

**Do not hardcode the search source** — accept `searchFn` as a prop so this component works in non-options contexts (framework portability label on this ticket).

**Fetch position symbols** in `AppContext`:
- On app load, call `GET /api/v1/positions/symbols`
- Store result in context as `positionSymbols`
- Re-fetch when positions change (listen for a `positions_updated` event or re-fetch after Follow/Close actions)
- Pass `positionSymbols` into `SymbolSearch` from whatever page uses it

**Acceptance criteria:**
- Typing `M` shows MSFT — Microsoft (teal, bold) above META — Meta Platforms (muted) if MSFT has active positions
- Typing `LLY` shows LLY — Eli Lilly & Co. in muted text
- Arrow keys navigate, Enter selects, Escape closes
- Page load shows placeholder text only — not a stale previous symbol

---

## Part 3 — OTA-307: Remove Analyze Button + Wire Auto-Analysis

**Rule:** When a symbol is selected from `SymbolSearch`, run analysis immediately. No Analyze button.

**Changes to make on each of these three pages:**

### Verticals page
- Replace the current symbol input + Analyze button with `<SymbolSearch onSelect={handleSymbolSelect} ... />`
- `handleSymbolSelect(symbol)`: set state, immediately fire the verticals analysis request
- Loading state appears while analysis is in flight
- Results update when analysis completes

### Puts & Calls page
- Same pattern — replace input + button with `SymbolSearch`
- On select: immediately load options for that symbol

### Security Strategies page
- Same pattern
- On select: immediately load the strategy scorecard for that symbol

**Grep first to find the exact button and handler on each page:**
```bash
grep -rn "Analyze\|<button\|onClick.*analyz" web/src/pages/ | grep -v node_modules
```

**Do not remove the Analyze button from any other page** — only Verticals, Puts & Calls, and Security Strategies as specified.

**Acceptance criteria:**
- Selecting AAPL on Verticals immediately loads AAPL verticals — no button click required
- Selecting MSFT on Puts & Calls immediately loads MSFT options
- Selecting LLY on Security Strategies immediately loads LLY scorecard
- No Analyze button visible on any of the three pages after this change
- Loading state is visible between selection and results rendering

---

### House Style
- `SymbolSearch` dropdown background: `#0D1117`
- Tier 1 text: Emerald Teal `#00C896`, bold
- Tier 2 text: muted (use existing muted CSS variable)
- Dropdown border: subtle, use existing border CSS variable
- No `$` anywhere

---

### After Building

```bash
npm run lint
```

Manually verify:
1. Open Verticals — confirm no Analyze button, type `AAPL`, select it, confirm analysis fires automatically
2. Open Puts & Calls — same check with `MSFT`
3. Open Security Strategies — same check with `LLY`
4. Confirm Tier 1 highlighting: if AAPL has active positions, it appears teal with count badge

---

### Commit Message
```
OTA-304 OTA-306 OTA-307 feat: SymbolSearch component with auto-analysis, remove Analyze button
```
