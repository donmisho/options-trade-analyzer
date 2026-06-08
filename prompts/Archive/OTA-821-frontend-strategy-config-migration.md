---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-821 — Frontend strategy-configs migration (consume the canonical read API)

> Split out of OTA-762 on 2026-06-03. This is the audit §5a #6 dual-source-mirror kill —
> a 10-site consumer migration, not a provider swap (confirmed by OTA-762 Phase 0).
> **Blocked by OTA-762** (the `GET /api/v1/config/strategies` endpoint must exist first).

## Terminal context
- This terminal: Terminal A (or B if backend work is running elsewhere)
- Concurrent terminals: none
- Cross-terminal dependencies: **OTA-762 must be committed first** (this consumes its endpoint). **Do NOT run concurrent with OTA-763** (Result-record rendering) — both edit `web/src/api/client.js`.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/architecture-plan.md     # cross-cutting: data layer + 10 components
```

## Relevant Context — Do Not Deviate Without Escalation

**1. The endpoint this consumes.**
Source: OTA-762.
`GET /api/v1/config/strategies` returns, per strategy: `strategy_key`, `display_name`, `consumer_surface`, `compatible_structures`, `verdict_band_set`, `dte_min`, `dte_max`, and per-criterion weights. Fetch via `web/src/api/client.js`.

**2. Field classification — what moves vs what stays.**
Source: OTA-762 Phase 0 §2.
- **Remove from `web/src/strategy-configs/` (now API-sourced):** `scoring_weights`, `compatible_structures`, `dte_min`, `dte_max`.
- **Keep (presentation):** `key`, `short_code`, `label`, `tabLabel`, `description`, `color_bg`, `color_text`, `scorecardStrategy`, `enabled`, `non_applicable_reason`.
- **`configSchema` STAYS (presentation).** ConfigDrawer slider bounds (delta / IV-rank / exit% / stop-loss min/max/default/step) are UX control bounds, not engine rules. Do NOT move them to the API. *(Ruling 2026-06-03.)*
- Bands: `verdict_band_set` is not in the frontend configs — nothing to remove. OTA-660 can now read 70/50 from the API.

**3. Module-load-time derived maps must relocate.**
Source: OTA-762 Phase 0 §3.
`strategy-configs/index.js` computes `STRATEGY_KEY_MAP`, `SHORT_CODE_MAP`, and a `short_code` uniqueness assertion **at import time**. With async fetch-once these cannot exist at import — relocate them into the provider/hook that owns the fetched config. No import-time derivation of canonical maps may remain.

**4. This is a 10-site migration, not a swap.**
Source: OTA-762 Phase 0 §3.
Ten sites statically import named exports (`STRATEGY_CONFIGS`, `SCORECARD_STRATEGIES`, `STRATEGY_KEY_MAP`, `getStrategiesForStructure`) and must convert to a hook read: `ConfigDrawer.jsx`, `Layout.jsx`, `ScanCard.jsx`, `StrategyScorecard.jsx`, `SystemVarsPanel.jsx`, `PositionsPage.jsx`, `StrategyPage.jsx`, `StrategyProfilePage.jsx`, `TradesPage.jsx`, `utils/strategyColors.js`. Handle loading/empty state (the data is now async, not import-time constant).

**5. Dead reference cleanup.**
Source: OTA-762 Phase 0 (OTA-779 confirmation).
The `steady-paycheck.config.js` comment referencing `strategy_scorer.py` is dead (that module was deleted under OTA-779). Remove it.

**6. House style.**
Source: `UI-GUIDANCE.md`; `CLAUDE.md` House Style.
Dark-theme CSS variables only (no inline hex); strategy names in their assigned color; scores `##.00`; dates `mm-dd-yyyy`. No behavior or visual change — this is a data-source refactor only.

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)

Read-only. Confirm and report GO, or STOP on contradiction:
1. `GET /api/v1/config/strategies` exists and returns the §1 shape (OTA-762 committed). If absent → STOP (blocked by OTA-762).
2. The 10 consumer sites and their imported names still match §4 (re-grep — the list may have drifted).
3. The module-load derived maps in `strategy-configs/index.js` are as described in §3.
4. Confirm `configSchema` is present and is the slider-bounds structure (stays).

## Scope
- A provider/hook (e.g. `useStrategyConfigs`) that fetches `GET /api/v1/config/strategies` once via `client.js`, owns the relocated derived maps, and exposes them + the canonical fields.
- Migrate the 10 consumer sites from static imports to the hook; handle async loading state.
- Strip canonical fields (`scoring_weights`, `compatible_structures`, `dte_min`, `dte_max`) from `strategy-configs/*`; keep presentation + `configSchema`.
- Remove the dead `strategy_scorer.py` comment.

## Acceptance criteria
- `grep` confirms no `scoring_weights` / `compatible_structures` / `dte_min` / `dte_max` literals remain in `web/src/strategy-configs/`.
- All 10 sites read via the hook; no static import of canonical data remains; `grep` for the old named-export imports of canonical data is clean.
- No import-time derivation of canonical maps in `strategy-configs/index.js`; derived maps live in the provider/hook.
- Presentation fields + `configSchema` still present in `strategy-configs/`.
- No visual/behavioral regression across the 10 surfaces (loading states handled).

## Out of scope
- The backend endpoint (OTA-762).
- F13 Strategy Admin write UI (OTA-782 → 793).
- Moving `configSchema` to the API.

## Verification steps
Regression Level 2 (cross-cutting frontend refactor): manual click-through of the affected surfaces.

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web"
npm run dev
```
1. Each of the 10 surfaces renders correctly with config sourced from the API (ConfigDrawer, scorecards, scan card, strategy pages, positions, trades, layout, system vars, strategy colors).
2. `grep -rn "scoring_weights\|compatible_structures\|dte_min\|dte_max" web/src/strategy-configs/` → clean.
3. `grep -rn "STRATEGY_CONFIGS\|SCORECARD_STRATEGIES\|STRATEGY_KEY_MAP\|getStrategiesForStructure" web/src/` → only the provider/hook, not the 10 sites' canonical reads.
4. Strategy colors and labels unchanged; no console errors on load.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)
*(Self-contained frontend refactor. Stage and present the message; Don executes.)*

## Coordination footer
Independent — no downstream dependency. *(Gated at the front by OTA-762; not concurrent with OTA-763.)*

## Commit message template
```
OTA-821 refactor: frontend consumes canonical strategy config API; kill the dual-source mirror

- useStrategyConfigs hook fetches GET /api/v1/config/strategies; derived maps relocated from index.js
- 10 consumer sites migrated from static imports to hook read
- canonical fields removed from strategy-configs/ (presentation + configSchema kept)
- dead strategy_scorer.py comment removed (OTA-779)
- Regression Level 2
```
