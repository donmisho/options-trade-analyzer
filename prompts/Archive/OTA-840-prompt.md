# OTA-840 — Directional surface-scoped validation + OTA-830 stopgap removal (clean fatal restore)

## Terminal context
- **This terminal:** single terminal — engine validation/runtime core + seed (`scripts/seed_engine_config.py`) + `app/main.py`.
- **Concurrent terminals:** none. Do **not** parallelize — touches `app/main.py` and the engine validation/runtime core, both shared files.
- **Cross-terminal dependencies:**
  - Runs **after OTA-836** (engine live for screening; directional seeded `enabled=0`; `chart_state_matches_direction` / `extension_matches_trade_direction` built).
  - If **OTA-839** took path (b) — repointing `chart_state_valid_alignment` to `chart_state_matches_direction` — that formula must be committed and stable before this runs (shared formula).
  - **OTA-838** (null_semantics) must be in (directional liquidity gates rely on SKIP). Landed.

---

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md            # §6.6 startup validation + dual formula-registry check; §3.x surfaces
cat claude_context/engine-formula-registry.md   # the contract side of the dual-registry check
```

---

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-836 Phase 1 Gate A trace (the architecture this story changes)**
Validation is all-or-nothing across the whole config:
- `validate_and_raise` → `is_valid = len(errors) == 0`, raises on any error (`validation.py:60-62, 174-175`).
- `init_engine_runtime` calls `validate_and_raise` (`engine_runtime.py:531`) **before** `set_engine_runtime(runtime)` (`:543`) → any error leaves `_runtime = None`.
- OTA-830 try/except (`main.py:339-353`) catches it → app boots but `get_engine_runtime()` raises (`engine_runtime.py:454-464`) → `/evaluate/structured` 500s (`evaluation_routes.py:744`).
So today one directional error darkens the **whole** engine. The goal is to scope that so a directional-only fault degrades directional alone, screening stays live.

**Source: `insight_engine.md` §6.6 (startup validation / dual registry)**
The fatal-hydration design intent is LOUD/FATAL on bad config. The restore must preserve that for a whole-engine or screening-surface fault. The dual-registry check requires `engine-formula-registry.md` ↔ SHARED `formula_registry` balance — re-enabling directional re-introduces the `dir_*` `formula_ref`s into the seed, so the contract doc must gain them in the same pass or the check flags `FORMULA_MISSING_FROM_CONTRACT`.

**Source: OTA-820 (input-catalog validation — non-fatal, Option 1)**
The input-catalog-completeness and null-semantics checks are deliberately **non-fatal** (offline/CI or logged). The fatal restore here must **not** move them onto the boot critical path.

**Source: OTA-836 (the disable this reverses)**
OTA-836 seeded `directional_income` / `directional_growth` / `directional_longshot` with `enabled=0` and did not emit their rules/junction rows. Re-enabling = `enabled=1` **and** re-emit the full rule/junction set OTA-833 defined.

**Source: `CLAUDE.md` house style + `insight_engine.md` §2**
- No `if strategy_key ==` / surface branching. Per-surface behavior is driven by config/structure, not code switches.
- Tables are source of truth; changes flow through `scripts/seed_engine_config.py` + reseed.

---

## Scope — Phase 0 (read-only discovery, hard STOP)

No edits, no reseed, no commit. Produce a findings + recommendation report and STOP for GO.

1. **Trace the hydration path.** Confirm the current `validate_and_raise` / `init_engine_runtime` / `set_engine_runtime` / `get_engine_runtime` flow and the exact failure behavior described above.
2. **Mechanism options for surface-scoping.** Lay out the candidate designs and their tradeoffs, e.g.:
   - **(a) Per-surface validate + hydrate:** validate each surface's config independently; set a live runtime for each surface that validates; a failed surface is absent/marked-failed while others serve.
   - **(b) Single runtime, per-surface validity:** one runtime that records which surfaces validated; `get_engine_runtime()` / the route layer consult per-surface validity and degrade only the failed surface.
   - Note which is the smaller, lower-risk change and how each interacts with `set_engine_runtime` ordering (so a partial failure never leaves `_runtime = None` for healthy surfaces).
3. **Failure contract.** State the intended post-removal behavior precisely: whole-engine / screening-surface fault → fatal crash-loop (LOUD); directional-only fault → directional degrades, screening live. Confirm where that decision is enforced.
4. **Directional resolution check.** Confirm every directional `formula_ref` (`dir_earnings`, `dir_negative_ev`, `dir_probability`, `dir_buffer`, `dir_expected_value`, `dir_max_loss_pct`, `dir_reward_risk`, `dir_payoff_multiple`, plus `chart_state_matches_direction` / `extension_matches_trade_direction` if bound) resolves once re-enabled.
5. **Registry delta.** State the net `engine-formula-registry.md` change from the `dir_*` refs re-entering the SHARED registry.
6. **OTA-830 removal point.** Confirm `main.py:339-353` is the removal site and the ordering after the scoping change.
7. **OTA-820 guard.** Confirm the input-catalog/null-semantics checks stay non-fatal after the restore.

**Recommend a mechanism (a / b / other) with a confidence read. HARD STOP — wait for Don's GO before any implementation.**

---

## Scope — Implementation (only after Don's GO on the mechanism)

Per the chosen mechanism:
- Implement surface-scoped validation/hydration so a directional-only fault does not null the screening runtime.
- Re-enable the three directional strategies (`enabled=1`) and re-emit their full rule/junction set (reverse the OTA-836 disable) in `scripts/seed_engine_config.py`.
- Update `engine-formula-registry.md` for the directional `formula_ref`s re-entering the SHARED registry.
- Reseed.
- Remove the OTA-830 try/except (`main.py:339-353`) — hydration is fatal again per the §6.6 design.
- Keep the OTA-820 input-catalog/null-semantics checks non-fatal.

---

## Acceptance criteria
- Validation/hydration is surface-scoped: a directional-surface config error does not prevent screening from hydrating, and vice versa.
- The three directional strategies are enabled with their full gate + scoring junction set; every directional `formula_ref` resolves.
- The OTA-830 try/except is removed; hydration is fatal/loud for a whole-engine or screening-surface fault.
- `/evaluate/structured` serves both surfaces; `get_engine_runtime()` returns a live runtime.
- `engine-formula-registry.md` ↔ SHARED `formula_registry` balanced; dual-registry check clean.
- OTA-820 input-catalog/null-semantics checks remain non-fatal.
- No `if strategy_key ==` branching introduced.

---

## Out of scope
- Routing directional through the engine at the app layer (OTA-765).
- Retiring `directional_engine.py` (OTA-756).
- The `chart_state` value-domain fix (OTA-839).
- Rule tuning / verdict-band recalibration.

---

## Verification steps

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

1. Reseed; app boots; `/evaluate/structured` serves both screening and directional candidates.
2. **Positive:** a directional candidate is evaluated by the engine (not the legacy path); screening still evaluates.
3. **Surface-isolation:** inject a deliberate directional-only config fault → directional degrades/absent, **screening still hydrates and serves**. Remove the fault; confirm clean.
4. **Fatal restore:** inject a screening/whole-engine fault → startup crash-loops loudly (no silent boot). Remove it.
5. `engine-formula-registry.md` ↔ seed balanced (dual-registry check clean).

---

## Commit instruction
I have been instructed to commit on Don's approval. After a clean reseed + the verification steps pass, present the diff and ask: **"Commit? (yes / no)"**. Do not commit before Don approves.

---

## Coordination footer
Standalone commit. Downstream consumer is **OTA-765** (directional app-wiring) — a separate prompt; do **not** begin it in this session.

---

## Commit message template (if committing)
`OTA-840 feat: surface-scoped engine validation + re-enable directional; remove OTA-830 stopgap (fatal hydration restored)`
