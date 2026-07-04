---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Bash(cat:*)
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git branch:*)
  - Bash(npm run build:*)
---

# OTA-846 — Add "Configuration" nav section with Strategy Admin link (branch-scoped subset)

**Branch:** `OTA-836-build-to-testable` (dev only — no prod deploy)
**Ticket:** OTA-846 (Story, Code & Test Complete on the OTA-781 lineage). This prompt ports a **strict subset** of OTA-846 onto the IE branch so the Strategy Admin screens are reachable from the rail during IE testing. Scope is deliberately narrower than the full 846 AC — see Scope Guard below — so the eventual 846 lineage merge stays additive, not conflicting.

**QA level:** Level 1 (frontend-only; no `app/` logic, no engine-evaluated code). Verify build passes, link renders, route resolves, active-state works.

---

## Mechanism A — Required reading (cat these first)

```powershell
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
```

> Note: the UI guidance doc is `claude_context/UI-GUIDANCE.md` per the CLAUDE.md doc table. If your working copy has renamed it to `UI-DECISIONS.md`, read that instead and report the discrepancy.

---

## Mechanism B — Embedded context (source: OTA-846 description, live Jira)

OTA-846's full intent is a **CONFIGURATION** rail section (peer to **STRATEGIES**) grouping two entries — **Strategy Admin** (routes to `/strategy-admin`, active-state on route) and **System Settings** (opens the existing System Settings cabinet) — and consolidating the bottom "Settings" gear into that section.

`/strategy-admin` (OTA-784) and the System Settings cabinet are already deployed. The route renders today; it simply has no nav entry (confirmed: reachable by direct URL on dev).

**This prompt implements only the Strategy Admin half.** System Settings consolidation and bottom-gear removal are left untouched so 846's later merge is additive.

---

## Phase 0 — Read-only discovery (HARD STOP before any edit)

Do not edit anything in Phase 0. Discover and report:

1. **Rail component.** Locate the left-nav rail component (expected `Layout.jsx`, per the "Change Log" nav entry placement in `deployment-workflow.md`). Report its path and how the existing **STRATEGIES** section header + items are structured (component, data array, or hardcoded JSX).
2. **Route registration.** Confirm `/strategy-admin` is registered in the router on this branch and renders (OTA-784). Report the router file and the route entry.
3. **Rail conventions.** From `UI-GUIDANCE.md`, confirm: section-header pattern, CSS-variable tokens for rail text/active-state (no hardcoded colors), and active-state mechanism used by existing links.
4. **Divergence check.** `git branch --show-current` to confirm `OTA-836-build-to-testable`. Grep the rail component for any existing "Configuration"/"Strategy Admin" entry (in case a partial 846 artifact is already present). Report clean or conflict.
5. **QA confirm.** Confirm Level 1 is correct (no `app/` changes implied).

**STOP and report GO/NO-GO.** Do not proceed to implementation until Don replies GO.

NO-GO conditions (report, don't work around):
- `/strategy-admin` route is **not** registered on this branch → the screens aren't here; adding a link would dead-end. Stop.
- Rail structure differs materially from the STRATEGIES pattern, or a conflicting Configuration/Strategy Admin entry already exists → stop and describe.

---

## Implementation (only after Don's GO)

Add to the left-nav rail, following the existing STRATEGIES section pattern exactly:

- A **CONFIGURATION** section header, placed per UI-GUIDANCE (peer to STRATEGIES).
- One item under it: **Strategy Admin** → navigates to `/strategy-admin`, with active-state on that route matching how existing rail items set active-state.
- CSS variables only — no hardcoded colors. No new dependencies.

### Scope Guard — do NOT do any of the following
- Do **not** add a System Settings entry.
- Do **not** touch, move, or remove the bottom "Settings" gear/launcher.
- Do **not** move the "Change Log" item.
- Do **not** modify the Strategy Admin screens, routes, or any config/settings API.
- Do **not** introduce role-gating (single-operator app).

If any of these seem necessary to make the link work, **STOP and report** — that's a signal the branch state differs from assumptions.

---

## QA (Level 1)

```powershell
npm run build
```

- Build passes clean.
- CONFIGURATION header renders peer to STRATEGIES.
- Strategy Admin link navigates to `/strategy-admin` and the screens load.
- Active-state highlights correctly when on `/strategy-admin` and clears when off it.

Report `git diff` summary for Don's review.

---

## Commit gate

**Do NOT commit.** Stop after QA and report the diff. Don commits manually.

Suggested commit message (Don runs it):

```
OTA-846 feat: add Configuration rail section with Strategy Admin link (branch-scoped subset)
```

---

## Coordination footer

- Single terminal. The rail component (`Layout.jsx`) is also touched by the full OTA-846 on its own lineage — this subset is intentionally additive so that merge stays clean. Flag any conflict at merge time.
- After this lands: resume the IE bundle test on `OTA-836-build-to-testable` (SP / TR / WG verdict check), then advance OTA-847 + OTA-850 out of Code & Test Complete.
