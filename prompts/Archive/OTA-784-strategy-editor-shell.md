---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-784 — Strategy editor shell and selector

> Re-cut 2026-06-03 after Phase 0 NO-GO. Supersedes the prior `ota784.md`. Resolves the
> two backend blockers (now OTA-822 + OTA-823) and the layout/route interpretation gaps.
> **Blocked by OTA-822 (status column) and OTA-823 (admin list endpoint); also depends on
> OTA-782 (CRUD) and OTA-783 (validation).** Runs after those land.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: OTA-822, OTA-823, OTA-782, OTA-783 committed first. Container story — section bodies are OTA-785/786/787/788.

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md          # prototype is the layout contract; CSS vars; ##.00; mm-dd-yyyy
cat claude_context/architecture-plan.md    # cross-cutting (new route + data layer)
```
Also open the mockup: `strategy-rules-prototype-v2.html` (the layout contract).

## Relevant Context — Do Not Deviate Without Escalation

**1. Layout = the mockup: stacked sections, NOT a three-tab body.** Phase 0 confirmed the prototype body is **stacked config sections** (Parameters / Scoring Weights / Hard Gates / Adjustments / Verdict Bands), not three tabs. The earlier "three-tab scaffold" was a prompt invention that contradicted the mockup. Build stacked sections. The only tabbed element is the rule-catalog drawer (internal to it), as in the mockup.

**2. Route = dedicated `/strategy-admin`** (selector + editor), rendered in the existing Layout shell (rail + main) per the mockup. Do NOT add an admin-mode toggle to the public `StrategyPage`. Register the route in `web/src/App.jsx` inside the `<AppProvider><Layout/></AppProvider>` nested-route block.

**3. Selector data = OTA-823.** The strategy selector reads `GET /api/v1/config/strategies/admin`: lists `owner_app_id='OTA'` strategies editable and `SHARED` strategies read-only (tagged by `owner_app_id`). Do not use the OTA-762 runtime projection for the selector (it's SCREENING-only, owner-blind, restart-gated).

**4. Status field = OTA-822.** The header `status` control edits the lifecycle value (active / inactive / deprecated; `draft` is reserved for the OTA-791 preview mechanism and is not a user-pickable header value). Sourced from the OTA-822 column.

**5. Writes = OTA-782, validated by OTA-783.** Field edits persist through the CRUD API; the shell is the container — it wires the header + section scaffolding and routes saves through OTA-782/783. Section bodies (gates/scoring/adjustments/bands) are their own stories.

**6. House style.** CSS variables per UI-GUIDANCE — **not `tokens.C`** (stale, diverges from the spec). Scores `##.00`; dates `mm-dd-yyyy` via `formatDate()`; no `$`. No visual invention beyond the mockup.

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)
1. Confirm `GET /api/v1/config/strategies/admin` exists and returns owner/enabled/status (OTA-823 landed). If not → STOP.
2. Confirm `engine_strategies.status` exists (OTA-822) and the CRUD path can write it (OTA-782). If not → STOP.
3. Confirm the mockup's stacked-section structure and the `/strategy-admin` registration seam in `App.jsx`.
4. Confirm UI-GUIDANCE CSS variables (ignore `tokens.C`).
Report GO or STOP.

## Scope
- `/strategy-admin` route in the Layout shell; strategy selector (from OTA-823); per-strategy header (key, label, status, enabled structures, DTE range); stacked section scaffolding (Parameters / Scoring Weights / Hard Gates / Adjustments) + Verdict Bands panel placeholder. Section bodies are OTA-785/786/787/788; this story stands up the container and header edits.

## Acceptance criteria
- Selector lists OTA strategies (editable) and SHARED (read-only) from OTA-823; selecting one loads it into the editor.
- Header renders/edits key, label, status (active/inactive/deprecated, OTA-822), enabled structures, DTE range; saves route through OTA-782/783.
- Stacked sections + Verdict Bands panel present per the mockup (bodies filled by their stories); rule-catalog drawer keeps its internal tabs.
- Renders at `/strategy-admin` in the Layout shell; CSS variables per UI-GUIDANCE (no `tokens.C`); `##.00` / `mm-dd-yyyy` where applicable.

## Out of scope
- Section bodies (OTA-785/786/787/788); Apply/Reset (OTA-790); draft preview (OTA-791); audit trail (OTA-792).
- The backend status column (OTA-822), list endpoint (OTA-823), CRUD (OTA-782), validation (OTA-783).

## Verification
Regression Level 2 (new admin surface): manual click-through.
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web"
npm run dev
```
1. `/strategy-admin` renders in the Layout shell; selector lists OTA (editable) + SHARED (read-only).
2. Selecting a strategy loads header + stacked-section scaffold; header edits persist via OTA-782 and survive reload.
3. `grep -rn "tokens" web/src/<new files>` → no `tokens.C` usage; CSS variables only.
4. No three-tab body; stacked sections per the mockup.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer
OK to continue to the section-body stories (OTA-785 / OTA-786 / OTA-787 / OTA-788) once the shell lands.

## Commit message template
```
OTA-784 feat: strategy editor shell + selector at /strategy-admin

- selector from OTA-823 admin list (OTA editable, SHARED read-only); header edits incl. status (OTA-822)
- stacked config sections per mockup (not three tabs); saves via OTA-782/783; CSS variables per UI-GUIDANCE
- Regression Level 2
```
