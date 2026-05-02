---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-179 + OTA-177 — Dashboard Widgets: Current Positions Scorecard + Market Overview

**Jira:** OTA-179, OTA-177 | Parents: OTA-33 (Dashboard Sections Build), OTA-32 (Backend Data Caching)
**Priority:** Medium | **Labels:** options-domain, requirement
**Run after OTA-325/326 are validated (shared dashboard layout may be affected).**

---

## Before You Start

```bash
cat web/src/pages/Dashboard.jsx
cat web/src/components/QuoteBar.jsx
grep -rn "MarketOverview\|PositionsScorecard\|dashboard" web/src/pages/Dashboard.jsx
grep -n "GET /api/v1/positions\|market_overview\|cached" app/api/market_routes.py
cat web/src/api/client.js | grep -A3 "positions\|market\|overview"
```

Read all output before making any changes.

---

## Context

Two dashboard widget tickets are batched here. Both are read-only display widgets for
the Dashboard page.

---

## Widget A — OTA-179: Current Positions Scorecard

### Description

A dashboard section showing a live scorecard of all open positions. Item #46 in the
dashboard spec.

### Columns (in order)

| Column | Format | Notes |
|--------|--------|-------|
| Symbol | String | e.g. NVDA |
| Strategy | String | e.g. "Bull Put Spread" |
| Entry Date | `mm-dd-yyyy` | Use `formatDate()` |
| P&L | Float | No `$` prefix. Green if positive, red if negative |
| DTE Remaining | Integer | Days until expiry |
| Status | Pill badge | "Active" / "Watch" / "Critical" using health colors |

### Data Source

`GET /api/v1/positions?status=open` — returns open positions list.

If the endpoint doesn't exist yet or returns no data, render the widget with an empty
state: `"No open positions"` in muted text, same widget chrome.

### Widget Behavior

- Loads on Dashboard mount
- Refreshes every 60 seconds (or on manual refresh — add a small `↺` icon in the widget header)
- Clicking a row navigates to `/positions` with that symbol pre-selected (set `activeSymbol`)
- Status indicator colors: Active = `var(--green)`, Watch = `var(--amber)`, Critical = `var(--red)`

### Status Derivation (frontend logic)

If position has a health grade from the most recent assessment:
- A or B → "Active"
- C → "Watch"
- D or F → "Critical"

If no health grade, default to "Active".

---

## Widget B — OTA-177: Market Overview (Cached → Live)

### Description

Market overview widget showing key index/ETF values. Loads cached values immediately,
then replaces with live data. Item #43 in the dashboard spec.

### Symbols to Show

SPY, QQQ, IWM, VIX (use Schwab `get_quote()` for each)

### Fields per Symbol

| Field | Format |
|-------|--------|
| Symbol | Bold |
| Price | Decimal |
| Change | +/- decimal, green/red |
| Change % | +/- decimal%, green/red |

### Cache Behavior

1. On mount, immediately render cached values from `localStorage` key
   `"market_overview_cache"` if present (parse JSON, render instantly — zero flicker)
2. Simultaneously fire live Schwab quote calls
3. On live data return: replace rendered values, update cache with new values + timestamp
4. Show **"Last Updated mm-dd-yyyy hh:mm"** label below widget (use `formatDate()`)
5. Target: live data renders under 5 seconds

### Backend Endpoint (if not already present)

If `GET /api/v1/market/overview` doesn't exist, create it in `app/api/market_routes.py`:

```python
@router.get("/api/v1/market/overview")
async def get_market_overview(current_user = Depends(require_read)):
    provider = _get_provider()
    symbols = ["SPY", "QQQ", "IWM", "VIX"]
    quotes = {}
    for s in symbols:
        try:
            quotes[s] = await provider.get_quote(s)
        except Exception:
            quotes[s] = None
    return { "quotes": quotes, "fetched_at": datetime.now(timezone.utc).isoformat() }
```

---

## Dashboard Layout Rules

- Both widgets go in the main dashboard content area
- Use the existing widget card chrome (consistent with other dashboard sections)
- Widget headers: left-aligned title, right-aligned refresh icon
- Dark theme tokens throughout — no inline colors
- `var(--bg2)` is ONLY for filter bars, QuoteBar, pill badge backgrounds — NOT on widget
  card backgrounds or table rows

---

## Acceptance Criteria

### OTA-179
- [ ] Current Positions Scorecard renders on Dashboard with correct 6 columns
- [ ] Empty state shows `"No open positions"` when no data
- [ ] Row click navigates to Positions page with correct symbol
- [ ] Status pill uses correct color per health grade mapping
- [ ] Refreshes every 60 seconds
- [ ] Date format `mm-dd-yyyy` via `formatDate()`
- [ ] No `$` prefix

### OTA-177
- [ ] Market Overview widget renders SPY, QQQ, IWM, VIX
- [ ] Cached values load immediately on mount (no blank flash)
- [ ] Live data replaces cached values within 5 seconds
- [ ] "Last Updated mm-dd-yyyy hh:mm" label present
- [ ] Price change colored green/red correctly
- [ ] Cache is written to localStorage after live fetch

---

## House Style Rules

- No `$` prefix on any monetary value
- Dates: `mm-dd-yyyy` via `formatDate()`
- Dark theme tokens; `var(--bg2)` restricted to filter bars/QuoteBar/pill badges only
- Buttons: sized to content, fixed padding, never full-width
- Provider routing: `_get_provider()` always

---

## Commit Message

```
OTA-179 OTA-177 Add Current Positions Scorecard and Market Overview dashboard widgets
```
