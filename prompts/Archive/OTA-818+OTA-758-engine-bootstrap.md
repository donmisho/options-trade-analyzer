# OTA-818 + OTA-758 — Engine app-side bootstrap: Azure-SQL config hydration + bronze sink injection

Ships as **one atomic commit** covering both tickets. The engine becomes live at startup: config hydrated in (OTA-818), decisions written out (OTA-758).

## Terminal context
- This terminal: solo
- Concurrent terminals: none — **run alone**
- Cross-terminal dependencies: none. Edits `app/main.py` (project-critical shared file per `CLAUDE.md`) and `app/database.py` plumbing — must not run concurrent with any other terminal.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-schema-ddl.md
```

If `insight_engine*.md` are not under `claude_context/`, locate them (`find . -name 'insight_engine*.md'`) and read them there.

## Relevant Context — Do Not Deviate Without Escalation

Source: `insight_engine.md` §2 (principle 5, Domain decoupling).
Rule: Strategies are config, never code branches. No `if strategy_id == X` anywhere. The source reads rows; the engine resolves strategies from data.

Source: `architecture-plan.md` (engine package boundary) + `insight_engine.md` §2.
Rule: The engine package `app/insight_engine/` stays DB-free. No DB import may leak into it. The concrete `ConfigSource` and the concrete sink live in the **app layer** and are injected — mirroring how the OTA-698 loader and the OTA-705 sink Protocol were designed.

Source: project async-credential rule (see OTA-758 description / `architecture-plan.md` Azure patterns).
Rule: `azure.identity.aio` only. `DefaultAzureCredential` lazy-init via double-checked locking — never at module level. Synchronous Azure SDK calls block the FastAPI event loop and cause 90s+ prod hangs. Reuse `app/database.py`'s existing async engine/credential plumbing rather than standing up a parallel one.

Source: audit §5a #6 (dual-source mirror) + OTA-762 constraint.
Rule: This concrete source is the **single** runtime read path for `engine_*`. No route, service, or endpoint opens its own connection to those tables.

Source: `insight_engine.md` §6.5 (restart-only reload).
Rule: Hydrate once at startup. Nothing re-reads the tables mid-run.

Source: `insight_engine.md` §6.6 + OTA-699 (startup validation).
Rule: After `load_config`, run the OTA-699 validator (`validate_and_raise` or equivalent — confirm in Phase 0). The engine refuses to evaluate on invalid config (weights sum to 1.0, monotonic bands, formula-registry coverage, parameter type/bound conformance, null-semantic compatibility, input-catalog completeness). A validation failure is loud and fatal to hydration — it must NOT be swallowed.

Source: `insight_engine-schema-ddl.md` §2 (config tables).
Facts: five tables — `engine_apps`, `engine_rules`, `engine_strategies`, `engine_strategy_rule_junction`, `engine_lookups`. Natural keys `(owner_app_id, <key>)`; scope `OTA` vs `SHARED`; only `enabled = 1` rows participate. JSON columns to parse: `parameters`, `parameter_schema`, `referenced_named_values`, `verdict_band_set`, `compatible_structures`, lookup `payload`. `engine_rules.rule_id` is an INT IDENTITY surrogate; bronze references the string `rule_key`, never the surrogate.

Source: `insight_engine.md` §4.3 (sink + bronze) + OTA-758 description.
Facts: two logical streams (`CandidateSnapshot`, `EvaluationDecision`) land in the **single** physical `bronze_evaluations` table discriminated by `record_type`, plus the `bronze_payload_contract` registry. Fire-and-forget: a sink write failure logs but never blocks the evaluate response.

Source: recon 2026-06-03 (DB state).
Fact: the `engine_*` tables are already seeded with current OTA config — the four SCREENING strategies carry per-strategy `verdict_band_set` (EXECUTE ≥70 / WAIT 50–69.99 / PASS <50), refreshed 2026-05-29. **Do NOT reseed.** Hydrate against the live rows. If the OTA-699 validator fails on rules/junctions/lookups/formula-registry, **STOP and escalate** — that is OTA-815 territory (the seed importer's `verdict_bands` NameError blocks a clean reseed). Do not patch config in code to make validation pass.

## Phase 0 — Discovery (READ-ONLY; STOP for go/no-go before any edit)

Report findings and WAIT. Do not edit in this phase.

1. `app/insight_engine/config_source.py` — the `ConfigSource` Protocol method(s) `AzureSqlConfigSource` must implement, and the `InMemoryConfigSource` shape to mirror (what `load_config` calls, and the exact return types — raw rows vs typed objects).
2. `app/insight_engine/loader.py` — `load_config` signature: what it expects from a `ConfigSource` and what it returns (resolved `EngineConfig` / `RuleSet`s).
3. Engine entry (`app/insight_engine/__init__.py` or equivalent) — `engine.evaluate(...)` signature; **how the sink is supplied** (per-call `sink=` vs engine-held); and the OTA-699 validator entry point (name + signature + where it's called).
4. `app/insight_engine/sink.py` — `PersistenceSink` Protocol + `InMemorySink`; the `write_snapshots` / `write_decisions` signatures the concrete sink must implement.
5. `app/main.py` — the lifespan; the exact slot after `init_db()` succeeds; and how the legacy hard-gate registry is stashed (the accessor pattern to mirror for the resolved-config accessor).
6. `app/database.py` — the async engine/session + `azure.identity.aio` credential pattern to reuse (so neither the source nor the sink stands up a parallel credential path).
7. The bronze migration (`bronze_evaluations` + `bronze_payload_contract`) — column layout + `record_type` discriminator values, for the sink's column mapping.
8. The `engine_*` model/row field names the source must populate, confirming the JSON column set above against as-built.

**GO/NO-GO:** if the engine API (`load_config` / `evaluate` / validator / sink Protocol) differs from the embedded context, or `app/main.py` has no clean post-`init_db()` slot, or `app/database.py`'s credential pattern can't be reused, **STOP and report** rather than reconciling silently.

---

## OTA-818 — Scope
Build `AzureSqlConfigSource` (app layer) implementing the OTA-698 `ConfigSource` Protocol: reads the five `engine_*` tables scoped `owner_app_id` ∈ {OTA, SHARED}, `enabled = 1` only, parsing JSON columns into the typed structures `load_config` expects. Reuse `app/database.py` plumbing + async credentials.
Then, in the `app/main.py` lifespan immediately after `init_db()` succeeds: build the source → `load_config(source)` once → run the OTA-699 validator → capture the config-version hash → stash the resolved config behind a single module-level accessor / FastAPI dependency.

## OTA-818 — Acceptance criteria
- Source reads all five tables scoped by `owner_app_id`, `enabled = 1`, JSON columns parsed to typed structures.
- Engine hydrated once at startup; validator runs; a failure is loud and fatal (not swallowed).
- One accessor exposes the resolved per-strategy `RuleSet`s; `grep` confirms no other `engine_*` SQL read in the app.
- Config-version hash captured for later result-record stamping.
- All Azure SDK calls use `.aio`; no module-level credential.

## OTA-818 — Out of scope
No `GET /api/v1/config/strategies` endpoint (that is OTA-762). No route rewiring (OTA-759/760). No frontend. No reseed. No schema changes. No reload-at-runtime.

---

## OTA-758 — Scope
Implement the concrete `PersistenceSink` (the OTA-705 Protocol) writing both streams into the single `bronze_evaluations` table (correct `record_type`) + `bronze_payload_contract`. Construct it in the same startup block and inject it so `engine.evaluate(...)` uses it. Async writes via `azure.identity.aio`; fire-and-forget.

## OTA-758 — Acceptance criteria
- Concrete sink implements `write_snapshots` / `write_decisions`, mapping `CandidateSnapshot` + `EvaluationDecision` into `bronze_evaluations` (`record_type`) + `bronze_payload_contract`.
- Sink injected at startup; no DB import leaks into `app/insight_engine/`.
- All Azure SDK calls use `.aio`; no module-level credential.
- A sink write failure is logged and swallowed — the evaluate response still returns.

## OTA-758 — Out of scope
No route calls `engine.evaluate` yet (OTA-759/760). This story only constructs + injects the sink so the engine is ready.

---

## Verification steps
- Dev boot succeeds; the lifespan hydrates config and instantiates the engine with the injected sink. Hydration logs the config-version hash and the count of resolved strategies (expect the 4 SCREENING strategies).
- Force a config-invalid case (e.g., point at a non-existent owner scope in a throwaway test) → validator raises loudly; engine refuses to evaluate. Revert.
- `grep -rn` proves: (a) no second `engine_*` read path outside the source; (b) no module-level `DefaultAzureCredential`; (c) no DB import inside `app/insight_engine/`.
- Sink: a simulated write failure is logged, not raised, and does not break the call path.
- Engine package import-cleanliness check (the OTA-695 forbidden-import CI test, if present) still passes.
- The combined prompt fails if **either** ticket's acceptance criteria fail.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no) — single atomic commit covers both tickets.

## Coordination footer
Independent — no downstream dependency queued for this terminal. (This unblocks OTA-759 / OTA-760 / OTA-762, but those are re-cut/authored by Claude Web before any next Claude Code run.)

## Commit message template
OTA-818 OTA-758 feat: wire Azure-SQL engine config hydration + bronze sink at startup
