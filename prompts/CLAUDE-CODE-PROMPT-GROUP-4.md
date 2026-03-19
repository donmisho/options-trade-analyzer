# Claude Code Prompt — UI Overhaul Group 4
## Left Navigation Migration

---

## Before you write a single line of code, answer this question:

**Has any part of this migration already been completed?**

Check the following and report what you find — one sentence of evidence per item:

1. `cat web/src/components/Layout.jsx` — look for a left rail (fixed-width column, ~220px) containing nav items stacked vertically. If it exists with vertical nav items, the layout shell may already be done.

2. `cat web/src/App.jsx` — look for how the Layout component is used. Check whether the current layout wraps all routes inside a left-rail shell. If `<Layout>` wraps the router and the nav items are vertical, the migration may be partially done.

3. `cat web/src/components/Header.jsx` — look at what this file still does. If it only contains the Schwab indicator and user/sign-out (no nav tabs), the nav items have already moved.

4. `cat web/src/components/Watchlist.jsx` — look for a collapsible toggle. If it has an `isOpen` / `collapsed` state and a toggle button, the sidebar-to-panel conversion may be done.

For each item: **"Already done"**, **"Partially done — [what's missing]"**, or **"Not done"** with one sentence of evidence. Then proceed only with what's missing.

---

## Context

You are working on Options Analyzer, a FastAPI + React options trading analysis app.

Read these files before making any changes. Do not rely on memory from a previous session — cat the actual files:

```
cat web/src/App.jsx
cat web/src/components/Layout.jsx
cat web/src/components/Header.jsx
cat web/src/components/Watchlist.jsx
cat web/src/pages/OptionsTerminal.jsx
cat UI-DECISIONS.md
cat CLAUDE.md
cat UI-OVERHAUL-COMPLETION-PLAN.md
```

**Why this session is its own isolated prompt:** The left nav migration touches the root layout and every page. It has no backend work, no API changes, and no scoring logic. It is purely structural. Keeping it separate from Groups 3 and 4 means that if anything goes wrong with the layout, you can isolate the cause without wondering if a scoring change caused it.

**The testing prerequisite:** Groups 1, 2, 3, and 4 must all be passing before this session runs. If you are in doubt, run the testing checklist from Prompt 3 first and confirm everything is green.

---

## Scope of This Session

Complete Group 5 of the UI Overhaul Completion Plan: the full left nav migration.

---

## L-1 — New Layout.jsx with Left Rail

### Layout structure

Replace the current `Layout.jsx` with a new version that uses a two-column flex structure:

```
┌─────────────────────────────────────────────────────┐
│  LEFT RAIL (220px fixed)  │  MAIN CONTENT (flex: 1) │
│                           │                         │
│  [Logo / App Name]        │  [Page content here]    │
│                           │                         │
│  Dashboard                │                         │
│  Security Strategies      │                         │
│  Verticals                │                         │
│  Puts & Calls             │                         │
│  Positions                │                         │
│                           │                         │
│  ──────────────────────   │                         │
│  ● Schwab Connected        │                         │
│  ⚙ Settings               │                         │
│  [User] Sign out          │                         │
└─────────────────────────────────────────────────────┘
```

### CSS spec

```css
/* Root wrapper */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #0d1117;  /* --bg */
}

/* Left rail */
.nav-rail {
  width: 220px;
  min-width: 220px;   /* never shrinks */
  height: 100vh;
  background: #0d1117;
  border-right: 1px solid #30363d;  /* --border */
  display: flex;
  flex-direction: column;
  padding: 0;
  position: fixed;   /* does not scroll with page content */
  top: 0;
  left: 0;
  z-index: 100;
}

/* Main content area */
.main-content {
  margin-left: 220px;   /* offset for fixed rail */
  flex: 1;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}
```

### Rail: Top section — logo

```jsx
<div className="rail-logo">
  {/* App name or logo mark */}
  <span style={{ fontSize: '13px', fontWeight: 700, color: '#2dd4bf', letterSpacing: '0.4px', textTransform: 'uppercase' }}>
    Options Analyzer
  </span>
</div>
```

Styles:
```css
.rail-logo {
  padding: 20px 16px 16px 16px;
  border-bottom: 1px solid #21262d;  /* --bg3 */
  cursor: pointer;  /* navigates to Dashboard on click */
}
```

### Rail: Nav items

Each nav item is a full-width clickable row. Use `NavLink` from `react-router-dom` for automatic active state detection.

```jsx
<nav className="rail-nav">
  <NavLink to="/dashboard"            className={navClass}>Dashboard</NavLink>
  <NavLink to="/security-strategies"  className={navClass}>Security Strategies</NavLink>
  <NavLink to="/verticals"            className={navClass}>Verticals</NavLink>
  <NavLink to="/puts-and-calls"       className={navClass}>Puts & Calls</NavLink>
  <NavLink to="/positions"            className={navClass}>Positions</NavLink>
</nav>
```

`navClass` is a function that returns the appropriate className based on `isActive`:

```css
/* Base nav item */
.nav-item {
  display: block;
  padding: 10px 16px;
  font-size: 12px;
  font-family: monospace;
  color: #8b949e;          /* --muted, inactive */
  text-decoration: none;
  border-left: 3px solid transparent;
  transition: color 0.15s, background 0.15s;
}

/* Active state */
.nav-item.active {
  color: #2dd4bf;                       /* --teal */
  border-left-color: #2dd4bf;
  background: rgba(45, 212, 191, 0.08);
}

/* Hover state (non-active) */
.nav-item:not(.active):hover {
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.04);
}
```

### Rail: Bottom section

Push to the bottom of the rail with `margin-top: auto` on the bottom container.

```jsx
<div className="rail-bottom">
  <SchwabStatusIndicator />   {/* existing component — move here */}
  <button className="rail-icon-btn" onClick={openSettings}>⚙</button>
  <div className="rail-user">
    <span className="rail-username">{username}</span>
    <button className="rail-signout" onClick={signOut}>Sign out</button>
  </div>
</div>
```

```css
.rail-bottom {
  margin-top: auto;
  padding: 12px 16px;
  border-top: 1px solid #21262d;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rail-username {
  font-size: 11px;
  color: #8b949e;
  font-family: monospace;
}

.rail-signout {
  font-size: 11px;
  font-family: monospace;
  color: #8b949e;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  text-align: left;
}

.rail-signout:hover {
  color: #f87171;  /* --red — sign out is a destructive action */
}
```

---

## L-2 — Convert Watchlist from Fixed Sidebar to Collapsible Panel

**Current state:** The Watchlist renders as a fixed right column alongside the main content area.

**New state:** The Watchlist is a collapsible panel that overlays or sits within the main content area. It does not occupy permanent horizontal space.

### Implementation

Add a toggle button to the top of the main content area (visible on all pages that show the Watchlist):

```jsx
<button className="watchlist-toggle" onClick={() => setWatchlistOpen(o => !o)}>
  {watchlistOpen ? '◀ Hide Watchlist' : '▶ Watchlist'}
</button>
```

```css
.watchlist-toggle {
  font-size: 10px;
  font-family: monospace;
  color: #8b949e;
  background: transparent;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  width: auto;   /* never stretch */
}

.watchlist-toggle:hover {
  color: #2dd4bf;
  border-color: rgba(45, 212, 191, 0.4);
}
```

### Watchlist panel when open

When `watchlistOpen` is true, the Watchlist renders as a fixed panel on the right edge of the main content area:

```css
.watchlist-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 220px;
  height: 100vh;
  background: #161b22;   /* --bg2 */
  border-left: 1px solid #30363d;
  z-index: 90;
  overflow-y: auto;
  padding-top: 16px;
}
```

When the Watchlist panel is open, the main content area should not reflow — the panel overlays it. This is simpler than a push layout and avoids expensive re-renders on toggle.

### State persistence

Persist the Watchlist open/closed state in `localStorage` so it survives page reloads:

```javascript
const [watchlistOpen, setWatchlistOpen] = useState(() => {
  return localStorage.getItem('watchlistOpen') !== 'false';  // default: open
});

useEffect(() => {
  localStorage.setItem('watchlistOpen', watchlistOpen);
}, [watchlistOpen]);
```

Default: open (true). A first-time user sees the watchlist.

### Clicking a symbol — does the panel auto-close?

**No.** Clicking a symbol in the Watchlist navigates to Security Strategies for that symbol and keeps the Watchlist panel open. The user may want to pick another symbol immediately. They close the panel manually with the toggle.

---

## L-3 — All Five Pages Tested in Left-Nav Layout

After L-1 and L-2 are built, verify each page renders correctly inside the new layout.

Work through each route and confirm:

1. **Dashboard** (`/dashboard`) — page fills the main content area, no horizontal overflow
2. **Security Strategies** (`/security-strategies`) — QuoteBar spans full content width; chart below it; no layout breakage
3. **Verticals** (`/verticals`) — trade table renders correctly; expansion panel opens without overlapping the rail; verdict card doesn't clip
4. **Puts & Calls** (`/puts-and-calls`) — same as Verticals; dimmed non-applicable strategies visible
5. **Positions** (`/positions`) — page renders (even if mostly empty/placeholder)

**Check specifically:**
- The nav rail active state is correct for each page (only the current page's item is highlighted)
- The Schwab Connected indicator in the rail footer reflects the real connection state
- The Watchlist toggle button is visible on pages that show analysis (Verticals, Puts & Calls, Security Strategies)
- Clicking a watchlist symbol navigates to Security Strategies and sets the active symbol correctly
- No horizontal scrollbar appears on any page at normal desktop width (1280px+)

---

## L-4 — Update Documentation

**This step is mandatory. Do not skip it.**

After the layout migration is visually confirmed working, update two documentation files:

### Update `UI-DECISIONS.md`

Replace the entire **Navigation Bar** section (the top-level section about tab order and nav rules) with a new **Navigation Rail** section:

```markdown
## Navigation Rail

### Layout
The app uses a fixed left navigation rail (220px wide). The top horizontal nav bar has been retired.

### Rail Structure (top to bottom)
- App logo / name — clicking navigates to Dashboard
- Nav items (vertically stacked): Dashboard · Security Strategies · Verticals · Puts & Calls · Positions
- Bottom: Schwab Connected indicator · Settings gear · User / Sign out

### Nav Item Order
Dashboard | Security Strategies | Verticals | Puts & Calls | Positions

### Rules
- Exactly these five items. No more, no less.
- Strategy tabs (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket) do NOT appear in the rail. They are scoring lenses inside pages only.
- "Security Strategies" was named deliberately. Do not shorten to "Security".
- Active item: 3px solid teal left border (#2dd4bf) + teal text + rgba(45,212,191,0.08) background.
- Inactive items: muted gray (#8b949e), no border, no background.

### Watchlist Panel
The Watchlist is a collapsible overlay panel triggered by a toggle button in the main content area.
Default state: open. State persists in localStorage.
Clicking a symbol: navigates to Security Strategies, panel stays open.
```

### Update `CLAUDE.md`

Find the section that describes the navigation bar (look for "Header", "nav tabs", or "tab order"). Update it to describe the left rail. The key facts to update:
- Layout is left rail (220px fixed), not top horizontal tabs
- Active state is teal left border, not teal bottom border
- Watchlist is a collapsible panel, not a fixed right column

---

## Definition of Done for This Session

Before ending the session, confirm all of the following:

- [ ] Left rail is visible on all five pages with correct width, dark background, and border-right
- [ ] Nav items are stacked vertically with correct active state (teal left border + teal text) on current page
- [ ] Navigating between pages: active state moves correctly
- [ ] App logo/name at top of rail — clicking navigates to Dashboard
- [ ] Schwab Connected indicator visible at bottom of rail
- [ ] Settings and Sign out at bottom of rail
- [ ] Watchlist toggle button visible on Verticals, Puts & Calls, Security Strategies pages
- [ ] Watchlist panel opens and closes when toggled
- [ ] Watchlist open/closed state persists on page reload
- [ ] Clicking a watchlist symbol navigates correctly, panel stays open
- [ ] All five pages render correctly inside the new layout (no overflow, no clipping)
- [ ] No horizontal scrollbar at 1280px viewport width
- [ ] Expansion panels on Verticals and Puts & Calls still open and render correctly (regression)
- [ ] Verdict cards do not clip or overflow behind the rail
- [ ] `UI-DECISIONS.md` Navigation Rail section updated
- [ ] `CLAUDE.md` nav description updated

Update `UI-OVERHAUL-COMPLETION-PLAN.md` — change L-1, L-2, and L-3 from 🔲 to ✅.

---

## After This Session — You Are Ready for Phase 2.9

When Group 5 is complete and all five pages are rendering correctly in the left-nav layout, the UI overhaul is done and the manual testing gate (Group 6 in the completion plan) can be run in full.

After the Group 6 gate passes, proceed to `PARALLEL-BUILD-GUIDE.md` Session 1 to begin Phase 2.9.
