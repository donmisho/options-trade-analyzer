---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-818 + OTA-758 — Engine bootstrap (read-side config hydration + persistence sink)

> Revised 2026-06-03 after Phase 0. This supersedes the pre-Phase-0 draft of this file.
> Three things are now settled and embedded below as non-negotiable context: (1) reuse
> `async_session`, no `.aio` / no parallel credential path; (2) Option 1 validator wiring
> (`input_catalog` omitted at boot); (3) OTA-819 (alembic dup-id fix) has been run, so the
> bronze tables should now exist — Phase 0 re-confirms.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: **OTA-819 (Duplicate Alembic revision id — bronze tables) must already be committed.** Reported run per Claude Code on 2026-06-03. The bronze tables must physically exist before the OTA-758 sink half is trusted; Phase 0 re-confirms.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/auth-process.md                 # credential/session — async_session reuse (Pattern 6)
cat claude_context/insight_engine.md                # §4.3 bronze contract; §6.1/6.2/6.5/6.6 loader + startup validation
cat claude_context/insight_engine-schema-ddl.md     # §2 engine_* config tables; §3 bronze tables
```

## Relevant Context — Do Not Deviate Without Escalation

**1. Credential plumbing — reuse, do not stand up a parallel path.**
Source: OTA-818 acceptance criteria (amended 2026-06-03); Phase 0 §6; `auth-process.md`.
`app/database.py` does NOT exist. The async engine and Azure credential plumbing live in `app/models/session.py` (`engine`, `async_session`). The live engine injects a **synchronous** `DefaultAzureCredential` via the pool's `do_connect` event listener (lazy, double-checked-lock, never module-level) because pyodbc token injection is synchronous. The new config source and sink make **zero direct Azure SDK calls** and inherit that token injection by going through `async_session`. The earlier "`azure.identity.aio` only / all Azure SDK calls use `.aio`" rule is **superseded** — a `.aio` credential path here would be the forbidden parallel path. No module-level credential.

**2. Validator wiring — Option 1 (omit `input_catalog`).**
Source: OTA-818 acceptance criteria (amended 2026-06-03); `insight_engine.md` §6.6.
Call `validate_and_raise(config, formula_registry=<screening get_registry()>, source=source)` with `input_catalog` **omitted** — exactly mirroring the passing integration wiring (`tests/integration/test_options_chain_adapter.py`, `tests/options_rules/test_scoring_formulas.py`). The input-catalog-completeness + null-semantics sub-checks have never been vetted against the live seed and are deferred to **OTA-820** — do NOT wire them here and do NOT make them a fatal boot gate. A genuine validation failure still raises a loud, structured `ConfigValidationError` and is fatal to hydration.

**3. Single runtime read path; engine package stays DB-free.**
Source: OTA-818 acceptance criteria; `insight_engine.md` §6.
`AzureSqlConfigSource` is the ONLY runtime reader of the `engine_*` tables. No route or endpoint opens its own SQL connection to them. No DB imports leak into `app/insight_engine/` — the source and sink live in the app layer and are injected, mirroring the existing sink pattern.

**4. Bronze sink contract.**
Source: OTA-758 acceptance criteria; `insight_engine.md` §4.3; `insight_engine-schema-ddl.md` §3.
Both logical streams (`CandidateSnapshot`, `EvaluationDecision`) land in the **single** physical table `bronze_evaluations`, discriminated by `record_type` ∈ {`SNAPSHOT`, `DECISION`}, plus the `bronze_payload_contract` registry. The promoted-column mapping is already aligned in `app/insight_engine/bronze_contract.py` — use it, do not re-derive.

**5. Fire-and-forget lives in the concrete sink.**
Source: Phase 0 §3; OTA-758 acceptance criteria.
`evaluate(...)` calls `sink.write_snapshots` / `write_decisions` directly and does NOT guard them. Therefore the fire-and-forget guarantee (a persistence failure logs and is swallowed; the evaluate response still returns) MUST be implemented inside the concrete sink. Synchronous Azure SDK calls block the event loop — schedule the writes so they never block the response.

**6. Sink is supplied per-call, not engine-held.**
Source: Phase 0 §3.
`evaluate(*, candidates, strategy_key, source_app_id, config, registry=None, adapter=None, sink=None)`. Startup constructs the sink and stashes it behind the runtime accessor; the per-call `sink=` is sourced from that accessor.

**7. Startup seam + accessor pattern.**
Source: Phase 0 §5.
Wire in the `app/main.py` lifespan AFTER `init_db()` succeeds, alongside the hard-gate registration (step 6c). Mirror the hard-gate accessor pattern (`app/analysis/hard_gates/__init__.py`: module-level list + `register_gate()`): a module-level resolved-config/sink holder + `init_engine_runtime()` / `get_engine_runtime()` + a FastAPI dependency.

**8. `app/main.py` is a project-critical shared file.**
Source: `build-execution.md`; `CLAUDE.md`.
Single terminal only; both halves of this prompt edit it. No parallel edits.

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)

Most ambiguity is resolved; this is a confirmation pass. **Read-only — change nothing.** Report a one-line GO, or STOP and report any contradiction with the embedded context above. Confirm:

1. `app/models/session.py` exports `async_session` + `engine`; credential injection is the sync `do_connect` listener; `app/database.py` does not exist.
2. `app/insight_engine/loader.py` — `load_config(source, *, app_ids=("SHARED","OTA"))`; `config_source.py` Protocol method names; `validation.py` — `validate_and_raise(config, *, input_catalog=None, formula_registry=None, source=None)`.
3. `app/insight_engine/sink.py` Protocol (`write_snapshots`/`write_decisions`); `models.py` record shapes; `bronze_contract.py` column mapping aligned to `bronze_evaluations`.
4. The screening formula-registry accessor used by the passing integration tests (the `get_registry()` they pass as `formula_registry=`).
5. `app/main.py` lifespan: the `await init_db()` point and the hard-gate registration block (the seam to insert after).
6. **Bronze tables present (post OTA-819):** run the read-only existence check —
   `SELECT name FROM sys.tables WHERE name IN ('bronze_evaluations', 'bronze_payload_contract');`
   Expect **2 rows**. If 0 or 1, **STOP** — OTA-819 did not fully take; do not proceed to the sink.
7. `engine_*` populated: 4 SCREENING strategies, per-strategy `verdict_band_set`, `enabled = 1` (hydration should succeed against live rows).

---

## OTA-818 — Scope

The read-side counterpart to the OTA-758 sink. Implement `AzureSqlConfigSource` and wire engine hydration at boot.

1. **`AzureSqlConfigSource`** (app layer, e.g. `app/ota_adapters/engine_runtime.py`) — implements the OTA-698 `ConfigSource` Protocol. Reads `engine_apps`, `engine_rules`, `engine_strategies`, `engine_strategy_rule_junction`, `engine_lookups` from Azure SQL **through `async_session`**, scoped by `owner_app_id` ∈ (`SHARED`, `OTA`), `enabled = 1` only, parsing the JSON columns (`parameters`, `parameter_schema`, `referenced_named_values`, `verdict_band_set`, `compatible_structures`, lookup `payload`) into the typed structures the loader expects. Bridge the sync Protocol over async DB I/O via an async pre-load into buffers, then serve the Protocol methods from the buffers. Tables only — no spreadsheet path.
2. **Startup hydration + accessor** — in the lifespan, after `init_db()`: build the source → `load_config(source, app_ids=("SHARED","OTA"))` → `validate_and_raise(config, formula_registry=<screening get_registry()>, source=source)` (`input_catalog` omitted, per Relevant Context §2) → capture the config-version hash → stash the resolved config behind the runtime accessor. Restart-only reload. Log the config-version and resolved strategy count (expect 4 SCREENING).

## OTA-818 — Acceptance criteria
- `AzureSqlConfigSource` reads all five `engine_*` tables scoped by `owner_app_id`, parses the JSON columns into typed structures, `enabled = 1` only, **through `async_session`** (no direct Azure SDK calls; no module-level credential).
- Engine hydrated once at startup via `load_config`; `validate_and_raise` runs with the screening formula registry + source, **`input_catalog` omitted**. A real validation failure raises loud/structured and is fatal to hydration.
- A single accessor exposes the resolved per-strategy `RuleSet`s; `grep` confirms no other `engine_*` SQL read in `app/`.
- Config-version hash captured at hydration for result-record stamping.

## OTA-818 — Out of scope
- `input_catalog` wiring / catalog-completeness / null-semantics checks → **OTA-820**.
- Any migration or DDL (OTA-708 done; OTA-819 done).
- Route rewiring (OTA-759/OTA-760), frontend (OTA-762/OTA-763), other adapters.

---

## OTA-758 — Scope

Implement the concrete `PersistenceSink` and inject it at startup.

- **`BronzeSqlSink`** — implements `write_snapshots(list[CandidateSnapshot])` / `write_decisions(list[EvaluationDecision])`, mapping both streams into `bronze_evaluations` (correct `record_type`) + `bronze_payload_contract`, using the `bronze_contract.py` column mapping. Writes go **through `async_session`** (Relevant Context §1). Fire-and-forget per §5: schedule the write, wrap in try/except → log-not-raise, never block the evaluate response.
- **Inject at startup** — construct the sink in the same lifespan block as OTA-818 hydration and stash it behind the runtime accessor; routes/`evaluate` source `sink=` from the accessor.

## OTA-758 — Acceptance criteria
- Concrete sink maps both streams into `bronze_evaluations` (`record_type` correct) + `bronze_payload_contract`.
- Sink injected at startup; **no DB imports leak into `app/insight_engine/`**.
- **Reuses `async_session`** — zero direct Azure SDK calls; no module-level credential. *(Supersedes the OTA-758 ticket's original "`.aio` variants" acceptance line — see Relevant Context §1; that ticket line is stale and being amended.)*
- A sink write failure is logged and swallowed — the evaluate response still returns.

## OTA-758 — Out of scope
- Bronze DDL (OTA-708 / OTA-819).
- Any engine-package change.
- Retry/queue/backfill logic for failed writes.

---

## Verification steps

Regression Level 2 (cross-cutting backend wiring): full backend test suite + manual boot + a click-through.

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

1. **Boot** the API and confirm the startup log shows the config-version hash + resolved strategy count = **4 SCREENING**; no `ConfigValidationError`.
2. **Single read path:** `grep -rn "engine_apps\|engine_rules\|engine_strategies\|engine_strategy_rule_junction\|engine_lookups" app/` → the only SQL reader is `AzureSqlConfigSource`.
3. **No parallel credential / no leak:** `grep -rn "azure.identity.aio\|DefaultAzureCredential" app/ota_adapters/` → none added by this work; `grep -rn "import.*models\|sqlalchemy\|async_session" app/insight_engine/` → no DB import leaked into the engine package.
4. **Persistence:** run one evaluation through the engine and confirm rows land in `bronze_evaluations` for **both** `record_type` values (`SNAPSHOT` + `DECISION`), and `bronze_payload_contract` is populated.
5. **Fire-and-forget:** force a sink write failure (e.g. temporarily point at a bad table name in a scratch test) and confirm the evaluate response still returns and the failure is logged — then revert the scratch change.
6. Run the backend test suite; confirm the integration tests that exercise screening still pass.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)
*(Single atomic commit covering both OTA-818 and OTA-758. Stage the changes and present the message; Don executes the commit.)*

## Coordination footer
Independent — no downstream dependency. *(The next wave — OTA-759/OTA-760 premise-checks and the OTA-762 re-cut — is prepared by Claude Web before it runs; nothing is queued for this terminal.)*

## Commit message template
```
OTA-818 OTA-758 feat: instantiate Insight Engine at boot — Azure SQL config hydration + bronze persistence sink

- AzureSqlConfigSource reads engine_* via async_session (single read path; no parallel credential)
- Startup hydration + runtime accessor; validate_and_raise with screening registry, input_catalog omitted (Option 1; catalog wiring deferred to OTA-820)
- BronzeSqlSink writes both streams to bronze_evaluations + bronze_payload_contract, fire-and-forget
- Regression Level 2
```
