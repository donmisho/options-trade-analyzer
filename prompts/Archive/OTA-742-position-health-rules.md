---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-742 — Position-health rule library
covers OTA-743, OTA-744, OTA-745, OTA-746, OTA-747, OTA-748, OTA-749, OTA-750, OTA-751

> Multi-story prompt. Builds the registered formulas + config that grade open positions as a weighted score [0, 100] → A/B/C/D/F. One commit at the end after the OTA-751 parity gate. Stop-and-report between phases. Claude Code does not commit; Don commits manually. After this ships, `app/analysis/health_grade.py` is deleted.

## Terminal context
- This terminal: **either terminal** (run after OTA-734's catalog lands; this is not parallel with OTA-734's build)
- Concurrent terminals: none required; if Terminal B is still on OTA-752, that work is disjoint (directional), so parallel is safe — but config/Strategies-tab edits here and in OTA-754 both touch the runtime tables. If both run at once, **sequence the Strategies-tab edits** and report before editing shared config.
- Cross-terminal dependencies:
  - **UPSTREAM GATE (catalog):** these rules bind to named values the **position-health adapter (OTA-734)** publishes via **OTA-740** (input catalog). The catalog must be **committed** before the rules can reference its inputs and pass startup validation. Soft/non-gating for *design*: formula design may pre-start against the §5.1 catalog spec in `insight_engine.md`, but the rules cannot be wired/validated until OTA-740 is on HEAD.
  - **UPSTREAM GATE (engine core):** needs OTA-695 — the registered-formula registry, weighted-score strategy support, and verdict-band lookup (plan F1 S1.5). **Do not start Phase 1 wiring until Phase 0 confirms OTA-740 + OTA-695.**

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-migration-plan.md
```

Then the actual sources:

```
cat app/analysis/health_grade.py                       # parity target + deletion target
ls -R app/options_rules/                                # rule-library + formula-registration pattern
cat app/ota_adapters/position_health/*.py              # the adapter you bind to (OTA-734)
# locate and inspect the published input catalog (OTA-740) the rules reference
```

If the `insight_engine*` docs are not under `claude_context/`, locate them (`git ls-files | grep insight_engine`). If `rules-engine-audit-2026-05-20.md` is present, read its §5a / `health_grade.py` section; if absent, the live `health_grade.py` is the authoritative parity target.

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-742 Work body — Option A locked in**
Health grade is a **weighted-score strategy, not a categorical decision tree.** Score 0–100 from per-criterion contributions, mapped to A/B/C/D/F by verdict bands. Every threshold, weight, and band lives in the configuration source (Scoring Parameters.xlsx / runtime tables). **No literals in code, no decision-tree control flow.** After this feature, all health-grade logic lives in config + registered formulas and `app/analysis/health_grade.py` is deleted.

**Source: OTA-743 Work body — two strategies, verdict bands**
The current code's two paths become two strategies: `position_health_full` (positions with stored Claude warning/stop levels — exit-level proximity dominant, P&L supplementary) and `position_health_basic` (no exit levels — P&L alone). Both share verdict bands **A ≥ 90, B ≥ 75, C ≥ 50, D ≥ 25, F < 25** (subject to Don's review when pinned). Scan parameters: monitor all open positions; run daily after market close + on demand. The Position Monitor Agent (Wave 4, app-side) picks the strategy per position from `position_exit_levels_complete` — **strategy selection is orchestration, not engine logic.**

**Source: OTA-744 Work body — hard gates replace the try/except**
Both strategies require `position_entry_price` not null and `current_position_mark` not null. `position_health_full` additionally requires `position_exit_levels_complete = true` and `position_structure_direction` in (bullish, bearish). The `health_grade.py:78` parse-failure try/except (→ P&L path) is replaced by agent strategy-selection + these hard gates: a `_full` candidate that fails completeness is re-run by the agent under `_basic`. **No silent fallback inside the engine.**

**Source: OTA-745 Work body — `exit_level_safety_score`**
Pure `(named_values, params) -> float in [0, 100]`. Reads `warning_breached`, `stop_breached`, `warning_proximity_ratio`, and a `proximity_buffer_fraction` parameter (**the 20% from `health_grade.py:66, 76`, now a junction parameter, not a literal**). Returns 0 if `stop_breached`; a low parameter-driven value if `warning_breached`; a graduated value on `warning_proximity_ratio` inside the buffer; 100 when well clear. Exact step shape comes from calibration (OTA-748) via parameters — not hardcoded.

**Source: OTA-746 Work body — `pnl_band_score`**
Pure function reading `pnl_pct`, returning [0, 100] from junction-bound band thresholds. The `-0.10 / -0.25 / -0.50` cutoffs in `health_grade.py:_grade_from_pnl_pct` become **four parameter values per strategy.** Same formula serves both strategies; each supplies its own band parameters.

**Source: OTA-747 Work body — post-scoring adjustments preserve the categorical guarantees**
Two atomic, junction-parameterised adjustments running **after** the weighted sum: `stop_breached_floor` (when `stop_breached`, force final score to a floor — default 0 → F band; cf. `health_grade.py:60-61, 71-72`); `warning_breached_cap` (when `warning_breached`, cap final score at a ceiling — default 24 → D band; cf. `health_grade.py:62-63, 73-74`). These preserve "if stop is breached you're F, no matter the rest."

**Source: OTA-748 Work body — junction weights + calibration**
`position_health_full`: `exit_level_safety_score` weight ≈ 0.70 (exit-level state currently overrides everything when present), `pnl_band_score` weight ≈ 0.30; `proximity_buffer_fraction = 0.20`; P&L bands matching `-0.10 / -0.25 / -0.50`; `stop_breached_floor = 0`, `warning_breached_cap = 24`. `position_health_basic`: `pnl_band_score` weight 1.0; same P&L bands. Calibrate against fixtures to parity with current `health_grade.py` letters **within tolerance — some letters change by design** (the Option B → Option A upgrade).

**Source: OTA-749 Work body — kill dead config**
`health_grade.py:31` parses `scale_out` but never uses it; the adapter (OTA-734) now publishes `position_exit_scale_out_underlying`. **Force the decision:** either retire `scale_out` from `claude_exit_levels_json`, or add a `scale_out_proximity_score` rule that consumes it. Dead config does not survive the migration.

**Source: OTA-750 Work body + UI-GUIDANCE.md + CLAUDE.md House Style — color is presentation**
The engine emits the **letter** only. Grade→color mapping moves to the UI rendering layer: A = green, B = teal, C = yellow, D = orange, F = red, using the design tokens (no inline hex; values from `web/src/styles/tokens.js`). No color logic in the engine or rule library.

**Source: business-rules.md — canonical home of the math**
Scoring formulas, hard gates, health-grade math, and verdict bands are business rules. As config/parameters are pinned here, the canonical statement of the health-grade math belongs in `business-rules.md`, not scattered in code or other docs. (Do not edit SoT docs unless this prompt instructs it; if a business-rules.md update is warranted, report it for Don/Claude Web rather than self-editing.)

---

## Phase 0 — Read-only discovery + GATE VERIFICATION (no edits)

Make no file changes. Report and STOP before Phase 1.

1. **Gate — catalog committed (OTA-740)?** Confirm the position-health adapter's input catalog is on HEAD and declares the names these rules read: `warning_breached`, `stop_breached`, `warning_proximity_ratio`, `pnl_pct`, `position_entry_price`, `current_position_mark`, `position_exit_levels_complete`, `position_structure_direction`, `position_exit_scale_out_underlying`. Missing → **STOP: "OTA-740 catalog gate not met."** (Formula *design* may proceed against §5.1 spec, but wiring/validation cannot.)
2. **Gate — engine core (OTA-695)?** Confirm the registered-formula registry, weighted-score strategy support, and verdict-band lookup exist. Confirm how a pure formula `(named_values, params) -> float` is registered and referenced (`formula:<name>`), and how post-scoring adjustments attach. Absent → **STOP: "OTA-695 gate not met."**
3. **Rule-library pattern.** Read `app/options_rules/` (e.g. screening rules) to mirror registration, the junction/Strategies-tab mechanism, and how scan parameters + verdict bands are configured.
4. **Parity target.** Read `app/analysis/health_grade.py` fully; map each branch to a planned formula/parameter. Record the exact current thresholds (the 20%, the `-0.10/-0.25/-0.50`, stop→F, warning→D) and their line refs for the OTA-751 parity suite.
5. **`scale_out` usage.** Confirm `scale_out` is parsed-but-unused today (line ≈31) and that no current code reads it — input to the OTA-749 decision.
6. **UI grade-render site.** Locate where the health grade letter is currently rendered, to plan the OTA-750 color-mapping move to the presentation layer with design tokens.

**STOP. Report Phase 0 findings + both gate verdicts + the recorded current thresholds. Wait for Don.**

---

## OTA-743 — Scope: define `position_health_full` and `position_health_basic` strategies
Add two Strategies-tab rows with shared verdict bands (A ≥ 90, B ≥ 75, C ≥ 50, D ≥ 25, F < 25) and scan parameters (all open positions; daily after close + on demand). `_full` = exit-level-dominant + P&L supplementary; `_basic` = P&L alone.

**OTA-743 — Acceptance:** both strategies exist in the runtime tables; bands + scan parameters are config-driven; the engine constructs each at startup; band values flagged as pending Don's pin-down.

**OTA-743 — Out of scope:** the formulas/gates themselves (later stories).

**STOP-AND-REPORT gate after OTA-743.**

---

## OTA-744 — Scope: data-completeness hard gates per strategy
Register hard gates: both require `position_entry_price` + `current_position_mark` non-null; `_full` additionally requires `position_exit_levels_complete = true` and `position_structure_direction` ∈ {bullish, bearish}. No in-engine silent fallback — the agent re-runs a failed `_full` candidate under `_basic`.

**OTA-744 — Acceptance:** gates are registered as config rules with `stop_if_fail` semantics; a `_full` candidate missing exit-levels fails its completeness gate (proven on a fixture) rather than silently degrading; no try/except fallback exists in engine/rule code.

**OTA-744 — Out of scope:** the agent's re-run orchestration (Wave 4 / Position Monitor Agent).

**STOP-AND-REPORT gate after OTA-744.**

---

## OTA-745 — Scope: `exit_level_safety_score` scoring formula
Register the pure formula per the Relevant Context: reads `warning_breached`, `stop_breached`, `warning_proximity_ratio`, `proximity_buffer_fraction`; returns 0 / low / graduated / 100 by the stated rules, all parameter-driven.

**OTA-745 — Acceptance:** registered and resolvable by `formula:<name>`; returns 0 on `stop_breached`, the low value on `warning_breached`, a monotonic graduated value across `warning_proximity_ratio` inside the buffer, 100 well clear; **zero literals** — the 20% arrives only as `proximity_buffer_fraction`.

**STOP-AND-REPORT gate after OTA-745.**

---

## OTA-746 — Scope: `pnl_band_score` scoring formula
Register the pure formula reading `pnl_pct`, returning [0, 100] from four junction-bound band thresholds (the `-0.10/-0.25/-0.50` become parameters). Same formula serves both strategies via their own band parameters.

**OTA-746 — Acceptance:** registered + resolvable; reproduces `health_grade.py:_grade_from_pnl_pct` banding when given the current thresholds as parameters; no threshold literals in code.

**STOP-AND-REPORT gate after OTA-746.**

---

## OTA-747 — Scope: `stop_breached_floor` + `warning_breached_cap` post-scoring adjustments
Register the two atomic, junction-parameterised adjustments that run after the weighted sum, defaults 0 (floor → F) and 24 (cap → D), preserving the categorical guarantees.

**OTA-747 — Acceptance:** both run after the weighted sum and after `exit_level_safety_score`; with defaults, a `stop_breached` candidate lands in F regardless of other contributions, and a `warning_breached` (not stopped) candidate is capped into D; both are parameters, not literals.

**STOP-AND-REPORT gate after OTA-747.**

---

## OTA-748 — Scope: junction weights and parameter calibration
Populate junction rows per the Relevant Context (`_full`: 0.70/0.30 + parameters; `_basic`: 1.0 + same P&L bands). Calibrate against fixtures to parity with current `health_grade.py` letters within tolerance; annotate intentional divergences (the Option A upgrade).

**OTA-748 — Acceptance:** junction rows complete for both strategies; calibration run documented; the fixture set reaches parity within the stated tolerance with divergences explicitly justified rather than treated as failures.

**STOP-AND-REPORT gate after OTA-748.**

---

## OTA-749 — Scope: resolve `scale_out` (wire a rule or retire the field)
Make the decision the config forces: either retire `scale_out` from `claude_exit_levels_json`, or register a `scale_out_proximity_score` rule consuming `position_exit_scale_out_underlying`. Record the decision + rationale.

**OTA-749 — Acceptance:** `scale_out` is either removed from the schema/parse path (no dangling parse) **or** consumed by a registered, junction-weighted rule — no parsed-but-unused field remains. Decision documented for Don.

**STOP-AND-REPORT gate after OTA-749.**

---

## OTA-750 — Scope: grade→color mapping at the presentation layer
Move the A/B/C/D/F → color mapping (A green, B teal, C yellow, D orange, F red) into the UI rendering layer using design tokens (no inline hex; from `web/src/styles/tokens.js`). The engine emits only the letter.

**OTA-750 — Acceptance:** no color logic in engine/rule-library code; the UI maps letter→token color at render; `grep` shows no hex literals introduced; matches UI-GUIDANCE.md health-grade color contract.

**OTA-750 — Out of scope:** restyling the surrounding component beyond the grade pill.

**STOP-AND-REPORT gate after OTA-750.**

---

## OTA-751 — Scope: rule-library tests and parity check
Fixture positions across the spectrum (just-entered/positive P&L; mid-life nearing warning; warning breached not stop; stop breached; no-exit-levels across P&L bands) produce expected letters under both `position_health_full` and `position_health_basic`. Pairs with the adapter parity tests (OTA-741). These tests are the acceptance gate for the Wave-4 Position Monitor Agent wiring story.

**OTA-751 — Acceptance:** suite runs green across all fixture cases under both strategies; intentional divergences from legacy `health_grade.py` annotated as expected; suite is the named gate for the Wave-4 wiring story.

---

## After OTA-751 passes — delete `health_grade.py`
Per the OTA-742 Work body, once the rule library reaches parity and the engine path is proven, **delete `app/analysis/health_grade.py`** and confirm `grep -rn "health_grade" app/` returns no live caller (the Wave-4 Position Monitor Agent wiring, app-side, is what calls the engine — confirm no rule/engine code imports the old module). If a live caller remains because the Wave-4 wiring has not landed, **do not delete** — leave a `# TODO(OTA-742): delete after Position Monitor Agent wiring removes the last caller` marker and report. (Mirror of the OTA-756 discipline.)

## Verification steps (whole feature)
1. `python -c "import app.options_rules.position_health"` succeeds.
2. Engine startup validation passes: both strategies, every `formula:<name>`, and all referenced catalog names resolve.
3. `grep -rn "0\.20\|-0\.10\|-0\.25\|-0\.50\|== 'F'\|color" app/options_rules/position_health/` shows the thresholds live as **parameters/config**, not code literals, and no color logic.
4. The categorical guarantees hold on fixtures: stop→F, warning→D (OTA-747).
5. OTA-751 parity suite green; divergences annotated.
6. `health_grade.py` deleted (or TODO-marked with caller status reported).
7. **Post-Build QA Gate** (CLAUDE.md): scoring-engine math change → recommend **Level 3** (analysis-layer/health parity + manual scoring-narrative consistency on a few positions). State the level in the commit body.

## Commit instruction
**"I have been instructed to commit. Do you approve? (yes / no)"**
One commit covers the whole feature after the OTA-751 parity gate. Don commits manually.

## Coordination footer
**STOP until Terminal A completes OTA-740 (position-health adapter input catalog) and OTA-695 (engine core) lands.** Formula *design* may pre-start against `insight_engine.md` §5.1, but wiring/validation waits for the committed catalog. If OTA-752 is running concurrently in another terminal, **sequence Strategies-tab edits** and report before editing shared runtime-table config. After this feature commits, it is **Independent** — the next dependent work is the Wave-4 Position Monitor Agent wiring (separate story).

## Commit message template (if committing)
```
OTA-742 OTA-743 OTA-744 OTA-745 OTA-746 OTA-747 OTA-748 OTA-749 OTA-750 OTA-751 feat: position-health rule library (weighted-score strategies, hard gates, calibrated to health_grade.py parity; health_grade.py retired)
```
