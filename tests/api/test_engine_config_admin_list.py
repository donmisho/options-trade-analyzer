"""
OTA-823 — owner-scoped admin strategy list endpoint.

Exercises ``GET /api/v1/config/strategies/admin`` end-to-end through
``app/api/engine_config_store.list_strategies_admin`` against an in-memory
SQLite DB (the repo's no-Azure-SQL test convention). The store uses SQLAlchemy
Core with a separate MetaData, so the same code path runs on SQLite here and
Azure SQL in prod.

Coverage:
  - returns every strategy across ALL owners (OTA + SHARED) and ALL surfaces,
    each tagged by owner_app_id, carrying enabled + status + header/band fields.
  - SHARED rows are returned, never filtered out.
  - reflects current DB state — a row inserted directly appears without any
    "restart" (proves it is not the OTA-762 hydrated projection).
  - JSON columns (verdict_band_set, compatible_structures) round-trip as objects.
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
    """App where get_current_user rejects, leaving require_read real so the
    endpoint's auth dependency chain produces the 401."""
    from app.auth.dependencies import get_current_user
    from app.models.session import get_db

    async def _reject():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = _reject
    app.dependency_overrides[get_db] = _get_test_db
    return app


# Three strategies spanning both owners and three surfaces, with the
# active/enabled and inactive/disabled invariant pairings.
_SEED = [
    {
        "owner_app_id": "OTA",
        "strategy_key": "steady_paycheck",
        "display_name": "Steady Paycheck",
        "consumer_surface": "SCREENING",
        "compatible_structures": json.dumps(["BULL_PUT_CREDIT"]),
        "verdict_band_set": json.dumps(
            [{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}]
        ),
        "dte_min": 30,
        "dte_max": 45,
        "status": "active",
        "enabled": True,
    },
    {
        "owner_app_id": "SHARED",
        "strategy_key": "position_health_full",
        "display_name": "Position Health (Full)",
        "consumer_surface": "POSITION_HEALTH",
        "compatible_structures": None,
        "verdict_band_set": json.dumps(
            [{"verdict": "A", "min_score": 90, "max_score": 100}]
        ),
        "dte_min": None,
        "dte_max": None,
        "status": "active",
        "enabled": True,
    },
    {
        "owner_app_id": "OTA",
        "strategy_key": "trend_rider",
        "display_name": "Trend Rider",
        "consumer_surface": "DIRECTIONAL",
        "compatible_structures": None,
        "verdict_band_set": json.dumps(
            [{"verdict": "WAIT", "min_score": 50, "max_score": 69}]
        ),
        "dte_min": None,
        "dte_max": None,
        "status": "inactive",
        "enabled": False,
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
        await conn.execute(insert(store.engine_strategies), _SEED)
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
async def test_admin_list_spans_owners_and_surfaces(client):
    r = await client.get("/api/v1/config/strategies/admin")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3

    by_key = {row["strategy_key"]: row for row in rows}
    # all three surfaces present — not SCREENING-only like OTA-762
    assert {row["consumer_surface"] for row in rows} == {
        "SCREENING",
        "POSITION_HEALTH",
        "DIRECTIONAL",
    }
    # both owners returned; SHARED not filtered out
    assert {row["owner_app_id"] for row in rows} == {"OTA", "SHARED"}
    assert by_key["position_health_full"]["owner_app_id"] == "SHARED"

    # enabled + status both surfaced, with the invariant pairing intact
    active = by_key["steady_paycheck"]
    assert active["enabled"] is True and active["status"] == "active"
    inactive = by_key["trend_rider"]
    assert inactive["enabled"] is False and inactive["status"] == "inactive"

    # JSON columns round-trip as objects, not escaped strings
    assert active["compatible_structures"] == ["BULL_PUT_CREDIT"]
    assert active["verdict_band_set"][0]["verdict"] == "EXECUTE"
    assert by_key["position_health_full"]["compatible_structures"] is None


@pytest.mark.asyncio
async def test_admin_list_reflects_current_db_state(client):
    """A row inserted after the first read appears on the next read — current
    DB state, not a restart-gated projection."""
    first = await client.get("/api/v1/config/strategies/admin")
    assert len(first.json()) == 3

    async with _test_session_factory() as session:
        await session.execute(
            insert(store.engine_strategies),
            [
                {
                    "owner_app_id": "OTA",
                    "strategy_key": "weekly_grind",
                    "display_name": "Weekly Grind",
                    "consumer_surface": "SCREENING",
                    "compatible_structures": None,
                    "verdict_band_set": json.dumps(
                        [{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}]
                    ),
                    "status": "draft",
                    "enabled": False,
                }
            ],
        )
        await session.commit()

    second = await client.get("/api/v1/config/strategies/admin")
    keys = {row["strategy_key"] for row in second.json()}
    assert "weekly_grind" in keys
    draft = next(r for r in second.json() if r["strategy_key"] == "weekly_grind")
    assert draft["status"] == "draft" and draft["enabled"] is False


@pytest.mark.asyncio
async def test_admin_list_requires_auth():
    app = _build_unauth_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/config/strategies/admin")
    assert r.status_code == 401
