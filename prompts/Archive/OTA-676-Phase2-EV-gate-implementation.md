# OTA-676 — EV calculation excludes modal-outcome probability mass, allowing negative-EV EXECUTE verdicts (Phase 2 — Implementation)

## Terminal context

- This terminal: Solo
- Concurrent terminals: none
- Cross-terminal dependencies: none

## Required reading

Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/diagnostics/ev-gate-msft-410p-trace.md
```

The diagnostic report from Phase 1 is the implementation blueprint. Every claim about file paths, line numbers, function names, and existing behavior in this prompt is sourced from that report. If the actual code disagrees with the report on a key fact, stop and escalate — do not work around silently.

This Story is in the **Scoring / gates / health / P&L** domain (primary) and crosses into **Frontend** (secondary).

## Relevant Context — Do Not Deviate Without Escalation

**Source: diagnostic report § Hypothesis 1**
Fact: `NegativeEVGate.evaluate()` reads `ctx.expected_value`, which is populated from `request.trade.get("total_ev")` at `app/api/evaluation_routes.py:561-562`. For `SINGLE_LONG_PUT` and `SINGLE_LONG_CALL` candidates, the trade dict produced by `NakedOptionEngine` (`app/analysis/long_call_engine.py:86-127`) does not include a `total_ev` field. Result: gate receives `None`, passes through.

**Source: diagnostic report § Hypothesis 2**
Fact: Gate logic is correct. When `ev < 0`, it returns `GateResult(triggered=True, verdict="PASS")` (`app/analysis/hard_gates/negative_ev_gate.py:72-84`). The caller at `app/api/evaluation_routes.py:578-591` short-circuits the pipeline correctly when `triggered=True`. **Do not modify the gate itself or its caller.**

**Source: diagnostic report § Hypothesis 3**
Fact: The hard-gate pipeline IS invoked for naked single-leg options at `app/api/evaluation_routes.py:575`. There is no branch that skips gates for `SINGLE_LONG_PUT` / `SINGLE_LONG_CALL`. **Do not add a separate gate invocation path; the existing one is correct.**

**Source: diagnostic report § Secondary Investigation — Probability Mass**
Fact: `compute_probability_matrix()` at `app/analysis/black_scholes.py:73-88` produces a normalized lognormal probability distribution over a discrete price grid (sums to 1.0). This is the canonical source for probability mass. **Use this function for the new EV computation.** Do not roll a parallel implementation.

**Source: diagnostic report § Layer 2**
Fact: The backend `_build_exit_rows()` (`app/api/evaluation_routes.py:1181-1296`) and `_spread_value()` (`app/api/evaluation_routes.py:1100-1115`) handle only four spread types (BEAR_PUT_DEBIT, BULL_CALL_DEBIT, BEAR_CALL_CREDIT, BULL_PUT_CREDIT). They do not handle naked single-leg options. The new EV computation must be added separately; do not retrofit `_build_exit_rows`.

**Source: diagnostic report § Recommended Phase 2 Fix**
Fact: The minimum-viable fix is a new function (analogous to `_build_exit_rows` but for naked single-leg long options) that computes `total_ev` from the lognormal probability matrix, called in `evaluate_structured()` between lines 534 and 558 (before `GateTradeContext` construction), with the result assigned to `request.trade["total_ev"]`. This makes the existing gate fire correctly with zero changes to the gate or its caller.

**Source: business-rules.md § Strategy-Structure Compatibility**
Rule: Lottery Ticket’s `compatible_structures` = `[SINGLE_LONG_CALL, SINGLE_LONG_PUT]`. The new EV computation applies to both. Implement once, dispatch by `option_type`.

**Source: UI-GUIDANCE.md § Part 10 Screen 2 → Trade Detail Expansion → Section B**
Rule: Exit scenario table is rendered in `Section B` with `Footer: Total EV`. The current implementation in `buildLongOptionExitScenarios()` (`web/src/pages/TradesPage.jsx:230-311`) displays five tagged rows: MAX PROFIT, MONITOR PROFIT, BREAK EVEN, MONITOR LOSS, STOP. A sixth tagged row — EXPIRES WORTHLESS — must be added for long single-leg options where the underlying is OTM at evaluation (long puts: underlying ≥ strike; long calls: underlying ≤ strike).

**Source: UI-GUIDANCE.md § Part 4**
Rule: Monetary display `##.00`, no `$` prefix. Probabilities `##.00%`. No deviations.

**Source: diagnostic report § Citation Index, line 36**
Note: `app/api/evaluation_routes.py:270` (`_build_structured_user_message`) already attempts `trade.get("total_ev")`. Once we populate this field, that consumer also benefits — no change needed there, but be aware it exists.

## Scope

### Backend changes (`app/`)

1. **Add `_compute_naked_long_option_ev()`** — a new helper function in `app/api/evaluation_routes.py` (near `_build_exit_rows`, or wherever the existing exit-scenario helpers live; keep it adjacent for discoverability). Signature:
   
   ```python
   def _compute_naked_long_option_ev(
       option_type: str,         # "PUT" or "CALL" (case-insensitive)
       strike: float,
       underlying_price: float,
       iv: float,                # decimal form, e.g., 0.2731
       days_to_exp: int,
       entry_price: float,       # debit paid per contract in option-price units (e.g., 14.90, not 1490)
   ) -> float:
       """
       Compute total expected value in dollars for a naked single-leg long option.
       Uses the canonical lognormal probability matrix from app/analysis/black_scholes.py.
       Returns EV in dollars per contract (consistent with how other EV values are reported
       in the trade payload — verify against _build_exit_rows row EV units before finalizing).
       """
   ```
   
   Implementation requirements:
- Use `compute_probability_matrix()` from `app/analysis/black_scholes.py`. Do not implement a parallel probability calculation.
- The probability matrix spans the full ±3σ range or wider. Sum `prob_i × pnl_i` across **every** price level in the matrix, not a truncated subset. The point of this fix is to capture the modal-outcome mass.
- P&L at price `p` for a long put with strike `K` and debit `d` (in option-price units): `pnl = max(0, K - p) × 100 - d × 100`. For a long call: `pnl = max(0, p - K) × 100 - d × 100`. Verify these match the units `_build_exit_rows` produces.
- Return units must match what `NegativeEVGate` expects via `ctx.expected_value`. The gate’s `ev < 0` check is unit-agnostic, but the surrounding code may not be. Confirm units from `app/api/evaluation_routes.py:561-562` and the existing spread EV path.
1. **Call the new helper in `evaluate_structured()`** before `GateTradeContext` construction.
   
   Per the diagnostic’s recommendation, insert between line 534 and line 558. Detect naked single-leg options by:
- The trade dict has `option_type` (or `option_side`, whichever the NakedOptionEngine emits — verify from `ScoredNakedOption` fields), AND
- The trade dict does NOT have both `long_strike` and `short_strike` (i.e., it’s not a spread).
   
   When this condition is met:
- Compute EV using the new helper.
- Set `request.trade["total_ev"] = computed_ev`.
- The existing line 561-562 read then picks it up automatically.
   
   Do not branch the gate invocation. Do not add a second gate runner. The existing line 575 invocation works once the dict has `total_ev`.
1. **Do not modify**:
- `NegativeEVGate` class or any code in `app/analysis/hard_gates/`.
- The gate caller logic at `app/api/evaluation_routes.py:578-591`.
- `_build_exit_rows()` or `_spread_value()`.
- `NakedOptionEngine` or `ScoredNakedOption`.
- Lottery Ticket scoring weights.
- The NakedOptionEngine delta filter parameters.
   
   (These are out-of-scope items tracked in separate tickets.)

### Frontend changes (`web/`)

1. **Add EXPIRES WORTHLESS tagged row** to `buildLongOptionExitScenarios()` (`web/src/pages/TradesPage.jsx:230-311`).
   
   Behavior:
- Compute `expireWorthlessProb` using the same approach as the existing per-bin probability calculation (`normCdf` etc.). Yes, the frontend’s normal-CDF approximation is imperfect; that is OUT OF SCOPE for this story. Match what the rest of the function does for consistency.
- For a long put with strike `K` and underlying `U`: include the row when `U > K` (option is OTM at evaluation). Probability = `P(price_at_expiry ≥ K)`.
- For a long call with strike `K` and underlying `U`: include the row when `U < K` (option is OTM at evaluation). Probability = `P(price_at_expiry ≤ K)`.
- Row content:
  - Displayed `underlying` value: for a long put, `strike + 0.01`; for a long call, `strike - 0.01` (sits just outside the breakeven on the loss side).
  - P&L: `-debit × 100` (full loss of premium).
  - Probability: as computed above, formatted `##.00%`.
  - EV: `pnl × probability` per the existing pattern.
  - Signal label: `EXPIRES WORTHLESS`.
- Render position: the row should appear in price-sorted order alongside the other tagged rows. Do not append at the end if it breaks the existing sort.
- The `totalEV` footer continues to be the sum across all bins (existing behavior — do not change the summation logic; the new row’s EV is already part of the bin sum, just newly tagged for display).
1. **Do not modify**:
- The frontend’s `normCdf` or `sigma` calculation.
- The exit-scenario API contract.
- The Trade Evaluation Card layout outside Section B.

### Tests

1. **`tests/analysis/test_ev_gate_msft_410p.py`** — new file. Exercises the MSFT 410P repro case as a regression fixture.
   
   Test contents:
- Build a `request.trade` dict mirroring the MSFT 410P trade (strike 410, underlying 416.78, IV 0.2731, DTE 58, debit 14.90, option_type PUT).
- Call `_compute_naked_long_option_ev()` with those inputs. Assert the result is < 0. Assert it is more negative than -$500 (sanity check that modal mass is captured; the diagnostic estimated -$850 to -$1,300).
- Build a minimal `GateTradeContext` with that EV. Call `NegativeEVGate._evaluate()`. Assert `triggered=True` and `verdict=="PASS"`.
- The test must FAIL on the pre-fix code (the helper doesn’t exist) and PASS on the post-fix code. Document this expectation in a test docstring.
1. **`tests/analysis/test_exit_scenario_probability_sum.py`** — new file. Asserts probability mass sums to 1.0 ± 1e-6 across the canonical probability matrix for a representative set of trade types.
   
   Test contents:
- For each of these trade types, build a candidate, retrieve its probability matrix via `compute_probability_matrix()`, and assert `abs(sum(probs) - 1.0) < 1e-6`:
  - Bull put credit (e.g., SPY 390/395 with 30 DTE)
  - Bear put debit (e.g., QQQ 350/340 with 30 DTE)
  - Single long put (the MSFT 410P case)
  - Single long call (any reasonable ATM/OTM call)
- The test does NOT need to exercise `_build_exit_rows` — only the canonical probability source. The invariant is about the matrix, not about what the rendering layer chooses to display.
1. **Do not** add tests that rely on hitting the live Schwab API or any external service. Use fixture data inline.

## Acceptance criteria

1. `_compute_naked_long_option_ev()` exists in `app/api/evaluation_routes.py` (or equivalent backend location), is unit-tested, and returns a negative value for the MSFT 410P inputs.
1. `evaluate_structured()` injects `total_ev` into `request.trade` for naked single-leg long options before `GateTradeContext` construction.
1. When `evaluate_structured` is called with the MSFT 410P trade payload, `NegativeEVGate` triggers (`triggered=True`, `verdict="PASS"`), the Claude API call is short-circuited, and the response verdict is `PASS`.
1. The probability-sum invariant test passes for all four trade types listed.
1. The MSFT 410P regression test passes.
1. `buildLongOptionExitScenarios()` renders an `EXPIRES WORTHLESS` tagged row when the underlying is OTM at evaluation, for both long puts and long calls.
1. Existing tests in `tests/analysis/` still pass.
1. `npm run build` (or equivalent frontend build command) succeeds with no new warnings.
1. `pytest` (backend) and the frontend lint/build pipeline both succeed locally before commit.

## Out of scope (tracked in separate tickets — do not address here)

- **Lottery Ticket scoring weight redistribution** (add `expected_value` as a weighted metric to LT scorer) — new ticket. Defense-in-depth, not required for this fix.
- **NakedOptionEngine delta filter fallback** (use LT’s intended `delta_max=0.15` instead of scorer fallback 0.85) — new ticket. Filters near-ATM options out of the LT pipeline.
- **Frontend EV calculation correctness** (replace normal-CDF with lognormal CDF, or have frontend read backend-computed EV) — new ticket. The frontend’s displayed Total EV will remain approximate after this fix; the gate is the authority that matters.
- **Composite score floor / veto mechanism** (prevent high-iv-score + high-delta-score from overwhelming zero rr_score) — OTA-506.
- **Narrative-verdict consistency check** — OTA-502.
- **Modal-outcome row for spread trades** — out of scope; the modal outcome for spreads is already represented by the spread P&L curve; this story only adds the row for naked single-leg long options where the OTM-at-expiry case is the dominant probability mass.

## Verification steps

Before signaling done:

1. Run the new unit test: `pytest tests/analysis/test_ev_gate_msft_410p.py -v`. Confirm it passes.
1. Run the invariant test: `pytest tests/analysis/test_exit_scenario_probability_sum.py -v`. Confirm it passes.
1. Run the full backend test suite: `pytest`. Confirm no regressions.
1. Trace the MSFT 410P case through the pipeline by hand (read the modified `evaluate_structured` and confirm the injection point is reached for the trade shape).
1. Frontend: open the Trades page, evaluate a long put where underlying > strike, expand the trade detail Section B, confirm the EXPIRES WORTHLESS row renders with a probability and an EV value, and that the existing five tagged rows still appear.
1. Frontend build: run the project’s frontend build command (PowerShell — Don’s environment).
1. `git status` shows changes confined to:
- `app/api/evaluation_routes.py` (helper + injection)
- `web/src/pages/TradesPage.jsx` (modal-outcome row)
- `tests/analysis/test_ev_gate_msft_410p.py` (new)
- `tests/analysis/test_exit_scenario_probability_sum.py` (new)
  No other files modified.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

The commit covers backend EV computation, frontend modal-outcome row, and both new tests. Single coherent change.

## Coordination footer

Independent — no downstream dependency. After this commit, Don will manually validate the MSFT 410P repro case in the deployed dev environment and decide whether to advance OTA-676 to Code & Test Complete.

## Commit message template (if committing)

```
OTA-676 fix: compute naked-option EV server-side so NegativeEVGate can fire

- Add _compute_naked_long_option_ev() using canonical lognormal probability matrix
- Inject total_ev into trade dict for naked single-leg options before gate eval
- Render EXPIRES WORTHLESS row in exit scenario table for OTM long options
- Add regression test for MSFT 410P 2026-07-17 repro case
- Add probability-sum invariant test across credit/debit/long trade types
```