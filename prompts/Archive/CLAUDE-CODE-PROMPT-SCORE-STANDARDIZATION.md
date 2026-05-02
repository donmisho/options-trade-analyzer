# Claude Code Prompt — Score Standardization
## All Scores 0–100, Formatted ##.00 Everywhere

---

## Before you write a single line of code, read and report first.

Do the following in order and report your findings before making any changes:

1. `cat app/analysis/vertical_engine.py` — find where the composite score is computed and returned. Answer:
   - Is the final composite score returned as a 0–1 decimal (e.g. `0.72`) or a 0–100 integer/float (e.g. `72`)?
   - Are the sub-component contributions in `score_breakdown` on a 0–1 scale or 0–100 scale?
   - What is the exact field name for the composite score in the response?

2. `cat app/analysis/long_call_engine.py` — same questions as above for the long call engine.

3. `cat app/models/schemas.py` — find `ScoreBreakdown`, `MetricBreakdown`, or equivalent. Answer:
   - What scale are `contribution`, `normalized`, and `composite_score` fields defined on?
   - Are there any `float` fields with validation constraints (e.g. `ge=0, le=1`) that would break if we switch to 0–100?

4. `cat web/src/components/ResultsTable.jsx` — find where the score value is rendered in the table row. Answer:
   - Is `score` rendered as-is, or is there a multiplication or formatting step?
   - Is there a score bar — and if so, what is it normalized against (1.0 or 100)?

5. `cat web/src/pages/OptionsTerminal.jsx` — find the expansion panel score display. Answer:
   - Where is `composite` rendered (the total row at the bottom)?
   - Where are individual metric contributions rendered?
   - Is there any `* 100` multiplication already in the display code?

Report your findings as a brief summary: "Backend returns X scale, frontend displays Y scale, discrepancy is Z." Then proceed.

---

## Context

You are working on Options Analyzer, a FastAPI + React options trading analysis app.

Read these files before making any changes:

```
cat app/analysis/vertical_engine.py
cat app/analysis/long_call_engine.py
cat app/models/schemas.py
cat web/src/components/ResultsTable.jsx
cat web/src/pages/OptionsTerminal.jsx
cat CLAUDE.md
```

This is a **standardization fix**, not a new feature. The goal is one consistent standard applied everywhere:

> **All scores — composite and every sub-component contribution — are on a 0–100 scale and formatted to exactly two decimal places (##.00). No exceptions.**

Current state: the inline row score and the expansion panel composite are showing different values for the same trade (e.g. `0.64` vs `54`). This is a scale mismatch between backend output and frontend display.

---

## The Standard

| Location | Required format | Example |
|----------|----------------|---------|
| API response — composite score | `float`, 0–100 scale | `72.00` |
| API response — each metric contribution | `float`, 0–100 scale | `8.40` |
| API response — each metric normalized value | `float`, 0–1 scale | `0.78` (unchanged — this is a ratio, not a score) |
| ResultsTable inline row | `##.00` string | `"72.00"` |
| Expansion panel — each contribution | `##.00` string | `"8.40"` |
| Expansion panel — total row | `##.00` string | `"→ 72.00"` |
| Score bar fill width | normalized against 100 | `width: 72%` |
| ConfigDrawer score display (if any) | `##.00` string | `"72.00"` |

**The `normalized` field (0–1) is NOT changed.** It represents a ratio used internally for the bar width and contribution calculation. Only `contribution` and `composite_score` move to 0–100.

---

## Backend Changes

### `vertical_engine.py`

Find the line where the composite score is computed from the weighted contributions. It likely looks something like:

```python
composite = sum(weight * normalized for weight, normalized in ...)
# or
composite = ev_contrib + rr_contrib + prob_contrib + liq_contrib + theta_contrib
```

**Change:** Multiply the final composite by 100 before returning it. Round to 2 decimal places.

```python
composite_score = round(sum_of_contributions * 100, 2)
```

For each metric contribution in `score_breakdown`, also multiply by 100 and round to 2:

```python
contribution = round(weight * normalized_value * 100, 2)
```

After this change, contributions should sum to `composite_score` within floating point tolerance. Verify: `sum(m.contribution for m in metrics)` should equal `composite_score` (within 0.01 rounding tolerance).

### `long_call_engine.py`

Apply the identical change. Same pattern — composite × 100, each contribution × 100, round to 2.

### `schemas.py`

Update the `ScoreBreakdown` / `MetricBreakdown` schema:

- `contribution: float` — if it has a validator `ge=0, le=1`, remove that constraint. The new range is 0–35 (for a 35% weighted metric at full score).
- `composite_score: float` — if it has `ge=0, le=1`, change to `ge=0, le=100`.
- `normalized: float` — leave any `ge=0, le=1` constraint unchanged. This field stays 0–1.

Add a docstring comment to `ScoreBreakdown`:

```python
class ScoreBreakdown(BaseModel):
    """
    Score breakdown for a single trade.
    All contribution and composite_score values are on a 0-100 scale, formatted to 2dp.
    normalized values remain on a 0-1 scale (used for bar widths and internal math).
    """
```

---

## Frontend Changes

### `ResultsTable.jsx` — Inline Score Display

Find where `trade.score` (or equivalent field) is rendered in the table row.

**Change:** Format it to exactly 2 decimal places.

```javascript
// Replace whatever is there with:
{typeof trade.score === 'number' ? trade.score.toFixed(2) : '—'}
```

**Score bar** (if present in the results row): normalize against 100, not 1.

```javascript
// Bar fill width
style={{ width: `${Math.min(trade.score, 100)}%` }}
// Not: style={{ width: `${trade.score * 100}%` }}
```

### `OptionsTerminal.jsx` — Expansion Panel

Find the section that renders the score breakdown (columns 1 and 2 of the expansion panel).

**Individual metric contributions:** format to 2 decimal places.

```javascript
// Each contribution value
{metric.contribution.toFixed(2)}
```

**Composite total row** at the bottom of column 2:

```javascript
// The "composite = XX" line
composite = {scoreBreakdown.composite_score.toFixed(2)}
```

And the colored composite value rendered to the right:

```javascript
// The large colored number
{scoreBreakdown.composite_score.toFixed(2)}
```

**Score bars in the expansion panel** (the horizontal bars showing normalized contribution): these should remain normalized against 1.0 (the `normalized` field, not `contribution`). Do not change these bars.

**Verify no `* 100` multiplications remain in the frontend display code.** After the backend change, the API already returns 0–100 values. Any frontend code that was previously doing `contribution * 100` or `score * 100` to compensate must be removed — it will now double-count.

Search for these patterns and remove them if found:
```javascript
// Remove any of these:
score * 100
contribution * 100
composite * 100
.score * 100
```

---

## Verification

After making all changes, restart the backend and reload the frontend. Then verify:

1. Run a vertical spread analysis on any symbol
2. Expand a trade row
3. Check that the inline score in the results row (e.g. `72.00`) matches the composite shown at the bottom of the expansion panel (e.g. `→ 72.00`)
4. Add up the five contribution values shown in column 2 manually — they must sum to the composite score within 0.01
5. Check that no score anywhere shows a value like `0.72` (un-multiplied) or `7200` (double-multiplied)
6. Run a long call analysis — confirm scores are also on 0–100 scale with 2dp format

---

## Definition of Done

Before ending the session, confirm all of the following:

- [ ] `vertical_engine.py`: composite score returned as 0–100, rounded to 2dp
- [ ] `vertical_engine.py`: each metric contribution in score_breakdown returned as 0–100, rounded to 2dp
- [ ] `long_call_engine.py`: same as above
- [ ] `schemas.py`: validators updated to allow 0–100 range on contribution and composite_score
- [ ] ResultsTable: inline score renders as `##.00` (e.g. `72.00`, not `0.72` or `72`)
- [ ] ResultsTable: score bar normalized against 100
- [ ] Expansion panel: each contribution renders as `##.00`
- [ ] Expansion panel: composite total renders as `##.00`
- [ ] No `* 100` multiplications remain in the frontend display code
- [ ] Inline row score and expansion panel composite show identical values for the same trade
- [ ] Five contributions sum to composite score (verified manually for at least one trade)
- [ ] Long call scores also display correctly on 0–100 scale with 2dp
