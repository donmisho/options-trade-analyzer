---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-328 — Hotfix: Risk Budget Displays Wrong Value in Pre-Screen Checks

**Jira:** OTA-328 | Parent: OTA-19 (DEV Housekeeping)
**Priority:** Medium | **Labels:** bug, frontend, hotfix
**Run in Terminal 1 alongside OTA-327. Both are quick isolated fixes.**

---

## Before You Start

```bash
grep -rn "riskBudget\|risk_budget\|maxLoss\|max_loss\|RiskBudget\|26400\|acct\|account_size\|accountSize" web/src/ --include="*.jsx" --include="*.js"
```

Identify which component renders the "Risk Budget" section of the Pre-Screen Checks panel.
It will be something like `PreScreenChecks.jsx`, `EvaluationCard.jsx`, or similar.
Read that file fully before making any changes.

---

## Bug Description

The Pre-Screen Checks panel shows:

```
Risk Budget
26400 max loss
264.0% of 10,000 acct
```

There are two separate bugs:

### Bug 1 — Wrong value: `26400` should be `264.00`

The max loss value is being rendered as `26400` instead of `264.00`.

**Root cause (likely):** The value is stored or passed in **cents** (26400¢ = $264.00) but
is being rendered without dividing by 100. OR the value has already been multiplied by 100
somewhere in the pipeline before display.

**Fix:** Find where `maxLoss` (or `max_loss`, or `riskBudget`) is rendered and ensure the
value is divided correctly so it displays as `264.00`.

**Format rule:** Display as `##.00` — two decimal places, **no `$` prefix** (house rule).

### Bug 2 — Remove the "% of acct" line entirely

The line `264.0% of 10,000 acct` is confusing and should be removed. Do not replace it
with anything. The account-size percentage display is not a useful pre-screen signal in
its current form and should be eliminated.

---

## Fix Instructions

1. Locate the component rendering the Risk Budget block in Pre-Screen Checks.

2. Fix the max loss value rendering:
   - If value comes from backend as `26400` (cents): divide by 100 before display
   - If value is already correct at `264` but formatted wrong: apply `.toFixed(2)`
   - Display result as `264.00` — no `$` prefix

3. Remove the `% of acct` / account size percentage line completely. Remove both the
   calculation and the JSX rendering. Do not leave a commented-out block.

4. After the fix the Risk Budget block should look like:
   ```
   Risk Budget
   264.00  max loss
   ```
   Just the label and the correctly formatted value. Nothing else.

---

## Verification

- [ ] Risk Budget shows `264.00` (two decimal places, no `$`)
- [ ] No `% of acct` line anywhere in the Pre-Screen Checks panel
- [ ] Other pre-screen values (R:R, PoP, Score, DTE) are unaffected
- [ ] No console errors
- [ ] Verify with a second trade to confirm the fix is not hardcoded — the value should
      change correctly per trade

---

## House Style Rules

- No `$` prefix on any monetary value — ever
- Monetary values: `##.00` format (`.toFixed(2)`)
- Scores: `##.00` format
- Probabilities: `##.00%` format

---

## Commit Message

```
OTA-[ticket] Fix risk budget max loss display (cents→dollars) and remove acct% line
```
