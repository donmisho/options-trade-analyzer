---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-762 — Engine config read API (`GET /config/strategies`)

> Re-cut 2026-06-03 after OTA-762 Phase 0 (NO-GO). The original prompt predated the OTA-818
> keystone, assumed a "clean provider swap," and referenced the deleted `strategy_scorer.py`.
> This version is the **backend read endpoint only** — the frontend consumption migration is
> split out to OTA-821. Targets the as-built `get_engine_runtime().config` accessor.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: OTA-818 keystone is committed (the `get_engine_runtime()` accessor exists). No shared-file contention — this is a new backend module + one router registration in `app/main.py` (committed clean after the keystone).

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/auth-process.md                 # require_read dependency pattern
cat claude_context/insight_engine.md                # §6 config shapes (Strategy, RuleSet, bindings)
cat claude_context/insight_engine-schema-ddl.md     # §2 verdict_band_set shape
```

## Relevant Context — Do Not Deviate Without Escalation

**1. Read from the as-built accessor — no second SQL path.**
Source: OTA-818 (keystone, committed); OTA-762 Phase 0 §1.
The hydrated config is `get_engine_runtime().config` in `app/ota_adapters/engine_runtime.py` (`EngineRuntime.config` is the `EngineConfig`). Serialize from it. Do NOT open a new SQL connection to `engine_*` — `AzureSqlConfigSource` must remain the only runtime reader (grep-enforced).

**2. Two-source serialization within the accessor.**
Source: OTA-762 Phase 0 §1.
- Strategy-level fields come from `config.strategies[key]` (a `Strategy`): `strategy_key`, `display_name`, `consumer_surface`, `compatible_structures`, `verdict_band_set`, `dte_min`, `dte_max`.
- **Per-criterion weights are NOT on `Strategy`.** They live on the scoring-phase junction bindings: walk `config.rule_sets[key].bindings[]` and read `binding.junction.weight` for the scoring-phase bindings. The serializer reads from both places.

**3. `verdict_band_set` shape.**
Source: OTA-762 Phase 0 §4; `scripts/seed_engine_config.py`; `insight_engine-schema-ddl.md` §2.
Each of the 4 SCREENING strategies carries a list: `[{"verdict":"EXECUTE","min_score":70,"max_score":100}, {"verdict":"WAIT","min_score":50,"max_score":69.99}, {"verdict":"PASS","min_score":0,"max_score":49.99}]`. Expose it as-is. The 70/50 surface as `min_score` of EXECUTE/WAIT so OTA-660 can source score-color thresholds from this endpoint.

**4. Router placement — dedicated module, shared prefix.**
Source: OTA-762 Phase 0 §5 (Decision B).
`/api/v1/config` already exists: `app/api/config_routes.py` mounts `APIRouter(prefix="/config")` with `GET ""`/`PUT ""` returning `UserConfigResponse` (per-user settings), registered in `app/main.py` (~line 496). Do NOT bolt onto it. Create a **new** `app/api/engine_config_routes.py` with its own `APIRouter(prefix="/config")` (FastAPI allows two routers sharing a prefix) and register it in `app/main.py`. OTA-782 (F13) will hang its write endpoints on this new module.

**5. Auth.**
Source: OTA-762 Phase 0 §5; `auth-process.md`.
`/api/v1` routes use `Depends(require_read)` / `require_write` from `app/auth/dependencies.py`. The read endpoint uses `require_read`.

**6. Scope correction — bands are already backend-only.**
Source: OTA-762 Phase 0 §2.
There are no hardcoded bands to remove anywhere in this story — the endpoint merely *exposes* `verdict_band_set`. (Removing the frontend dual-source is OTA-821, not here.)

## Phase 0 — Read-only discovery (STOP for GO/NO-GO)

Read-only. Confirm and report a one-line GO, or STOP on any contradiction:
1. `get_engine_runtime().config` exposes `config.strategies[key]` (`Strategy` with the fields in §2) and `config.rule_sets[key].bindings[].junction.weight` for scoring-phase weights.
2. `app/api/config_routes.py` mounts `/config` (user settings) and its registration line in `app/main.py`.
3. `require_read` import path in `app/auth/dependencies.py`.
4. The four SCREENING strategies are present in the hydrated config (endpoint will return them).

## Scope
- New `app/api/engine_config_routes.py`: `APIRouter(prefix="/config")`, `GET /strategies` → `Depends(require_read)`.
- Serializer mapping per Relevant Context §2/§3: strategy-level fields from `config.strategies`, weights from scoring-phase `rule_sets[...].bindings[].junction.weight`, `verdict_band_set` passed through.
- Register the new router in `app/main.py`.

## Acceptance criteria
- `GET /api/v1/config/strategies` returns the four SCREENING strategies serialized from `get_engine_runtime().config`; `grep` confirms no new `engine_*` SQL read (`AzureSqlConfigSource` remains the only reader).
- Per-criterion weights are sourced from scoring-phase junction bindings, not any `Strategy` attribute.
- `verdict_band_set` present in `[{verdict, min_score, max_score}]` shape.
- Endpoint guarded by `require_read`; lives in the new `engine_config_routes.py` (not in user-config `config_routes.py`).

## Out of scope
- Any frontend change (`web/src/**`) → OTA-821.
- Write/PUT endpoints → OTA-782 (F13).
- Changes to the engine package or the hydration accessor (OTA-818, done).

## Verification steps
Regression Level 1 (additive read endpoint).

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```
1. Boot the API; `GET /api/v1/config/strategies` (authenticated) returns 4 strategies with strategy fields + per-criterion weights + `verdict_band_set`.
2. Unauthenticated request → 401 (require_read enforced).
3. `grep -rn "engine_apps\|engine_rules\|engine_strategies\|engine_strategy_rule_junction\|engine_lookups" app/api/` → no SQL read in the route module (it reads the accessor only).
4. Spot-check one strategy's weights against its scoring-phase junction rows.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)
*(Self-contained additive endpoint. Stage and present the message; Don executes.)*

## Coordination footer
OK to continue to OTA-782.md (F13 Strategy Admin UI — unblocked once this read endpoint is in the tree). OTA-821 (frontend migration) is also unblocked but runs separately and not concurrent with OTA-763 (shared `client.js`).

## Commit message template
```
OTA-762 feat: engine config read API — GET /config/strategies serialized from hydrated config

- New engine_config_routes.py (/config prefix), require_read
- Serializes strategy fields from config.strategies + per-criterion weights from scoring-phase junction bindings
- Exposes verdict_band_set for OTA-660; no new engine_* SQL read
- Regression Level 1
```
