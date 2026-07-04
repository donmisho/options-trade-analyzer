# OTA-836 Implementation Prompt (Updated) — Engine Startup Errors: Build-to-Testable

> This prompt supersedes the original OTA-836 body. Read this in full before touching code. If anything here conflicts with the existing ticket body, this prompt wins.

## Intent

Get the engine to boot cleanly enough to be **backtested and paper-traded**. We are explicitly **not** chasing a fully clean fatal restore in this pass, and we are **not** tuning any rule for correctness. Rule correctness will be validated later through backtesting and paper trades, and rules may be moved between phases at that time. Your job is to clear the startup blockers, wire the formulas the contract already expects, remove dead config-path code, and leave the system running with its existing safety net intact.

## Hard constraints

1. **Do NOT remove the OTA-830 try/except in `app/main.py` (around lines 339-353).** The original 836 body called for removing it. That is now explicitly deferred to a follow-on ticket. The safety net stays so the engine keeps booting while any remaining validation errors are logged rather than fatal.
2. **Do NOT tune rule behavior.** Where a rule currently produces a value or verdict, replicate it exactly. Capture the current value before you write the formula.
3. **Do NOT do the directional surface-scoped validation work.** That is the follow-on. Directional validation errors will remain caught-and-logged by the safety net in this pass, and that is acceptable.
4. Read-only first. No edits, no reseed, no commit until Phase 1 reports clean.

## Out of scope (capture as a follow-on story, do not build here)

- Directional surface-scoped validation (the 8 bound `dir_*` formulas being validated against the screening registry).
- Removal of the OTA-830 try/except (the clean fatal restore / true "engine goes live" milestone).
- Any rule-correctness or threshold tuning.
- OTA-839's `chart_state_valid_alignment` value-domain rule. This prompt touches `chart_state_matches_trade_direction` (the `formula:` rule) and adds the `chart_state_matches_direction` live implementation. It must not touch `chart_state_valid_alignment`.

---

## Phase 1 — Read-only preflight (conditional STOP)

Run all four gates read-only. Report findings. Apply the STOP rule below before any edits.

**Gate A (critical, decides the whole approach): runtime-fallback check.**
Determine what the engine does at runtime when `init_engine_runtime` runs `validate_and_raise`, that raises, and the OTA-830 try/except catches it. Specifically: after the exception is caught, does the engine still evaluate the config-driven rules at request time, or does it fall back to a legacy or no-engine path? Trace the except block and whatever runtime path the scan and evaluation routes take after a caught restore failure.
- If the engine still runs the config-driven rules with errors merely logged: testable. Proceed.
- If it falls back to a legacy path or disables the engine: **STOP and report.** In that case the build-to-testable plan does not actually yield a testable system, and we need to rethink before writing any code.

**Gate B: binding verification.**
Confirm, per strategy, which of the four workbook-sourced carve-outs are enabled AND bound to a live screening strategy. Use a `--dry-run` seed inspection (the .xlsx is binary, so do not try to read it directly). The four to check:
- `adj_sma_alignment_against_trade`
- `spread_width_tier_compliance`
- `stock_extended_against_entry`
- `stock_extended_in_trade_direction`

(`adj_dte_8_13_penalty` binding is already confirmed in code: bound to all four screening strategies.)
A carve-out blocks `load_config` only if it is enabled and bound. That binding set determines which carve-outs need action.

**Gate C: dead-rule consumer check.**
Grep for any consumer of the five EV-gate formulas OUTSIDE the FormulaRegistry path before deregistering them: `dte_hard_filter`, `dte_warning_penalty`, `credit_pct_of_width_floor`, `debit_pct_of_width_ceiling`, `negative_ev_gate`. Confirm nothing in `evaluation_routes.py`, analysis, or any other live path calls them directly. If a live consumer exists, report it and do not deregister that one.

**Gate D: capture current behavior to replicate.**
Record the exact current behavior for the formulas you will build, so you replicate and do not invent:
- `adj_dte_8_13_penalty`: confirmed `-20` when `8 <= dte <= 13`, else `0`.
- `adj_sma_alignment_against_trade`: read the current workbook condition and penalty value from the dry-run output.
- `chart_state_matches_direction` and `extension_matches_trade_direction`: confirm the intended pass/fail and adjustment behavior from their existing rule definitions (`chart_state_matches_trade_direction` and `adj_stock_extended_direction_match`).

**STOP rule:** If Gate A shows fallback, STOP and report. Otherwise report Gates A-D and proceed to Phase 2.

---

## Phase 2 — Implementation

### 1. Resolve the five carve-outs (cheapest wiring that lets `load_config` pass)

- `adj_dte_8_13_penalty`: implement as a formula (see step 2). It is bound to all four strategies and blocks the loader.
- `adj_sma_alignment_against_trade`: if Gate B shows it is bound, implement as a formula (step 2). If it is not bound, leave it as-is (it does not block the loader); do not build it.
- `spread_width_tier_compliance`: no producer exists for the five-tier width lookup, so an honest formula is not possible today. If Gate B shows it is bound, **park it**: disable the rule or unbind it from the screening strategies so it no longer blocks the loader. Add a code comment noting it is parked pending the width-tier producer and is to be revisited during backtesting. Do not build the lookup.
- `stock_extended_against_entry` and `stock_extended_in_trade_direction`: if Gate B shows either is bound, park it the same way (disable or unbind). If not bound, leave as-is. Do not retire or delete the rows in this pass; parking is reversible and keeps correctness decisions for backtesting.

### 2. Build the formulas the contract expects

Add live implementations so the screening registry matches the contract. Decorate each correctly and replicate the captured behavior exactly.

In `app/options_rules/screening/gate_formulas.py`:
- `chart_state_matches_direction` (`@gate_formula`): cross-field, passes when chart state aligns with `trade_direction`. Already present in the contract; this adds the missing live implementation.

In `app/options_rules/screening/adjustment_formulas.py`:
- `extension_matches_trade_direction` (`@adjustment_formula`): cross-field, replicate the existing `adj_stock_extended_direction_match` behavior. Already in the contract; adds the missing live implementation.
- `adj_dte_8_13_penalty` (`@adjustment_formula`): returns `-20` when `8 <= dte <= 13`, else `0`. Mirror the pattern of `probability_asymmetry_penalty` / `cushion_penalty_moderate`. Do **not** implement as `BETWEEN`: a penalty implemented as two split atoms would double-apply across bindings. New formula, new contract row.
- `adj_sma_alignment_against_trade` (`@adjustment_formula`), only if Gate B showed it bound: cross-field (SMA alignment vs `trade_direction`), replicate the captured workbook penalty. New formula, new contract row.

Wire the `formula_ref` for each in `scripts/seed_engine_config.py` where those rules are seeded.

### 3. Deregister the five dead EV-gate formulas

In `app/options_rules/screening/gate_formulas.py`, remove the five EV-gate formula implementations confirmed clean in Gate C: `dte_hard_filter`, `dte_warning_penalty`, `credit_pct_of_width_floor`, `debit_pct_of_width_ceiling`, `negative_ev_gate`. These are live in the registry but absent from the contract and referenced by no live `formula_ref` (the engine's real EV gate is `total_expected_value BETWEEN`). They currently fire `FORMULA_REGISTRY_DRIFT`. Remove only those Gate C confirmed have no live consumer.

### 4. Leave the safety net in place

Do not touch `app/main.py`. The try/except stays.

### 5. Update the contract docs

Update `claude_context/engine-formula-registry.md` and `requirements/Configuration/formula-registry-contract.md`:
- Add the new adjustment formula rows: `adj_dte_8_13_penalty` and, if built, `adj_sma_alignment_against_trade`.
- `chart_state_matches_direction` and `extension_matches_trade_direction` are already in the contract; no rows added for them.
- The five EV-gate formulas were never in the contract; their removal changes no contract rows.
- Resulting screening contract count: **26 if `adj_sma_alignment_against_trade` was bound and built, otherwise 25.**
- Do **not** add a directional contract section in this pass.

### 6. Reseed

Run the seed after the above:

```
python scripts/seed_engine_config.py
```

---

## Acceptance criteria

1. `load_config` no longer raises (the five carve-outs are resolved by formula or by parking).
2. The app boots. The engine restore runs. Any remaining validation errors (directional surface, and anything else still open) are caught by the OTA-830 safety net and logged, not fatal.
3. Gate A's finding holds in practice: the engine evaluates config-driven rules at runtime, so the system is genuinely backtestable and paper-tradeable.
4. The four (or three) new formulas appear in the screening registry and their rules resolve their `formula_ref`.
5. The five EV-gate formulas no longer fire `FORMULA_REGISTRY_DRIFT`.
6. The OTA-830 try/except is unchanged.

## QA (Level 3)

Scoring-engine math plus cross-cutting config and validation, so run the full Post-Build QA Gate: AMZN regression, MSFT anchor (OTA-284), and a dev deploy smoke before prod. Add a live mixed-surface boot check, since the AMZN and MSFT suites will not exercise the directional surface and a green directional test in isolation is not proof of a clean live boot.

## Files touched

- `scripts/seed_engine_config.py` (carve-out resolution: formula_ref wiring and park/disable rows; EV-gate dead-row cleanup if seeded here)
- `app/options_rules/screening/gate_formulas.py` (add `chart_state_matches_direction`; remove the five EV-gate formulas)
- `app/options_rules/screening/adjustment_formulas.py` (add `extension_matches_trade_direction`, `adj_dte_8_13_penalty`, and `adj_sma_alignment_against_trade` if bound)
- `claude_context/engine-formula-registry.md` and `requirements/Configuration/formula-registry-contract.md` (doc delta to 25 or 26)
- NOT `app/main.py` (safety net stays)
- Reseed after the above

## Workflow

1. Run Phase 1. Report Gates A-D.
2. Apply the STOP rule. If Gate A shows fallback, stop and report; otherwise proceed.
3. Implement Phase 2.
4. Reseed, then run QA.
5. Capture the deferred work as a follow-on story: directional surface-scoped validation plus removal of the OTA-830 try/except (the clean fatal restore).
6. Move OTA-836 to In Review.
