# OTA-834 — Add four directional scoring formulas and their adapter inputs

> **Ticket:** OTA-834 (Story under Epic OTA-679; labels `IE-Completion`, `directional`,
> `options-domain`). The additive code layer for the three-objective directional model. Extends
> the directional rule library (OTA-755) and adapter catalog (OTA-753), both Production Deployed.
> Commits **independently** of the OTA-815 → OTA-832 seed chain, but **must land before OTA-833**
> (OTA-833's junction rows reference the names added here; absent them, OTA-833 Phase 0 NO-GOs).

## Terminal context
- This terminal: **Terminal A**
- Concurrent terminals: safe to parallelize with the OTA-815 / OTA-832 seed work — this touches
  `app/options_rules/directional/` and `app/ota_adapters/directional/adapter.py`, not
  `scripts/seed_engine_config.py`. Do NOT parallelize with OTA-833 (which consumes these names).
- Cross-terminal dependencies: none upstream. Downstream: OTA-833 depends on this.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
```

Then inspect (read-only, Phase 0):

```
cat app/options_rules/directional/__init__.py        # @directional_formula registry
cat app/options_rules/directional/scoring_formulas.py # existing dir_probability / dir_buffer pattern
cat app/ota_adapters/directional/adapter.py           # _CATALOG (~lines 331-397) + producers
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: insight_engine.md §3 (rules) + the directional registry (live)**
Formulas register into the module-level `DictFormulaRegistry` via `@directional_formula(name)`;
implementations live in `scoring_formulas.py`. Contract: `(named_values, params) -> float in
[0, 100]`. The decorator hard-enforces the range (`FormulaReturnValueError`). Formulas are pure —
they read only `named_values` and `params`, no I/O, no shared state.

**Source: insight_engine.md §3.5 (tiers) + the directional `_CATALOG` (live)**
Named values carry a tier (RAW / DERIVED / COMPUTED), a type, and null-semantics drawn from the
SHARED set `FAIL_OPEN` / `FAIL_CLOSED` / `SKIP`. New catalog entries must declare all three.

**Source: live Phase 0 discovery (directional catalog, 2026-06-07)**
- EV is split by structure: `ev_raw` (DERIVED, spreads, SKIP-null for naked) and `total_ev`
  (COMPUTED, naked longs). No single unified EV value exists.
- `reward_risk_ratio` (DERIVED, SKIP) = `max_profit / max_loss`; **null for naked longs**
  (unlimited upside).
- `max_loss` (DERIVED, FAIL_CLOSED) is absolute dollars — suitable as the numerator over
  `thesis_risk_budget` (RAW, FAIL_CLOSED).
- `thesis_target_price` (RAW, FAIL_CLOSED), `strike`, `cost` exist — enough to derive a
  target-based payoff multiple for naked longs without a new named value.
- `bid` / `ask` exist (RAW, FAIL_OPEN); `open_interest` and `volume` do **not** exist in the
  catalog and must be added.
- Existing `dir_probability` (reads `prob_of_profit`) and `dir_buffer` (reads `buffer_pct`,
  cap 10) are unchanged. Direction enums are lowercase `bullish` / `bearish`.

## Phase 0 — Read-only discovery, hard GO/NO-GO STOP

No edits. Confirm, then STOP and report GO or NO-GO.

1. Capture the exact `@directional_formula` registration pattern and the param-schema convention
   from `dir_probability` / `dir_buffer` (so the four new formulas mirror it).
2. Capture the `_CATALOG` entry shape (tier / type / null-semantics fields) to mirror for the new
   named values.
3. Confirm the EV producers: `ev_raw` (DERIVED) and `total_ev` (COMPUTED) and their null behaviour,
   so `dir_expected_value` can read whichever is populated at scoring time.
4. Confirm `reward_risk_ratio` is null for naked longs (drives `dir_reward_risk` → 100 and the
   `dir_payoff_multiple` target-based branch).
5. **Locate the existing earnings source** (ContextStore + Finnhub path used elsewhere, e.g. the
   screening earnings gate) and confirm how the directional adapter can populate `next_earnings_date`
   from it. If no reusable path exists → NO-GO, escalate (don't build a new Finnhub client here).
6. Confirm `bid` / `ask` are available to derive `bid_ask_spread_pct`.

Report: the registration pattern, the catalog entry shape, the EV/RR null facts, the earnings
source path, and GO|NO-GO. STOP for approval.

## Scope

### 1. Four new scoring formulas (`app/options_rules/directional/scoring_formulas.py` + registry)

- `dir_expected_value` — reads `ev_raw` when present, else `total_ev`; positive EV scales toward
  100, negative scales toward 0. Unified across structures.
- `dir_max_loss_pct` — `max_loss / thesis_risk_budget`; lower budget consumption scores higher
  (params govern the scaling/cap).
- `dir_reward_risk` — reads `reward_risk_ratio`; **null → 100** (naked long, unlimited upside).
- `dir_payoff_multiple` — target-based: naked longs use payoff at `thesis_target_price` from
  `strike`/`cost`; spreads use `reward_risk_ratio`.

Each pure, `[0, 100]`, registered via `@directional_formula`, with a declared param schema.

### 2. Four adapter named values (`app/ota_adapters/directional/adapter.py` `_CATALOG`)

- `next_earnings_date` (RAW; populate from the existing ContextStore + Finnhub path found in
  Phase 0) and `earnings_unknown` (boolean; true when the earnings date is absent).
- `open_interest` (RAW), `volume` (RAW).
- `bid_ask_spread_pct` (DERIVED, from `bid`/`ask`).

Declare tier / type / null-semantics for each; ensure `produce_candidates` / `populate_computed`
publish them so engine startup catalog validation passes.

## Acceptance criteria

- Four formulas registered; each returns `[0, 100]` (decorator-enforced) and is pure.
- `dir_reward_risk` → 100 when `reward_risk_ratio` is null.
- `dir_expected_value` reads `ev_raw` else `total_ev`; negative EV scores low.
- `dir_payoff_multiple` target-based for naked longs, `reward_risk_ratio` for spreads.
- `_CATALOG` publishes `next_earnings_date` (+ `earnings_unknown`), `open_interest`, `volume`,
  `bid_ask_spread_pct` with correct tier/type/null-semantics; engine startup catalog validation passes.
- **No** skew named value or `skew_alignment` formula added.

## Out of scope

- Junction wiring, gate config, verdict bands, the seed block, orphan `config.py` deletion — all OTA-833.
- `dir_probability` / `dir_buffer` (unchanged); `dir_budget_fit` / `dir_defined_risk` (untouched).
- Skew (dropped).

## Verification steps

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python -c "import app.options_rules.directional"   # confirm the four formulas register without error
# run any directional adapter/rule-library tests
```
Confirm: the four formulas resolve in the registry; a directional candidate (spread and naked long)
produces the new named values; `dir_reward_risk` returns 100 for a naked long; engine startup
catalog validation passes. QA level: **Level 2** — rule-library + adapter change.

## Commit instruction

This ships as its own commit. Present the full diff and verification output, then ask:
"I have been instructed to commit. Do you approve? (yes / no)". On approval, Don runs the commit
manually — Claude Code does not run `git commit`.

## Coordination footer

Independent — no upstream gate, commits on its own. **Must be committed before OTA-833 runs**
(OTA-833 Phase 0 checks for these four formulas and four named values).

## Commit message template (Don runs this)

```
OTA-834 feat: add directional EV/reward-risk/max-loss-pct/payoff-multiple formulas + earnings, OI, volume, spread% adapter inputs
```
