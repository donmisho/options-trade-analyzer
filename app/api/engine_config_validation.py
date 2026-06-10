"""
Save-time config validation (OTA-783) — reuses the OTA-699 engine-load checks.

Every config write through ``engine_config_store`` is validated against the
*exact* path the engine runs at startup (``insight_engine.md`` §6.6): build the
in-memory config from the (staged, uncommitted) table state, run the OTA-698
loader and the OTA-699 validator, and reject the write if either would refuse a
clean engine load. There is **no parallel validator** here — this module only
orchestrates the existing engine functions and translates their structured
output into a store error.

Why "load the whole config", not "check one row"
------------------------------------------------
The loader/validator operate over the entire resolved config (all strategies,
all rule bindings, all lookups). A single write can only be judged in that whole
— e.g. a scoring-weight edit is valid only relative to the strategy's other
weights. So the store stages the DML, flushes (so the change is visible inside
the transaction), and this module re-reads all five ``engine_*`` tables and runs
the same ``load_config`` + ``validate_config`` that ``init_engine_runtime`` runs
at startup. On success the store commits; on failure it rolls back — no partial,
non-loadable state is ever persisted (ticket AC).

Parity with startup wiring
--------------------------
Matches ``init_engine_runtime``: ``formula_registry`` is the **combined** live
registry (screening ∪ directional — OTA-840 ``build_combined_registry``), so the
formula-in-live and registry-drift checks resolve every surface's formulas;
``input_catalog`` is intentionally NOT passed (named-value-completeness and
null-semantics checks are skipped at startup, so they are correctly absent here
too); ``source`` is passed so the junction-FK check runs.

Note: save-time validation stays whole-config all-or-nothing (``validate_config``),
deliberately stricter than startup's surface-scoped degrade — a write that would
break any surface is rejected rather than silently degrading that surface.

OTA-783, OTA-840
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.engine_config_store import (
    engine_apps,
    engine_junction,
    engine_lookups,
    engine_rules,
    engine_strategies,
)
from app.insight_engine import (
    EngineConfig,
    InMemoryConfigSource,
    load_config,
    validate_config,
)
from app.insight_engine.expressions import UnsupportedExpressionError


class ConfigSaveValidationError(Exception):
    """A staged write would prevent a clean engine load.

    Carries the loader/validator's structured error identity verbatim (the same
    codes/messages OTA-699 emits at startup), so the API surfaces the engine's
    own diagnosis rather than a re-spelled copy. Mapped to HTTP 422 by the route.
    """

    def __init__(self, errors: list[dict[str, Any]], summary: str) -> None:
        self.errors = errors
        self.summary = summary
        super().__init__(summary)


def _get_registry():
    """Return the combined live formula registry used at startup (OTA-840).

    Indirected through a function (and imported lazily) so tests can monkeypatch
    it — e.g. to a ``StubFormulaRegistry`` — without standing up the real
    registries. Uses the same ``build_combined_registry`` (screening ∪ directional)
    that ``init_engine_runtime`` injects, so save-time validation does not falsely
    reject directional formulas as missing-from-live.
    """
    from app.ota_adapters.engine_runtime import build_combined_registry

    return build_combined_registry()


async def _fetch(session: AsyncSession, table) -> list[dict[str, Any]]:
    """Read every row of *table* as a plain dict keyed by DDL column name.

    JSON columns come back as strings (as stored) — exactly the shape the OTA-698
    loader expects, matching ``AzureSqlConfigSource``.
    """
    result = await session.execute(select(table))
    return [dict(row) for row in result.mappings().all()]


async def _load_in_memory_source(session: AsyncSession) -> InMemoryConfigSource:
    """Snapshot the staged (uncommitted) state of all five engine_* tables."""
    return InMemoryConfigSource(
        apps=await _fetch(session, engine_apps),
        rules=await _fetch(session, engine_rules),
        strategies=await _fetch(session, engine_strategies),
        junction=await _fetch(session, engine_junction),
        lookups=await _fetch(session, engine_lookups),
    )


async def validate_pending(session: AsyncSession) -> EngineConfig:
    """Validate the staged config via the OTA-699 path; raise on any failure.

    Must be called after the write DML is flushed but before commit. Reuses
    ``load_config`` (OTA-698) + ``validate_config`` (OTA-699) — no checks are
    re-derived here.

    Returns the resolved :class:`EngineConfig` (OTA-792) so the caller can read
    its ``loadable_version`` — the version stamp the committed change produces —
    without a second full-config load. ``load_config`` here uses the default
    ``app_ids=("SHARED","OTA")``, so this hash is identical to the one
    ``init_engine_runtime`` stamps and ``GET /config/status`` compares against.
    """
    source = await _load_in_memory_source(session)

    # Loader-path rejections (unknown phase, unsupported expression, malformed
    # BETWEEN) raise plain exceptions — surface them with the loader's message.
    try:
        config = load_config(source)
    except (ValueError, UnsupportedExpressionError) as exc:
        raise ConfigSaveValidationError(
            errors=[{"code": type(exc).__name__, "message": str(exc), "context": {}}],
            summary=f"Config would not load: {exc}",
        ) from exc

    # OTA-699 structured validation — same call init_engine_runtime makes.
    report = validate_config(config, formula_registry=_get_registry(), source=source)
    if not report.is_valid:
        raise ConfigSaveValidationError(
            errors=[
                {"code": e.code, "message": e.message, "context": e.context}
                for e in report.errors
            ],
            summary=report.summary(),
        )

    return config
