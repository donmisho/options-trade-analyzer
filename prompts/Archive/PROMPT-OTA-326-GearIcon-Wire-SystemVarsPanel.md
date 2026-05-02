---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-326 — Wire Left Nav Gear Icon Permanently to SystemVarsPanel

**Jira:** OTA-326 | Parent: OTA-34 (Config Drawer Popout Sidebar)
**Priority:** Medium | **Labels:** frontend, nav, phase-2-3
**Run this AFTER OTA-325 is validated.**

---

## Before You Start

```bash
cat web/src/components/LeftNav.jsx
cat web/src/context/AppContext.jsx
grep -n "gear\|settings\|systemVarsPanel\|setSystemVarsPanel" web/src/components/LeftNav.jsx
grep -n "systemVarsPanelOpen\|setSystemVarsPanelOpen" web/src/context/AppContext.jsx
```

Read all output. Confirm `systemVarsPanelOpen` and `setSystemVarsPanelOpen` exist in
AppContext from OTA-325 before proceeding.

---

## Goal

Formally establish the gear icon in the left nav footer as the **permanent** entry point
for `SystemVarsPanel`. OTA-325 wired this as a placeholder — this subtask locks it in
and ensures correct styling and accessibility.

---

## Changes Required

### `web/src/components/LeftNav.jsx`

1. The gear icon's `onClick` must call `setSystemVarsPanelOpen(true)` — confirm this is
   already wired from OTA-325. If not, wire it now.

2. **Remove any route navigation** from the gear icon's click handler (e.g. no
   `navigate('/settings')` or `history.push`). The gear opens a panel, not a page.

3. **Add accessible tooltip:** `title="System Settings"` on the gear icon button element
   (or `aria-label="System Settings"` if using an icon-only button).

4. **Icon styling** — consistent with nav footer style:
   - Default state: `color: var(--muted)` (muted gray `#8b949e`)
   - Hover state: `color: var(--fg)` (foreground white)
   - Transition: `color 150ms ease`
   - No background change on hover — icon color change only

---

## Acceptance Criteria

- [ ] Gear icon opens SystemVarsPanel on every page without exception
- [ ] Clicking gear does NOT navigate to any route
- [ ] Button has `title="System Settings"` or `aria-label="System Settings"`
- [ ] Icon renders `var(--muted)` at rest
- [ ] Icon renders `var(--fg)` on hover
- [ ] Hover transition is smooth (CSS transition, not instant)
- [ ] No console errors

---

## House Style Rules

- CSS variables for all colors — no inline hex
- No `$` prefix on any monetary value
- Buttons: visible state on hover, consistent with nav footer

---

## Commit Message

```
OTA-326 Wire gear icon permanently to SystemVarsPanel, add tooltip and hover style
```
