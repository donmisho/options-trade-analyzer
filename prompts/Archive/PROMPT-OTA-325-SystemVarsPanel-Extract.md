---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-325 — Extract System Variables into Dedicated SystemVarsPanel Component

**Jira:** OTA-325 | Parent: OTA-34 (Config Drawer Popout Sidebar)
**Priority:** Medium | **Labels:** frontend, phase-2-3, ui-overhaul
**Run this BEFORE OTA-326.**

---

## Before You Start

```bash
cat web/src/components/ConfigDrawer.jsx
cat web/src/context/AppContext.jsx
cat web/src/components/LeftNav.jsx
grep -n "systemVars\|SystemVars\|configOpen\|setConfigOpen" web/src/context/AppContext.jsx
grep -rn "SystemVariables\|System Variables\|systemVars" web/src/components/ConfigDrawer.jsx
```

Read all output before touching anything.

---

## Goal

The `ConfigDrawer` currently contains a **System Variables** section alongside trade-specific
parameters. These application-wide settings (exit levels, stop buffers, health thresholds)
do not belong next to SMA periods or Greek filters. Extract them into a dedicated
`SystemVarsPanel.jsx`.

---

## Step 1 — Create `web/src/components/SystemVarsPanel.jsx`

Build a right-side slide-out drawer component. Reuse the **same panel chrome** as ConfigDrawer:
- Right-side drawer
- Overlay backdrop
- Header: title + close `×` button

**Title:** `System Settings`
**Subtitle:** `Application-wide behavior defaults`

### Fields to include (all currently under "System Variables" in ConfigDrawer)

| Field | Control | Notes |
|-------|---------|-------|
| Exit Warning Level | Slider | % of debit |
| Exit Scale-Out Level | Slider | % of debit |
| Underlying Stop Buffer | Number input | Distance below price |
| Time Stop Days Before Expiry | Number input | Days |
| Min Reward:Risk | Number input | Ratio |
| Min Expected Value | Number input | Dollar threshold (no `$` prefix in UI) |
| Health Indicator Thresholds | Three number inputs | Green / Amber / Red pip cutoffs |

### Behavior
- **Apply** button: saves current field values to `systemVars` in AppContext + persists to
  `localStorage` (same pattern as ConfigDrawer's Apply)
- **Reset to Defaults** button: restores hardcoded default values to all fields (do not save
  to localStorage until user clicks Apply)
- Open/close state managed via `systemVarsPanelOpen` boolean (see Step 2)
- Opening SystemVarsPanel does NOT affect `configOpen` / ConfigDrawer state

---

## Step 2 — Add `systemVarsPanelOpen` State to AppContext

In `web/src/context/AppContext.jsx`:

```js
const [systemVarsPanelOpen, setSystemVarsPanelOpen] = useState(false);
```

Expose both `systemVarsPanelOpen` and `setSystemVarsPanelOpen` through the context value.

---

## Step 3 — Remove System Variables Section from ConfigDrawer

In `web/src/components/ConfigDrawer.jsx`:
- Remove the entire System Variables section (fields + heading)
- Do NOT remove any trade-specific parameters (SMA periods, Greek filters, DTE windows, etc.)
- After removal, verify ConfigDrawer still renders and saves correctly

---

## Step 4 — Wire Gear Icon in LeftNav (Placeholder)

In `web/src/components/LeftNav.jsx`:
- The gear icon's `onClick` should call `setSystemVarsPanelOpen(true)`
- This is placeholder wiring — the permanent connection is formalized in OTA-326

---

## Step 5 — Mount SystemVarsPanel in App.jsx

In `web/src/App.jsx` (or wherever ConfigDrawer is mounted):
```jsx
<SystemVarsPanel
  open={systemVarsPanelOpen}
  onClose={() => setSystemVarsPanelOpen(false)}
/>
```

---

## Acceptance Criteria

- [ ] Gear icon in left nav opens SystemVarsPanel (right-side drawer)
- [ ] ConfigDrawer no longer shows any System Variables section
- [ ] All system var fields present and functional in SystemVarsPanel
- [ ] Apply saves to AppContext `systemVars` + persists to localStorage
- [ ] Reset to Defaults restores hardcoded default values (does not auto-save)
- [ ] Opening/closing SystemVarsPanel has no effect on ConfigDrawer open state
- [ ] Dark theme tokens throughout — no inline colors, no hardcoded hex values
- [ ] No `$` prefix on any monetary value
- [ ] Buttons sized to content with fixed padding, never full-width
- [ ] Visible border or background on buttons in default state

---

## House Style Rules

- Dark theme: background `#0D1117`, Emerald Teal `#00C896`, Apricot Amber `#F5A623`
- CSS variables for all colors — never inline hex
- Date format `mm-dd-yyyy` via `formatDate()` (not relevant here but keep in mind)

---

## Commit Message

```
OTA-325 Extract SystemVarsPanel from ConfigDrawer, wire gear icon placeholder
```
