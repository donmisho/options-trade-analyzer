---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
---

# OTA-505 — Probability Asymmetry Scoring Factor

**Wave:** AMZN April 22 Scoring Pipeline Fixes v2
**Parent Epic:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Parent Feature:** OTA-501 (Scoring Pipeline Fixes v2 — AMZN Validation April 22)
**Depends on:** OTA-502 (touches same scoring pipeline — run after)
**Relationship to OTA-503:** complementary, not overlapping. OTA-503 is a hard verdict gate for negative EV. OTA-505 is a graduated score penalty for borderline cases where EV is positive-but-thin and asymmetry is still present.

## Context

R:R ratio passing the threshold gate (≥1.5:1 for debit spreads) does not guarantee a positive EV setup when probability distribution is skewed against the trade.

AMZN 260/270 May 15 example:
- R:R: 1.70:1 (passes 1.5 floor)
- Cost % of width: 37% (passes 40% ceiling)
- P(max profit): 29.85%
- P(max loss): 56.66%
- Loss/profit probability ratio: **1.90:1 against**
- Computed EV: −5.86

R:R of 1.70 cannot compensate for 1.90 probability disadvantage. The computed EV already reflects this. The score (70.74) does not.

**Key distinction from OTA-503:** OTA-503 handles the binary negative-EV case — blocks verdict outright. This Story handles the continuous case — when probability skew is present but hasn't tipped EV negative, the score should reflect that risk in a graduated way. Both can ship together and their effects are additive for the worst setups.

## Scoring rule

```python
def asymmetry_penalty(p_max_loss: float, p_max_profit: float) -> int:
    """Graduated penalty based on loss/profit probability ratio."""
    if p_max_profit == 0:
        return 25  # max penalty — degenerate case
    ratio = p_max_loss / p_max_profit
    if ratio >= 2.0:
        return 25
    elif ratio >= 1.5:
        return 15
    elif ratio >= 1.25:
        return 8
    return 0
```

Applied **post-scoring, pre-band-assignment**. The penalty reduces the final score before it maps to EXECUTE/WAIT/PASS thresholds.

## Prerequisites

```bash
cat CLAUDE.md                              # confirm header timestamp is current
pwd                                        # should show ...options-analyzer
venv\Scripts\activate                      # Windows
git status                                 # uncommitted unrelated changes OK
```

If venv isn't activated or you're not in project root, STOP and report.

## Phase 0 — Discover the post-score / pre-band hook point

This factor is NOT a hard gate. It applies after the base score is computed but before the score is mapped to a verdict band (EXECUTE ≥ X, WAIT ≥ Y, PASS otherwise).

```bash
# Find where the band assignment happens
grep -rn "EXECUTE" app/analysis/ --include="*.py"
grep -rn "score_band\|band_assign\|verdict_band" app/ --include="*.py"
grep -rn "def.*score" app/analysis/ --include="*.py"
```

Read in full:
- The scoring pipeline entry point (discovered during OTA-502 work)
- Any score-to-band mapping function
- The probability matrix calculation (where do `p_max_loss` and `p_max_profit` come from?)

**STOP and report:**
- Exact function where the final base score is computed
- Exact function (or code block) that maps score → band (EXECUTE/WAIT/PASS)
- Between those two, find the hook point for this penalty
- The field names for `p_max_loss` and `p_max_profit` in the evaluation payload (they may be named differently — e.g., `prob_max_loss`, `max_loss_probability`)
- Whether `p_max_profit` can ever be exactly 0.0 in practice or if it's always ≥ some floor (affects the edge case handling)

Wait for confirmation before Phase 1.

## Phase 1 — Design the penalty module

Propose module structure as a short design note:

1. **Location:** Where does `asymmetry_penalty()` live? Options:
   - Inline in scoring pipeline (acceptable if small)
   - `app/analysis/scoring_factors/asymmetry.py` (cleaner if more factors are expected)
   - Same module as hard gates (incorrect — this is not a gate, different semantic layer)

   Recommend based on codebase conventions and whether future factors are anticipated.

2. **Function signature:**
   ```python
   def asymmetry_penalty(p_max_loss: float, p_max_profit: float) -> int:
       """Return penalty points (0-25) based on loss/profit probability ratio."""
   ```

3. **Diagnostic exposure:** The ticket requires the penalty be "visible in score breakdown (diagnostic field)." Where does the breakdown live in the current payload? Add `asymmetry_penalty: int` and `asymmetry_ratio: float` (or equivalent) to the exposed diagnostic fields.

4. **Integration point:** Where in the pipeline does this get called? Propose the exact line placement relative to the base score and the band assignment.

**STOP and report the design note.** Wait for Don's approval before Phase 2.

## Phase 2 — Implement the penalty function

Create the file per Phase 1. Pure function, no async needed, no side effects.

```python
def asymmetry_penalty(p_max_loss: float, p_max_profit: float) -> int:
    if p_max_profit is None or p_max_loss is None:
        return 0
    if p_max_profit == 0:
        return 25
    ratio = p_max_loss / p_max_profit
    if ratio >= 2.0:
        return 25
    elif ratio >= 1.5:
        return 15
    elif ratio >= 1.25:
        return 8
    return 0


def asymmetry_ratio(p_max_loss: float, p_max_profit: float) -> Optional[float]:
    """Diagnostic helper. Returns None when undefined."""
    if p_max_profit is None or p_max_loss is None or p_max_profit == 0:
        return None
    return p_max_loss / p_max_profit
```

**Behaviors to get right:**

1. **`p_max_profit == 0` is a real edge case.** Don't just let it divide-by-zero. Max penalty is the right response (a trade with zero profit probability is by definition broken), but do it with an explicit early return, not a try/except.

2. **Null inputs** return 0 penalty, not max penalty. Missing probability data should not punish a trade.

3. **Boundary inclusivity:** The ratio thresholds use `>=`. Confirm this matches the ticket spec exactly. Ratio exactly 1.25 → 8 points (not 0). Ratio exactly 1.5 → 15 points (not 8). Ratio exactly 2.0 → 25 points (not 15).

Unit tests in `tests/analysis/test_asymmetry.py`:
- **AMZN regression:** `p_max_loss=0.5666, p_max_profit=0.2985` → ratio ≈ 1.898 → penalty = 15
- **Boundary 1.25:** ratio exactly 1.25 → 8
- **Boundary just below 1.25:** ratio 1.249 → 0
- **Boundary 1.5:** ratio exactly 1.5 → 15
- **Boundary 2.0:** ratio exactly 2.0 → 25
- **Boundary just above 2.0:** ratio 2.001 → 25
- **Favorable skew:** `p_max_loss=0.3, p_max_profit=0.5` → ratio 0.6 → 0
- **Zero profit:** `p_max_profit=0.0` → 25
- **Null probabilities:** returns 0

Run tests. All must pass.

**STOP.** `git diff`. Wait for approval before Phase 3.

## Phase 3 — Wire into scoring pipeline

Per the Phase 1 design, insert the penalty call between base-score computation and band assignment:

```python
# In the scoring pipeline entry function
base_score = compute_base_score(...)
penalty = asymmetry_penalty(p_max_loss, p_max_profit)
final_score = max(0, base_score - penalty)   # clamp at 0

# Expose diagnostics
eval_payload.score = final_score
eval_payload.score_breakdown = {
    "base_score": base_score,
    "asymmetry_penalty": penalty,
    "asymmetry_ratio": asymmetry_ratio(p_max_loss, p_max_profit),
    # ... existing breakdown fields preserved
}

# Band assignment uses final_score
verdict = assign_verdict_band(final_score)
```

**Critical behaviors:**

1. **Clamp the final score at 0.** A large penalty shouldn't produce negative scores. `max(0, base_score - penalty)`.

2. **Preserve existing diagnostic fields.** The evaluation payload's `score_breakdown` (or equivalent) must not lose any existing fields when the two new fields are added.

3. **Don't apply the penalty twice.** If the pipeline re-scores for any reason (retry, alternative strikes), the penalty must be applied exactly once per final score calculation.

**STOP.** `git diff`. Show the hook point edits. Wait for approval before Phase 4.

## Phase 4 — AMZN regression test

Add an end-to-end regression test:

- AMZN fixture with `p_max_loss=0.5666, p_max_profit=0.2985`
- Assume base score before penalty = whatever the existing scorer produces (don't hardcode; just assert the difference)
- Assert: `final_score = base_score - 15` (or 0 if base < 15)
- Assert: `score_breakdown.asymmetry_penalty == 15`
- Assert: `score_breakdown.asymmetry_ratio` is approximately 1.898 ± 0.01

Also add a "favorable skew" test:
- Probabilities where `p_max_loss < p_max_profit` → penalty = 0, base score unchanged

Run both. Confirm.

**STOP and report.** `git diff --stat`.

## Phase 5 — Calibration note (optional but recommended)

Before closing this Story, consider running a calibration pass against historical evaluations to confirm the penalty values (8/15/25) don't over-correct. This is a judgment call — the ticket's "Acceptance criteria" mention "Backtest against historical scoring to confirm penalty calibration is not overly aggressive."

Options:
- **If a historical evaluation table exists** (`agent_run_log` with structured evaluations), run a one-off script that re-scores the last N evaluations with the penalty applied and reports:
  - How many EXECUTE → WAIT transitions
  - How many WAIT → PASS transitions
  - How many verdicts unchanged
  - Distribution of penalty values applied
- **If no historical data is accessible,** skip this phase and note: "Calibration deferred to OTA-204 (backtest variables) when backtesting infrastructure is in place."

**STOP and report.** Don decides whether to accept the current calibration or adjust the thresholds/values.

## Phase 6 — Summary

Print:
- Files created / modified (paths + line counts)
- OTA-505 acceptance criteria:
  - [ ] Asymmetry penalty applied to all spread evaluations
  - [ ] Penalty visible in score breakdown (diagnostic field)
  - [ ] Backtest against historical scoring (Phase 5 — calibration findings or deferral note)
  - [ ] AMZN regression shows asymmetry penalty applied (independent of OTA-503 outcome)
- Explicit relationship statement: "When OTA-503 and OTA-505 are both in effect, a negative-EV trade is blocked by OTA-503 regardless of this penalty. This factor materially affects borderline positive-EV trades with unfavorable probability skew."
- Any deviations from this prompt and why

**Do not commit.** Don reviews and commits manually.

## Commit message format (when Don is ready to commit)

```
OTA-505: Probability asymmetry scoring factor
```

## House rules summary

- This is a SCORING FACTOR, not a hard gate — different module location, different semantic layer
- Null inputs → 0 penalty, not max penalty
- `p_max_profit == 0` → 25 penalty via explicit early return, never divide-by-zero
- Boundary thresholds use `>=` — test them explicitly
- Clamp final score at 0 after penalty
- Preserve existing score_breakdown fields
- STOP after every phase with a diff for review

## Exit criteria

- Phases 0–6 complete and approved
- AMZN regression shows penalty = 15 applied, ratio ≈ 1.898 recorded
- Favorable-skew regression shows no penalty, original score preserved
- Score breakdown exposes `asymmetry_penalty` and `asymmetry_ratio` for diagnostics
- No commit made
