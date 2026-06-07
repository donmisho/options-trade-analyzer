"""
Engine runtime wiring — Azure-SQL config hydration + bronze persistence sink.

This is the **app-layer** bridge between the domain-free Insight Engine
(``app/insight_engine/``) and OTA's Azure SQL store. The engine package never
imports a DB driver (insight_engine.md §2.5); the concrete ``ConfigSource`` and
``PersistenceSink`` live here and are injected.

Two responsibilities:

  OTA-818 — :class:`AzureSqlConfigSource` reads the five ``engine_*`` tables
            (scoped ``owner_app_id`` ∈ {SHARED, OTA}, ``enabled = 1`` handled by
            the loader), and :func:`init_engine_runtime` hydrates + validates the
            config once at startup, stashing it behind a module-level accessor.

  OTA-758 — :class:`BronzeSqlSink` writes the engine's two record streams
            (``CandidateSnapshot`` / ``EvaluationDecision``) into the single
            ``dbo.bronze_evaluations`` table discriminated by ``record_type``,
            plus the ``dbo.bronze_payload_contract`` registry. Writes are
            fire-and-forget: a failure logs but never blocks the evaluate call.

Credential / engine reuse
--------------------------
Neither class stands up its own credential path. Both take the app's existing
async session factory (``app.models.session.async_session``), which already
injects an Azure AD token per physical connection via a ``do_connect`` event
listener (see ``app/models/session.py``). There is no module-level credential
here and no parallel ``DefaultAzureCredential``.

Sync Protocol over async DB
---------------------------
The engine's ``ConfigSource`` and ``PersistenceSink`` Protocols are synchronous.
The source bridges by **pre-loading** all five tables (async) at startup, then
serving the buffered rows synchronously. The sink bridges by scheduling each
write as a coroutine on the captured event loop via
``asyncio.run_coroutine_threadsafe`` — non-blocking from either the loop thread
or a worker thread.

OTA-818, OTA-758
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.insight_engine import (
    CandidateSnapshot,
    ConfigSource,
    EngineConfig,
    EvaluationDecision,
    PersistenceSink,
    load_config,
    validate_and_raise,
)
from app.insight_engine.config_source import RawRow

logger = logging.getLogger(__name__)


# ── Config source (OTA-818) ──────────────────────────────────────────────


# The five engine_* tables, in (attribute, table) form. SELECT * keeps the
# row dicts keyed by the live DDL column names, which is exactly what the
# OTA-698 loader consumes — no column list to drift against the schema.
_ENGINE_TABLES: dict[str, str] = {
    "apps": "dbo.engine_apps",
    "rules": "dbo.engine_rules",
    "strategies": "dbo.engine_strategies",
    "junction": "dbo.engine_strategy_rule_junction",
    "lookups": "dbo.engine_lookups",
}


class AzureSqlConfigSource:
    """The single runtime read path for the ``engine_*`` config tables.

    Implements the OTA-698 :class:`ConfigSource` Protocol. Rows are pre-loaded
    once (async) via :meth:`load` and served back verbatim through the sync
    ``fetch_*`` methods — the loader does all parsing, filtering, and scoping.

    Per audit §5a #6 and the OTA-762 constraint, this is the **only** place in
    the app that reads ``engine_*``. No route, service, or endpoint opens its
    own connection to those tables.
    """

    def __init__(
        self,
        *,
        apps: list[RawRow],
        rules: list[RawRow],
        strategies: list[RawRow],
        junction: list[RawRow],
        lookups: list[RawRow],
    ) -> None:
        self._apps = apps
        self._rules = rules
        self._strategies = strategies
        self._junction = junction
        self._lookups = lookups

    @classmethod
    async def load(
        cls, session_factory: async_sessionmaker[AsyncSession]
    ) -> "AzureSqlConfigSource":
        """Pre-load all five ``engine_*`` tables into buffers (restart-only).

        Runs five ``SELECT *`` queries on one async session, materializing each
        as a list of plain dicts keyed by DDL column name. Called once at
        startup (insight_engine.md §6.5 — nothing re-reads the tables mid-run).
        """
        buffers: dict[str, list[RawRow]] = {}
        async with session_factory() as session:
            for attr, table in _ENGINE_TABLES.items():
                result = await session.execute(text(f"SELECT * FROM {table}"))
                buffers[attr] = [dict(row) for row in result.mappings().all()]

        logger.info(
            "engine config rows loaded: apps=%d rules=%d strategies=%d "
            "junction=%d lookups=%d",
            len(buffers["apps"]),
            len(buffers["rules"]),
            len(buffers["strategies"]),
            len(buffers["junction"]),
            len(buffers["lookups"]),
        )
        return cls(
            apps=buffers["apps"],
            rules=buffers["rules"],
            strategies=buffers["strategies"],
            junction=buffers["junction"],
            lookups=buffers["lookups"],
        )

    def fetch_apps(self) -> list[RawRow]:
        return list(self._apps)

    def fetch_rules(self) -> list[RawRow]:
        return list(self._rules)

    def fetch_strategies(self) -> list[RawRow]:
        return list(self._strategies)

    def fetch_junction(self) -> list[RawRow]:
        return list(self._junction)

    def fetch_lookups(self) -> list[RawRow]:
        return list(self._lookups)


# ── Bronze persistence sink (OTA-758) ─────────────────────────────────────


# Column order for the bronze_evaluations INSERT. record_id (IDENTITY) and
# registered_at default are omitted. Matches the DDL in
# insight_engine-schema-ddl.md §3 / migration ff832488933d.
_BRONZE_COLUMNS: tuple[str, ...] = (
    "record_type",
    "run_id",
    "snapshot_id",
    "source_app_id",
    "config_version",
    "engine_version",
    "evaluated_at",
    "payload_version",
    "candidate_type",
    "strategy_key",
    "symbol",
    "user_id",
    "subject_type",
    "subject_id",
    "final_score",
    "verdict",
    "terminal_phase",
    "rule_key",
    "phase",
    "tier",
    "evaluation_order",
    "passed",
    "stop_if_fail",
    "was_terminal",
    "score_contribution",
    "payload_json",
)

_BRONZE_INSERT_SQL = (
    "INSERT INTO dbo.bronze_evaluations ("
    + ", ".join(_BRONZE_COLUMNS)
    + ") VALUES ("
    + ", ".join(f":{c}" for c in _BRONZE_COLUMNS)
    + ")"
)

# Idempotent contract registration — UQ_bronze_payload_contract is the backstop;
# the IF NOT EXISTS guard avoids races and a per-write in-memory cache avoids
# re-attempting the same combo every batch.
_CONTRACT_INSERT_SQL = (
    "IF NOT EXISTS (SELECT 1 FROM dbo.bronze_payload_contract "
    "WHERE record_type = :record_type "
    "AND discriminator_value = :discriminator_value "
    "AND payload_version = :payload_version) "
    "INSERT INTO dbo.bronze_payload_contract "
    "(record_type, discriminator_value, payload_version, shape_description, source_app_id) "
    "VALUES (:record_type, :discriminator_value, :payload_version, :shape_description, :source_app_id)"
)


def _json_or_none(payload: Any) -> str | None:
    """Serialize a payload dict to a JSON string (ISJSON-safe), or None."""
    if payload is None:
        return None
    return json.dumps(payload, default=str)


class BronzeSqlSink:
    """Concrete :class:`PersistenceSink` landing both streams into bronze.

    The engine drives ``write_snapshots`` / ``write_decisions`` synchronously
    after each run. This sink maps the records to ``dbo.bronze_evaluations``
    rows (discriminated by ``record_type``), registers the
    ``(record_type, discriminator_value, payload_version)`` combos in
    ``dbo.bronze_payload_contract``, and schedules the write on the captured
    event loop.

    Fire-and-forget (insight_engine.md §4.3): a write failure is logged and
    swallowed — the evaluate response always returns. The engine never blocks
    on the sink.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._session_factory = session_factory
        self._loop = loop
        # Combos already (attempted to be) registered this process, to skip the
        # contract round-trip on the hot path. The DB unique constraint is the
        # source of truth; this is only an optimization.
        self._registered_contracts: set[tuple[str, str, int]] = set()

    # -- Protocol methods (sync; called by the engine) --------------------

    def write_snapshots(self, records: list[CandidateSnapshot]) -> None:
        if not records:
            return
        rows = [self._snapshot_to_row(r) for r in records]
        contracts = self._collect_contracts(
            (r.source_app_id, "SNAPSHOT", r.candidate_type, r.payload_version)
            for r in records
        )
        self._schedule(rows, contracts, stream="snapshots")

    def write_decisions(self, records: list[EvaluationDecision]) -> None:
        if not records:
            return
        rows = [self._decision_to_row(r) for r in records]
        contracts = self._collect_contracts(
            (r.source_app_id, "DECISION", r.phase, r.payload_version)
            for r in records
        )
        self._schedule(rows, contracts, stream="decisions")

    # -- Scheduling (fire-and-forget) -------------------------------------

    def _schedule(
        self,
        rows: list[dict[str, Any]],
        contracts: list[dict[str, Any]],
        *,
        stream: str,
    ) -> None:
        """Schedule the async write on the captured loop, never blocking.

        Safe from either the loop thread or a worker thread. Any failure to
        even schedule is logged and swallowed.
        """
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_write(rows, contracts, stream=stream), self._loop
            )
            future.add_done_callback(lambda f: self._log_future_exception(f, stream))
        except Exception:  # pragma: no cover - scheduling itself failing is rare
            logger.exception(
                "bronze sink: failed to schedule %s write (swallowed)", stream
            )

    @staticmethod
    def _log_future_exception(future: Any, stream: str) -> None:
        try:
            exc = future.exception()
        except Exception:  # cancelled / not done
            return
        if exc is not None:
            logger.error(
                "bronze sink: %s write failed (swallowed, fire-and-forget): %r",
                stream,
                exc,
            )

    async def _async_write(
        self,
        rows: list[dict[str, Any]],
        contracts: list[dict[str, Any]],
        *,
        stream: str,
    ) -> None:
        try:
            async with self._session_factory() as session:
                for contract in contracts:
                    await session.execute(text(_CONTRACT_INSERT_SQL), contract)
                if rows:
                    await session.execute(text(_BRONZE_INSERT_SQL), rows)
                await session.commit()
        except Exception:
            logger.exception(
                "bronze sink: %s write failed (swallowed, fire-and-forget)", stream
            )

    # -- Contract registration --------------------------------------------

    def _collect_contracts(self, combos) -> list[dict[str, Any]]:
        """Build contract rows for combos not yet registered this process."""
        out: list[dict[str, Any]] = []
        for source_app_id, record_type, discriminator, payload_version in combos:
            key = (record_type, str(discriminator), int(payload_version))
            if key in self._registered_contracts:
                continue
            self._registered_contracts.add(key)
            out.append(
                {
                    "record_type": record_type,
                    "discriminator_value": str(discriminator),
                    "payload_version": int(payload_version),
                    "shape_description": (
                        f"Auto-registered by BronzeSqlSink for "
                        f"{record_type}/{discriminator}/v{payload_version}"
                    ),
                    "source_app_id": source_app_id,
                }
            )
        return out

    # -- Record → row mappers ---------------------------------------------

    @staticmethod
    def _snapshot_to_row(r: CandidateSnapshot) -> dict[str, Any]:
        return {
            "record_type": "SNAPSHOT",
            "run_id": r.run_id,
            "snapshot_id": r.snapshot_id,
            "source_app_id": r.source_app_id,
            "config_version": r.config_version,
            "engine_version": r.engine_version,
            "evaluated_at": r.evaluated_at,
            "payload_version": r.payload_version,
            # SNAPSHOT promoted columns
            "candidate_type": r.candidate_type,
            "strategy_key": r.strategy_key,
            "symbol": r.symbol,
            "user_id": r.user_id,
            "subject_type": r.subject_type,
            "subject_id": r.subject_id,
            "final_score": r.final_score,
            "verdict": r.verdict,
            "terminal_phase": r.terminal_phase,
            # DECISION columns NULL on snapshot rows
            "rule_key": None,
            "phase": None,
            "tier": None,
            "evaluation_order": None,
            "passed": None,
            "stop_if_fail": None,
            "was_terminal": None,
            "score_contribution": None,
            "payload_json": _json_or_none(r.payload_json),
        }

    @staticmethod
    def _decision_to_row(r: EvaluationDecision) -> dict[str, Any]:
        return {
            "record_type": "DECISION",
            "run_id": r.run_id,
            "snapshot_id": r.snapshot_id,
            "source_app_id": r.source_app_id,
            "config_version": r.config_version,
            "engine_version": r.engine_version,
            "evaluated_at": r.evaluated_at,
            "payload_version": r.payload_version,
            # SNAPSHOT columns NULL on decision rows
            "candidate_type": None,
            "strategy_key": None,
            "symbol": None,
            "user_id": None,
            "subject_type": None,
            "subject_id": None,
            "final_score": None,
            "verdict": None,
            "terminal_phase": None,
            # DECISION promoted columns
            "rule_key": r.rule_key,
            "phase": r.phase,
            "tier": r.tier,
            "evaluation_order": r.evaluation_order,
            "passed": r.passed,
            "stop_if_fail": r.stop_if_fail,
            "was_terminal": r.was_terminal,
            "score_contribution": r.score_contribution,
            "payload_json": _json_or_none(r.payload_json),
        }


# ── Runtime holder + accessor (OTA-818) ───────────────────────────────────


@dataclass(frozen=True)
class EngineRuntime:
    """The hydrated, validated engine runtime, resolved once at startup.

    Mirrors the hard-gate registry accessor pattern in
    ``app/analysis/hard_gates/__init__.py``: a module-level holder set once,
    read through a single accessor / FastAPI dependency.
    """

    config: EngineConfig
    sink: PersistenceSink
    source: ConfigSource
    config_version: str
    # The loadable-set hash stamped at startup (OTA-790). GET /config/status
    # recomputes the same hash from current DB rows and compares; a difference
    # means the persisted config diverged from what is running → restart pending.
    # Distinct from config_version (which hashes drafts in); see
    # loader._compute_loadable_version.
    loadable_version: str


_runtime: EngineRuntime | None = None


def set_engine_runtime(runtime: EngineRuntime) -> None:
    """Stash the resolved runtime. Called once from the app lifespan."""
    global _runtime
    _runtime = runtime


def get_engine_runtime() -> EngineRuntime:
    """Return the hydrated engine runtime, or raise if not initialized.

    Doubles as a FastAPI dependency (``Depends(get_engine_runtime)``).
    """
    if _runtime is None:
        raise RuntimeError(
            "Engine runtime not initialized. init_engine_runtime() must run "
            "in the app lifespan before any route resolves the engine config."
        )
    return _runtime


def _reset_engine_runtime() -> None:
    """Clear the holder. For tests only."""
    global _runtime
    _runtime = None


async def compute_persisted_loadable_version(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app_ids: tuple[str, ...] = ("SHARED", "OTA"),
) -> str:
    """Recompute the loadable config version from CURRENT DB rows, on demand.

    Reads a FRESH :class:`AzureSqlConfigSource` and runs ``load_config`` — the
    same path startup uses — so the loadable-set hash has a single definition
    (``EngineConfig.loadable_version``). GET /config/status compares this to the
    running :attr:`EngineRuntime.loadable_version` to detect a pending restart.

    Restart-only invariant (insight_engine.md §6.5): this never mutates the
    running runtime — it does not call ``set_engine_runtime`` and does not touch
    the holder. It is a read-only recompute.
    """
    source = await AzureSqlConfigSource.load(session_factory)
    return load_config(source, app_ids=app_ids).loadable_version


# ── Startup hydration (OTA-818 + OTA-758) ─────────────────────────────────


async def init_engine_runtime(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    formula_registry: Any = None,
    app_ids: tuple[str, ...] = ("SHARED", "OTA"),
) -> EngineRuntime:
    """Hydrate, validate, and stash the engine runtime once at startup.

    1. Build :class:`AzureSqlConfigSource` (pre-loads the five tables).
    2. ``load_config`` resolves per-strategy RuleSets + the config-version hash.
    3. The OTA-699 validator runs (fail-closed). A validation failure raises
       :class:`ConfigValidationError` — loud and **fatal** to hydration, never
       swallowed (acceptance criterion). Per the prompt, a validator failure on
       the live seed is OTA-815 territory — do not patch config to pass.
    4. Construct :class:`BronzeSqlSink` and stash both behind the accessor.

    The input catalog is intentionally **not** passed (see OTA-818 decision):
    the live ``CatalogEntry`` shape differs from the engine ``NamedValue``
    shape, so the named-value-completeness and null-semantic validator
    sub-checks are skipped here, exactly as the proven test wiring does. The
    weight-sum, monotonic-band, formula-coverage, parameter-conformance, and
    junction-FK checks all still run.
    """
    if formula_registry is None:
        # Live screening formula registry (OTA-726). Imported lazily so the
        # engine package stays import-clean and this module has no hard
        # dependency on the registry module at import time.
        from app.options_rules.screening import get_registry

        formula_registry = get_registry()

    source = await AzureSqlConfigSource.load(session_factory)
    config = load_config(source, app_ids=app_ids)

    # Fail-closed startup validation (OTA-699). Raises on any failure.
    validate_and_raise(config, formula_registry=formula_registry, source=source)

    loop = asyncio.get_running_loop()
    sink = BronzeSqlSink(session_factory=session_factory, loop=loop)

    runtime = EngineRuntime(
        config=config,
        sink=sink,
        source=source,
        config_version=config.config_version,
        loadable_version=config.loadable_version,
    )
    set_engine_runtime(runtime)

    logger.info(
        "Engine runtime hydrated: config_version=%s strategies=%d (%s)",
        config.config_version,
        len(config.rule_sets),
        ", ".join(sorted(config.rule_sets)) or "(none)",
    )
    return runtime
