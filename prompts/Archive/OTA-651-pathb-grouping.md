# OTA-651 — Path B: symbol-driven recommendation flow on Trades

## Terminal context
- This terminal: Terminal A (W4 of routing-fix build schedule; final sequenced Story)
- Concurrent terminals: none
- Cross-terminal dependencies: OTA-636, OTA-637, OTA-649, and OTA-650 must all be committed and deployed. This Story is the closing piece — the journey-correct shape for symbol-first navigation.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
```

Plus, before editing:

```
cat web/src/pages/TradesPage.jsx
cat web/src/config/verticals-columns.js
cat web/src/config/long-options-columns.js
```

Plus the vertical-spreads and long-options section components. Find them in PowerShell: `Get-ChildItem -Recurse web/src -Filter "*.jsx" | Select-String "Vertical spreads\|Long options"`.

## Relevant Context — Do Not Deviate Without Escalation

**Source: UI-GUIDANCE.md → Part 1 (Two paths — Path B)**
Path B: "Trade first — Scan card click or direct symbol entry → Trades → expand a row → Claude recommends best strategy fit." Today this is implemented as a flat grid scored across all strategies. Corrected behavior: a strategy-grouped result set where the top group is the recommendation.

**Source: business-rules.md → `best_fit` semantics**
A spread's `best_fit` is the highest-scoring strategy among `eligible_strategies(spread)`. Spreads where `best_fit = null` are dropped from Path B's grouping entirely — they have no recommendation.

**Source: OTA-637 frontend behavior**
Trade-detail expansion mechanics inside each section are already correct. This Story only changes the *grouping* and *section ordering* at the page level.

**Source: UI-GUIDANCE.md → Part 3 (Color tokens) and Part 4 (Formatting)**
Section headers use existing strategy color tokens (one per strategy — SP/WG/TR/LT). The "Recommended" badge uses an existing emphasis token (likely the same one used for the Best Fit badge in OTA-637). Do not introduce new tokens.

## Scope

When `/trades?symbol={symbol}` is loaded with no strategy context, the Trades page renders results grouped by `best_fit`. The recommended group is the top-scoring group, rendered expanded with a Recommended badge.

### Phase 1 — Read-only diagnostic (mandatory stop-and-report)

1. `cat` every file in Required Reading.
2. Inspect `web/src/pages/TradesPage.jsx`. Report:
   - How does the page distinguish "strategy context present" from "no strategy context" today?
   - How are spreads currently rendered — flat grid, structure-grouped, strategy-grouped, or other?
   - Where in the response shape does `best_fit` arrive (post-OTA-637)?
3. Inspect the vertical-spreads and long-options section components. Report whether they're currently structure-grouped (one Vertical spreads section + one Long options section) or already strategy-aware.
4. Identify the URL parameter for symbol search. Confirm it's `?symbol={symbol}` and not something else.

**STOP at the end of Phase 1.** Report findings. Wait for "proceed to Phase 2" before continuing.

### Phase 2 — Implementation

#### 2a. Branching logic on page mount
- If `?strategy={key}` is set in URL or strategy context is otherwise present: render in **Path A mode** — the existing structure delivered by OTA-637, unchanged.
- If only `?symbol={symbol}` is set (no strategy context): render in **Path B mode** — the new grouping below.

#### 2b. Path B mode rendering

1. Fetch the eligible spread universe for the symbol (all four structure families). The backend response carries `eligible_strategies` and `best_fit` per spread (post-OTA-636).
2. Drop spreads where `best_fit = null`.
3. Group surviving spreads by `best_fit.key`. Each group is a collapsible section.
4. Within each group, candidates are ranked by `score(spread, best_fit_strategy)` descending.
5. Order groups by their top candidate's score, descending. The first group is the recommendation.
6. Render the recommendation section:
   - Section header: strategy color (per UI-GUIDANCE Part 3), `{strategy.display_name} — Recommended` text with the Recommended badge to the right.
   - Section expanded by default.
7. Render other eligible-strategy sections:
   - Section header: strategy color, `{strategy.display_name}` text, no Recommended badge.
   - Section collapsed by default (user can expand).
8. Below all sections: a thin footer reads `No compatible setups today for: {comma-separated list of strategies with zero eligible candidates}`. If all four strategies have candidates, render `No compatible setups today: none — full coverage for {symbol}` or omit the footer.

#### 2c. Section internals
- Inside each section, render the existing spread-row component (delivered by OTA-637).
- Pill rendering, Best Fit label, verdict, click-through-to-expand mechanics are all unchanged.
- The only change is that the row's column for "score" displays `score(spread, this_section's_strategy)`, not the top score across all strategies (which would be ambiguous in a strategy-grouped view).

#### 2d. URL state
- The grouping is a derived view, not a separately-routed page. The URL remains `/trades?symbol={symbol}`. No new route.
- If the user expands a row, the expansion state should survive page refresh if existing Path A behavior supports that (do not regress the existing behavior; do not add new persistence if it doesn't exist).

### Phase 3 — Visual verification on canonical cases

1. `/trades?symbol=MMM`: one expanded section labeled `Trend Rider — Recommended` populated with the Bear Put candidates ranked by TR score. Footer reads `No compatible setups today for: Steady Paycheck, Weekly Grind`. LT either has a section (collapsed, below Trend Rider) or appears in the footer depending on whether any single-long candidates pass LT gates.
2. `/trades?symbol={bullish symbol with healthy IV}`: Steady Paycheck and Weekly Grind sections rendered (one recommended, the other collapsed); Trend Rider section if any Bull Call debits pass gates; LT per single-leg availability.
3. `/trades?strategy=steady-paycheck&symbol=MMM`: Path A mode — the existing OTA-637 behavior. Grid filtered to SP-compatible candidates only (likely empty for MMM under current market). No grouping by `best_fit`.

### Phase 4 — Edge cases

- **All-null universe**: `/trades?symbol=XYZ` where no spread passes any strategy's gates. The page renders no sections, just the footer: `No compatible setups today for: Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket`. Don't show an empty grid or a misleading "loading" state.
- **Single-section universe**: only one strategy has eligible candidates. That section renders expanded with the Recommended badge; no "other eligible" sections; footer lists the three with no candidates.
- **Tie-breaking**: two strategies' top candidates have the same score. Order them by an arbitrary but stable tiebreaker (alphabetical by strategy key is fine). Document the tiebreaker in a code comment.

## Acceptance criteria

- [ ] `/trades?symbol=MMM` renders one expanded section `Trend Rider — Recommended` with Bear Put candidates ranked by TR score; footer notes SP and WG have no compatible setups.
- [ ] `/trades?symbol={bullish symbol with healthy IV}` renders SP and WG sections (higher-scoring recommended); TR if applicable; LT per availability.
- [ ] `/trades?strategy=steady-paycheck&symbol=MMM` uses Path A mode (no `best_fit` grouping).
- [ ] No mixed flat grid — every visible row sits inside a section that owns its strategy.
- [ ] Recommended section visually distinct via existing color and badge tokens; no new tokens.
- [ ] Footer correctly enumerates strategies with zero eligible candidates.
- [ ] All-null universe renders the footer + no sections, not an empty grid.
- [ ] Single-section universe renders one expanded section with Recommended; footer covers the three without setups.
- [ ] Tie-breaking is stable and documented in a code comment.

## Out of scope

- Security Strategies grid click-through landing — OTA-649 (lands on a specific spread, not a grouped view).
- Persistence of user's preferred-strategy override per symbol.
- Cross-symbol comparison views.
- Section collapse/expand persistence beyond what existing behavior supports.
- New URL route for grouped view (stays at `/trades?symbol=X`).

## Verification steps

1. Hard refresh in browser; do not rely on cached bundle.
2. Run the three visual verification cases from Phase 3.
3. Run the three edge cases from Phase 4 — find or construct a symbol that produces each.
4. Inspect the Network tab on `/trades?symbol=MMM` — confirm the backend response carries `best_fit` on each spread.
5. Run any frontend tests if they exist for the Trades page: `cd web && npm test`.
6. Reload the page in the recommended-section-expanded state; confirm no flicker or layout shift on hydration.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

Independent — no downstream dependency. This Story closes the OTA-646 Epic.

## Commit message template

```
OTA-651 feat: Path B symbol-driven recommendation flow on Trades

- /trades?symbol=X groups spreads by best_fit strategy
- Top-scoring group rendered expanded with "Recommended" badge
- Other eligible-strategy sections rendered collapsed
- Spreads with best_fit=null dropped from view
- Footer lists strategies with zero eligible candidates
- /trades?strategy=X&symbol=Y retains Path A mode (no regrouping)
- Edge cases: all-null universe shows footer only, no empty grid
- Tie-breaking stable and documented

Reuses spread-row components from OTA-637; no new color/badge tokens.
Closes OTA-646 Epic when combined with OTA-636/637/645/649/650.
Depends on OTA-636, OTA-637, OTA-649, OTA-650.
```
