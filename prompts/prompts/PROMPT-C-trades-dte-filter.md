---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
---

# OTA-560 — Trades page: user-controlled DTE / expiration filter

## Terminal context
- This terminal: **Terminal C**
- Concurrent terminals: **A (OTA-515 + OTA-549/509/510), B (OTA-542 data isolation), D (governance docs)**
- Cross-terminal dependencies:
  - **No file contention with A, B, or D.** This is a frontend-only Story under `web/src/`.
  - **Do NOT touch `web/src/api/client.js`.** Per OTA project shared-file rule, `client.js` is exclusivity-protected. This Story filters client-side from the already-fetched response — no API client changes required.
  - **Do NOT touch the verdict badge component** that Terminal A is editing for OTA-515 #5.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
```

Then orient on the current Trades page:

```
find web/src -name "TradesPage*" -print
sed -n '1,80p' web/src/pages/TradesPage.jsx     # adjust path per find
grep -rn "vertical\|verticals" web/src/pages/TradesPage.jsx | head -30
grep -rn "useSearchParams\|useNavigate" web/src/ | head -10    # confirm router conventions for URL state
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: `UI-GUIDANCE.md` (enforced for ALL frontend work)**
- No `$` prefix on any monetary value (irrelevant here — DTE filter has no monetary fields).
- Dates as `mm-dd-yyyy` via the project's `formatDate()` helper.
- Dark-theme CSS variables only — no inline hex.
- Buttons sized to content, never full-width.
- `var(--bg2)` restricted to filter bars, QuoteBar, and pill-badge backgrounds — using it for the filter bar IS appropriate here.
- Inputs follow existing input styling — locate the Strategy config or Positions filter for the canonical pattern; reuse, don't reinvent.

**Source: OTA-560 ticket — Implementation note**
Rule: The vertical scan caps at 20 results. Filter client-side from the already-fetched response — no backend round-trip on filter changes. If a future Story raises the cap or introduces pagination, switch to query-param-based server-side filtering then; do NOT preemptively build server-side filtering now.

**Source: OTA-560 ticket — Default behavior**
Rule: Default Min/Max DTE values match the underlying scan defaults. Until the user changes them, the filter is a no-op. This makes OTA-560 safe to ship before OTA-559 (per-strategy DTE windowing at scan time) — the filter becomes a true override once OTA-559 lands; until then it just narrows what's already there.

**Source: OTA project — Frontend conventions**
- React/Vite. Hooks-based components. No class components.
- URL state via `useSearchParams` (React Router pattern in use elsewhere in the app — confirm in Phase 1).
- Debounce numeric input handlers if needed (existing helper preferred over a new dependency).

---

## Phase 1 — Read-only orientation (brief; STOP gate is shorter here)

This Story is small enough that a heavy phase-gate is overkill. Still, before edits:

1. Confirm exact path of TradesPage component and which child component renders the Vertical spreads section.
2. Identify the existing pattern for filter UI on this page (or the closest cousin page — Positions, Strategy config). Note its CSS approach (CSS variables, class names, layout).
3. Identify the URL-state pattern in use (React Router `useSearchParams` vs. a project wrapper).
4. Identify how the vertical results array is held in component state — that's the array we filter over.
5. Identify any existing "filtered N of M" callout pattern; reuse if present.

Report findings as a short checklist (one bullet per item above) and proceed to Phase 2 unless any item turns up missing or substantially different from expectation.

---

## Phase 2 — Implementation

### 2a. Filter UI
- Add a DTE filter control above the Vertical spreads section. Two number inputs labeled **Min DTE** and **Max DTE** (preferred over a dual-thumb slider unless the existing layout makes a slider obviously better — implementer's call, justify in the report).
- Range: 1 to 365. Integers only. Min ≤ Max enforced (the larger of the two snaps to maintain the invariant on each change, OR a validation message — implementer's choice consistent with existing form patterns on this page).
- Sized to content per UI-GUIDANCE. Filter bar uses `var(--bg2)` background as that's the approved use case.
- Reset button (sized to content) restores defaults.

### 2b. Filtering behavior
- Filter the visible vertical results array client-side. Source of truth for "DTE" on each result is the existing DTE field in the result payload — confirm field name in Phase 1.
- Update on every change (debounce 150ms if the existing pattern uses debouncing; otherwise apply immediately on input blur or change).
- Update the visible result count and any "filtered N of M" callout in real time.
- Empty-state message when no results match: clear text stating the active filter range with a Reset link inline.

### 2c. URL state persistence
- Filter values persist in URL params: `?dte_min=14&dte_max=45`.
- On mount, hydrate from URL params if present; otherwise use scan defaults.
- On change, update URL via the project's URL-state pattern (do NOT trigger navigation/reload).
- Copying the URL to a new tab preserves the filter.

### 2d. Defaults
- Default Min/Max match the underlying scan defaults. If the scan defaults are not surfaced to the frontend, hardcode them to match what the scanner uses today (look in the scan response or a config endpoint — confirm in Phase 1; if neither, escalate before hardcoding).

---

## Acceptance criteria

- Two number inputs (or one range slider) labeled "DTE: Min / Max" visible on the Trades page above the Vertical spreads section.
- Range 1–365, integers only, Min ≤ Max enforced.
- Changing values immediately filters the visible result set and updates the result count.
- Filter state persists in URL params (`?dte_min=N&dte_max=M`).
- Reset button restores defaults.
- Existing Vertical spreads features (sort, expansion, evaluation) continue to work after filtering.
- Empty state when no results match: clear message stating the active filter range with a Reset link.
- No regression to scan response time (filter is purely client-side).
- No edits to `web/src/api/client.js` or any backend file.
- No inline hex colors. Dark-theme CSS variables only.

## Out of scope

- Long options / Puts & Calls section — this Story is verticals only.
- Persisting filter as a per-user preference beyond URL state.
- Strategy-band-specific filter UI (the Strategy config screen handles per-strategy band tuning).
- Server-side filtering (deferred until result-set sizes warrant it).
- Any backend change.

## Verification steps

Before requesting commit approval:

1. `npm run build` — clean build, no TypeScript / lint errors.
2. `npm run dev` — start frontend; navigate to Trades page.
3. Manual:
   - Verify default values render and the result set is unfiltered.
   - Set Min=14, Max=45 — verify result count updates and only matching DTEs remain visible.
   - Click Reset — verify defaults restored and full set returns.
   - Set Min=200, Max=210 (no matches expected) — verify empty-state message and the inline Reset link works.
   - Try Min=50, Max=20 — verify Min ≤ Max enforcement (snap or validation).
   - Try Min=0, Max=400 — verify range clamp to 1–365.
   - Copy URL to new tab; confirm filter state persists.
4. Confirm sort, expansion, and evaluation still work on filtered results.
5. `grep -rn "var(--" web/src/pages/TradesPage.jsx` (or the file you edited) — confirm every color is a CSS variable, no inline hex.
6. `grep -rn "client.js" web/src/pages/TradesPage.jsx` — should return nothing (no API client changes).

## Commit instruction
**I have been instructed to commit. Do you approve? (yes / no)**

## Coordination footer
**Independent — no downstream dependency.** Other terminals proceed in parallel; nothing in this batch waits on Terminal C. OTA-559 (per-strategy DTE windowing at scan time) is the natural successor but is deferred (blocked on OTA-513 + OTA-516).

## Commit message template (if committing)
```
OTA-560 feat: Trades page DTE filter for Vertical spreads with URL state persistence
```
