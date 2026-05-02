# Claude Code Prompt — UI Overhaul Part 2
## Left Navigation Migration

---

## Prerequisite

**This session assumes Part 1 is complete.** Before starting, verify:

```bash
# Check Part 1 completion signals
grep -n "useToast\|ToastContext\|showToast" web/src/components/Toast.jsx 2>/dev/null | head -5
grep -n "trade_structure\|tradeStructure" web/src/strategy-configs/steady-paycheck.config.js 2>/dev/null
grep -n "auto.*collapse\|selectedStrategy.*null\|setVerdict.*null" web/src/pages/OptionsTerminal.jsx 2>/dev/null | head -5
```

If Toast.jsx does not exist or `tradeStructure` is missing from strategy configs, stop and complete Part 1 first.

---

## Before you do anything else

**Check whether the left nav is already done.**

```bash
# 1. Check if Layout.jsx has a left rail
grep -n "left.*rail\|rail.*width\|220\|sidebar.*nav\|nav.*sidebar\|flex.*row.*layout" web/src/components/Layout.jsx 2>/dev/null | head -20

# 2. Check if Header.jsx still contains the nav tabs
grep -n "Dashboard\|Verticals\|Positions\|nav.*tab\|activeTab" web/src/components/Header.jsx 2>/dev/null | head -20

# 3. Check if Watchlist is a collapsible panel or still a fixed sidebar
grep -n "collapsible\|collapsed\|toggle.*watch\|watchlist.*open\|isOpen" web/src/components/Watchlist.jsx 2>/dev/null | head -20

# 4. Check App.jsx for current layout structure
grep -n "Layout\|Header\|Watchlist\|flex\|grid" web/src/App.jsx 2>/dev/null | head -30

# 5. Check if UI-DECISIONS.md still describes top nav or has been updated
grep -n "left.*nav\|top.*nav\|horizontal.*nav\|vertical.*nav\|rail" UI-DECISIONS.md 2>/dev/null | head -10
```

If the left nav is already in place and all five pages are rendering correctly inside it, report that and stop — this work is done.

---

## Context

Read these files in full before writing any code:

```bash
cat UI-DECISIONS.md
cat CLAUDE.md
cat web/src/App.jsx
cat web/src/components/Layout.jsx
cat web/src/components/Header.jsx
cat web/src/components/Watchlist.jsx
cat web/src/context/AppContext.jsx
```

Pay close attention to:
- Current routing structure in `App.jsx`
- What `Layout.jsx` renders today (does it wrap pages?)
- How `Header.jsx` handles the active tab state
- How `Watchlist.jsx` is positioned relative to the main content

The current nav (from UI-DECISIONS.md): `Dashboard | Security Strategies | Verticals | Puts & Calls | Positions`

---

## Scope of This Session

Build the left navigation rail layout. This is a one-time structural migration. All five pages reflow into the new layout. No new pages are created.

---

## Step 1 — Update Layout.jsx

Replace the current Layout with a two-column flex structure:

```
┌────────────────────────────────────────────┐
│  Left Rail (220px fixed)  │  Main Content  │
│  (see spec below)         │  (flex-grow:1) │
└────────────────────────────────────────────┘
```

**Left rail spec:**

```css
/* Rail container */
width: 220px;
min-width: 220px;
height: 100vh;
position: fixed;   /* does not scroll with content */
top: 0;
left: 0;
background: #0d1117;  /* var(--bg) */
border-right: 1px solid #30363d;  /* var(--border) */
display: flex;
flex-direction: column;
z-index: 100;
```

**Rail sections (top to bottom):**

1. **Logo area** — top 16px padding. App name or wordmark. Clicking navigates to `/dashboard`. Use teal (`#2dd4bf`) for the brand text if using text only.

2. **Nav items** — flex-grow: 1. Vertically stacked. Each nav item:
   ```css
   /* Item container */
   display: flex;
   align-items: center;
   padding: 10px 16px;
   font-family: monospace;
   font-size: 12px;
   cursor: pointer;
   text-decoration: none;
   color: #8b949e;   /* inactive */
   border-left: 3px solid transparent;  /* inactive */
   ```
   
   **Active state** (when route matches):
   ```css
   color: #2dd4bf;
   border-left: 3px solid #2dd4bf;
   background: rgba(45,212,191,0.08);
   ```
   
   **Hover state** (inactive only):
   ```css
   color: #e6edf3;
   background: rgba(255,255,255,0.04);
   ```

3. **Bottom area** — `margin-top: auto`. Contains:
   - Schwab connected indicator: small dot (green `#4ade80` if connected, red `#f87171` if not) + `"Schwab Connected"` or `"Schwab Disconnected"` text in 10px muted
   - Settings gear icon (`⚙`) — 14px muted, clicking navigates to settings (if route exists) or opens ConfigDrawer
   - User avatar or username + sign out — 10px muted

**Nav items — exact five, in this order:**
```
Dashboard
Security Strategies
Verticals
Puts & Calls
Positions
```

These are the only nav items. No strategy names (Steady Paycheck etc.) in the rail.

**Main content area:**
```css
margin-left: 220px;  /* push right by rail width */
min-height: 100vh;
flex: 1;
overflow-x: hidden;
```

---

## Step 2 — Strip Nav from Header.jsx

`Header.jsx` currently contains the nav tabs. After the rail is built:

1. Remove the tab row from `Header.jsx`
2. Keep the Header component if it is used for the QuoteBar or a page-level title bar — do not delete it if other pages depend on it
3. If Header only served as a nav container and nothing else, it can be retired. Check all imports before removing.

---

## Step 3 — Convert Watchlist to Collapsible Panel

The Watchlist currently occupies a fixed right column. In the left-nav layout, there is no longer a three-column structure (nav | content | watchlist). The Watchlist becomes a collapsible panel within the main content area.

**Implementation:**

1. Add a toggle button in the main content area — top-right of the content zone. Label: `"Watchlist ▶"` when collapsed, `"Watchlist ▼"` when expanded. Style: neutral outlined button (see UI-DECISIONS.md Button Standards).

2. When expanded, Watchlist renders below the toggle button or as an inline panel at the right edge of the content area. Width: 200px. Style unchanged from current Watchlist design.

3. Persist open/closed state in `localStorage` with key `"watchlist_open"`. Default: `true` (expanded on first load).

4. When a symbol is clicked in the Watchlist, the existing behavior is unchanged: set `activeSymbol` and navigate to `/security-strategies/:symbol`.

---

## Step 4 — Test All Five Pages

After the layout migration, manually verify each page renders correctly:

**Dashboard** (`/dashboard`):
- Content fills the full width to the right of the rail
- No horizontal overflow
- Rail shows "Dashboard" as active

**Security Strategies** (`/security-strategies`):
- QuoteBar spans the full content width
- SMA chart renders below QuoteBar
- Rail shows "Security Strategies" as active

**Verticals** (`/verticals` or existing route):
- 4-column expansion panel does not overflow horizontally
- QuoteBar spans full width
- Rail shows "Verticals" as active

**Puts & Calls** (`/puts-calls` or existing route):
- Same checks as Verticals
- Rail shows "Puts & Calls" as active

**Positions** (`/positions`):
- If PositionsPage exists: renders in content area
- If not yet built: shows an empty state placeholder
- Rail shows "Positions" as active

Check: Watchlist toggle works. Clicking a Watchlist symbol navigates to Security Strategies and the rail highlights "Security Strategies".

---

## Step 5 — Update Documentation

After all pages pass the visual check, update both documentation files:

### UI-DECISIONS.md — Navigation Bar section

Replace the existing "Navigation Bar" section with:

```markdown
## Navigation Bar

### Layout: Left Rail

The navigation is a fixed-width left rail (220px). It does not scroll with the page.
The main content area occupies the remaining width (`100% minus 220px`).

### Nav Items (top to bottom in the rail)
- Dashboard
- Security Strategies
- Verticals
- Puts & Calls
- Positions

### Active State
- 3px solid teal left border (#2dd4bf)
- Teal text (#2dd4bf)
- Background: rgba(45,212,191,0.08)

### Inactive State
- No border (3px solid transparent)
- Muted gray text (#8b949e)
- No background

### Bottom of Rail
- Schwab connection indicator (colored dot + label)
- Settings gear icon
- User / sign out

### Rules
- Exactly these five items. No more, no less.
- Strategy scoring lenses (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket)
  do NOT appear in the rail. They are scoring lenses inside pages only.
- "Security Strategies" was named deliberately. Do not shorten to "Security".
- The Watchlist is a collapsible panel within the main content area,
  not a fixed right column.
```

### CLAUDE.md — UI Decisions section

Update the "Key decisions summarized" bullet for the nav bar:

Replace: `- Nav bar: Dashboard | Security Strategies | Verticals | Puts & Calls | Positions`

With: `- Nav: Left rail (220px fixed). Items top-to-bottom: Dashboard · Security Strategies · Verticals · Puts & Calls · Positions. Watchlist is a collapsible panel in the content area, not a column.`

---

## Delivery Checklist

Confirm each item before finishing:

- [ ] `Layout.jsx` — left rail (220px) + main content area structure
- [ ] All five nav items render in the rail with correct active/inactive states
- [ ] Logo / brand name at top of rail, links to Dashboard
- [ ] Schwab indicator + settings + sign out at bottom of rail
- [ ] `Header.jsx` — nav tabs removed (or file retired if appropriate)
- [ ] `Watchlist.jsx` — collapsible panel with toggle button; localStorage persistence
- [ ] Dashboard page renders correctly in new layout
- [ ] Security Strategies page renders correctly in new layout
- [ ] Verticals page renders correctly in new layout (4-col panel fits within content width)
- [ ] Puts & Calls page renders correctly in new layout
- [ ] Positions page renders correctly (or shows placeholder) in new layout
- [ ] `UI-DECISIONS.md` Navigation Bar section updated to reflect left rail spec
- [ ] `CLAUDE.md` nav bullet updated

---

## Do Not

- Do not modify any page content, scoring logic, or API calls
- Do not change the color system, button styles, or typography
- Do not add any new pages or routes — this session is layout only
- Do not add strategy names (Steady Paycheck etc.) to the nav rail under any circumstances
- Do not change the active route behavior — clicking a nav item navigates exactly as before
- Do not start Phase 2.9 work after finishing this session — the testing gate (Group 6 in the Completion Plan) must be run first
