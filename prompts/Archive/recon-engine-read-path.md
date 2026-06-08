# [RECON] Insight Engine read-path & engine_* seed status — pre-wiring discovery

**Read-only discovery. No edits, no migrations, no commits, no DB writes.**
Purpose: decide whether the missing read-side wiring is **one** new story (concrete Azure-SQL `ConfigSource` + startup hydration) or **two** (that, plus a screening-strategy/band seed story ahead of it). Output returns to Claude Web.

## Terminal context
- This terminal: single, read-only
- Concurrent terminals: none
- Cross-terminal dependencies: none

## Required reading
Before answering anything:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-schema-ddl.md
```

If `insight_engine.md` / `insight_engine-schema-ddl.md` are not at `claude_context/`, locate them (`find . -name 'insight_engine*.md'`) and read them there. The migration plan (`insight_engine-migration-plan.md`) may not be in the repo yet — do not block on it; the relevant facts are embedded below.

## Relevant Context — hypotheses under test (verify, don't assume)

Source: prior Phase 0 report (OTA-762) + `insight_engine-migration-plan.md` S1.3 / S5.1.
- **H1** — OTA-698 shipped only the *generic* loader: `load_config` + the `ConfigSource` Protocol + `InMemoryConfigSource`. The concrete Azure-SQL `ConfigSource` and startup hydration were deferred to "Wave 4 app-side wiring" and may not exist anywhere.
- **H2** — The engine is currently fed only by `InMemoryConfigSource` (tests) and per-adapter build-time row-dict modules at `app/ota_adapters/{position_health,directional}/config.py`. The **options_chain (screening)** adapter has only `adapter.py` — no strategy/band config rows.
- **H3** — Runtime scoring does not use the engine yet; it runs through the in-code `STRATEGIES` dict in `app/analysis/strategy_definitions.py` plus `vertical_engine.py` / `long_call_engine.py`.

Source: `insight_engine-schema-ddl.md` §2; `insight_engine.md` §6.1, §6.2, §6.6.
- The runtime read path is expected to read `engine_apps`, `engine_rules`, `engine_strategies`, `engine_strategy_rule_junction`, `engine_lookups` from Azure SQL, scoped by `owner_app_id` (OTA vs SHARED), `enabled = 1` only, resolving each strategy into a `RuleSet`.
- Per-strategy verdict bands live in `engine_strategies.verdict_band_set`. The screening EXECUTE/WAIT/PASS **70/50** bands are the OTA-660 (score colors) and OTA-761 (band-literal removal) dependency.

## Scope — answer Q1–Q5 with evidence (file paths + line numbers + short quoted snippets)

**Q1 — Read-side wiring.** Is there ANY concrete (non-`InMemory`) `ConfigSource` that reads the `engine_*` tables? Any startup hydration in `app/main.py` that calls `load_config`? Any accessor/singleton exposing resolved `RuleSet`s? Quote the OTA-698 loader docstring that defers the concrete source to "Wave 4." (Confirms/refutes "nothing to extend.")

**Q2 — Schema & migration.** Do the five `engine_*` tables exist as DDL/migrations in the repo? Which migration created them? Are migrations applied (read-only `alembic heads` / `alembic history`, or inspect the migration chain)? Do NOT run migrations.

**Q3 — Seed mechanism & coverage (the decisive question).** How are `engine_*` rows populated — a seed script, the build-time row-dict modules, or the one-time spreadsheet seed? Trace the seed source. Then: **does the seed populate the SCREENING (options_chain) strategies** — SP / WG / TR / LT on the screening surface — with their rules, junction rows, and `verdict_band_set`? Or only `position_health` / `directional`? List, per strategy: seeded vs absent.

**Q4 — Screening verdict bands.** Do the 70/50 EXECUTE/WAIT/PASS screening bands exist as `engine_strategies.verdict_band_set` config (or equivalent) for the screening strategies? Or are they still in-code literals / absent from config?

**Q5 — Startup sequence map.** What does `app/main.py` currently do at startup regarding the engine and the OTA-758 sink? Is the engine instantiated at boot at all? Where would config hydration + sink injection slot in so the two land as one coherent startup block? Capture the current shape precisely (the keystone prompt will target it).

## Out of scope
No edits. No migrations. No commits. No DB writes. Do not run anything that mutates state.

## DB query policy
Answer from **code** wherever possible (migrations, seed scripts, row-dict modules, `main.py`). Only if the code is genuinely ambiguous about whether screening rows are seeded in the live DB: **STOP and report** that a read-only `SELECT` against the dev `engine_*` tables is needed — do not run it without Don's explicit go. The dev SQL is serverless/auto-pausing and a query wakes it.

## Report format (return to Claude Web)
- Q1–Q5: ANSWER + evidence each.
- **Decision call:** ONE story (ConfigSource + hydration) or TWO (also a screening-seed story sequenced first)? State which, with the Q3/Q4 evidence that drives it.
- Any finding that contradicts H1–H3 or the schema expectations above.

## Commit instruction
I have been instructed NOT to commit. No edits will be made — this is discovery only.

## Coordination footer
Independent — no downstream dependency. Output returns to Claude Web to decide one-vs-two and author the keystone prompt.
