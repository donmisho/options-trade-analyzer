# OTA-637 — Frontend: pill rendering, best_fit null handling, verdict source unification

## Terminal context
- This terminal: Terminal A (single-stream — W2 of routing-fix build schedule)
- Concurrent terminals: none
- Cross-terminal dependencies: OTA-636 must be committed and deployed (or at minimum committed and locally testable) before this Story starts. The backend null-score and null-best_fit contracts must be live or the frontend changes can't be verified.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/architecture-plan.md
```

Plus, before editing any frontend file:

```
cat web/src/pages/TradesPage.jsx
cat web/src/config/verticals-columns.js
cat web/src/config/long-options-columns.js
```

And the trade-detail expansion components plus the Security Strategies card component. Find them in PowerShell with `Get-ChildItem -Recurse web/src -Filter "*.jsx" | Select-String "best_fit\|Best fit\|verdict"`.

## Relevant Context — Do Not Deviate Without Escalation

**Source: UI-GUIDANCE.md → Part 8 (Claude's Voice — Best Fit badge)**
Best Fit label format: `Best fit: {strategy.display_name}`. White outlined badge. Strategy name slot in strategy color when populated; "none" in muted gray when null.

**Source: UI-GUIDANCE.md → Part 3 (Color tokens)**
No inline hex anywhere. CSS variables only. The `var(--bg2)` token is restricted to filter bars, QuoteBar, and pill-badge backgrounds — never apply it to table rows.

**Source: UI-GUIDANCE.md → Part 4 (Formatting)**
All scores formatted `##.00`. Probabilities as `##.00%`. No `$` prefix on any monetary value. Dates always `mm-dd-yyyy` via `formatDate()`.

**Source: UI-GUIDANCE.md → Part 10 (Buttons)**
Buttons sized to content, never full-width.

**Source: OTA-636 backend contract**
After OTA-636 lands:
- A spread's per-strategy score may be `null` (not `0` or missing — explicitly `null`).
- `best_fit` may be `null`; when null, `best_fit_reason` is a populated string explaining why.
- The MMM 146/136 Bear Put will return `score(SP) = null`, `score(WG) = null`, `score(TR) = <number>`, `score(LT) = null` (or whatever LT compatibility resolves to), `best_fit = "trend_rider"`.

**Source: CLAUDE.md → No commits made by Claude Code unless instructed**
Don commits manually. Commit message references OTA-637 for Jira auto-closure.

## Scope

This Story aligns the frontend to the null contracts that OTA-636 introduces. Three target surfaces: row pills (Trades grid and Security Strategies cards), the Best Fit label (trade detail header), and the verdict (pill + narrative source unification).

### Phase 1 — Read-only diagnostic (mandatory stop-and-report)

1. `cat` every file in Required Reading above.
2. Locate where strategy pills are rendered on Trades-page rows. Report the file path, the component name, and a 5-line summary of the current pill-rendering logic — specifically: how does it decide which strategies to render pills for?
3. Locate where the Best Fit label is rendered in the trade detail header. Report the file, component, and current rendering logic.
4. Locate the verdict pill rendering and the narrative verdict-word rendering. Report whether they currently read from the same field on the verdict object. If not, report what each reads from.
5. Locate the Security Strategies card pill rendering. Report whether it shares a component/utility with the Trades grid or duplicates logic.

**STOP at the end of Phase 1.** Report findings to Don. Do not edit any file. Wait for "proceed to Phase 2" before continuing.

### Phase 2 — Implementation

#### 2a. Strategy pill rendering (Trades grid + Security Strategies cards)
- Audit pill rendering wherever strategies are displayed on a spread row.
- Render a pill only when the strategy's score for that spread is non-null. Null score → no pill, no tooltip, no placeholder dash. The strategy simply does not appear for that spread.
- This change applies symmetrically to Trades-page rows and Security Strategies cards. If they share a utility, fix at the utility. If they don't, fix both sites and add a TODO comment about consolidation (do not consolidate in this Story; out of scope).

#### 2b. Best Fit label — null state
- Trade detail header reads `best_fit` from the spread.
- When `best_fit` is populated: `Best fit: {strategy.display_name}` per UI-GUIDANCE Part 8. Strategy name in strategy color.
- When `best_fit` is null: `Best fit: none` with `best_fit_reason` as hover tooltip. "none" in muted gray (use the existing muted-text CSS variable; do not introduce a new color token).
- Same white outlined badge shape in both cases. No layout shift between the two states.

#### 2c. Verdict pill / narrative source unification
- Identify the field producing the verdict pill (likely `verdict.verdict` or `verdict.banner` — confirm in Phase 1).
- Identify the field producing the narrative's verdict word.
- They MUST read from the same field. Update whichever side disagrees so both read from the canonical field.
- Remove any frontend logic that re-derives verdict from score thresholds or other heuristics. Single source of truth: the backend's verdict field.

#### 2d. Path A pre-filter — Trades-page request shaping
When the Trades page is loaded with strategy context (`?strategy={key}` in URL, or strategy selected in a strategy-picker if one exists):
- The verticals/long-options request to the backend includes the active strategy.
- Backend already (post-OTA-636) returns only compatible structures for an active strategy. No frontend filtering is required, but as a defensive guard: client-side, drop any row where `this_strategy ∉ spread.eligible_strategies` (a defensive belt-and-suspenders check).
- If `?strategy={key}` is the URL pattern but is not currently honored in the page's data-fetch logic, wire it now.

#### 2e. Reduced pill density audit
- After 2a lands, Bear Put symbols (and any debit-structure-heavy symbol) will display fewer pills per row than before. This is correct behavior, not a regression.
- Verify rows still render cleanly with one pill, with no pill (the `best_fit = null` case), and with two pills (the bull-put-credit case at 30 DTE that fits both SP and WG).
- No layout collapse, no missing-element placeholder. The row's structure is stable across pill count.

### Phase 3 — Manual verification

1. Load `/trades?strategy=steady-paycheck&symbol=MMM`. Grid is empty or only shows surviving Bull Put Credits.
2. Load `/trades?symbol=MMM` (no strategy context). Bear Put rows appear with TR pill only.
3. Expand the MMM 146/136 Bear Put. Trade detail header reads `Best fit: Trend Rider {TR score}`. Verdict computed against Trend Rider.
4. Find a `best_fit = null` case (a spread that fails all strategy gates for its compatible structure). Confirm header reads `Best fit: none` with tooltip.
5. Load a known-bullish symbol with healthy IV at ~30 DTE. Find a Bull Put Credit. Confirm two pills (SP and WG). Confirm Best Fit picks the higher-scoring of the two.
6. On any spread: verdict pill word equals narrative verdict word. No contradictions.

## Acceptance criteria

- [ ] Strategy pills render only when score is non-null. No zero-fill, no placeholder dash.
- [ ] `Best fit: none` renders correctly with `best_fit_reason` as tooltip when backend returns null. Layout stable across populated/null states.
- [ ] Verdict pill always equals narrative verdict word. Both read from the same backend field.
- [ ] Path A: `/trades?strategy={key}` correctly pre-filters the grid to that strategy's compatible structures.
- [ ] Reduced pill density on Bear Put symbols (one TR pill per row) is the correct, intended state — no layout regression.
- [ ] Security Strategies cards render only compatible strategies per spread.
- [ ] All UI-GUIDANCE conventions honored: `##.00` formatting, no `$` prefix, formatDate() for dates, no inline hex, no `var(--bg2)` on table rows.
- [ ] Manual click-through of Path A and Path B on both a credit-spread symbol and a debit-spread symbol passes.

## Out of scope

- Backend changes — OTA-636.
- Verdict/narrative regression test fixtures — OTA-645.
- Security Strategies grid cell-score N/A semantics (different from pill rendering) — OTA-649.
- Positions surface — OTA-650.
- Path B grouped-by-strategy display — OTA-651.
- Consolidation of duplicated pill-rendering utilities (TODO only).
- Narrative content rewrite.

## Verification steps

1. Hard refresh in browser; do not rely on cached bundle.
2. Run the manual verification list from Phase 3 above (6 items) on both dev and a built bundle if available.
3. Inspect the Network tab on `/trades?strategy=steady-paycheck&symbol=MMM` — confirm the request payload includes the strategy and the response excludes debit structures.
4. Run the frontend test suite if one exists for these components: `cd web && npm test`.
5. Sanity check: open the Security Strategies page for MMM, confirm cards display only the strategies with non-null scores. (This is preview behavior — OTA-649 changes the cell-score model itself, but pill rendering should be correct after this Story.)

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

OK to continue to **OTA-645-verdict-narrative-regression.md**

## Commit message template

```
OTA-637 feat: align frontend to compatibility-gated scoring model

- Strategy pills render only for non-null scores (Trades grid +
  Security Strategies cards)
- Best Fit label handles best_fit=null: "Best fit: none" with
  best_fit_reason as tooltip; layout stable across states
- Verdict pill and narrative verdict word unified to single backend
  field; removed client-side re-derivation from score thresholds
- Path A pre-filter: /trades?strategy={key} pre-filters grid;
  defensive client-side filter for eligible_strategies membership
- Reduced pill density on debit-structure rows is correct behavior

Honours UI-GUIDANCE: ##.00 formatting, no $ prefix, no inline hex,
formatDate() for dates, var(--bg2) restricted to filter bars and pill
backgrounds.

Depends on OTA-636.
```
