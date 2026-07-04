# OTA-846 — Add "CONFIGURATION" left-nav section (Strategy Admin + System Settings)

## Terminal context
- This terminal: **Terminal C** (frontend)
- Concurrent terminals: Terminal A (OTA-847, seed) · Terminal B (OTA-843, tests)
- Cross-terminal dependencies: none. You touch the left-nav rail component and its styles only — no backend, no seed, no tests those terminals own.

You are working on branch **`OTA-836-build-to-testable`**. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
cat strategy-rules-prototype-v2.html      # the rail pattern reference
```
Then locate the live left-rail component (do not guess the path):
```
grep -rn "STRATEGIES" web/src
```

## Relevant Context — Do Not Deviate Without Escalation

Source: `UI-GUIDANCE.md` (rail sections, CSS variables) + OTA-846
- **Hard constraint:** the four primary nav items are fixed — do not add/remove/reorder them. CONFIGURATION is a **section** peer to the existing **STRATEGIES** section, and must **mirror the STRATEGIES section pattern** exactly (same header treatment, same item styling, same active-state mechanism).
- **Dark-theme CSS variables only.** Never inline hex colors. All color values come from `web/src/styles/tokens.js`. (CLAUDE.md → styling invariant.)
- **No role-gating** — single-operator app.

Source: OTA-846 — what CONFIGURATION contains
- **Strategy Admin** → routes to `/strategy-admin` (deployed at OTA-784; active-state on route).
- **System Settings** → opens the **existing** System Settings cabinet (the slide-out launched today from the bottom "Settings" gear). Keep it as a cabinet — do not convert it to a routed page.
- Consolidate the redundant bottom "Settings" launcher into this section so there is a single entry point.

## Phase 0 — Locate and confirm (read-only, brief)
Make NO edits. Report:
1. The left-rail component file and how the **STRATEGIES** section header + items + active-state are implemented (the pattern you will mirror).
2. How the System Settings cabinet is currently launched from the bottom "Settings" gear (handler/state to reuse).
3. Confirm the `/strategy-admin` route exists and how active-state is derived for routed items.

Then proceed — this is a confined frontend change, no GO/NO-GO gate required.

## Scope
1. Add a **CONFIGURATION** section header to the left rail, peer to STRATEGIES, placed per UI-GUIDANCE, mirroring the STRATEGIES section pattern.
2. Add two items under it: **Strategy Admin** (routes to `/strategy-admin`, active-state on route) and **System Settings** (opens the existing cabinet via the reused launcher).
3. Consolidate the bottom "Settings" gear launcher into the System Settings item (single entry point).

## Acceptance criteria
- A "CONFIGURATION" section header appears in the left rail, peer to "STRATEGIES", placed per UI-GUIDANCE.
- Strategy Admin routes to `/strategy-admin` with correct active-state; System Settings opens the existing cabinet.
- The redundant bottom "Settings" launcher is consolidated into the Configuration section.
- Styling uses CSS variables from `tokens.js` — no hardcoded colors; placement/treatment follow the existing rail pattern.

## Out of scope
- Converting the System Settings cabinet into a routed page (keep as cabinet).
- Any change to the admin screens or the config/settings APIs.
- Moving the "Change Log" item — it stays in the bottom rail.
- The four fixed primary nav items — do not touch.

## Verification steps
QA Level 1 (single-component UI change) — manual click-through:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web"
npm run dev
```
- CONFIGURATION renders peer to STRATEGIES, styled identically.
- Strategy Admin navigates to `/strategy-admin` and shows active-state on that route.
- System Settings opens the existing cabinet; the old bottom "Settings" gear no longer duplicates the entry.
- Change Log unchanged; the four primary nav items unchanged.

## Commit instruction
Do NOT commit. STOP and summarize the staged diff (files, line counts) plus the click-through result. Don commits with the `OTA-846 feat:` prefix. The commit-triggered automation transitions OTA-846; do not transition it yourself.

## Coordination footer
Independent — no downstream dependency, no file overlap with OTA-847 or OTA-843. (Config screens become visible on dev once this + the OTA-844 position-health seed are deployed.) Do not deploy — Don holds the deploy gate.

## Commit message template (Don)
```
OTA-846 feat: add CONFIGURATION left-nav section grouping Strategy Admin + System Settings
```
