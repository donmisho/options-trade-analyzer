# Claude Code Prompt — OTA-310 OTA-311
## Positions Live Dashboard Widget

### Tickets
- OTA-310: Create `positions_live` widget type with real-time market data
- OTA-311: Register `positions_live` in the dashboard widget registry with default layout

---

### Before You Start

```bash
cat web/src/pages/DashboardPage.jsx
grep -rn "widget_registry\|widgetRegistry\|registerWidget\|widget_type" web/src/ | grep -v node_modules | head -30
cat web/src/context/AppContext.jsx | grep -n "position\|symbol\|schwab\|price" | head -30
grep -rn "dashboard_layouts\|pnl_by_strategy\|market_overview" web/src/ | grep -v node_modules | head -20
```

Read all before writing. The `positions_live` widget must follow the existing widget registry pattern exactly — do not invent a new pattern.

---

## Part 1 — OTA-310: `positions_live` Widget Component

**File:** `web/src/components/widgets/PositionsLiveWidget.jsx`

**What it shows:** Real-time market data for every symbol with an active position.

**Columns per symbol row:**
| Symbol | Price | Change | Change % |
|--------|-------|--------|----------|
| AAPL | 187.42 | +1.83 | +0.99% |

- **Symbol**: Emerald Teal `#00C896`, bold, clickable
- **Clicking a symbol**: Navigate to `/security-strategies/{symbol}` (Security Strategies page)
- **Price**: `##.00` format, no `$`
- **Change**: with sign, `##.00` format — green `#00C896` if positive, Danger `#F85149` if negative
- **Change %**: `##.00%` with sign — same color logic

**Data source:**
- Fetch distinct active position symbols from `GET /api/v1/positions/symbols` (built in OTA-306)
- For each symbol, get current quote via the Schwab polling mechanism already in the app (look at how other components get live price data — match that pattern)
- Auto-maintained: symbols appear/disappear as positions are followed/closed
- No duplicates — one row per unique symbol regardless of how many positions exist for it

**Refresh behavior:**
- Prices update on the same Schwab polling interval used elsewhere in the app
- Following a new position → symbol appears on next refresh
- Closing the last position on a symbol → symbol disappears on next refresh

**Empty state:**
- If no active positions: show muted text `"No active positions"` — no blank widget

**Widget background:** `#0D1117`

---

## Part 2 — OTA-311: Register in Widget Registry

**Follow the existing widget registry pattern exactly.** Read the existing registry before writing this.

Register `positions_live` with:
- Widget type key: `positions_live`
- Component: `PositionsLiveWidget`
- Default grid position: `x: 0, y: 0` (top-left), `w: 2` (2 columns wide), `h: 3` (3 rows tall)
- Layout is **fixed** (`isDraggable: false`) — do not change this

**Persist to `dashboard_layouts` table:**
- Follow the same persistence pattern as the existing `pnl_by_strategy` widget
- If `dashboard_layouts` has no row for the current user, create a default layout that includes `positions_live` in the default slot
- If a layout already exists, add `positions_live` only if it's not already registered (idempotent)

**Acceptance criteria:**
- Widget appears on Dashboard on first load after deployment
- Widget position persists across sessions (reload and confirm it's in the same place)
- Widget coexists with existing `pnl_by_strategy` widget (no overlap, no displacement)

---

### House Style
- No `$` prefix on any value
- Prices: `##.00`
- Change %: `##.00%`
- Symbol links: Emerald Teal, never underlined like a web link — styled as navigation

---

### After Building

```bash
npm run lint
```

Manually verify:
1. Open Dashboard — confirm `positions_live` widget appears
2. Confirm symbols with active positions appear with price and change data
3. Click a symbol — confirm navigation to Security Strategies page for that symbol
4. Refresh the page — confirm widget is still in the same position

---

### Commit Message
```
OTA-310 OTA-311 feat: positions_live dashboard widget with real-time market data
```
