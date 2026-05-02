# OTA-158 OTA-159 OTA-160 OTA-161: Strategy Fit Panel

## Tickets
- OTA-158: Strategy Fit panel: show matched strategy parameters (✓/✗ grid)
- OTA-159: Strategy Fit panel: score calculation breakdown
- OTA-160: Strategy Fit panel: consistent expand/collapse behavior
- OTA-161: Strategy Fit panel: select a strategy row to see its details

## Context
The StrategyScorecard shows 4 strategy rows with scores and a progress bar.
When a user clicks a strategy row, a Strategy Fit panel should expand below
it showing WHY that strategy scored what it scored.

## Step 1 — Read current state first
cat web/src/components/StrategyScorecard.jsx
cat web/src/api/client.js | grep -n "scorecard\|score" | head -20

## Step 2 — Understand the scorecard API response
The POST /api/v1/analyze/scorecard response includes per-strategy data.
cat app/api/analysis_routes.py | grep -n "scorecard" -A 30
cat app/analysis/strategy_scorer.py | grep -n "return\|score\|signal\|check" | head -60

Identify what fields are returned per strategy — specifically any signal
checks, parameter matches, or sub-scores.

## Step 3 — Build StrategyFitPanel component
Create web/src/components/StrategyFitPanel.jsx

The panel must show:
1. Parameter match grid (OTA-158)
   - A ✓/✗ grid showing which strategy criteria the current trade meets
   - Example rows: "DTE in range", "Credit ≥ 30% of width", "IV rank > 30"
   - Green ✓ for pass, red ✗ for fail, amber ~ for marginal
   - Pull criteria from the scorecard API response signal checks

2. Score breakdown (OTA-159)
   - Show the sub-component scores that add up to the total score
   - Each sub-score as a labeled bar (same style as existing score bars)
   - Label, value (##.00), and proportional bar

3. Expand/collapse (OTA-160)
   - Panel animates open/closed with CSS transition (max-height or opacity)
   - Only one panel open at a time — clicking a new row closes the previous
   - Chevron indicator on each strategy row (▶ collapsed, ▼ expanded)
   - Teal top border on expanded panel (house rule from existing expansion panels)

4. Selection behavior (OTA-161)
   - Clicking a strategy row toggles its fit panel
   - Selection (checkbox) and expansion (row click) are independent:
     checkbox = include in evaluation, row click = show fit details
   - Clicking checkbox does NOT expand the panel
   - Clicking anywhere else on the row DOES expand the panel

## Step 4 — Wire into StrategyScorecard.jsx
- Import StrategyFitPanel
- Add expandedStrategy state (null or strategy key)
- Pass relevant scorecard data into StrategyFitPanel
- Render panel inline below each strategy row when expanded

## Step 5 — House style rules
- No $ prefix issues — scores are 0-100, no currency here
- Score format: ##.00
- No full-width buttons
- Dark theme colors: use CSS variables (--color-bullish, --color-warning, etc.)
- Font sizes consistent with existing scorecard rows

## Step 6 — Verify
- Click a strategy row → panel expands with parameter grid and score breakdown
- Click same row → panel collapses
- Click different row → previous closes, new one opens
- Checkbox still works independently for evaluation selection

## Commit message
OTA-158 OTA-159 OTA-160 OTA-161: Strategy Fit panel with parameter grid,
score breakdown, and expand/collapse behavior
