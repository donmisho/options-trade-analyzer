---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-183 + OTA-185 — Strategies Navigation Section + Strategy Admin (Light)

**Jira:** OTA-183, OTA-185 | Parent: OTA-37 (Strategies Navigation + Strategy Profile Pages)
**Priority:** Medium/Low | **Labels:** claude-code, requirement, options-domain
**Run after OTA-325/326 are validated (both touch LeftNav).**

---

## Before You Start

```bash
cat web/src/components/LeftNav.jsx
cat web/src/context/AppContext.jsx
grep -rn "strategy\|strategies\|configSchema" web/src/strategy-configs/
ls web/src/strategy-configs/
grep -n "STRATEGIES\|strategy_name\|enabled" web/src/strategy-configs/index.js 2>/dev/null
```

Read all output before making any changes.

---

## Context

Two strategy-related tickets are batched here:

- **OTA-183:** Add a collapsible "Strategies" section to the left nav below the main tabs
- **OTA-185:** Light strategy admin — enable/disable per strategy and rename (full builder
  deferred to Phase 4.x pending backtest validation)

These are **lower priority** than OTA-325/326 and the backend tickets. Run last.

---

## Feature A — OTA-183: Strategies Navigation Section (Collapsible)

### Location in LeftNav

Below the five main nav tabs (Dashboard · Security Strategies · Verticals · Puts & Calls · Positions).
Separated by a subtle horizontal divider.

### Structure

```
─────────────────  (divider)
STRATEGIES ▾       (section header, collapsible)
  Steady Paycheck
  Weekly Grind
  Trend Rider
  Lottery Ticket
```

### Behavior

- Section header "STRATEGIES" is clickable — toggles collapsed/expanded
- Default state: **expanded**
- Collapsed state persists in `localStorage` key `"strategiesNavOpen"` (boolean)
- Each strategy item is a clickable link — navigates to `/strategies/{strategy_id}`
  (these pages do not need to exist yet; create stub routes if needed)
- Active strategy: same active styling as main nav (3px teal left border, teal text,
  `rgba(45,212,191,0.08)` background)
- Inactive strategy items: muted gray `#8b949e`, no border

### Strategy List Source

Read from `web/src/strategy-configs/index.js` (or wherever the canonical strategy list
lives). Do NOT hardcode strategy names in LeftNav.

Each strategy entry needs at minimum: `{ id: string, name: string, enabled: boolean }`.
Add `enabled` field to strategy config if not present — default `true`.

Only show strategies where `enabled === true` in the nav.

---

## Feature B — OTA-185: Strategy Admin (Light)

### Scope

Light admin only — enable/disable per strategy and rename. Full strategy builder
(weights, thresholds) is deferred to Phase 4.x.

### Where It Lives

Add a small admin section to the **SystemVarsPanel** (created in OTA-325).
Below the existing system var fields, add a collapsible "Strategy Settings" section.

### Controls Per Strategy

| Control | Type | Notes |
|---------|------|-------|
| Strategy name | Text input | Editable display name |
| Enabled | Toggle switch | Controls visibility in nav and scoring |

### Behavior

- Changes saved to `localStorage` key `"strategyAdmin"` as `{ [strategy_id]: { name, enabled } }`
- Apply button in SystemVarsPanel saves all strategy settings simultaneously
- Reset to Defaults restores original `name` from config and `enabled: true` for all
- When a strategy is disabled: disappears from LeftNav strategies section; its scores
  are excluded from scorecards

### Read Strategy Settings

In strategy-configs, when rendering names or checking enabled status, always check
`localStorage.getItem('strategyAdmin')` first — user overrides take precedence over
config defaults.

---

## Acceptance Criteria

### OTA-183
- [ ] "STRATEGIES" collapsible section appears in LeftNav below main 5 tabs
- [ ] Section header toggles collapsed/expanded
- [ ] Collapsed state persists in localStorage
- [ ] Shows all enabled strategies from config (not hardcoded)
- [ ] Active strategy item matches main nav active styling
- [ ] Disabled strategies do not appear in nav

### OTA-185
- [ ] Strategy admin section appears in SystemVarsPanel
- [ ] Each strategy has name input + enabled toggle
- [ ] Changes save to localStorage on Apply
- [ ] Reset to Defaults restores original names and all enabled
- [ ] Disabling a strategy removes it from LeftNav strategies section

---

## Rules

- Strategy tabs (Steady Paycheck etc.) do NOT appear as top-level nav tabs — only in
  this collapsible strategies section. This is explicitly in `UI-DECISIONS.md`.
- The five main nav tabs (Dashboard · Security Strategies · Verticals · Puts & Calls ·
  Positions) must not change. Exactly five, exactly in that order.
- CSS variables for all colors — no inline hex
- No `$` prefix on any monetary value
- Dark theme tokens throughout

---

## Commit Message

```
OTA-183 OTA-185 Add strategies nav section to LeftNav and light strategy admin in SystemVarsPanel
```
