---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
---

# OTA-506 — Strategy Classifier Uses Effective DTE

**Wave:** AMZN April 22 Scoring Pipeline Fixes v2
**Parent Epic:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Parent Feature:** OTA-501 (Scoring Pipeline Fixes v2 — AMZN Validation April 22)
**Depends on:** OTA-502 (requires `effective_DTE` field) — must be in Production Deployed before this prompt runs
**Last item in Session A** — the finishing piece of the AMZN wave

## Context

Strategy classifier ("Best fit" — Trend Rider, Steady Paycheck, Weekly Grind, Lottery Ticket) currently uses nominal DTE.

AMZN 260/270 May 15 trade was classified as "Best fit: Trend Rider" with score 71. With earnings April 29 (7 days from entry), the user must exit before then per framework. Effective DTE = 6 trading days, not 22. The strategy is structurally a pre-earnings momentum play, not a Trend Rider.

This Story adjusts the classifier to consume `effective_DTE` (exported by OTA-502) and disqualifies strategies whose time requirements aren't met.

## Strategy DTE requirements

```python
STRATEGY_DTE_REQUIREMENTS = {
    "TREND_RIDER":     {"min": 14, "max": 60},
    "STEADY_PAYCHECK": {"min": 14, "max": 45},
    "WEEKLY_GRIND":    {"min": 14, "max": 21},   # OTA-140 already enforces ≤7 PASS
    "LOTTERY_TICKET":  {"min":  7, "max": 60},
}
```

If no strategy fits the effective DTE, return **"No viable strategy — effective DTE {N} insufficient for any profile"** rather than forcing a classification.

Strategy keys above are placeholders — confirm the actual keys used in the codebase during Phase 1 (the user memory references SP/WG/TR/LT abbreviations, and OTA-436 is a pending taxonomy redesign). Use whatever internal keys match the existing classifier.

## Prerequisites

```bash
cat CLAUDE.md                              # confirm header timestamp is current
pwd                                        # should show ...options-analyzer
venv\Scripts\activate                      # Windows
git status                                 # uncommitted unrelated changes OK
```

If venv isn't activated or you're not in project root, STOP and report.

## Phase 0 — Confirm OTA-502 landed

`effective_DTE` must be available in the evaluation payload before this Story can be built.

```bash
# Verify OTA-502 shipped
grep -rn "effective_DTE\|effective_dte" app/analysis/ --include="*.py"
grep -rn "effective_DTE\|effective_dte" app/api/ --include="*.py"
```

Read the scoring pipeline entry function (identified during OTA-502 work). Confirm:
1. The payload includes `effective_DTE` when set by the earnings gate
2. When the earnings gate does NOT modify DTE, the payload still carries a useful DTE value (either `effective_DTE == nominal_DTE` or a separate `nominal_DTE` field — either is fine, just needs to be consistent)

**STOP and report:**
- Exact field name used: `effective_DTE`, `effective_dte`, or something else — use whatever shipped in OTA-502
- What value is present when no earnings-in-window gate has triggered (nominal DTE? same DTE? separate field?)
- The exact file + function where strategy classification happens

Wait for confirmation before Phase 1.

## Phase 1 — Discover current strategy classifier

```bash
grep -rn "class.*Classif\|classify_strategy\|best_fit\|best_strategy" app/ --include="*.py"
grep -rn "TREND_RIDER\|STEADY_PAYCHECK\|WEEKLY_GRIND\|LOTTERY_TICKET" app/ --include="*.py"
grep -rn "SP\b\|WG\b\|TR\b\|LT\b" app/analysis/ --include="*.py"
```

Read in full:
- The strategy classifier file(s)
- The strategy config files (`app/strategy-configs/` per project hierarchy, or similar — per CLAUDE.md the frontend has these in `web/src/strategy-configs/`; there may be a backend equivalent)
- Any existing DTE-based filtering in the classifier

**STOP and report:**
- Exact file + function name for strategy classification
- The internal strategy keys actually used in the codebase (uppercase constants? enum values? string keys like "steady-paycheck"?)
- Whether there are already DTE thresholds in any strategy config that we should honor rather than hardcode in a new dict
- The shape of the classifier's return value (single best fit? ranked list? per-strategy scores?)

Wait for confirmation before Phase 2.

## Phase 2 — Design decision: where does STRATEGY_DTE_REQUIREMENTS live?

Two options:

**Option A: centralized constant in classifier module.** `STRATEGY_DTE_REQUIREMENTS` dict lives next to the classifier logic. Simple. Changes require editing classifier code.

**Option B: per-strategy config.** Each strategy's config file (`verticals.config.js`, `steady-paycheck.config.js` etc., or their backend equivalents) declares its own `dte_min` / `dte_max`. The classifier reads from configs. Requires config schema extension.

Phase 1 should have surfaced whether per-strategy configs already have DTE fields. If they do, **Option B is strongly preferred** — it keeps strategy-specific data with its strategy. If they don't, **Option A is pragmatic for this Story**, with a follow-up ticket to migrate to Option B when OTA-436 (strategy taxonomy redesign) lands.

**STOP and report the recommendation.** Wait for Don's call before Phase 3.

## Phase 3 — Implement strategy filtering

Per the approved Phase 2 decision, implement the DTE-based filter.

If Option A:

```python
# app/analysis/strategy_classifier.py  (or wherever the classifier lives)

STRATEGY_DTE_REQUIREMENTS = {
    # Keys match internal strategy identifiers — confirmed in Phase 1
    "TREND_RIDER":     {"min": 14, "max": 60},
    "STEADY_PAYCHECK": {"min": 14, "max": 45},
    "WEEKLY_GRIND":    {"min": 14, "max": 21},
    "LOTTERY_TICKET":  {"min":  7, "max": 60},
}


def filter_strategies_by_effective_dte(
    candidates: list,
    effective_dte: int,
) -> list:
    """Return only strategies whose DTE range includes effective_dte."""
    return [
        c for c in candidates
        if STRATEGY_DTE_REQUIREMENTS.get(c.strategy_key, {}).get("min", 0)
           <= effective_dte
           <= STRATEGY_DTE_REQUIREMENTS.get(c.strategy_key, {}).get("max", 365)
    ]
```

If Option B: analogous implementation reading from strategy configs.

**Handle the "no viable strategy" case:**

```python
def classify_best_strategy(trade_context, effective_dte: int):
    viable = filter_strategies_by_effective_dte(all_candidates, effective_dte)
    if not viable:
        return StrategyClassification(
            best_fit=None,
            reason=(
                f"No viable strategy — effective DTE {effective_dte} "
                f"insufficient for any profile"
            )
        )
    # Existing ranking logic on the viable subset
    return rank_and_select(viable, trade_context)
```

The "no viable strategy" case must NOT raise an exception. It's a valid classifier output — the UI should display it as informational text.

Unit tests in `tests/analysis/test_strategy_classifier.py`:
- **AMZN regression:** `effective_dte=6`, candidates include TREND_RIDER → TREND_RIDER is filtered out. Best fit should be LOTTERY_TICKET (if its scoring wins) or "no viable strategy" (if the remaining candidates are weaker).
- **Nominal DTE regression:** `effective_dte=22`, candidates include all four → TREND_RIDER is viable and can win.
- **Sub-7 DTE:** `effective_dte=3`, all strategies filtered out → return "no viable strategy" with the expected reason string.
- **Boundary 14:** `effective_dte=14` → TREND_RIDER, STEADY_PAYCHECK, WEEKLY_GRIND all viable (inclusive min).
- **Boundary 21:** `effective_dte=21` → WEEKLY_GRIND still viable (inclusive max), TREND_RIDER/STEADY_PAYCHECK also viable.
- **Boundary 45:** `effective_dte=45` → STEADY_PAYCHECK viable, TREND_RIDER viable, LOTTERY_TICKET viable, WEEKLY_GRIND out (21 max).
- **Boundary 60:** `effective_dte=60` → TREND_RIDER and LOTTERY_TICKET viable, others out.
- **Over 60:** `effective_dte=90` → LOTTERY_TICKET out, all others out. "No viable strategy."

Run tests. All must pass.

**STOP.** `git diff`. Wait for approval before Phase 4.

## Phase 4 — Wire classifier to consume effective_DTE

Update the classifier's entry point (or its caller in the scoring pipeline) to pass `effective_DTE` instead of nominal DTE.

Also update the output payload to show both values when they differ:

```python
# In the evaluation payload construction
payload.strategy_fit = {
    "best_fit": classification.best_fit,
    "reason": classification.reason,
    "nominal_dte": nominal_dte,
    "effective_dte": effective_dte,
    "dte_source": "earnings_in_window" if effective_dte != nominal_dte else "nominal",
}
```

When `effective_dte == nominal_dte`, the UI can still show just one number. When they differ (earnings-in-window warning band), the UI can show "22 DTE (6 effective)" — that frontend work is not in this Story's scope, but the payload must carry both so the frontend can render intelligently.

**STOP.** `git diff`. Show the classifier and payload edits. Wait for approval before Phase 5.

## Phase 5 — AMZN regression test

Update the end-to-end AMZN regression fixture:

- Symbol: AMZN, entry April 22, expiry May 15, earnings April 29
- Earnings gate (OTA-502) is expected to trigger `PASS` verdict (7 days ≤ 7)
- BUT the regression test for THIS Story should also work on a hypothetical "earnings in warning band" trade:
  - Modify fixture: earnings 10 days from entry (warning band, not auto-PASS)
  - `effective_DTE` = 9
  - Expected classifier behavior: TREND_RIDER disqualified, LOTTERY_TICKET or "no viable strategy" returned
  - Assert payload has `strategy_fit.best_fit != "TREND_RIDER"` or `best_fit == None`
  - Assert payload has `strategy_fit.effective_dte == 9` and `strategy_fit.nominal_dte == 23` (or whatever the nominal is)
  - Assert payload has `strategy_fit.dte_source == "earnings_in_window"`

Also add a "no earnings in window" sanity check:
- Trade with no earnings → `effective_dte == nominal_dte == 22` → TREND_RIDER can still be the best fit

Run both. Confirm.

**STOP and report.** `git diff --stat`.

## Phase 6 — Summary

Print:
- Files created / modified (paths + line counts)
- OTA-506 acceptance criteria:
  - [ ] Strategy classifier reads `effective_DTE`, not nominal DTE
  - [ ] TREND_RIDER not selectable when effective_DTE < 14
  - [ ] AMZN regression (warning-band earnings) classifies as something other than TREND_RIDER (or "no viable strategy")
  - [ ] Output displays both nominal DTE and effective DTE when they differ (payload carries both; frontend rendering is downstream work)
- Option chosen in Phase 2 (A or B) and why
- Any follow-up work implied (e.g., frontend rendering of effective vs nominal DTE, OTA-436 migration if Option A chosen)
- Any deviations from this prompt and why

**Do not commit.** Don reviews and commits manually.

## Commit message format (when Don is ready to commit)

```
OTA-506: Strategy classifier uses effective_DTE
```

## House rules summary

- `effective_DTE` field name must match exactly what OTA-502 shipped — confirm in Phase 0
- Strategy keys must match exactly what the codebase uses — confirm in Phase 1 (do NOT assume the uppercase constants from the ticket description)
- "No viable strategy" is a valid output, not an exception
- Boundary tests use inclusive ranges (min and max both inclusive)
- Payload exposes BOTH nominal and effective DTE so the frontend can render intelligently
- STOP after every phase with a diff for review

## Exit criteria

- Phases 0–6 complete and approved
- AMZN warning-band regression: TREND_RIDER disqualified
- "No viable strategy" path exercised by at least one test
- Payload carries both nominal and effective DTE
- Boundary cases (14, 21, 45, 60) all verified
- No commit made

## Wave 1 completion gate

This is the last Story in Session A. When OTA-506 commits land and the parent Feature OTA-501's acceptance criterion is met — **AMZN 260/270 May 15 verdict flips from EXECUTE to PASS** — the Wave is complete. Run the full AMZN fixture one more time and confirm the end-to-end verdict change, ideally with at least two of the gates triggering independently (defense in depth). Report the final verdict and which gates fired.
