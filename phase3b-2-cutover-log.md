# Phase 3b.2 — api_symbol Normalization Helpers + Inbound Wiring Cutover Log

**Date:** 2026-05-19
**Ticket:** OTA-668
**Commit:** `OTA-668 feat: phase 3b.2 - api_symbol normalization helpers and wiring`

---

## Scope Shipped

**Phases 1–4 complete. Phase 5 deferred.**

### Action 1 — Helper module created

`app/services/symbol_normalization.py` — 3 functions per audit §3.4 signatures:

- `canonicalize(symbol: str) -> str` — strips leading `$`, uppercases, strips whitespace. Idempotent.
- `async to_api_symbol(db, symbol, provider) -> str` — canonical → provider-specific form. Branches on provider: Schwab queries `symbol_reference.api_symbol`; all others return canonical unchanged.
- `async from_api_symbol(db, api_symbol) -> str` — reverse lookup on `api_symbol` column; falls back to `canonicalize()` if no row matches.

**1 new file, ~50 LOC.**

### Action 2 — Inbound `canonicalize()` wiring (all 7 audit §3.2 sites)

| # | File | Lines Changed | Target Table | Before | After |
|---|------|---------------|--------------|--------|-------|
| 1 | `app/api/position_routes.py` | 666, 752 | `positions` | `req.symbol.upper()` | `canonicalize(req.symbol)` |
| 2 | `app/api/analysis_routes.py` | 508, 684, 855 | `option_chain_snapshots`, `trade_candidates` | `req.symbol.upper()` | `canonicalize(req.symbol)` |
| 3 | `app/api/analysis_routes.py` | 824, 963 | `Thesis`, `ProbabilityMatrixResponse` | `req.symbol.upper()` | `canonicalize(req.symbol)` |
| 4 | `app/analysis/chain_collection.py` | 56 | `options_chain_snapshots` | `symbol=symbol` | `symbol=canonicalize(symbol)` |
| 5 | `app/agents/context_store.py` | 75 | `symbol_context` | `signal.symbol.upper()` | `canonicalize(signal.symbol)` |
| 6 | `app/api/trade_evaluation_routes.py` | 260, 497, 516, 616 | `agent_run_log`, `trade_recommendations` | `request.symbol` (BREAKING — no normalization) | `canonicalize(request.symbol)` |
| 7 | `app/api/evaluation_routes.py` | 679, 1027 | `agent_run_log` | `request.symbol` (STALE) | `canonicalize(request.symbol)` |

**6 existing files modified, ~14 LOC changed (import + call-site replacements).**

### Action 3 — Schwab outbound `to_api_symbol()` wiring: DEFERRED

**Phase 5 was not applied.** The three Schwab outbound call sites (`schwab.py:91`, `schwab.py:182`, `schwab_context_source.py:60`) do not have an `AsyncSession` in scope. `to_api_symbol()` requires an `AsyncSession` for the `symbol_reference` lookup. This is a refactor problem (provider method signatures need a `db` parameter or the translation must move to the caller), not a wiring problem.

**Escalated to Don.** The session-availability gap requires an architectural decision on where the translation belongs:
1. Add `db` to `MarketDataProvider` interface (changes all providers)
2. Translate at caller sites before calling provider methods (callers have sessions)
3. Inject session into provider at construction time

This will be addressed in a follow-up Subtask under OTA-666.

---

## Test Results

### Import check
```
python -c "from app.services import symbol_normalization; print('imports OK')"  → PASS
python -c "from app.api import position_routes, analysis_routes, trade_evaluation_routes, evaluation_routes; from app.analysis import chain_collection; from app.agents import context_store; print('imports OK')"  → PASS
```

### pytest
```
pytest --ignore=scratch --ignore=dev-agents -q
503 passed, 2 skipped, 0 failures in 34.77s
```

The 2 skipped tests are pre-existing (same as 3b.1 baseline of 484 passed + 2 skipped). 19 new `symbol_normalization` tests are among the 503 passing.

### New test breakdown (19 tests)
- `TestCanonicalize`: 8 tests (dollar strip, uppercase, whitespace, idempotent, edge cases)
- `TestToApiSymbol`: 5 tests (Schwab with mapping, Schwab without mapping, non-Schwab provider, unknown symbol, canonicalizes input)
- `TestFromApiSymbol`: 3 tests (reverse lookup, no matching row, canonicalizes fallback)
- `TestRoundTrip`: 3 tests (with mapping, without mapping, all fixtures)

### Smoke-test queries (Section 5)

Not re-run for 3b.2. The inbound changes are all at the application-code level (Python normalization before DB writes). No schema, FK, or ORM model changes were made — 3b.1's smoke test results remain valid.

### Index symbol live round-trip

**Omitted.** The index symbol round-trip test is only meaningful when outbound Schwab wiring (Phase 5) is active. Since Phase 5 is deferred, there is no outbound path to test. This will be verified when the Schwab outbound wiring ships.

---

## Deviations from Audit

- **Phase 5 (outbound wiring) deferred.** Audit §7.3b.2 Action 3 (`to_api_symbol` into Schwab calls) was not applied due to the `AsyncSession` availability gap at all three Schwab outbound call sites. The helper functions exist and are tested; only the wiring is deferred.
- **`analysis_routes.py` lines 824 and 963** were also wired through `canonicalize()`. These are `Thesis` and `ProbabilityMatrixResponse` objects respectively — not strictly DB writes but symbol values that flow through the system. The audit's §3.2 rows 2 and 5 cover the same file's `sym = req.symbol.upper()` assignments, which feed these downstream sites.

## Findings Not in Audit

- None. All inbound wiring was mechanical as predicted.

---

## File Inventory

| Status | File |
|--------|------|
| NEW | `app/services/symbol_normalization.py` |
| NEW | `tests/services/__init__.py` |
| NEW | `tests/services/test_symbol_normalization.py` |
| MODIFIED | `app/api/position_routes.py` |
| MODIFIED | `app/api/analysis_routes.py` |
| MODIFIED | `app/analysis/chain_collection.py` |
| MODIFIED | `app/agents/context_store.py` |
| MODIFIED | `app/api/trade_evaluation_routes.py` |
| MODIFIED | `app/api/evaluation_routes.py` |

**No files in `web/src/`, `app/models/`, `app/agents/insight_engine.py`, or `app/agents/position_monitor.py` were modified.**

---

## Banner: SUCCESS (Phases 1–4; Phase 5 deferred)
