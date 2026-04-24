---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
---

# OTA-502 — Earnings-in-Window Hard Gate

**Wave:** AMZN April 22 Scoring Pipeline Fixes v2
**Parent Epic:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Parent Feature:** OTA-501 (Scoring Pipeline Fixes v2 — AMZN Validation April 22)
**Depends on:** OTA-508 (Finnhub EarningsCalendarProvider) — must be in Production Deployed before this prompt runs
**Downstream consumers:** OTA-503 (reuses hard-gate scaffolding), OTA-506 (consumes `effective_DTE` field)

## Context

OTA-146 covers earnings within 14 days **after** expiry. The inverse case — earnings **inside** the trade window — has zero pipeline coverage. AMZN 260/270 May 15 trade scored EXECUTE at 70.74 despite earnings April 29 (7 days from entry, 16 days before expiry).

User framework rule: never hold through earnings. With this rule applied, effective DTE = min(DTE_to_expiry, DTE_to_earnings − 1). The scoring model currently uses nominal DTE.

**This Story establishes the reusable hard-gate scaffolding** that OTA-503 will extend. Design the scaffolding before coding the earnings gate itself.

## Gating rules

```
earnings_in_window = (earnings_date is not None
                     AND entry_date <= earnings_date <= expiry_date)

if earnings_in_window:
    days_to_earnings = earnings_date - entry_date
    if days_to_earnings <= 7:
        verdict = PASS
        score = None
        reason = "Earnings {date} falls {N} trading days into trade window. Insufficient time to enter and exit before catalyst."
    else:
        # 8-13 days: warning band
        effective_DTE = days_to_earnings - 1
        scoring_penalty = 15
        # Pass effective_DTE to scoring model and strategy classifier
```

If earnings data is unavailable (Finnhub returned null): the gate does NOT trigger. "Unknown earnings" ≠ "no earnings." Null earnings are logged to the evaluation audit trail but do not force a verdict.

## Prerequisites

```bash
cat CLAUDE.md                              # confirm header timestamp is current
pwd                                        # should show ...options-analyzer
venv\Scripts\activate                      # Windows
git status                                 # uncommitted unrelated changes OK
```

If venv isn't activated or you're not in project root, STOP and report.

## Phase 0 — Confirm OTA-508 landed

Earnings data must already flow to `symbol_context` for this prompt to be executable.

```bash
# Verify Finnhub source is registered
grep -rn "finnhub_earnings" app/providers/

# Verify rows exist in symbol_context for test symbols
# (via a small Python script using the existing Azure SQL connection)
```

Write `scratch/verify_earnings_data.py`:
- Query `symbol_context WHERE source_id='finnhub_earnings' AND symbol IN ('AMZN','NVDA','AAPL')`
- Print each row's `signal_value.next_earnings_date` field
- If zero rows returned, OTA-508 hasn't shipped / hasn't run against these symbols yet

**STOP and report:**
- How many rows exist per test symbol
- AMZN's current `next_earnings_date` value
- If AMZN has null/missing earnings data: STOP and ask Don whether to proceed (the regression test depends on AMZN having a near-term earnings date)

Wait for confirmation before Phase 1.

## Phase 1 — Discover current scoring pipeline entry point

Don't assume file layout. Find the actual code paths.

```bash
grep -rn "def score" app/analysis/ --include="*.py"
grep -rn "verdict" app/analysis/ --include="*.py"
grep -rn "expected_value" app/analysis/ --include="*.py"
grep -rn "class.*Scor" app/analysis/ --include="*.py"
```

Read in full:
- Whatever file(s) contain the main scoring entry point
- `app/api/evaluation_routes.py` (the consumer)
- `architecture-plan.md` sections on "Claude Structured Evaluation" and scoring

**STOP and report:**
- Exact file + function name of the scoring pipeline entry point
- Where `verdict` is assigned (same function, or a separate verdict-assignment step?)
- Whether there's an existing pre-filter pattern (OTA-140 0-DTE filter was cited in ticket description — find and report the pattern)
- The data shape of the trade context object passed into scoring (field names for `expected_value`, `entry_date`, `expiry_date`, `symbol`, etc.)

Wait for confirmation before Phase 2.

## Phase 2 — DESIGN the hard-gate scaffolding

This is the reusable piece that OTA-503 will extend. Get the design right before coding.

Propose the module structure as a design note. Show:

1. **Where the scaffolding lives** — options to consider:
   - New module: `app/analysis/hard_gates/__init__.py` + per-gate files (clean, most extensible)
   - Single module: `app/analysis/hard_gates.py` with all gates inline (simpler, faster)
   - Inline in scoring pipeline (rejected — couples gates to scorer)
   Recommend one based on existing codebase conventions from Phase 1.

2. **Gate interface** — probable shape (adapt to codebase conventions):
   ```python
   from abc import ABC, abstractmethod
   from dataclasses import dataclass
   from typing import Optional

   @dataclass
   class GateResult:
       triggered: bool
       verdict: Optional[str] = None          # "PASS" when triggered
       reason: Optional[str] = None
       penalty_points: int = 0                # non-gating penalty (earnings 8-13 day band)
       effective_dte_override: Optional[int] = None
       gate_id: str = ""                      # for audit trail

   class HardGate(ABC):
       gate_id: str

       @abstractmethod
       async def evaluate(self, trade_context) -> GateResult: ...
   ```

3. **Registration + first-match-wins evaluation:**
   ```python
   _registered_gates: list[HardGate] = []

   def register_gate(gate: HardGate) -> None:
       _registered_gates.append(gate)

   async def evaluate_gates(trade_context) -> Optional[GateResult]:
       """Return first triggered gate's result, or None if no gate triggered."""
       for gate in _registered_gates:
           result = await gate.evaluate(trade_context)
           if result.triggered:
               return result
       return None
   ```

4. **How the scoring pipeline invokes it** — where in the entry function does `evaluate_gates()` get called? Before any scoring math? As a decorator? Propose one based on Phase 1's discovered pipeline.

5. **Non-gating outputs** — the earnings gate's 8-13 day band does NOT force a verdict but DOES inject `effective_dte_override` and `penalty_points`. The scaffolding must support this hybrid mode. Show how.

6. **Audit trail** — when any gate returns `triggered=True`, write a record linking trade → gate_id → reason. Fire-and-forget. Never block emission.

**STOP and report the design note.** Wait for Don's approval before Phase 3. This scaffolding will live in the codebase for years — getting it right matters more than shipping today.

## Phase 3 — Implement the scaffolding module

Create the files specified in the approved Phase 2 design. Add docstrings on every public class and function. Add one minimal test:

```python
# tests/analysis/test_hard_gates.py
def test_no_registered_gates_returns_none():
    # Register zero gates, evaluate — should return None
    assert await evaluate_gates(mock_trade_context()) is None
```

Run the test. Confirm pass.

**STOP.** `git diff`. Wait for approval before Phase 4.

## Phase 4 — Implement EarningsInWindowGate

Create the earnings gate in the location approved in Phase 2.

```python
# app/analysis/hard_gates/earnings_gate.py  (or inline, per approved design)

class EarningsInWindowGate(HardGate):
    gate_id = "earnings_in_window"

    def __init__(self, context_store):
        self._store = context_store

    async def evaluate(self, trade_context) -> GateResult:
        signal = await self._store.fetch_or_cache(
            trade_context.symbol,
            source_id="finnhub_earnings"
        )
        earnings_date_str = (signal.signal_value or {}).get("next_earnings_date")
        if not earnings_date_str:
            return GateResult(triggered=False, gate_id=self.gate_id)

        earnings_date = parse_iso_date(earnings_date_str)
        entry_date = trade_context.entry_date
        expiry_date = trade_context.expiry_date

        # Out of window — no action
        if not (entry_date <= earnings_date <= expiry_date):
            return GateResult(triggered=False, gate_id=self.gate_id)

        days_to_earnings = business_days_between(entry_date, earnings_date)

        if days_to_earnings <= 7:
            return GateResult(
                triggered=True,
                verdict="PASS",
                reason=(
                    f"Earnings {earnings_date_str} falls {days_to_earnings} "
                    f"trading days into trade window. Insufficient time to "
                    f"enter and exit before catalyst."
                ),
                gate_id=self.gate_id
            )
        else:  # 8-13 days: warning band
            return GateResult(
                triggered=False,   # does not force verdict
                effective_dte_override=days_to_earnings - 1,
                penalty_points=15,
                reason=(
                    f"Earnings {earnings_date_str} in window at "
                    f"{days_to_earnings} days. Effective DTE reduced, "
                    f"15-point scoring penalty applied."
                ),
                gate_id=self.gate_id
            )
```

**Two specific behaviors to get right:**

1. **Business days vs calendar days.** The ticket says "7 trading days." Use a business-day helper (skip weekends). If one doesn't exist in the codebase, implement a minimal one inline — don't pull in pandas just for this.

2. **Null/missing earnings data** must return `triggered=False` cleanly. The gate is fail-soft. Log the null case for observability but don't raise.

Unit tests in `tests/analysis/test_earnings_gate.py`:
- **AMZN regression:** earnings 7 days from entry, 16 days before expiry → `triggered=True`, `verdict="PASS"`
- **Warning band:** earnings 10 days from entry, 20 days before expiry → `triggered=False`, `effective_dte_override=9`, `penalty_points=15`
- **Out of window:** earnings 2 days AFTER expiry → `triggered=False`, no override, no penalty
- **Missing earnings:** signal returns null → `triggered=False`, no error raised
- **Boundary:** earnings exactly 7 days from entry → `triggered=True` (inclusive)
- **Boundary:** earnings exactly 8 days → `triggered=False`, warning band applied

Run tests. All must pass.

**STOP.** `git diff`. Wait for approval before Phase 5.

## Phase 5 — Register the gate and wire into scoring pipeline

1. Register `EarningsInWindowGate` at app startup (wherever other providers/sources are registered).

2. Modify the scoring pipeline entry point discovered in Phase 1 to:
   - Call `evaluate_gates(trade_context)` before any scoring math
   - If a gate returned `triggered=True` with a forced verdict, short-circuit and return the gate's verdict + reason
   - If a gate returned `triggered=False` but with `effective_dte_override` or `penalty_points`, pass those through to the scoring model
   - Log gate outcomes to the audit trail (fire-and-forget)

3. The scoring model must consume `effective_DTE` when present, falling back to nominal DTE when not. Export `effective_DTE` in the final evaluation payload so downstream consumers (OTA-506) can see it.

**Observability:**
- Every scoring call records: gate outcomes, effective_DTE, penalty_points applied
- Fire-and-forget via `asyncio.create_task`
- Never let observability block the scoring path

**STOP.** `git diff`. Show edits to scoring pipeline + registration. Wait for approval before Phase 6.

## Phase 6 — AMZN regression test

Add (or update) an end-to-end test with the AMZN 260/270 May 15 fixture:

- Symbol: AMZN
- Entry date: April 22, 2026
- Expiry: May 15, 2026
- Earnings fixture: April 29, 2026 (7 days from entry — exactly at the auto-PASS boundary)
- Computed EV: -5.86 (will matter for OTA-503 regression; for this Story only the verdict matters)
- Expected verdict from this Story alone: **PASS** (earnings gate triggers)
- Expected reason substring: "Earnings 2026-04-29 falls 7 trading days into trade window"

Also add a "golden path" test:
- Symbol: any symbol with no earnings in window (or mock null earnings)
- Expected: gate does NOT trigger, scoring proceeds normally

Run both. Confirm AMZN verdict is now PASS.

**STOP and report.** `git diff --stat`.

## Phase 7 — Summary

Print:
- Files created (paths + line counts)
- Files modified (paths + diff summary)
- Which OTA-502 acceptance criteria are satisfied:
  - [ ] Earnings date inside window surfaces as banner-level flag in output
  - [ ] `effective_DTE` field computed and passed to all downstream scoring + classifier components
  - [ ] DTE-to-earnings ≤ 7 → auto-PASS
  - [ ] DTE-to-earnings 8–13 → 15-point scoring penalty
  - [ ] AMZN 260/270 May 15 regression case flips from EXECUTE to PASS
- Explicit note: **"Hard-gate scaffolding is in place. OTA-503 can now register a `NegativeEVGate` following the same pattern."**
- Any deviations from this prompt and why

**Do not commit.** Don reviews and commits manually.

## Commit message format (when Don is ready to commit)

```
OTA-502: Earnings-in-window hard gate + hard-gate scaffolding
```

## House rules summary

- Hard-gate scaffolding designed before coded (Phase 2 STOP gate)
- Gate registration at app startup — never per-request
- First-match-wins evaluation — deterministic ordering matters if you add multiple forced-verdict gates later
- Fail-soft on missing upstream data (null earnings → no trigger, no raise)
- Fire-and-forget observability — never block scoring
- Business days for the 7-day threshold, not calendar days
- Tests include boundary cases (exactly 7, exactly 8) — off-by-one here is a real risk
- STOP after every phase with a diff for review

## Exit criteria

- Phases 0–7 complete and approved
- AMZN regression: verdict flips to PASS with earnings reason in payload
- Golden-path trade still evaluates normally (gate does not over-fire)
- Hard-gate scaffolding is ready for OTA-503 to extend
- `effective_DTE` is exported in the payload for OTA-506 to consume
- No commit made
