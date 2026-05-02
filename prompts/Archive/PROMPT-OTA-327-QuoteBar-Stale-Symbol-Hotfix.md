---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-327 — Hotfix: QuoteBar Shows Stale Symbol on Initial Load

**Jira:** OTA-327 | Parent: OTA-19 (DEV Housekeeping)
**Priority:** Medium | **Labels:** bug, frontend, hotfix

---

## Before You Start

```bash
cat web/src/context/AppContext.jsx
cat web/src/components/QuoteBar.jsx
```

Read both files completely before touching anything.

---

## Problem

On fresh page load, `activeSymbol` is initialized from `localStorage.getItem('activeSymbol')`.
This causes QuoteBar to render with stale data (e.g. PLTR from a prior session) before the
user has selected anything.

Per the watchlist retirement decision (`UI-DECISIONS.md`), `activeSymbol` is **session-only
state** — it must NOT persist across browser sessions.

---

## Fix Required

### `web/src/context/AppContext.jsx`

1. Find the `activeSymbol` state initialization. It currently looks like:
   ```js
   const [activeSymbol, setActiveSymbol] = useState(
     localStorage.getItem('activeSymbol') || null
   );
   ```
2. Change it to:
   ```js
   const [activeSymbol, setActiveSymbol] = useState(null);
   ```
3. **Do NOT remove** any other `localStorage.getItem` calls. Only remove the `activeSymbol`
   read on initialization.
4. **Do NOT remove** any `localStorage.setItem` or `localStorage.removeItem` calls for
   `activeSymbol` — those can stay (they are harmless writes; we're fixing the read-on-init
   only).

---

## Verification Checklist

After making the change, verify manually:

- [ ] Clear `localStorage` in DevTools → refresh → QuoteBar is blank (no symbol shown)
- [ ] Set `localStorage.setItem('activeSymbol', 'PLTR')` in DevTools console → refresh →
      QuoteBar is still blank (stale value is NOT read on init)
- [ ] Select a symbol via SymbolSearch → QuoteBar populates correctly with that symbol's data
- [ ] No console errors when `activeSymbol` is `null`
- [ ] Other localStorage state (watchlist toggle, systemVars, configOpen, etc.) is unaffected

---

## House Style Rules

- No `$` prefix on any monetary value
- Dark theme tokens only — no inline colors
- Dates: `mm-dd-yyyy` via `formatDate()`

---

## Commit Message

```
OTA-327 Fix stale activeSymbol on init — remove localStorage read, session-only state
```
