"""
OTA-825 — owner-spanning rules-catalog admin endpoint.

Exercises ``GET /api/v1/config/rules/admin`` end-to-end through
``app/api/engine_config_store.list_rules_admin`` against an in-memory SQLite DB
(the repo's no-Azure-SQL test convention), mirroring the OTA-823 strategies
admin test harness.

Coverage:
  - returns OTA + SHARED rules, each tagged by owner_app_id; SHARED not filtered.
  - the owner_app_id IN ('OTA','SHARED') filter EXCLUDES a non-bindable owner
    (deliberate divergence from list_strategies_admin's no-filter — OTA-782).
  - disabled rules (enabled=0) are returned, not filtered out.
  - formula_registered is tri-state: None for a null formula_ref, True for a
    formula present in the live screening registry, False for an unregistered
    or malformed ref.
  - reflects current DB state (a directly-inserted row appears without restart).
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


# Rules spanning both bindable owners + a non-bindable owner (STK), covering the
# three formula_registered states and the disabled-row case.
#   - earnings_gate   : SHARED, enabled, no formula_ref          -> registered None
#   - theta_scoring   : OTA, enabled, formula:theta_margin_ratio -> registered True
#                       (theta_margin_ratio IS in the live screening registry)
#   - ghost_scoring   : OTA, DISABLED, formula:not_a_real_formula -> registered False
#   - malformed_rule  : OTA, enabled, formula_ref present but no 'formula:' prefix
#                       -> registered False (present but malformed)
#   - stk_only_rule   : STK (non-bindable) -> must NOT appear
_SEED = [
    {
        "owner_app_id": "SHARED",
        "rule_key": "earnings_gate",
        "phase": "gate",
        "tier": "RAW",
        "intent": "No entry within 7 days of earnings.",
        "condition_expression": "days_to_earnings > 7",
        "formula_ref": None,
        "enabled": True,
    },
    {
        "owner_app_id": "OTA",
        "rule_key": "theta_scoring",
        "phase": "scoring",
        "tier": None,
        "intent": "Reward theta margin.",
        "condition_expression": None,
        "formula_ref": "formula:theta_margin_ratio",
        "enabled": True,
    },
    {
        "owner_app_id": "OTA",
        "rule_key": "ghost_scoring",
        "phase": "scoring",
        "tier": None,
        "intent": "References a formula that is not registered.",
        "condition_expression": None,
        "formula_ref": "formula:not_a_real_formula",
        "enabled": False,
    },
    {
        "owner_app_id": "OTA",
        "rule_key": "malformed_rule",
        "phase": "scoring",
        "tier": None,
        "intent": "formula_ref missing the formula: prefix.",
        "condition_expression": None,
        "formula_ref": "theta_margin_ratio",
        "enabled": True,
    },
    {
        "owner_app_id": "STK",
        "rule_key": "stk_only_rule",
        "phase": "gate",
        "tier": "RAW",
        "intent": "Belongs to a non-bindable owner; excluded from OTA's catalog.",
        "condition_expression": "x > 0",
        "formula_ref": None,
        "enabled": True,
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
                {"app_id": "STK", "name": "Stock Analyzer"},
            ],
        )
        await conn.execute(insert(store.engine_rules), _SEED)
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
async def test_rules_admin_spans_bindable_owners_only(client):
    r = await client.get("/api/v1/config/rules/admin")
    assert r.status_code == 200
    rows = r.json()
    by_key = {row["rule_key"]: row for row in rows}

    # OTA + SHARED returned; the STK (non-bindable) row is excluded.
    assert {row["owner_app_id"] for row in rows} == {"OTA", "SHARED"}
    assert "stk_only_rule" not in by_key
    assert by_key["earnings_gate"]["owner_app_id"] == "SHARED"


@pytest.mark.asyncio
async def test_rules_admin_includes_disabled_rows(client):
    rows = (await client.get("/api/v1/config/rules/admin")).json()
    by_key = {row["rule_key"]: row for row in rows}
    # ghost_scoring is enabled=0 and must still appear (no enabled filter).
    assert by_key["ghost_scoring"]["enabled"] is False


@pytest.mark.asyncio
async def test_rules_admin_formula_registered_tristate(client):
    rows = (await client.get("/api/v1/config/rules/admin")).json()
    by_key = {row["rule_key"]: row for row in rows}

    # None: no formula_ref at all.
    assert by_key["earnings_gate"]["formula_registered"] is None
    # True: formula present in the live screening registry.
    assert by_key["theta_scoring"]["formula_registered"] is True
    # False: present but unregistered name.
    assert by_key["ghost_scoring"]["formula_registered"] is False
    # False: present but malformed (no 'formula:' prefix).
    assert by_key["malformed_rule"]["formula_registered"] is False


@pytest.mark.asyncio
async def test_rules_admin_reflects_current_db_state(client):
    first = (await client.get("/api/v1/config/rules/admin")).json()
    assert "fresh_rule" not in {row["rule_key"] for row in first}

    async with _test_session_factory() as session:
        await session.execute(
            insert(store.engine_rules),
            [
                {
                    "owner_app_id": "OTA",
                    "rule_key": "fresh_rule",
                    "phase": "gate",
                    "tier": "RAW",
                    "formula_ref": None,
                    "enabled": True,
                }
            ],
        )
        await session.commit()

    second = (await client.get("/api/v1/config/rules/admin")).json()
    assert "fresh_rule" in {row["rule_key"] for row in second}


@pytest.mark.asyncio
async def test_rules_admin_requires_auth():
    app = _build_unauth_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/config/rules/admin")
    assert r.status_code == 401
