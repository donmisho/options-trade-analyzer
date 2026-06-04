"""
OTA-824 — wire status through the as-built engine_strategies CRUD.

Exercises the OTA-782 strategy CRUD (``app/api/engine_config_routes.py`` →
``app/api/engine_config_store.py``) now that it reads/writes the OTA-822
``status`` column, against in-memory SQLite (the repo's no-Azure-SQL convention).

Invariant under test (OTA-824 §3): status is the input of record; ``enabled`` is
derived from it. ``active`` ⇔ enabled=1; ``inactive``/``deprecated``/``draft`` ⇒
enabled=0. Invalid status → 4xx; omitted on create → ``active``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import engine_config_store as store
from app.api.engine_config_routes import router as engine_config_router

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
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(store._metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    app = _build_authed_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _strategy(**overrides) -> dict:
    body = {
        "strategy_key": "steady_paycheck",
        "display_name": "Steady Paycheck",
        "consumer_surface": "SCREENING",
        "compatible_structures": ["BULL_PUT_CREDIT"],
        "verdict_band_set": [{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}],
        "dte_min": 30,
        "dte_max": 45,
    }
    body.update(overrides)
    return body


# ── Verification steps 1–4 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_inactive_persists_and_disables(client):
    r = await client.post("/api/v1/config/strategies", json=_strategy(status="inactive"))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "inactive"
    assert body["enabled"] is False  # derived from status


@pytest.mark.asyncio
async def test_put_active_enables(client):
    assert (
        await client.post("/api/v1/config/strategies", json=_strategy(status="inactive"))
    ).status_code == 201

    upd = {k: v for k, v in _strategy(status="active").items() if k != "strategy_key"}
    r = await client.put("/api/v1/config/strategies/steady_paycheck", json=upd)
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert r.json()["enabled"] is True


@pytest.mark.asyncio
async def test_post_without_status_defaults_active(client):
    r = await client.post("/api/v1/config/strategies", json=_strategy())
    assert r.status_code == 201
    assert r.json()["status"] == "active"
    assert r.json()["enabled"] is True


@pytest.mark.asyncio
async def test_post_invalid_status_rejected(client):
    r = await client.post("/api/v1/config/strategies", json=_strategy(status="bogus"))
    assert r.status_code == 422  # 4xx domain rejection, not a 500


@pytest.mark.parametrize(
    "status_value, expected_enabled",
    [("active", True), ("inactive", False), ("deprecated", False), ("draft", False)],
)
@pytest.mark.asyncio
async def test_invariant_across_domain(client, status_value, expected_enabled):
    r = await client.post(
        "/api/v1/config/strategies", json=_strategy(status=status_value)
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == status_value
    assert body["enabled"] is expected_enabled
