---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash
---

# OTA-837 — Register directional earnings and negative-EV gate formulas

## Terminal context
- This terminal: Terminal A (single terminal)
- Concurrent terminals: none
- Cross-terminal dependencies: none. This is code-only in `app/options_rules/directional/`; it does NOT touch `scripts/seed_engine_config.py`, `app/main.py`, or any shared exclusivity-locked file. It is the new head of the seed chain and must land before OTA-833.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
```

Read `insight_engine.md` §3.6 (formula rules) and §6.3 (expression library) closely — they govern this work. `business-rules.md` is the source of truth for any gate behavior/thresholds; do not invent thresholds in code.

## Relevant Context — Do Not Deviate Without Escalation

Source: OTA-833 Phase 0 report (the NO-GO that created this ticket)
The engine generic predicate path (`app/insight_engine/expressions.py`) evaluates only:
`LHS = named_values[referenced_named_values[0]]  OP  RHS = a single bound parameter literal`.
It cannot compare two named values and has no arithmetic. Two directional gates therefore
cannot be expressed as generic predicates and must be backed by registered formulas:
  1. earnings — needs `next_earnings_date <= expiration + buffer` (two named values + date math).
  2. negative-EV — needs unified EV `< 0`, but EV is split across two named values (below).

Source: OTA-833 Phase 0 report + OTA-730 (screening earnings gate)
The SCREENING surface already solved the earnings case with registered formulas
(`formula:earnings_route1…4`). This ticket mirrors that proven pattern on the directional
surface. Read screening's implementation and replicate its formula-backed-gate contract
exactly — do not invent a new gate mechanism.

Source: OTA-834 (shipped) + insight_engine.md §3.6
Directional EV is deliberately split into two named values:
  - `ev_raw` — DERIVED, spreads only; `None` for naked longs.
  - `total_ev` — COMPUTED, naked longs only; absent for spreads.
`dir_negative_ev` must read `ev_raw` when present, else `total_ev`. A naked candidate
(`ev_raw` is `None`) must coalesce to `total_ev` and must NOT be false-halted by a naive
`None >= 0 → False`. If BOTH are absent, defer to the data-completeness gate (do not halt
on `None`).

Source: OTA-834 (shipped; confirmed present in OTA-833 Phase 0 item #2)
The directional adapter `_CATALOG` already publishes `next_earnings_date`, `earnings_unknown`,
`open_interest`, `volume`, `bid_ask_spread_pct`. Do NOT re-add or modify these. `expiration`
is referenced by the report as an available directional named value — confirm in Phase 0.

Source: Epic OTA-679 acceptance criteria (engine invariants)
- No `if strategy_id == …` / `if strategy_key == …` branches in engine or rule-library code.
- Formulas are pure `(named_values, params) -> …`; per-strategy behavior comes from junction
  rows, never from code. The earnings kill-vs-record-only split (Income hard-stop;
  Growth/Longshot record-only) and the unknown-earnings flag-don't-kill path are driven by
  OTA-833's junction config (`stop_if_fail` / `score_penalty`) plus the `earnings_unknown`
  flag — NOT by branching inside `dir_earnings`.

Source: OTA-836 description (dual-registry / contract balance)
`build_formula_registry()` auto-derives the SHARED `formula_registry` seed from `formula_ref`,
so any newly-registered formula auto-lands in the seed but not in
`claude_context/engine-formula-registry.md`. OTA-836's `validate_and_raise` dual-registry check
flags `FORMULA_MISSING_FROM_CONTRACT` on drift. Keeping the doc balanced for these two formulas
is owned by OTA-836's existing doc-balance scope ("update engine-formula-registry.md for any new
impls") — this ticket does NOT edit that doc. Phase 0 must report the exact net delta (expected
+2: `dir_earnings`, `dir_negative_ev`) so OTA-836 picks it up.

---

## Phase 0 — Read-only discovery (HARD STOP before any edits)

No edits, no writes, no commits in this phase. Produce findings, then STOP for a GO/NO-GO decision.

Confirm and report, each with file:line evidence:

1. **Gate-formula return contract.** Read screening's `formula:earnings_route1…4` implementation
   and the engine's formula-backed-gate evaluation path. Report the EXACT contract a
   formula-backed gate returns (bool? float compared by the junction operator? a halt/terminal
   sentinel like the OD-2 `terminal_verdict` mechanism?) and how `stop_if_fail` interacts with it.
   This contract is what `dir_earnings` / `dir_negative_ev` must implement.
2. **Registry mechanism.** Confirm the decorator/registry these formulas register under in
   `app/options_rules/directional/` (expected: the same `@directional_formula` registry OTA-755/834
   used) and whether gate formulas share it with scoring formulas or use a separate decorator.
   Note any range decorator (scoring formulas are `[0,100]`-enforced; a gate formula likely is not).
3. **Named-value availability.** Confirm `next_earnings_date`, `earnings_unknown`, `expiration`,
   `ev_raw`, `total_ev` are all resolvable to directional formulas, with their tier/type and exact
   null-semantics (especially: is `expiration` a named value on the directional surface?).
4. **Buffer/param mechanism.** Confirm how a junction row supplies a formula `param` (the earnings
   buffer/window) and that `dir_earnings` can read it from `params` — mirroring how screening's
   earnings routes parameterize their window.
5. **Doc-balance delta.** State the net `engine-formula-registry.md` change (expected +2) for
   OTA-836 to absorb. Do not edit the doc.
6. **QA level confirmation.** Confirm Level 2 (engine-evaluated rule-library code).

**GO** if items 1–4 resolve cleanly (the contract is known and both formulas are expressible against
available named values + params). **NO-GO** if the gate-formula contract or a required named value is
missing — report and STOP; do not work around it.

### STOP — report Phase 0 findings and await GO/NO-GO before proceeding to implementation.

---

## Implementation — only after GO

Register two formulas in `app/options_rules/directional/` per the contract confirmed in Phase 0:

- **`dir_earnings`** — reads `next_earnings_date` and `expiration`, applies the junction-supplied
  buffer `param`; returns the gate result per the confirmed contract. No strategy branching; the
  unknown-earnings path is handled by reading `earnings_unknown` + the junction config, not in-formula.
- **`dir_negative_ev`** — reads `ev_raw` when present, else `total_ev`; signals halt when `< 0`.
  Naked (`ev_raw` is `None`) coalesces to `total_ev` and is never false-halted; both-absent defers
  to the data-completeness gate.

## Acceptance criteria
- `dir_earnings` and `dir_negative_ev` registered in the directional formula registry; each a pure
  function of `named_values` + `params`; return contract matches screening's formula-backed gates.
- `dir_earnings` reads `next_earnings_date` + `expiration` with a junction-supplied buffer param;
  no `if strategy_key ==` branching; unknown earnings handled via `earnings_unknown` + junction config.
- `dir_negative_ev` reads `ev_raw` else `total_ev`; halts on `< 0`; naked with `ev_raw` null is not
  false-halted; both-null does not halt.
- Both names resolve through `build_formula_registry()` into the SHARED `formula_registry` seed
  (verify by running the builder; do NOT reseed the DB here).
- Engine startup formula-registry membership validation passes (or the relevant unit/validation
  test passes) for the two new names.
- New/updated unit tests cover: naked vs spread EV coalesce, `None`-EV non-halt, both-null defer,
  and an in-window vs out-of-window earnings case.

## Out of scope
- The other three directional gates (data-completeness, liquidity, budget-flag) — seeded as atomic
  predicates by OTA-833.
- Any change to `scripts/seed_engine_config.py`, junction wiring, gate config, verdict bands — OTA-833.
- Any DB reseed — happens in OTA-833.
- Editing `claude_context/engine-formula-registry.md` — owned by OTA-836 (report the delta only).
- Directional scoring formulas + adapter inputs — OTA-834 (done). No skew.

## Verification steps
- `cat` the required-reading files; confirm no embedded-context contradiction with the canonical docs (escalate if any).
- Run the directional rule-library unit tests + the formula-registry membership/validation test.
- Run `build_formula_registry()` (builder only, no DB write) and confirm both names appear.
- Confirm `grep` shows zero `if strategy_key ==` / `if strategy_id ==` introduced.
- QA level 2 applied (rule-library, engine-evaluated). Note which tests were run in the diff summary.

## Commit instruction
I have been instructed NOT to commit. Stage the changes, present the full diff and the test output, and STOP. Don reviews and commits manually.

## Coordination footer
STOP after presenting the diff. Downstream: OTA-833 (which references these two `formula_ref`s) runs next, after Don commits this and confirms.

## Commit message template (Don will apply on approval)
OTA-837 feat: register dir_earnings + dir_negative_ev directional gate formulas
