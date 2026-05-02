---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
---

# OTA-503 — Negative EV Hard Gate

**Wave:** AMZN April 22 Scoring Pipeline Fixes v2
**Parent Epic:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Parent Feature:** OTA-501 (Scoring Pipeline Fixes v2 — AMZN Validation April 22)
**Depends on:** OTA-502 (Earnings-in-window hard gate) — hard-gate scaffolding must be in place
**Independent of:** OTA-508 (this gate doesn't need earnings data)

## Context

OTA-294 built OutcomeSummaryCard with NEGATIVE EV / POSITIVE EV badges. The badge displays correctly but does not enforce a verdict gate.

AMZN 260/270 May 15 trade: computed EV = −5.86, NEGATIVE EV badge displayed, verdict still EXECUTE at score 70.74. The flag is cosmetic.

Per user framework: **EV is the primary quality gate.** A negative EV trade should never reach EXECUTE or WAIT.

This Story reuses the hard-gate scaffolding established in OTA-502. The gate itself is a minimal addition — the heavy lifting happened in 502. Expect this Story to be significantly shorter than OTA-502.

## Gating rule

```
if expected_value < 0:
    verdict = PASS
    score = None  # retain for diagnostic but suppress display
    reason = f"Negative expected value ({expected_value:.2f}). Trade fails primary quality gate."
```

Defense in depth with OTA-502: earnings catches the catalyst risk; this catches the math. Either alone would have flipped the AMZN verdict. Both together is belt-and-suspenders, matching the OTA-140/OTA-141 pattern from March 17.

## Prerequisites

```bash
cat CLAUDE.md                              # confirm header timestamp is current
pwd                                        # should show ...options-analyzer
venv\Scripts\activate                      # Windows
git status                                 # uncommitted unrelated changes OK
```

If venv isn't activated or you're not in project root, STOP and report.

## Phase 0 — Confirm OTA-502 landed

The hard-gate scaffolding must be in place before this Story can be built.

```bash
# Verify the scaffolding module exists
ls app/analysis/hard_gates/ 2>/dev/null || ls app/analysis/hard_gates.py 2>/dev/null

# Verify the earnings gate ships
grep -rn "class EarningsInWindowGate" app/

# Verify the scaffolding interface
grep -rn "class HardGate" app/
grep -rn "GateResult" app/
grep -rn "register_gate" app/
```

Read the Phase 2 scaffolding output from OTA-502:
- `HardGate` abstract class — confirm the interface shape
- `GateResult` dataclass — confirm the fields
- The registration pattern — where does gate registration happen at app startup?
- How the scoring pipeline calls `evaluate_gates()` and interprets the result

**STOP and report:**
- Exact file location of `HardGate` base class
- Exact shape of `GateResult` (fields, types)
- Where gates are registered at startup (the file + function to edit)
- Whether there are any other gates registered already (if so, the ordering matters — more on this in Phase 2)

Wait for confirmation before Phase 1.

## Phase 1 — Gate ordering decision

Hard gates are first-match-wins. If earnings gate AND negative-EV gate both trigger for the same trade, only the first-registered gate's reason appears in the verdict.

Question for design: which gate should win on a trade that triggers both?

**Option A — Earnings gate wins (register earnings first):** the user sees "Earnings in window" as the reason. Makes sense if catalyst risk is communicated as the primary problem.

**Option B — Negative EV wins (register neg-EV first):** the user sees "Negative expected value" as the reason. Makes sense if the math verdict is always presented first.

**Option C — Both reasons captured:** modify scaffolding to collect all triggered gates, concat reasons. Less ambiguous but changes OTA-502's contract.

My recommendation: **Option A.** Earnings is a reason to exit fast regardless of EV math; EV can sometimes be iterated (different strikes), earnings cannot. Presenting earnings first guides the user toward the right next action (pick a different expiry, not a different strike).

**STOP and report your recommendation.** Wait for Don's call before Phase 2. If Don picks B or C, the implementation changes in Phase 2 and/or Phase 3.

## Phase 2 — Implement NegativeEVGate

Create the gate in the location matching OTA-502's scaffolding decision (either `app/analysis/hard_gates/negative_ev_gate.py` or inline in the single-module file — match OTA-502's pattern exactly).

```python
class NegativeEVGate(HardGate):
    gate_id = "negative_ev"

    async def evaluate(self, trade_context) -> GateResult:
        ev = trade_context.expected_value
        if ev is None:
            # EV not yet computed — gate does not trigger
            return GateResult(triggered=False, gate_id=self.gate_id)
        if ev < 0:
            return GateResult(
                triggered=True,
                verdict="PASS",
                reason=(
                    f"Negative expected value ({ev:.2f}). "
                    f"Trade fails primary quality gate."
                ),
                gate_id=self.gate_id
            )
        return GateResult(triggered=False, gate_id=self.gate_id)
```

**Behaviors to get right:**

1. **`expected_value is None`** must NOT trigger the gate. It's a "not computed yet" signal, not a negative value. Treat as no-action.

2. **`expected_value == 0`** (exactly zero) must NOT trigger. The rule is strictly `< 0`, not `<= 0`. Zero-EV trades are poor setups but don't violate the "must be positive" framework rule.

3. **Dollars, not cents.** The AMZN EV was −5.86 (dollars). Confirm `trade_context.expected_value` is in dollars, not cents, before landing this gate. If the codebase uses cents internally, the threshold is `< 0` regardless of units (zero is zero in both units), but the reason string should format dollars correctly.

Unit tests in `tests/analysis/test_negative_ev_gate.py`:
- **AMZN regression:** EV = −5.86 → `triggered=True`, `verdict="PASS"`, reason contains "−5.86"
- **Positive EV:** EV = 12.50 → `triggered=False`
- **Zero EV:** EV = 0.0 → `triggered=False` (strict `<`, not `<=`)
- **Null EV:** EV = None → `triggered=False`, no error raised
- **Tiny negative:** EV = −0.01 → `triggered=True` (no tolerance — negative is negative)

Run tests. All must pass.

**STOP.** `git diff`. Wait for approval before Phase 3.

## Phase 3 — Register the gate

Following Phase 1's ordering decision, register `NegativeEVGate` at app startup in the appropriate position relative to `EarningsInWindowGate`.

Add one integration test in `tests/integration/test_gate_ordering.py`:
- Construct a trade that triggers BOTH gates (in-window earnings AND negative EV)
- Assert that `evaluate_gates()` returns the expected winner per the Phase 1 decision
- Confirm the other gate's reason does NOT appear in the result

**STOP.** `git diff`. Wait for approval before Phase 4.

## Phase 4 — AMZN regression test

Update the AMZN fixture to also verify this gate would trigger independently:

- Create (or update) a second regression case where earnings is OUT of window but EV is still negative:
  - AMZN-style trade, earnings moved to AFTER expiry, EV = −5.86
  - Expected verdict: **PASS** via negative EV gate (not earnings gate)
  - Expected reason substring: "Negative expected value"

This proves the negative EV gate works standalone, not just as a defense-in-depth layer behind earnings.

Also confirm the original AMZN case (both gates would trigger) still produces the Phase 1-approved ordering.

**STOP and report.** `git diff --stat`.

## Phase 5 — Summary

Print:
- Files created / modified (paths + line counts)
- OTA-503 acceptance criteria:
  - [ ] Negative EV → auto-PASS, no exceptions
  - [ ] NEGATIVE EV badge in OutcomeSummaryCard remains as visual indicator (no frontend change needed — just confirm the badge still renders; it's independent of the backend gate)
  - [ ] Verdict reason field surfaces "Negative expected value" when gate triggers
  - [ ] AMZN regression (earnings out of window, EV negative) flips from EXECUTE to PASS on this gate alone
- Gate ordering: confirm which gate wins on a double-trigger trade (per Phase 1)
- Any deviations from this prompt and why

**Do not commit.** Don reviews and commits manually.

## Commit message format (when Don is ready to commit)

```
OTA-503: Negative EV hard gate
```

## House rules summary

- Reuse OTA-502's scaffolding exactly — do NOT refactor the scaffolding in this Story
- `expected_value is None` is not a trigger (fail-soft on missing data)
- `expected_value == 0` is not a trigger (strict `<`, not `<=`)
- Tiny negatives ARE triggers — no tolerance on zero
- Gate ordering is a design decision with user-visible consequences — Phase 1 STOP gate is not optional
- Tests include boundary cases explicitly
- STOP after every phase with a diff for review

## Exit criteria

- Phases 0–5 complete and approved
- AMZN earnings-out-of-window regression: verdict is PASS via negative EV gate
- Original AMZN regression (both gates) produces the agreed-upon winning reason
- No changes to OTA-502's scaffolding code — only additions
- No commit made
