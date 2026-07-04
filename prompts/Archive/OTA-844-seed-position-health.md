---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Bash(cat*)
  - Bash(python*)
  - Bash(pytest*)
  - Bash(grep*)
---

# OTA-844 — Seed POSITION_HEALTH surface into the live engine

You are working on branch `OTA-836-build-to-testable`. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## Objective

The position-health adapter (OTA-734) and rule library (OTA-742) shipped as code and pass parity in isolation, but the POSITION_HEALTH surface was never seeded into the live `engine_*` tables, never added to the combined registry, and never covered by surface validation. As a result `engine.evaluate(strategy_key="position_health_full")` fails closed. This story seeds the surface so OTA-764 (Position Monitor Agent wiring) can resolve it. Same pattern the directional surface needed (OTA-833 seed → OTA-836 reseed) before OTA-765 could wire its route.

**Immediate intent (product owner):** the point of this build is to get the position-health strategies, rules, and junctions seeded so they are visible and editable through the Strategy Administration UI — so the configuration can be inspected and tuned. Grade ACCURACY is not a goal at this stage; errors are expected and acceptable. The gate is that the surface seeds, the runtime loads it, and the config-read API exposes it to the UI.

## Mechanism A — Required Reading (run these first)

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-migration-plan.md
cat scripts/seed_engine_config.py
cat app/ota_adapters/position_health/config.py
cat app/insight_engine/engine_runtime.py
cat tests/insight_engine/test_full_seed_boot.py
cat tests/options_rules/test_position_health_parity.py
```

## Mechanism B — Relevant Context (verify, do not trust blindly)

- `scripts/seed_engine_config.py` currently seeds screening + directional only. POSITION_HEALTH appears once (~line 461) as a surface-label lookup, not as seeded rows.
- `build_combined_registry()` (`engine_runtime.py` ~line 541) composes screening ∪ directional. The position-health rule library registers 4 formulas: `exit_level_safety_score`, `pnl_band_score` (scoring) and `stop_breached_floor`, `warning_breached_cap` (post-scoring adjustments). Target registry 36 → 40.
- `app/ota_adapters/position_health/config.py::get_all_config_rows()` is the seed source: both `position_health_full` and `position_health_basic` strategies (enabled, A–F bands) plus their rules, junctions, and lookups.
- `tests/insight_engine/test_full_seed_boot.py` asserts only `{SCREENING, DIRECTIONAL}` load and registry == 36.
- `tests/options_rules/test_position_health_parity.py` (OTA-751) is the parity gate — 12-fixture A→F spectrum, 34 passing, 2 documented Option A divergences. Informational for this story (see Phase 3).
- INVARIANT: the engine resolves all position-health content from the runtime tables. No in-memory config built inside the agent or engine; the config module is read only by this seed importer. No `if strategy_key ==` branching anywhere.

## Phase 0 — Read-only discovery (HARD GO/NO-GO STOP)

Make NO edits. Answer, then STOP and report A–E.

1. Confirm `get_all_config_rows()` returns strategies (full + basic), rules, junctions, and lookups in the exact shape `seed_engine_config.py` consumes for directional; confirm both strategies are enabled.
2. Identify the directional seed path in `seed_engine_config.py` to mirror. Determine whether the seed truncates-and-reseeds per surface or upserts — adding POSITION_HEALTH must NOT disturb existing screening/directional rows.
3. Confirm `build_combined_registry()` location/signature and the exact insertion point for the position-health registry.
4. Check for formula-NAME collisions between the 4 position-health formulas and the existing 36 in the combined registry. (Eval-order is per-strategy, so cross-surface order collisions are not expected — confirm.)
5. Confirm `validate_by_surface` structure and how surfaces are enumerated; confirm the current `test_full_seed_boot.py` assertions (surface set + count == 36).
6. Confirm the config-read endpoint the Strategy Administration UI consumes (the OTA-762 config-read family, normalized by OTA-841) will surface the seeded position_health strategies once they exist in `engine_*` — i.e., it enumerates all seeded surfaces and is not hardcoded to screening/directional. If it filters by surface, report what change is needed for POSITION_HEALTH to appear (do not build it yet — report it).

GO only if: config rows present and well-shaped · seed pattern to mirror is clear · no formula-name collision. NO-GO and STOP if any of these fail.

## Phase 1 — Seed extension (after GO)

- Extend `seed_engine_config.py` to import `get_all_config_rows()` and seed `position_health_full` / `position_health_basic` strategies + rules + junctions + lookups, mirroring the directional seed path. Idempotent; leave screening and directional rows untouched.
- Run the seed and verify position-health rows land and screening/directional counts are unchanged:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts/seed_engine_config.py
```

## Phase 2 — Registry + surface validation

- Add the position-health registry to `build_combined_registry()`.
- Extend `validate_by_surface` to cover POSITION_HEALTH.
- Confirm the runtime boots with all three surfaces and the registry is exactly 40.

## Phase 3 — Verify it loads and surfaces (the real gate)

- Update `tests/insight_engine/test_full_seed_boot.py`: assert `{SCREENING, DIRECTIONAL, POSITION_HEALTH}` load and registry == 40. THIS is the gate — it proves the surface is live and the config API / UI can read it.
- Run the position-health parity test for INFORMATION ONLY. Grade mismatches are expected and acceptable at this stage — a parity failure does NOT block the commit. Report the results so Don can see current grading behavior; do not chase parity.
- Run the broader engine suite only to confirm screening/directional still load and don't crash — structural regression check, not a grading check.

```powershell
pytest tests/insight_engine/test_full_seed_boot.py -v
pytest tests/options_rules/test_position_health_parity.py -v   # informational
pytest tests/insight_engine tests/options_rules -q             # structural only
```

## Manual commit gate

STOP. Summarize the staged diff (files touched, line counts) and the test results. Commit is fine even if parity is red, as long as the three surfaces load and registry == 40. Do NOT commit yourself — Don commits with the `OTA-844 feat:` prefix.

## Coordination

- Branch `OTA-836-build-to-testable` only. Part of the current pre-prod bundle.
- Single terminal — this touches `seed_engine_config.py`; do not parallelize with any other seed-touching work.
- **Blocks OTA-764.** Do not touch `position_monitor.py` or `position_routes.py`.
- Do not deploy. Don holds the deploy gate.
