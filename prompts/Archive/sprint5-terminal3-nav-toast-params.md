---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 — Terminal 3: Navigation, Toast, Strategy Params

**Tickets:** OTA-408, OTA-409, OTA-410
**Commit prefix:** `OTA-408 OTA-409 OTA-410`

Read `claude_context/UI-GUIDANCE.md` Parts 1, 6, 7, 9 before starting.

## House style (enforce everywhere)
- No `$` prefix on monetary values. Format `##.00` via `.toFixed(2)`
- Config %: `##%` (no decimals). Multipliers: `#×`
- Dark theme CSS variables only — never inline hex
- Buttons: auto-width, never full-width
- Claude advice badge: white outlined (rgba(255,255,255,0.06) bg, rgba(255,255,255,0.35) border)

---

## Step 1 — Create shared Toast component (OTA-410)

1. Create `web/src/components/Toast.jsx`
2. Toast spec:
   - Position: fixed, top-right (top: 20px, right: 20px)
   - Auto-dismiss: 4 seconds (configurable)
   - Dismiss on X click
   - Optional link (e.g., "View Positions" → navigates to /positions)
   - Variants:
     - `success`: left border 3px `var(--green)`
     - `error`: left border 3px `var(--red)`
     - `info`: left border 3px `var(--teal)`
   - Background: `var(--bg)`, border: 1px `var(--border)`, border-radius: 4px
   - Font: 10px monospace, `var(--text)` color
   - Stack multiple toasts vertically (each below the previous)
   - Slide-in animation from right

3. Create `web/src/hooks/useToast.js` (or a ToastContext):
   ```js
   const { showToast } = useToast();
   showToast({ type: 'success', message: 'Position followed — SPY 630/620', link: { text: 'View Positions', to: '/positions' } });
   showToast({ type: 'error', message: 'Failed to evaluate: network error' });
   ```

4. Wrap the app with ToastProvider in App.jsx

5. Audit and wire toasts across all pages:
   - **TradesPage**: Section E Follow → success toast with "View Positions" link. Take Position → success toast. Evaluate failure → error toast. Follow-up failure → error toast.
   - **PositionsPage**: Refresh all → success toast. Refresh single → success toast. Refresh failure → error toast.
   - **StrategyPage**: Refresh all → success toast. Find trades navigation is not a toast.
   - **SecurityStrategiesPage**: Scan complete → info toast "Scanned {n} symbols". Scan failure → error toast.
   - Replace any `alert()`, `console.error`-only, or ad-hoc notification patterns

## Step 2 — StrategyPage editable parameters (OTA-408)

1. `cat web/src/pages/StrategyPage.jsx` — find the parameter cards section (lines ~383-404 per audit)
2. Currently renders read-only display of default values. Convert to editable:
   - For each parameter in `configSchema`:
     - Render a number input (for thresholds) or range input (for percentages)
     - Show: parameter label, current value (editable), default value (muted), valid range
     - Format: percentages as `##%`, multipliers as `#×`
   - Track modified values in local state (`editedParams`)
   - Show "unsaved changes" indicator when any value differs from default
3. Add buttons below the parameter grid:
   - "Apply" (teal outlined) — calls the scoring endpoint with modified params, updates strategy positions/scores
   - "Reset to defaults" (neutral outlined) — restores all values to configSchema defaults
4. Buttons: auto-width, flex row, gap 10px, left-aligned

## Step 3 — Navigation path verification (OTA-409)

**Run after T1 and T2 are committed.** Test every navigation path:

1. **Scan card → Trades**: Navigate to `/security-strategies`, scan, click a card → verify `/trades?symbol=X` loads
2. **Strategy "Find trades →"**: Navigate to `/strategies/steady-paycheck`, click "Find trades →" → verify `/trades?strategy=steady-paycheck` loads and pre-filters results to credit spread structures only
3. **Follow/Take Position toast**: On Trades page, expand a row, evaluate, click Follow → verify success toast appears with "View Positions" link → click link → verify `/positions` loads
4. **`/favorites` redirect**: Navigate to `/favorites` → verify redirect to `/positions`
5. **Strategy sub-nav**: Click each of the 4 strategy names in left rail → verify `/strategies/{key}` loads for each
6. **Dashboard nav**: Click "Dashboard" in left rail → verify `/dashboard` loads
7. **Logo click**: Click "Options Analyzer" logo → verify navigates to `/dashboard`

For each path, if the navigation doesn't work:
- Check `App.jsx` route definitions
- Check `useSearchParams()` or `useParams()` in the target page
- Fix and verify

## Verification

After all steps:
1. Toast appears top-right on Follow, Take Position, Refresh, and errors
2. Toast auto-dismisses after 4s, link navigates correctly
3. StrategyPage parameters are editable with Apply/Reset
4. All 7 navigation paths work end-to-end
5. No build errors, no console errors
