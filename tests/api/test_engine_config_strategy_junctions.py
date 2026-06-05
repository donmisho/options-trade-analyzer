"""
OTA-826 — per-strategy junction read endpoint.

Exercises ``GET /api/v1/config/strategies/{key}/junctions`` end-to-end through
``app/api/engine_config_store.list_strategy_junctions`` against an in-memory
SQLite DB (the repo's no-Azure-SQL test convention), mirroring the OTA-823 /
OTA-825 admin-list test harness.

Coverage:
  - a live OTA strategy returns all its junction bindings, ordered by
    evaluation_order, each joined to its rule's phase / intent / parameter_schema.
  - the ``parameters`` (junction) and ``parameter_schema`` (rule) JSON columns
    come back parsed to objects, not escaped strings.
  - a ``<key>__draft`` strategy resolves and returns the draft's own bindings
    (drafts are OTA-owned).
  - disabled bindings (enabled=0) are returned, not filtered out.
  - a junction binding a SHARED rule still surfaces that rule's metadata (the
    join is on the rule_id FK, not owner-scoped).
  - an unknown strategy key (and a SHARED strategy, not OTA-owned) → 404.
  - unauthenticated request rejected (401).
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import engine_config_store as store
from app.api.engine_config_routes import router as engine_config_router

# ── Test DB (in-memory SQLite) ────────────────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


async def _get_test_db():
    async with _test_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


def _user_dep():
    async def _dep():
        return {"sub": "u1", "username": "dev", "role": "admin", "mfa": True}

    return _dep


def _build_authed_app() -> FastAPI:
    from app.auth.dependencies import get_current_user, require_read, require_write
    from app.models.session import get_db

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    dep = _user_dep()
    app.dependency_overrides[require_read] = dep
    app.dependency_overrides[require_write] = dep
    app.dependency_overrides[get_current_user] = dep
    app.dependency_overrides[get_db] = _get_test_db
    return app


def _build_unauth_app() -> FastAPI:
    from app.auth.dependencies import get_current_user
    from app.models.session import get_db

    async def _reject():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = _reject
    app.dependency_overrides[get_db] = _get_test_db
    return app


# ── Seed ───────────────────────────────────────────────────────────────────
#
# Strategies (explicit ids so junction FKs are deterministic):
#   1  alpha          OTA, live
#   2  alpha__draft   OTA, draft (status='draft', enabled=0)
#   3  shared_strat   SHARED  (must NOT resolve via the OTA-scoped read → 404)
# Rules:
#   1  entry_gate     OTA,    gate,    parameter_schema present
#   2  theta_scoring  OTA,    scoring, parameter_schema present
#   3  liquidity_gate SHARED, gate     (bound by alpha to prove FK-join, not
#                                       owner-scoped, surfaces SHARED metadata)
#   4  ghost_scoring  OTA,    scoring  (bound DISABLED — must still surface)
_VBS = json.dumps([{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}])

_STRATEGIES = [
    {
        "strategy_id": 1, "owner_app_id": "OTA", "strategy_key": "alpha",
        "display_name": "Alpha", "consumer_surface": "SCREENING",
        "verdict_band_set": _VBS, "status": "active", "enabled": True,
    },
    {
        "strategy_id": 2, "owner_app_id": "OTA", "strategy_key": "alpha__draft",
        "display_name": "Alpha", "consumer_surface": "SCREENING",
        "verdict_band_set": _VBS, "status": "draft", "enabled": False,
    },
    {
        "strategy_id": 3, "owner_app_id": "SHARED", "strategy_key": "shared_strat",
        "display_name": "Shared", "consumer_surface": "SCREENING",
        "verdict_band_set": _VBS, "status": "active", "enabled": True,
    },
]

_RULES = [
    {
        "rule_id": 1, "owner_app_id": "OTA", "rule_key": "entry_gate",
        "phase": "gate", "tier": "RAW", "intent": "Block on earnings proximity.",
        "parameter_schema": json.dumps({"days": {"type": "number", "min": 0, "max": 30}}),
        "enabled": True,
    },
    {
        "rule_id": 2, "owner_app_id": "OTA", "rule_key": "theta_scoring",
        "phase": "scoring", "tier": None, "intent": "Reward theta margin.",
        "parameter_schema": json.dumps({"scale": {"type": "number", "min": 0, "max": 100}}),
        "enabled": True,
    },
    {
        "rule_id": 3, "owner_app_id": "SHARED", "rule_key": "liquidity_gate",
        "phase": "gate", "tier": "RAW", "intent": "Minimum open interest.",
        "parameter_schema": None, "enabled": True,
    },
    {
        "rule_id": 4, "owner_app_id": "OTA", "rule_key": "ghost_scoring",
        "phase": "scoring", "tier": None, "intent": "A disabled binding.",
        "parameter_schema": None, "enabled": True,
    },
]

# alpha bindings — intentionally inserted OUT of evaluation_order to prove the
# endpoint sorts. theta(scoring) order 1, entry_gate order 2, liquidity_gate
# order 3, ghost order 4 (DISABLED). Draft binds only theta, order 1.
# Every dict carries the same key set: Core executemany compiles the column list
# from the first row, so a key present on only some rows would be silently dropped.
_JUNCTIONS = [
    {
        "junction_id": 10, "strategy_id": 1, "rule_id": 3, "evaluation_order": 3,
        "stop_if_fail": True, "weight": None, "parameters": None,
        "rationale": "shared liq gate", "enabled": True,
    },
    {
        "junction_id": 11, "strategy_id": 1, "rule_id": 1, "evaluation_order": 2,
        "stop_if_fail": True, "weight": None, "parameters": json.dumps({"days": 7}),
        "rationale": "earnings gate", "enabled": True,
    },
    {
        "junction_id": 12, "strategy_id": 1, "rule_id": 2, "evaluation_order": 1,
        "stop_if_fail": False, "weight": 1.0, "parameters": json.dumps({"scale": 50}),
        "rationale": "theta", "enabled": True,
    },
    {
        "junction_id": 13, "strategy_id": 1, "rule_id": 4, "evaluation_order": 4,
        "stop_if_fail": False, "weight": None, "parameters": None,
        "rationale": "disabled", "enabled": False,
    },
    {
        "junction_id": 20, "strategy_id": 2, "rule_id": 2, "evaluation_order": 1,
        "stop_if_fail": False, "weight": 1.0, "parameters": json.dumps({"scale": 80}),
        "rationale": "draft theta", "enabled": True,
    },
]


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with _test_engine.begin() as conn:
        await conn.run_sync(store._metadata.create_all)
        await conn.execute(
            insert(store.engine_apps),
            [
                {"app_id": "OTA", "name": "Options Analyzer"},
                {"app_id": "SHARED", "name": "Shared rule library"},
            ],
        )
        await conn.execute(insert(store.engine_strategies), _STRATEGIES)
        await conn.execute(insert(store.engine_rules), _RULES)
        await conn.execute(insert(store.engine_junction), _JUNCTIONS)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(store._metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    app = _build_authed_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lists_bindings_ordered_by_evaluation_order(client):
    r = await client.get("/api/v1/config/strategies/alpha/junctions")
    assert r.status_code == 200
    rows = r.json()
    # All four alpha bindings returned (incl. the disabled one), sorted by order.
    assert [row["evaluation_order"] for row in rows] == [1, 2, 3, 4]
    assert [row["rule_key"] for row in rows] == [
        "theta_scoring", "entry_gate", "liquidity_gate", "ghost_scoring"
    ]
    for row in rows:
        assert row["strategy_key"] == "alpha"
        assert row["strategy_id"] == 1


@pytest.mark.asyncio
async def test_joins_rule_metadata_and_parses_json(client):
    rows = (await client.get("/api/v1/config/strategies/alpha/junctions")).json()
    by_rule = {row["rule_key"]: row for row in rows}

    theta = by_rule["theta_scoring"]
    assert theta["phase"] == "scoring"
    assert theta["intent"] == "Reward theta margin."
    # parameter_schema (rule JSON) parsed to a dict, not a string.
    assert theta["parameter_schema"] == {"scale": {"type": "number", "min": 0, "max": 100}}
    # parameters (junction JSON) parsed to a dict.
    assert theta["parameters"] == {"scale": 50}
    assert theta["weight"] == 1.0
    assert theta["stop_if_fail"] is False

    gate = by_rule["entry_gate"]
    assert gate["phase"] == "gate"
    assert gate["stop_if_fail"] is True
    assert gate["parameters"] == {"days": 7}


@pytest.mark.asyncio
async def test_shared_rule_binding_surfaces_its_metadata(client):
    rows = (await client.get("/api/v1/config/strategies/alpha/junctions")).json()
    by_rule = {row["rule_key"]: row for row in rows}
    # liquidity_gate is a SHARED rule; the FK join (not owner-scoped) surfaces it.
    assert "liquidity_gate" in by_rule
    assert by_rule["liquidity_gate"]["phase"] == "gate"
    assert by_rule["liquidity_gate"]["parameter_schema"] is None


@pytest.mark.asyncio
async def test_disabled_binding_is_returned(client):
    rows = (await client.get("/api/v1/config/strategies/alpha/junctions")).json()
    by_rule = {row["rule_key"]: row for row in rows}
    # ghost_scoring binding is enabled=0 and must still appear (no enabled filter).
    assert by_rule["ghost_scoring"]["enabled"] is False


@pytest.mark.asyncio
async def test_draft_key_resolves_and_returns_draft_bindings(client):
    rows = (await client.get("/api/v1/config/strategies/alpha__draft/junctions")).json()
    assert len(rows) == 1
    assert rows[0]["rule_key"] == "theta_scoring"
    assert rows[0]["strategy_key"] == "alpha__draft"
    assert rows[0]["strategy_id"] == 2
    # The draft carries its OWN parameters (80), distinct from live (50).
    assert rows[0]["parameters"] == {"scale": 80}


@pytest.mark.asyncio
async def test_unknown_strategy_is_404(client):
    r = await client.get("/api/v1/config/strategies/nope/junctions")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_shared_strategy_not_ota_owned_is_404(client):
    # The read is OTA-scoped; a SHARED strategy key does not resolve.
    r = await client.get("/api/v1/config/strategies/shared_strat/junctions")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_requires_auth():
    app = _build_unauth_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/config/strategies/alpha/junctions")
    assert r.status_code == 401
