"""
OTA-782 — config CRUD write API over the engine_* tables.

Exercises ``app/api/engine_config_routes.py`` write endpoints end-to-end through
``app/api/engine_config_store.py`` against an in-memory SQLite DB (the repo's
no-Azure-SQL test convention). The store uses SQLAlchemy Core with a separate
MetaData, so the same code path runs on SQLite here and Azure SQL in prod.

Coverage (QA medium-high — negative paths, not just happy path):
  - CRUD round-trip for each of the four entities; canonical full-row shape back.
  - owner_app_id forced to OTA; a SHARED-targeting write is rejected (403).
  - duplicate natural key → 409 (not 500); referenced-row delete → 409.
  - junction parameters persist to the parameters JSON column (valid JSON);
    mechanical fields persist to typed columns.
  - unauthenticated request rejected (401); missing row → 404; bad JSON → 422.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
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
    """App where get_current_user rejects — leaves require_write real so the
    endpoint's auth dependency chain is what produces the 401."""
    from app.auth.dependencies import get_current_user
    from app.models.session import get_db

    async def _reject():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = _reject
    app.dependency_overrides[get_db] = _get_test_db
    return app


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with _test_engine.begin() as conn:
        await conn.run_sync(store._metadata.create_all)
        # FK targets (FK enforcement is off on SQLite by default, but seed for realism)
        from sqlalchemy import insert

        await conn.execute(
            insert(store.engine_apps),
            [
                {"app_id": "OTA", "name": "Options Analyzer"},
                {"app_id": "SHARED", "name": "Shared rule library"},
            ],
        )
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(store._metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    app = _build_authed_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Sample bodies ──────────────────────────────────────────────────────────

_STRATEGY = {
    "strategy_key": "steady_paycheck",
    "display_name": "Steady Paycheck",
    "consumer_surface": "SCREENING",
    "compatible_structures": ["BULL_PUT_CREDIT"],
    "verdict_band_set": [{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}],
    "dte_min": 30,
    "dte_max": 45,
}

_RULE = {
    "rule_key": "delta_band",
    "phase": "gate",
    "tier": "RAW",
    "intent": "Delta within band",
    "condition_expression": "delta BETWEEN low AND high",
    "referenced_named_values": ["delta"],
    "parameter_schema": {"low": {"type": "number"}, "high": {"type": "number"}},
}


async def _seed_strategy_and_rule(client):
    assert (await client.post("/api/v1/config/strategies", json=_STRATEGY)).status_code == 201
    assert (await client.post("/api/v1/config/rules", json=_RULE)).status_code == 201


# ── Strategy CRUD ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_crud_roundtrip(client):
    r = await client.post("/api/v1/config/strategies", json=_STRATEGY)
    assert r.status_code == 201
    body = r.json()
    assert body["strategy_key"] == "steady_paycheck"
    assert body["owner_app_id"] == "OTA"
    assert body["compatible_structures"] == ["BULL_PUT_CREDIT"]  # JSON round-trips as a list
    assert body["verdict_band_set"][0]["verdict"] == "EXECUTE"
    assert isinstance(body["strategy_id"], int)

    r = await client.put(
        "/api/v1/config/strategies/steady_paycheck",
        json={**{k: v for k, v in _STRATEGY.items() if k != "strategy_key"}, "display_name": "SP v2"},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "SP v2"
    assert r.json()["updated_at"] is not None

    r = await client.delete("/api/v1/config/strategies/steady_paycheck")
    assert r.status_code == 200
    assert r.json()["strategy_key"] == "steady_paycheck"  # canonical shape returned on delete
    assert (await client.put(
        "/api/v1/config/strategies/steady_paycheck",
        json={k: v for k, v in _STRATEGY.items() if k != "strategy_key"},
    )).status_code == 404


# ── Rule CRUD ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rule_crud_roundtrip(client):
    r = await client.post("/api/v1/config/rules", json=_RULE)
    assert r.status_code == 201
    body = r.json()
    assert body["rule_key"] == "delta_band"
    assert body["owner_app_id"] == "OTA"
    assert body["parameter_schema"] == {"low": {"type": "number"}, "high": {"type": "number"}}

    r = await client.put(
        "/api/v1/config/rules/delta_band",
        json={**{k: v for k, v in _RULE.items() if k != "rule_key"}, "intent": "tighter band"},
    )
    assert r.status_code == 200
    assert r.json()["intent"] == "tighter band"

    r = await client.delete("/api/v1/config/rules/delta_band")
    assert r.status_code == 200
    assert r.json()["rule_key"] == "delta_band"


# ── Junction CRUD ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_junction_crud_roundtrip_and_param_storage(client):
    await _seed_strategy_and_rule(client)

    payload = {
        "strategy_key": "steady_paycheck",
        "rule_key": "delta_band",
        "evaluation_order": 1,
        "stop_if_fail": True,
        "score_penalty": -10.0,
        "weight": 0.25,
        "parameters": {"low": 0.2, "high": 0.35},
        "rationale": "core gate",
    }
    r = await client.post("/api/v1/config/junction", json=payload)
    assert r.status_code == 201
    body = r.json()
    # Mechanical fields in typed columns
    assert body["evaluation_order"] == 1
    assert body["stop_if_fail"] is True
    assert body["score_penalty"] == -10.0
    assert body["weight"] == 0.25
    # Variable params round-trip from the JSON column as an object
    assert body["parameters"] == {"low": 0.2, "high": 0.35}
    assert body["strategy_key"] == "steady_paycheck"
    assert body["rule_key"] == "delta_band"

    # parameters is stored as a valid JSON string (ISJSON-equivalent)
    async with _test_session_factory() as s:
        from sqlalchemy import select

        raw = await s.scalar(select(store.engine_junction.c.parameters))
        assert isinstance(raw, str)
        assert json.loads(raw) == {"low": 0.2, "high": 0.35}

    r = await client.put(
        "/api/v1/config/junction/steady_paycheck/delta_band",
        json={**{k: v for k, v in payload.items() if k not in ("strategy_key", "rule_key")},
              "weight": 0.5},
    )
    assert r.status_code == 200
    assert r.json()["weight"] == 0.5

    r = await client.delete("/api/v1/config/junction/steady_paycheck/delta_band")
    assert r.status_code == 200
    assert r.json()["rule_key"] == "delta_band"


# ── Lookup CRUD ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_crud_roundtrip(client):
    payload = {
        "lookup_set": "width_configuration",
        "lookup_key": "tier_1",
        "payload": {"price_min": 0, "price_max": 50, "width_min": 1},
        "sort_order": 1,
    }
    r = await client.post("/api/v1/config/lookups", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["owner_app_id"] == "OTA"
    assert body["payload"] == {"price_min": 0, "price_max": 50, "width_min": 1}

    r = await client.put(
        "/api/v1/config/lookups/width_configuration/tier_1",
        json={"payload": {"price_min": 0, "price_max": 60}, "sort_order": 2},
    )
    assert r.status_code == 200
    assert r.json()["payload"] == {"price_min": 0, "price_max": 60}
    assert r.json()["sort_order"] == 2

    r = await client.delete("/api/v1/config/lookups/width_configuration/tier_1")
    assert r.status_code == 200
    assert r.json()["lookup_key"] == "tier_1"


# ── owner_app_id forcing + SHARED rejection ────────────────────────────────


@pytest.mark.asyncio
async def test_owner_app_id_forced_to_ota(client):
    # owner_app_id omitted → forced to OTA
    r = await client.post("/api/v1/config/strategies", json=_STRATEGY)
    assert r.json()["owner_app_id"] == "OTA"
    # explicit OTA is accepted
    r = await client.post(
        "/api/v1/config/rules", json={**_RULE, "owner_app_id": "OTA"}
    )
    assert r.status_code == 201
    assert r.json()["owner_app_id"] == "OTA"


@pytest.mark.asyncio
async def test_shared_row_mutation_rejected(client):
    # A write naming a SHARED owner is rejected — no SHARED mutation via this API.
    r = await client.post("/api/v1/config/rules", json={**_RULE, "owner_app_id": "SHARED"})
    assert r.status_code == 403

    r = await client.post(
        "/api/v1/config/lookups",
        json={"owner_app_id": "SHARED", "lookup_set": "pipeline_phases",
              "lookup_key": "gate", "payload": {"label": "Gate"}},
    )
    assert r.status_code == 403

    r = await client.post(
        "/api/v1/config/strategies", json={**_STRATEGY, "owner_app_id": "STK"}
    )
    assert r.status_code == 403


# ── Conflicts (409) ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_natural_key_conflict(client):
    assert (await client.post("/api/v1/config/strategies", json=_STRATEGY)).status_code == 201
    dup = await client.post("/api/v1/config/strategies", json=_STRATEGY)
    assert dup.status_code == 409  # not a 500

    assert (await client.post("/api/v1/config/rules", json=_RULE)).status_code == 201
    j = {"strategy_key": "steady_paycheck", "rule_key": "delta_band",
         "evaluation_order": 1, "stop_if_fail": False}
    assert (await client.post("/api/v1/config/junction", json=j)).status_code == 201
    assert (await client.post("/api/v1/config/junction", json=j)).status_code == 409


@pytest.mark.asyncio
async def test_delete_rule_in_use_conflict(client):
    await _seed_strategy_and_rule(client)
    j = {"strategy_key": "steady_paycheck", "rule_key": "delta_band",
         "evaluation_order": 1, "stop_if_fail": False}
    assert (await client.post("/api/v1/config/junction", json=j)).status_code == 201

    # rule is bound → delete blocked with a clear conflict, not an FK 500
    assert (await client.delete("/api/v1/config/rules/delta_band")).status_code == 409
    assert (await client.delete("/api/v1/config/strategies/steady_paycheck")).status_code == 409


# ── 404 / 422 / 401 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_not_found_paths(client):
    assert (await client.put(
        "/api/v1/config/rules/nope",
        json={k: v for k, v in _RULE.items() if k != "rule_key"},
    )).status_code == 404
    assert (await client.delete("/api/v1/config/lookups/x/y")).status_code == 404
    # junction create against a missing strategy → 404
    assert (await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "ghost", "rule_key": "delta_band",
              "evaluation_order": 1, "stop_if_fail": False},
    )).status_code == 404


@pytest.mark.asyncio
async def test_invalid_json_string_is_422(client):
    # referenced_named_values given as an invalid JSON *string* → 422, never a 500
    bad = {**_RULE, "referenced_named_values": "{not valid json"}
    r = await client.post("/api/v1/config/rules", json=bad)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_rejected():
    app = _build_unauth_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/config/strategies", json=_STRATEGY)
        assert r.status_code == 401
        r = await c.delete("/api/v1/config/rules/delta_band")
        assert r.status_code == 401
