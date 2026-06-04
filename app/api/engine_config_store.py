"""
Engine config write store (OTA-782).

The durable maintenance surface for the four editable ``engine_*`` configuration
tables — ``engine_strategies``, ``engine_rules``, ``engine_strategy_rule_junction``,
``engine_lookups`` — that replaces spreadsheet edits (``insight_engine.md`` §6.2).

Each write is staged, then validated against the engine-load path before commit
(:func:`_commit_with_validation` → ``engine_config_validation.validate_pending``,
OTA-783): a write that would prevent a clean engine load is rejected and rolled
back, so the tables never hold a non-loadable state. The validation reuses the
OTA-699 checks — it is not a parallel validator.

Why SQLAlchemy Core, not ORM
----------------------------
The ``engine_*`` tables have no ORM models on ``app/models/database.py`` ``Base``
(they are owned by Alembic migration ``c83ed6dc89cf`` and read at runtime via raw
SQL in ``AzureSqlConfigSource``). Defining them here with a **separate**
``MetaData`` keeps the Alembic CI gate (which watches ``database.py``) untouched,
keeps these tables out of ``Base.metadata.create_all`` for the app, and lets Core
emit dialect-correct SQL — Azure SQL in production, in-memory SQLite in tests.
``create_all(_metadata, ...)`` builds the test schema; production never calls it.

App-scoping invariants (ticket AC + ``insight_engine-schema-ddl.md`` §1)
------------------------------------------------------------------------
- Every write forces ``owner_app_id='OTA'``. SHARED rows (the cross-app rule
  library and SHARED lookup sets) are read-only through this API — a request that
  names a non-OTA owner is rejected with :class:`SharedRowError`.
- Natural-key uniqueness is respected: a duplicate create surfaces
  :class:`DuplicateKeyError` (mapped to 409), never a 500.
- Junction mechanical fields persist to their typed columns; variable per-rule
  parameters persist to the single validated ``parameters`` JSON column.

Read-after-write staleness
---------------------------
These writes change what the engine loads at **next start** (``insight_engine.md``
§6.5). The hydrated runtime config behind ``get_engine_runtime()`` is not
refreshed here, so ``GET /config/strategies`` (OTA-762, which reads the in-memory
projection) will not reflect a write until the app restarts. Each write returns
the freshly-written **row** so the editor surface has an immediate round-trip.

OTA-782
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# The forced owner scope for every write through this API.
OTA_APP_ID = "OTA"

RawRow = dict[str, Any]


# ── Typed errors (mapped to HTTP status by the route layer) ───────────────


class EngineConfigError(Exception):
    """Base class for store-level errors with a stable HTTP mapping."""


class SharedRowError(EngineConfigError):
    """A write targeted a non-OTA (e.g. SHARED) row. → 403."""


class DuplicateKeyError(EngineConfigError):
    """A create violated a natural-key unique constraint. → 409."""


class NotFoundError(EngineConfigError):
    """A targeted row (or a referenced parent) does not exist. → 404."""


class InUseError(EngineConfigError):
    """A delete was blocked because dependent junction rows reference the row. → 409."""


# ── Core schema (separate MetaData; faithful to insight_engine-schema-ddl.md §2) ──
#
# Only column names, types, PKs, and the natural-key UNIQUE constraints matter:
# they drive Core SQL generation in prod and the SQLite schema in tests. The
# ISJSON CHECK constraints are intentionally omitted (SQLite has no ISJSON); JSON
# validity is enforced in Python on the write path and by the DB CHECK in prod.

_metadata = MetaData()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


engine_apps = Table(
    "engine_apps",
    _metadata,
    Column("app_id", String(16), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("description", String(500)),
    Column("status", String(20), nullable=False, default="active"),
    Column("created_at", DateTime, nullable=False, default=_utcnow),
)

engine_rules = Table(
    "engine_rules",
    _metadata,
    Column("rule_id", Integer, primary_key=True, autoincrement=True),
    Column("owner_app_id", String(16), ForeignKey("engine_apps.app_id"), nullable=False),
    Column("rule_key", String(100), nullable=False),
    Column("phase", String(40), nullable=False),
    Column("tier", String(16)),
    Column("intent", String(500)),
    Column("condition_expression", String(500)),
    Column("formula_ref", String(100)),
    Column("referenced_named_values", Text),
    Column("parameter_schema", Text),
    Column("null_semantics", String(20)),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=_utcnow),
    Column("updated_at", DateTime),
    UniqueConstraint("owner_app_id", "rule_key", name="UQ_engine_rules_owner_key"),
)

engine_strategies = Table(
    "engine_strategies",
    _metadata,
    Column("strategy_id", Integer, primary_key=True, autoincrement=True),
    Column("owner_app_id", String(16), ForeignKey("engine_apps.app_id"), nullable=False),
    Column("strategy_key", String(50), nullable=False),
    Column("display_name", String(100), nullable=False),
    Column("consumer_surface", String(40), nullable=False),
    Column("description", Text),
    Column("compatible_structures", Text),
    Column("verdict_band_set", Text, nullable=False),
    Column("dte_min", Integer),
    Column("dte_max", Integer),
    # status: lifecycle column (OTA-822). Declared here so the admin read
    # (OTA-823) can SELECT it and the SQLite test schema carries it. Wiring it
    # into create/update + the status<->enabled invariant is OTA-824; this
    # column's default mirrors the migration's server_default.
    Column("status", String(16), nullable=False, default="active"),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=_utcnow),
    Column("updated_at", DateTime),
    UniqueConstraint("owner_app_id", "strategy_key", name="UQ_engine_strategies_owner_key"),
)

engine_junction = Table(
    "engine_strategy_rule_junction",
    _metadata,
    Column("junction_id", Integer, primary_key=True, autoincrement=True),
    Column("strategy_id", Integer, ForeignKey("engine_strategies.strategy_id"), nullable=False),
    Column("rule_id", Integer, ForeignKey("engine_rules.rule_id"), nullable=False),
    Column("evaluation_order", Integer, nullable=False),
    Column("stop_if_fail", Boolean, nullable=False),
    Column("score_penalty", Numeric(6, 2)),
    Column("weight", Numeric(7, 4)),
    Column("parameters", Text),
    Column("terminal_verdict", String(32)),
    Column("rationale", String(1000)),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=_utcnow),
    Column("updated_at", DateTime),
    UniqueConstraint("strategy_id", "rule_id", name="UQ_engine_junction"),
)

engine_lookups = Table(
    "engine_lookups",
    _metadata,
    Column("lookup_id", Integer, primary_key=True, autoincrement=True),
    Column("owner_app_id", String(16), ForeignKey("engine_apps.app_id"), nullable=False),
    Column("lookup_set", String(60), nullable=False),
    Column("lookup_key", String(100), nullable=False),
    Column("payload", Text, nullable=False),
    Column("sort_order", Integer),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=_utcnow),
    UniqueConstraint("owner_app_id", "lookup_set", "lookup_key", name="UQ_engine_lookups"),
)


# Per-table set of columns whose stored value is a JSON string. Serialized on
# write, parsed back to Python objects on read so the canonical shape carries
# real JSON, not an escaped string.
_JSON_COLUMNS: dict[str, frozenset[str]] = {
    "engine_rules": frozenset({"referenced_named_values", "parameter_schema"}),
    "engine_strategies": frozenset({"compatible_structures", "verdict_band_set"}),
    "engine_strategy_rule_junction": frozenset({"parameters"}),
    "engine_lookups": frozenset({"payload"}),
}


# ── JSON (de)serialization helpers ────────────────────────────────────────


def _dump_json(value: Any, field: str) -> str | None:
    """Serialize a JSON-able value to a string (ISJSON-safe), or pass a string through.

    Raises ``ValueError`` on a non-serializable value or an invalid JSON string —
    the route maps this to 422 so a bad payload never reaches the DB CHECK as a 500.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid JSON for {field!r}: {exc}") from exc
        return value
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Value for {field!r} is not JSON-serializable: {exc}") from exc


def _row_to_dict(row: Any, table_name: str) -> RawRow:
    """Convert a result Row mapping to a plain dict, parsing JSON columns to objects."""
    data = dict(row)
    for col in _JSON_COLUMNS.get(table_name, ()):  # parse stored JSON strings
        raw = data.get(col)
        if isinstance(raw, str):
            try:
                data[col] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass  # leave as-is; should not happen given write-path validation
    return data


# ── Save-time validation (OTA-783) ────────────────────────────────────────


async def _commit_with_validation(session: AsyncSession) -> None:
    """Flush the staged write, validate via the OTA-699 engine-load path, commit.

    This is the OTA-782 validation seam, now realized (OTA-783). The DML is
    already staged on ``session``; we flush so the change is visible inside the
    transaction, run ``engine_config_validation.validate_pending`` (which reuses
    ``load_config`` + ``validate_config``), and commit only if it passes. A
    validation failure rolls back — no partial / non-loadable state is persisted.

    Imported lazily to avoid a module-level cycle (the validation module imports
    this module's Table objects).
    """
    from app.api import engine_config_validation  # lazy: breaks import cycle

    await session.flush()
    try:
        await engine_config_validation.validate_pending(session)
    except engine_config_validation.ConfigSaveValidationError:
        await session.rollback()
        raise
    await session.commit()


# ── Strategies ────────────────────────────────────────────────────────────


async def create_strategy(session: AsyncSession, data: RawRow) -> RawRow:
    _reject_shared(data.get("owner_app_id"))
    payload = _strategy_values(data)
    await _ensure_absent(
        session, engine_strategies,
        engine_strategies.c.owner_app_id == OTA_APP_ID,
        engine_strategies.c.strategy_key == payload["strategy_key"],
        what=f"strategy {payload['strategy_key']!r}",
    )
    await _insert(session, engine_strategies, payload)
    return await _get_strategy(session, payload["strategy_key"])


async def update_strategy(session: AsyncSession, strategy_key: str, data: RawRow) -> RawRow:
    _reject_shared(data.get("owner_app_id"))
    await _get_strategy(session, strategy_key)  # 404 if missing
    payload = _strategy_values({**data, "strategy_key": strategy_key})
    payload.pop("strategy_key")  # natural key is immutable via PUT path
    payload["updated_at"] = _utcnow()
    await session.execute(
        update(engine_strategies)
        .where(engine_strategies.c.owner_app_id == OTA_APP_ID)
        .where(engine_strategies.c.strategy_key == strategy_key)
        .values(**payload)
    )
    await _commit_with_validation(session)
    return await _get_strategy(session, strategy_key)


async def delete_strategy(session: AsyncSession, strategy_key: str) -> RawRow:
    existing = await _get_strategy(session, strategy_key)  # 404 if missing
    in_use = await session.scalar(
        select(engine_junction.c.junction_id)
        .where(engine_junction.c.strategy_id == existing["strategy_id"])
        .limit(1)
    )
    if in_use is not None:
        raise InUseError(
            f"strategy {strategy_key!r} has junction rows; remove them before deleting"
        )
    await session.execute(
        delete(engine_strategies)
        .where(engine_strategies.c.owner_app_id == OTA_APP_ID)
        .where(engine_strategies.c.strategy_key == strategy_key)
    )
    await _commit_with_validation(session)
    return existing


def _strategy_values(data: RawRow) -> RawRow:
    return {
        "owner_app_id": OTA_APP_ID,
        "strategy_key": data["strategy_key"],
        "display_name": data["display_name"],
        "consumer_surface": data["consumer_surface"],
        "description": data.get("description"),
        "compatible_structures": _dump_json(
            data.get("compatible_structures"), "compatible_structures"
        ),
        "verdict_band_set": _dump_json(data["verdict_band_set"], "verdict_band_set"),
        "dte_min": data.get("dte_min"),
        "dte_max": data.get("dte_max"),
        "enabled": data.get("enabled", True),
    }


async def _get_strategy(session: AsyncSession, strategy_key: str) -> RawRow:
    row = (
        await session.execute(
            select(engine_strategies)
            .where(engine_strategies.c.owner_app_id == OTA_APP_ID)
            .where(engine_strategies.c.strategy_key == strategy_key)
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(f"strategy {strategy_key!r} not found")
    return _row_to_dict(row, "engine_strategies")


# ── Admin read (OTA-823) ──────────────────────────────────────────────────
#
# Owner-scoped admin listing for the strategy selector (OTA-784). Returns the
# CURRENT engine_strategies state across ALL owners (OTA + SHARED) and ALL
# consumer surfaces, read straight from the table via the injected session, so a
# just-saved write shows immediately. This is deliberately a different read path
# from the OTA-762 hydrated runtime projection (restart-gated, SCREENING-only,
# owner-blind) — it reuses no engine-load accessor. owner_app_id rides on every
# row so the UI renders OTA rows editable and SHARED rows read-only; SHARED rows
# are returned, never filtered out.


async def list_strategies_admin(session: AsyncSession) -> list[RawRow]:
    """Return every ``engine_strategies`` row (all owners + surfaces), current state."""
    rows = (
        await session.execute(
            select(engine_strategies).order_by(
                engine_strategies.c.owner_app_id, engine_strategies.c.strategy_key
            )
        )
    ).mappings().all()
    return [_row_to_dict(row, "engine_strategies") for row in rows]


# ── Rules ─────────────────────────────────────────────────────────────────


async def create_rule(session: AsyncSession, data: RawRow) -> RawRow:
    _reject_shared(data.get("owner_app_id"))
    payload = _rule_values(data)
    await _ensure_absent(
        session, engine_rules,
        engine_rules.c.owner_app_id == OTA_APP_ID,
        engine_rules.c.rule_key == payload["rule_key"],
        what=f"rule {payload['rule_key']!r}",
    )
    await _insert(session, engine_rules, payload)
    return await _get_rule(session, payload["rule_key"])


async def update_rule(session: AsyncSession, rule_key: str, data: RawRow) -> RawRow:
    _reject_shared(data.get("owner_app_id"))
    await _get_rule(session, rule_key)  # 404 if missing
    payload = _rule_values({**data, "rule_key": rule_key})
    payload.pop("rule_key")
    payload["updated_at"] = _utcnow()
    await session.execute(
        update(engine_rules)
        .where(engine_rules.c.owner_app_id == OTA_APP_ID)
        .where(engine_rules.c.rule_key == rule_key)
        .values(**payload)
    )
    await _commit_with_validation(session)
    return await _get_rule(session, rule_key)


async def delete_rule(session: AsyncSession, rule_key: str) -> RawRow:
    existing = await _get_rule(session, rule_key)  # 404 if missing
    in_use = await session.scalar(
        select(engine_junction.c.junction_id)
        .where(engine_junction.c.rule_id == existing["rule_id"])
        .limit(1)
    )
    if in_use is not None:
        raise InUseError(
            f"rule {rule_key!r} is bound to one or more strategies; "
            "remove those junction rows before deleting"
        )
    await session.execute(
        delete(engine_rules)
        .where(engine_rules.c.owner_app_id == OTA_APP_ID)
        .where(engine_rules.c.rule_key == rule_key)
    )
    await _commit_with_validation(session)
    return existing


def _rule_values(data: RawRow) -> RawRow:
    return {
        "owner_app_id": OTA_APP_ID,
        "rule_key": data["rule_key"],
        "phase": data["phase"],
        "tier": data.get("tier"),
        "intent": data.get("intent"),
        "condition_expression": data.get("condition_expression"),
        "formula_ref": data.get("formula_ref"),
        "referenced_named_values": _dump_json(
            data.get("referenced_named_values"), "referenced_named_values"
        ),
        "parameter_schema": _dump_json(data.get("parameter_schema"), "parameter_schema"),
        "null_semantics": data.get("null_semantics"),
        "enabled": data.get("enabled", True),
    }


async def _get_rule(session: AsyncSession, rule_key: str) -> RawRow:
    row = (
        await session.execute(
            select(engine_rules)
            .where(engine_rules.c.owner_app_id == OTA_APP_ID)
            .where(engine_rules.c.rule_key == rule_key)
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(f"rule {rule_key!r} not found")
    return _row_to_dict(row, "engine_rules")


# ── Junction ──────────────────────────────────────────────────────────────
#
# Identified by the natural (strategy_key, rule_key) pair, both resolved within
# the OTA owner scope. The junction carries no owner_app_id of its own; SHARED
# read-only protection applies to the rule/strategy library, not the binding.


async def create_junction(session: AsyncSession, data: RawRow) -> RawRow:
    strategy_key = data["strategy_key"]
    rule_key = data["rule_key"]
    strat = await _get_strategy(session, strategy_key)
    rule = await _get_rule(session, rule_key)
    existing = await session.scalar(
        select(engine_junction.c.junction_id)
        .where(engine_junction.c.strategy_id == strat["strategy_id"])
        .where(engine_junction.c.rule_id == rule["rule_id"])
    )
    if existing is not None:
        raise DuplicateKeyError(
            f"junction ({strategy_key!r}, {rule_key!r}) already exists"
        )
    payload = _junction_values(strat["strategy_id"], rule["rule_id"], data)
    await _insert(session, engine_junction, payload)
    return await _get_junction(session, strategy_key, rule_key)


async def update_junction(
    session: AsyncSession, strategy_key: str, rule_key: str, data: RawRow
) -> RawRow:
    await _get_junction(session, strategy_key, rule_key)  # 404 if missing
    strat = await _get_strategy(session, strategy_key)
    rule = await _get_rule(session, rule_key)
    payload = _junction_values(strat["strategy_id"], rule["rule_id"], data)
    payload.pop("strategy_id")  # binding identity is immutable via PUT path
    payload.pop("rule_id")
    payload["updated_at"] = _utcnow()
    await session.execute(
        update(engine_junction)
        .where(engine_junction.c.strategy_id == strat["strategy_id"])
        .where(engine_junction.c.rule_id == rule["rule_id"])
        .values(**payload)
    )
    await _commit_with_validation(session)
    return await _get_junction(session, strategy_key, rule_key)


async def delete_junction(
    session: AsyncSession, strategy_key: str, rule_key: str
) -> RawRow:
    existing = await _get_junction(session, strategy_key, rule_key)  # 404 if missing
    await session.execute(
        delete(engine_junction).where(
            engine_junction.c.junction_id == existing["junction_id"]
        )
    )
    await _commit_with_validation(session)
    return existing


def _junction_values(strategy_id: int, rule_id: int, data: RawRow) -> RawRow:
    return {
        "strategy_id": strategy_id,
        "rule_id": rule_id,
        "evaluation_order": data["evaluation_order"],
        "stop_if_fail": data["stop_if_fail"],
        "score_penalty": data.get("score_penalty"),
        "weight": data.get("weight"),
        "parameters": _dump_json(data.get("parameters"), "parameters"),
        "terminal_verdict": data.get("terminal_verdict"),
        "rationale": data.get("rationale"),
        "enabled": data.get("enabled", True),
    }


async def _get_junction(
    session: AsyncSession, strategy_key: str, rule_key: str
) -> RawRow:
    j = engine_junction
    s = engine_strategies
    r = engine_rules
    row = (
        await session.execute(
            select(
                j,
                s.c.strategy_key.label("strategy_key"),
                r.c.rule_key.label("rule_key"),
            )
            .select_from(
                j.join(s, j.c.strategy_id == s.c.strategy_id).join(
                    r, j.c.rule_id == r.c.rule_id
                )
            )
            .where(s.c.owner_app_id == OTA_APP_ID)
            .where(s.c.strategy_key == strategy_key)
            .where(r.c.owner_app_id == OTA_APP_ID)
            .where(r.c.rule_key == rule_key)
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(
            f"junction ({strategy_key!r}, {rule_key!r}) not found"
        )
    return _row_to_dict(row, "engine_strategy_rule_junction")


# ── Lookups ───────────────────────────────────────────────────────────────


async def create_lookup(session: AsyncSession, data: RawRow) -> RawRow:
    _reject_shared(data.get("owner_app_id"))
    payload = _lookup_values(data)
    await _ensure_absent(
        session, engine_lookups,
        engine_lookups.c.owner_app_id == OTA_APP_ID,
        engine_lookups.c.lookup_set == payload["lookup_set"],
        engine_lookups.c.lookup_key == payload["lookup_key"],
        what=f"lookup {payload['lookup_set']!r}/{payload['lookup_key']!r}",
    )
    await _insert(session, engine_lookups, payload)
    return await _get_lookup(session, payload["lookup_set"], payload["lookup_key"])


async def update_lookup(
    session: AsyncSession, lookup_set: str, lookup_key: str, data: RawRow
) -> RawRow:
    _reject_shared(data.get("owner_app_id"))
    await _get_lookup(session, lookup_set, lookup_key)  # 404 if missing
    payload = _lookup_values(
        {**data, "lookup_set": lookup_set, "lookup_key": lookup_key}
    )
    payload.pop("lookup_set")  # natural key is immutable via PUT path
    payload.pop("lookup_key")
    await session.execute(
        update(engine_lookups)
        .where(engine_lookups.c.owner_app_id == OTA_APP_ID)
        .where(engine_lookups.c.lookup_set == lookup_set)
        .where(engine_lookups.c.lookup_key == lookup_key)
        .values(**payload)
    )
    await _commit_with_validation(session)
    return await _get_lookup(session, lookup_set, lookup_key)


async def delete_lookup(
    session: AsyncSession, lookup_set: str, lookup_key: str
) -> RawRow:
    existing = await _get_lookup(session, lookup_set, lookup_key)  # 404 if missing
    await session.execute(
        delete(engine_lookups)
        .where(engine_lookups.c.owner_app_id == OTA_APP_ID)
        .where(engine_lookups.c.lookup_set == lookup_set)
        .where(engine_lookups.c.lookup_key == lookup_key)
    )
    await _commit_with_validation(session)
    return existing


def _lookup_values(data: RawRow) -> RawRow:
    return {
        "owner_app_id": OTA_APP_ID,
        "lookup_set": data["lookup_set"],
        "lookup_key": data["lookup_key"],
        "payload": _dump_json(data["payload"], "payload"),
        "sort_order": data.get("sort_order"),
        "enabled": data.get("enabled", True),
    }


async def _get_lookup(
    session: AsyncSession, lookup_set: str, lookup_key: str
) -> RawRow:
    row = (
        await session.execute(
            select(engine_lookups)
            .where(engine_lookups.c.owner_app_id == OTA_APP_ID)
            .where(engine_lookups.c.lookup_set == lookup_set)
            .where(engine_lookups.c.lookup_key == lookup_key)
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(f"lookup {lookup_set!r}/{lookup_key!r} not found")
    return _row_to_dict(row, "engine_lookups")


# ── Shared internals ──────────────────────────────────────────────────────


def _reject_shared(owner_app_id: Any) -> None:
    """Reject any write that names a non-OTA owner. Absent owner → forced to OTA."""
    if owner_app_id is not None and owner_app_id != OTA_APP_ID:
        raise SharedRowError(
            f"owner_app_id {owner_app_id!r} is read-only through this API; "
            "writes are scoped to OTA"
        )


async def _ensure_absent(session: AsyncSession, table: Table, *conditions, what: str) -> None:
    """Raise :class:`DuplicateKeyError` if a row matching ``conditions`` exists."""
    existing = await session.scalar(
        select(table.c[table.primary_key.columns.keys()[0]]).where(and_(*conditions))
    )
    if existing is not None:
        raise DuplicateKeyError(f"{what} already exists")


async def _insert(session: AsyncSession, table: Table, payload: RawRow) -> None:
    """Stage an insert, validate the resulting config, then commit.

    A unique-constraint race surfaces as DuplicateKeyError; a config that would
    not load cleanly surfaces as ConfigSaveValidationError (both before commit,
    so nothing partial is persisted).
    """
    try:
        await session.execute(insert(table).values(**payload))
    except IntegrityError as exc:  # natural-key race or FK miss → clear conflict
        await session.rollback()
        raise DuplicateKeyError(f"write to {table.name} violated a constraint") from exc
    await _commit_with_validation(session)
