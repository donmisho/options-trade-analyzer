# OTA-676 — EV calculation excludes modal-outcome probability mass, allowing negative-EV EXECUTE verdicts (Phase 1 — Diagnostic, read-only)

## Terminal context
- This terminal: Solo
- Concurrent terminals: none
- Cross-terminal dependencies: none

## Required reading
Before any analysis or code reading:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
```

This Story is in the **Scoring / gates / health / P&L** domain per the CLAUDE.md per-domain required-reading table.

## Relevant Context — Do Not Deviate Without Escalation

**Source: architecture-plan.md § Hard Gates Pipeline**
Rule: Hard gates live in `app/analysis/hard_gates/` as a registered sub-package. Each gate implements `evaluate(candidate, context) -> GateResult`. Gates are registered via `register_gate(gate_class)` at startup. Gate ordering is significant — gates run in registration order; a single FAIL short-circuits subsequent gates. Currently registered gates: `EarningsInWindowGate`, `NegativeEVGate`.

**Source: architecture-plan.md § End-to-End Data Flow, step 5**
Rule: "The chain is fed through the registered hard gates... NegativeEVGate filters on expected value. Pre-screen before scoring is the cost optimization that prevents Claude from ever seeing trades that would be auto-rejected."

**Source: business-rules.md § Strategy-Structure Compatibility**
Rule: Lottery Ticket strategy's `compatible_structures` = `[SINGLE_LONG_CALL, SINGLE_LONG_PUT]`. The MSFT 410P trade is a `SINGLE_LONG_PUT` and is routed through the long-options engine (`app/analysis/long_call_engine.py`), not the verticals engine.

**Source: business-rules.md § Hard Gates (P0 Pipeline) — placeholder block**
Rule (paraphrased from placeholder): NegativeEVGate is intended to FAIL candidates with negative expected value.

**Source: UI-GUIDANCE.md § Part 10 Screen 2 → Trade Detail Expansion → Section B**
Rule: Exit scenario table renders `$5 increments` with `Footer: Total EV`. The table currently surfaces selected price points; the modal-outcome scenario (e.g., expires worthless for OTM long premium) is not consistently surfaced as a row.

**Source: business-rules.md § Display Formatting Rules — placeholder block**
Rule: Monetary display `##.00` via `.toFixed(2)`; no `$` prefix. Scores `##.00`. Probabilities `##.00%`.

## Reproduction case (the artifact under investigation)

Trade evaluated on 2026-05-19:

| Field | Value |
|---|---|
| Ticker | MSFT |
| Structure | SINGLE_LONG_PUT |
| Strike | 410 |
| Expiration | 2026-07-17 (58 DTE) |
| Underlying at evaluation | $416.78 |
| Debit | $14.90 / contract |
| Breakeven | $395.10 (requires 5.20% downside) |
| Delta | 0.4180 |
| IV | 27.31% |
| Theta | $15.70/day |
| Chart status | "Mixed — No Signal" |
| Earnings | 2026-07-28 (post-expiry) |
| App verdict | **EXECUTE** |
| App composite score | **73.13** |
| App displayed total EV | **-$36.90** |

Exit scenario table as displayed by the app:

| Underlying | P&L | Probability | EV | Signal |
|---|---|---|---|---|
| 280.00 | +11510 | 0.05% | +5.24 | MAX PROFIT |
| 340.00 | +5510 | 1.03% | +56.72 | MONITOR PROFIT |
| 395.00 | +10 | 3.89% | +0.39 | BREAK EVEN |
| 405.00 | -990 | 4.23% | -41.84 | MONITOR LOSS |
| 410.00 | -1490 | 4.33% | -64.51 | STOP |

Listed probabilities sum to ~13.5%. The remaining ~86.5% of probability mass (the modal outcome — MSFT > $410 at expiry, -$1,490 loss) is not surfaced as a row.

Hypothesized true total EV including modal mass:
- 0.865 × -$1,490 = -$1,288.85 from modal row
- Plus listed EV: ~-$37
- **True total: ~-$1,325**

## Scope (Phase 1 — Diagnostic only)

This phase is **read-only**. No source files outside `claude_context/diagnostics/` are modified. The deliverable is a written report.

Investigate and confirm or rule out, with file:line evidence:

### Hypothesis 1 — The EV gate runs but on incomplete EV

Trace the EV calculation:
- Where is total EV computed for a `SINGLE_LONG_PUT` candidate?
- Does the calculation iterate over all price points in the Black-Scholes probability matrix, or only the surfaced exit scenarios?
- What is the actual value passed to `NegativeEVGate.evaluate()` for the MSFT 410P case (reconstruct from code path, not from a live run)?

### Hypothesis 2 — The EV gate runs but only flags, does not FAIL

Read `app/analysis/hard_gates/negative_ev_gate.py` (or equivalent path):
- What does `evaluate()` return when EV is negative?
- Is the return value a `GateResult.FAIL` that short-circuits the pipeline, or a softer flag/warning that allows the candidate to continue to scoring?
- Trace the call site that consumes the `GateResult` — does it actually act on `FAIL`?

### Hypothesis 3 — The EV gate is not invoked on the long-options path

Check the gate registration and invocation:
- Where are gates registered? Confirm `NegativeEVGate` is in the active registry.
- Where is the gate runner invoked? Find every call site.
- Specifically: does `long_call_engine.py` (the `SINGLE_LONG_PUT` / `SINGLE_LONG_CALL` path) pass candidates through the same gate runner that `vertical_engine.py` uses? Or does it bypass the hard-gate pipeline?

### Secondary investigation — Probability mass

For the MSFT 410P case (or the closest analogue you can reconstruct from code without a live API call):
- Does the Black-Scholes probability matrix output (`app/analysis/black_scholes.py`) include the full probability mass (sums to 1.0 across price levels at expiry), or is it truncated to a price band like ±10%?
- Does the exit scenario table generator filter the matrix down to "interesting" price points, dropping the modal outcome from the table even when it would be the dominant contributor to EV?
- Where is "total EV" computed for display? Is it summed over the displayed rows only, or over the full probability distribution?

### Tertiary — Scoring formula sanity check

This is not a hypothesis to confirm, just data to gather for the Phase 2 prompt:
- Read `app/analysis/strategy_scorer.py` and the Lottery Ticket scoring weights in `strategy_definitions.py`.
- Record the per-metric weights for Lottery Ticket: how much does `iv_score` contribute? `delta_score`? `rr_score`? Other metrics?
- Note any place where a near-zero metric is *not* able to drag the composite below an EXECUTE threshold via veto or floor.

This information is for the next Story's Phase 2, not for action in this Phase 1.

## Acceptance criteria

1. A report file is created at `claude_context/diagnostics/ev-gate-msft-410p-trace.md` containing:
   - A confirmed-or-ruled-out verdict for each of the three primary hypotheses, each with file:line citations.
   - The actual EV value `NegativeEVGate` would see for the MSFT 410P case (reconstructed from code, with the reasoning shown).
   - The actual gate return value path: what `evaluate()` returns and how the caller handles it.
   - The actual invocation path for `long_call_engine` candidates: confirmed-passes-through-gates or confirmed-bypasses-gates.
   - Secondary findings on probability mass / EV calculation completeness.
   - Tertiary findings on Lottery Ticket scoring weights (informational only).
   - A "Recommended Phase 2 fix" section: one paragraph describing the minimum code change that would cause `NegativeEVGate` to FAIL the MSFT 410P case.
2. No source files outside `claude_context/diagnostics/` are modified.
3. The report cites every claim with `file:line` references that a reader can navigate to.
4. The report's "Recommended Phase 2 fix" is consistent with the evidence — it does not propose changes whose necessity has not been established by the trace.

## Out of scope (Phase 1)

- Any change to `app/analysis/`, `app/api/`, or `web/src/`.
- Any new tests (Phase 2 work).
- Running the live app or hitting Schwab to reproduce; this is a code-trace exercise. If a live run is essential to answer a hypothesis, surface that as a blocker in the report rather than running it.
- Speculation about the right Phase 2 fix beyond the single recommended paragraph.
- Anything listed in the Story's "Out of scope (tracked separately)" block.

## Verification steps

Before signaling done:

1. The report file exists at the specified path.
2. Each of the three primary hypotheses has an explicit Confirmed / Ruled out / Inconclusive verdict.
3. Every factual claim in the report has a `file:line` citation.
4. The Black-Scholes matrix completeness question has been answered (sums to 1.0 or doesn't).
5. The total-EV computation site has been located in code.
6. The "Recommended Phase 2 fix" paragraph is present and consistent with the trace evidence.
7. `git status` shows changes only inside `claude_context/diagnostics/`.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

The commit contains the diagnostic report only. No source code changes.

## Coordination footer

OK to continue to `OTA-676-Phase2-EV-gate-fix.md` after Don reviews the diagnostic report and Claude Web issues the Phase 2 prompt.

## Commit message template (if committing)

```
OTA-676 diag: trace EV gate bypass on MSFT 410P repro case
```
