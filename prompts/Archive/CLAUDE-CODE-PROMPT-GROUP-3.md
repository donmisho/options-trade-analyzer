# Claude Code Prompt — UI Overhaul Group 3
## Puts & Calls Expansion Panel + Formula Transparency

---

## Before you write a single line of code, answer this question:

**Has any part of this group already been completed?**

Check the following and report what you find — one sentence of evidence per item:

1. `cat web/src/pages/OptionsTerminal.jsx` — find the Puts & Calls expansion panel section. Look for:
   - A `trade_structure` or `payoff_type` read from the strategy config that drives which strategies are scored vs. grayed out. If filtering is driven by config (not hardcoded strategy names), P-1 may be done.
   - A grayed-out / dimmed strategy row with a reason string (e.g. "requires credit spread structure") and a dashed divider above it. If this exists, P-2 may be done.

2. `cat web/src/strategy-configs/index.js` (or list `web/src/strategy-configs/`) — look for a `trade_structure` or `payoff_type` field on each strategy config object. If it exists on all four strategies, P-1's data source is ready.

3. `cat web/src/components/FormulaBreakdown.jsx` — look for references to real API data (fetched values, `score_breakdown`, `metric_contributions`, or similar). If it's wired to live scoring data rather than static/mock values, G-4 may be done.

For each item: **"Already done"** or **"Not done"** with one sentence of evidence. Proceed only with items that are not done.

---

## Context

You are working on Options Analyzer, a FastAPI + React options trading analysis app.

Read these files before making any changes. Do not rely on memory from a previous session — cat the actual files:

```
cat web/src/pages/OptionsTerminal.jsx
cat web/src/components/FormulaBreakdown.jsx
cat web/src/strategy-configs/index.js
cat UI-DECISIONS.md
cat CLAUDE.md
cat UI-OVERHAUL-COMPLETION-PLAN.md
```

The canonical spec for all interaction and visual behavior is in `UI-DECISIONS.md`. When in doubt, it wins.

**Critical architecture rule:** Sub-components defined outside the main React component. Do not define new components inside `OptionsTerminal` — put them above the export, at module level.

---

## Scope of This Session

Complete Groups 3 and 4 of the UI Overhaul Completion Plan.

---

# GROUP 3 — Puts & Calls Expansion Panel

The Puts & Calls page uses the same `OptionsTerminal.jsx` as Verticals. The expansion panel structure is identical — same 4-column grid, same verdict card. The only difference is how strategy rows are filtered in Column 3.

---

## P-1 — Strategy Fit Filtered by `trade_structure` Field

**Files:** `web/src/strategy-configs/*.config.js`, `web/src/pages/OptionsTerminal.jsx`

**The rule from `UI-DECISIONS.md`:**
- Filtering MUST be driven by the `trade_structure` field in strategy config files.
- NEVER hardcode strategy names in filter logic.
- A new `long_option` strategy added in the future must automatically appear without code changes.

**Step 1: Ensure `trade_structure` exists on all four strategy configs.**

Each strategy config file must have a `trade_structure` field with one of two values:
- `"credit_spread"` — for Steady Paycheck and Weekly Grind
- `"long_option"` — for Trend Rider and Lottery Ticket

Open each config file in `web/src/strategy-configs/`. If any are missing the `trade_structure` field, add it. Do not rename or restructure anything else in the config.

**Step 2: Wire the filter in the expansion panel.**

The Puts & Calls expansion panel's Column 3 must filter strategy rows based on the current page context. The page context is already available — `OptionsTerminal.jsx` knows whether it is rendering Verticals or Puts & Calls (look for the route or prop that distinguishes them).

For the **Puts & Calls context:**
- Import all strategy configs from `strategy-configs/index.js`
- Split into two arrays using `trade_structure`:
  - `applicableStrategies` — where `strategy.trade_structure === 'long_option'`
  - `nonApplicableStrategies` — where `strategy.trade_structure !== 'long_option'`
- Render `applicableStrategies` as normal scored rows (exactly as Column 3 works on Verticals)
- Render `nonApplicableStrategies` as grayed-out rows below a dashed divider (see P-2)

For the **Verticals context:** no change — all four strategies render as before.

---

## P-2 — Grayed-Out Non-Applicable Strategies

**File:** `web/src/pages/OptionsTerminal.jsx` — Column 3 of the Puts & Calls expansion panel

**Spec from `UI-DECISIONS.md`:**
> Non-applicable strategies are shown grayed out below a divider labeled "not applicable to this trade type"

**Build this exactly:**

After the last applicable strategy row, render:

```
── ── ── ── not applicable to this trade type ── ── ──
```

This is a dashed horizontal rule with centered label text. Style:
```css
border-top: 1px dashed #30363d;  /* --border */
color: #8b949e;                   /* --muted */
font-size: 9px;
text-align: center;
margin: 8px 0;
letter-spacing: 0.4px;
text-transform: uppercase;
```

Below the divider, render each non-applicable strategy as a dimmed row:
- Same visual layout as a normal strategy row (name, score bar area, score number)
- BUT: `opacity: 0.35` on the entire row
- Score bar is empty / zero-width (no score is computed for non-applicable strategies)
- Score number replaced with `—` (em dash) in muted text
- Not clickable — `pointer-events: none` on the row
- Below the strategy name (same position as the "why" text from V-1): show the reason in 9px italic muted text:
  - For Steady Paycheck: `"requires credit spread structure"`
  - For Weekly Grind: `"requires credit spread structure"`
  - **Important:** these reason strings should come from the strategy config, not be hardcoded in the render logic. Add a `non_applicable_reason: string` field to the two credit spread strategy configs.

---

## P-3 — Verdict Card Confirmed for Long Option Context

**File:** `web/src/pages/OptionsTerminal.jsx` — the verdict card (already built for Verticals)

The verdict card component is already built and working for vertical spread trades. For Puts & Calls, it renders for a long option trade (single leg — a call or put).

**Check the following and fix anything that breaks:**

1. **Exit Plan column (Verdict body col 2):** Vertical spreads have a defined max loss (spread width minus credit). Long options have a defined max loss (premium paid). Confirm the Exit Plan column renders correctly for both. Specifically:
   - HARD STOP row: for a long call, this is a price below which the trade is abandoned (e.g. underlying price, not a spread price). Confirm the label and value make sense for a long option.
   - TAKE PROFIT: for a long call, this is a target underlying price or option value. Confirm it renders.

2. **Trade reference in the Verdict Header:** The trade reference string (symbol · type · strikes · expiry · credit) needs to render correctly for a long option. A long call has no "sell strike" — the format should be: `AAPL · Long Call · 185C · Apr 17 · 3.40 debit`. Confirm the trade reference formatting handles both spread and single-leg trades without showing undefined or blank fields.

3. **Pre-Screen Checks (col 3):** Confirm no vertical-spread-specific check (e.g. "spread width > minimum") renders for a long option trade. Pre-screen checks should be filtered by the trade type.

Fix any of the above that are rendering incorrectly. If the verdict card works correctly for long options as-is, write "P-3: No changes needed — verdict card renders correctly for long option context" and move on.

---

# GROUP 4 — Formula Transparency with Real Data

## G-4 — Wire FormulaBreakdown to Real Scoring Data

**Files:** `web/src/components/FormulaBreakdown.jsx`, `app/api/analysis_routes.py`, `app/models/schemas.py`

**Current state:** `FormulaBreakdown.jsx` exists and renders, but shows static/mock scoring data. The user sees score bars and numbers that don't reflect the actual trade they're looking at.

**Goal:** When a user expands a trade row and opens FormulaBreakdown, they see the real scoring math for that specific trade: raw metric values → normalized scores → weighted contributions → composite score. The numbers must add up correctly.

### Step 1: Confirm the backend returns score breakdown data

Check the response shape of `POST /api/v1/analyze/verticals` (and long-calls). Specifically, look at what's returned per trade in `app/models/schemas.py`.

The response for each trade must include a `score_breakdown` object. If it doesn't exist yet, add it to the response schema and populate it in `vertical_engine.py`.

The `score_breakdown` shape should be:

```python
class MetricBreakdown(BaseModel):
    raw_value: float          # the actual number (e.g. expected value = 0.18)
    normalized: float         # 0.0 to 1.0 after min-max normalization
    weight: float             # e.g. 0.35 for Expected Value
    contribution: float       # normalized * weight (e.g. 0.35 * 0.78 = 0.273)
    formula: str              # human-readable formula string, e.g. "(credit / width) * prob_profit"

class ScoreBreakdown(BaseModel):
    expected_value: MetricBreakdown
    reward_risk: MetricBreakdown
    probability: MetricBreakdown
    liquidity: MetricBreakdown
    theta_efficiency: MetricBreakdown
    composite_score: float    # must equal sum of all contributions * 100, rounded
```

**Integrity rule:** `sum(m.contribution for m in metrics) * 100` must equal `composite_score`. If the engine currently has a rounding difference, fix it here — this is the scoring math integrity requirement.

### Step 2: Wire FormulaBreakdown.jsx to real data

`FormulaBreakdown.jsx` receives the `trade` object as a prop. After Step 1, `trade.score_breakdown` contains the real data.

Update `FormulaBreakdown.jsx` to render from `trade.score_breakdown` instead of any mock or hardcoded values.

**Per metric row, render:**
- Colored dot (metric color — these are fixed, see below) + metric name + weight badge (e.g. `"35%"`)
- Formula string in 9px italic muted text: `trade.score_breakdown[metric].formula`
- 3px horizontal bar showing `trade.score_breakdown[metric].normalized` (0–1 scale), colored to match the metric dot
- The actual numbers: raw value + normalized + weighted contribution
- The contribution value in the metric color (e.g. `+0.273`)

**At the bottom, a total row:**
- Shows each contribution in sequence: `0.273 + 0.187 + ... → 88`
- "→ 88" is the composite score, rendered in white or teal

**Metric colors — fixed, never change:**
```
Expected Value:    #60a5fa  (blue)
Reward:Risk:       #2dd4bf  (teal)
Probability:       #f59e0b  (amber)
Liquidity:         #c084fc  (purple)
Theta Efficiency:  #f87171  (red)
```

### Step 3: Verify the numbers add up

Before calling this done, verify with one real trade:
1. Run an analysis on any symbol
2. Expand a trade row and open FormulaBreakdown
3. Add up the five contribution values manually
4. The sum × 100 must equal the composite score shown in the results table (within ±1 for rounding)

If there's a discrepancy, trace it back to `vertical_engine.py` and fix the normalization or rounding.

---

# ⚑ TESTING BREAKPOINT — Login and Test Before Continuing

**Stop here after Groups 3 and 4 are complete. Do not start Group 5 (left nav) until you have manually tested the app.**

The left nav migration touches every page and the root layout. If there are any rendering bugs in the Verticals panel, Puts & Calls panel, or FormulaBreakdown, they are far easier to diagnose before the layout changes around them.

## Testing Checklist — Run This Now

Log into the running app and verify all of the following. Check off each item as you go.

### Verticals Page (regression — confirm Groups 1 & 2 still working)
- [ ] Expand a trade row — all 4 columns render without errors in the browser console
- [ ] Column 3: each strategy row shows a "why" text line (9px italic, muted) below the strategy name
- [ ] Column 4: shows strategy name, subtitle, parameter grid (✓/✗), and signal check box
- [ ] Click a strategy row in Column 3 — Column 4 updates immediately
- [ ] Click Evaluate — animated dots appear on the button, context text appears below it
- [ ] Verdict arrives — card slides in with correct verdict badge, all 3 body columns render
- [ ] Switch strategy while verdict is visible — verdict collapses, button resets to "Evaluate with Claude →"
- [ ] FormulaBreakdown: click to expand for any trade — raw values, normalized scores, contributions, and total row all show real numbers; total adds up to composite score

### Puts & Calls Page
- [ ] Expand a long call trade row
- [ ] Column 3: only Trend Rider and Lottery Ticket show as scored rows
- [ ] Column 3: Steady Paycheck and Weekly Grind appear below the dashed divider, dimmed, with reason text
- [ ] Clicking a dimmed row does nothing (pointer-events: none)
- [ ] Click Evaluate on an applicable strategy — verdict card renders correctly
- [ ] Verdict card trade reference shows the long option format (no sell strike, shows "debit" not "credit")
- [ ] Exit Plan column shows correct price levels for a long option

### Watchlist & QuoteBar (regression — confirm Group 1 still working)
- [ ] Watchlist sidebar shows live prices (not dashes) on page load
- [ ] Click a different symbol in the watchlist — QuoteBar updates
- [ ] Symbol with earnings within 14 days — amber highlight on earnings date
- [ ] Symbol with earnings beyond 60 days — no earnings field shown at all
- [ ] No value in QuoteBar has a `$` prefix

### General
- [ ] Click Follow (Paper) on any verdict — Toast appears top-right, includes "View Positions" link
- [ ] Toast auto-dismisses after ~4 seconds
- [ ] No button on any page stretches to fill its container
- [ ] No errors in the browser console on any page

**If any check fails: fix it before moving on.** Do not start Group 5 with known rendering bugs.

---

## Definition of Done for This Session

Before ending the session, confirm:

- [ ] P-1: `trade_structure` field exists on all 4 strategy configs; Puts & Calls Column 3 filters by it (not by name)
- [ ] P-2: Non-applicable strategies render below dashed divider, dimmed, with reason text from config
- [ ] P-3: Verdict card renders correctly for long option trades (trade reference format, exit plan labels, pre-screen checks)
- [ ] G-4: FormulaBreakdown renders real `score_breakdown` data; contributions sum to composite score
- [ ] All testing checklist items above are checked off
- [ ] No browser console errors on Verticals or Puts & Calls pages

Update `UI-OVERHAUL-COMPLETION-PLAN.md` — change the status of each completed item from 🔲 to ✅.
