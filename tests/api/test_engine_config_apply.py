"""
OTA-790 — Apply (junction-only promote) + GET /config/status wiring.

Exercises ``POST /config/strategies/{key}/apply`` and ``GET /config/status``
through ``engine_config_routes`` / ``engine_config_store`` against in-memory
SQLite (repo no-Azure-SQL convention), mirroring ``test_engine_config_draft``.

Coverage:
  - Apply promotes the draft's junctions onto live and deletes the draft; the
    live HEADER is untouched (header edits are live-direct, OTA-827).
  - Apply of a draft that would make live invalid (duplicate gate eval_order) is
    blocked by §6.6 validation → 422, the transaction rolls back (live junctions
    unchanged), and the draft survives.
  - Apply with no draft → 404.
  - GET /config/status maps the loadable-version comparison to restart_pending.
"""

from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import engine_config_routes
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


def _build_app() -> FastAPI:
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
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Seed bodies ────────────────────────────────────────────────────────────

_STRATEGY = {
    "strategy_key": "steady_paycheck",
    "display_name": "Steady Paycheck",
    "consumer_surface": "SCREENING",
    "compatible_structures": ["bull_put_credit"],
    "verdict_band_set": [{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}],
    "dte_min": 30,
    "dte_max": 45,
}

_RULE = {
    "rule_key": "delta_band",
    "phase": "gate",
    "tier": "RAW",
    "intent": "Delta at or above floor",
    "condition_expression": ">=",
    "referenced_named_values": ["delta"],
    "parameter_schema": {"threshold": {"type": "number"}},
}

# A second gate rule used to stage an invalid (duplicate eval_order) draft.
_RULE2 = {
    "rule_key": "iv_band",
    "phase": "gate",
    "tier": "RAW",
    "intent": "IV at or above floor",
    "condition_expression": ">=",
    "referenced_named_values": ["iv_rank"],
    "parameter_schema": {"threshold": {"type": "number"}},
}

_JUNCTION = {
    "strategy_key": "steady_paycheck",
    "rule_key": "delta_band",
    "evaluation_order": 1,
    "stop_if_fail": True,
    "parameters": {"threshold": 0.2},
    "rationale": "core gate",
}


async def _seed(client):
    assert (await client.post("/api/v1/config/strategies", json=_STRATEGY)).status_code == 201
    assert (await client.post("/api/v1/config/rules", json=_RULE)).status_code == 201
    assert (await client.post("/api/v1/config/rules", json=_RULE2)).status_code == 201
    assert (await client.post("/api/v1/config/junction", json=_JUNCTION)).status_code == 201


async def _live_junctions(client) -> list[dict]:
    r = await client.get("/api/v1/config/strategies/steady_paycheck/junctions")
    assert r.status_code == 200
    return r.json()


def _admin_keys(admin_json) -> set[str]:
    return {row["strategy_key"] for row in admin_json}


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_promotes_junctions_and_leaves_header(client):
    await _seed(client)
    assert (await client.post("/api/v1/config/strategies/steady_paycheck/draft")).status_code == 201

    # Edit the LIVE header AFTER the draft is taken (live-direct, OTA-827).
    assert (
        await client.put(
            "/api/v1/config/strategies/steady_paycheck",
            json={
                **{k: v for k, v in _STRATEGY.items() if k != "strategy_key"},
                "display_name": "LIVE HEADER EDIT",
            },
        )
    ).status_code == 200

    # Edit the DRAFT's junction parameter.
    assert (
        await client.put(
            "/api/v1/config/junction/steady_paycheck__draft/delta_band",
            json={"evaluation_order": 1, "stop_if_fail": True, "parameters": {"threshold": 0.9}},
        )
    ).status_code == 200

    # Apply.
    r = await client.post("/api/v1/config/strategies/steady_paycheck/apply")
    assert r.status_code == 200

    # Junction promoted to live.
    live_js = await _live_junctions(client)
    assert len(live_js) == 1
    assert live_js[0]["parameters"] == {"threshold": 0.9}

    # Draft consumed.
    admin = await client.get("/api/v1/config/strategies/admin")
    assert "steady_paycheck__draft" not in _admin_keys(admin.json())

    # Live HEADER untouched by Apply — the live-direct edit survives, NOT reverted
    # to the draft's clone-time "Steady Paycheck".
    live_row = next(x for x in admin.json() if x["strategy_key"] == "steady_paycheck")
    assert live_row["display_name"] == "LIVE HEADER EDIT"
    assert live_row["status"] == "active" and live_row["enabled"] is True


@pytest.mark.asyncio
async def test_apply_invalid_draft_rolls_back(client):
    await _seed(client)
    assert (await client.post("/api/v1/config/strategies/steady_paycheck/draft")).status_code == 201

    # Bind a SECOND gate to the draft at the SAME evaluation_order as the first.
    # The draft is disabled, so save-time validation (which excludes drafts) lets
    # it persist — the collision only bites when promoted onto the live strategy.
    assert (
        await client.post(
            "/api/v1/config/junction",
            json={
                "strategy_key": "steady_paycheck__draft",
                "rule_key": "iv_band",
                "evaluation_order": 1,  # duplicate gate eval_order
                "stop_if_fail": True,
                "parameters": {"threshold": 0.3},
            },
        )
    ).status_code == 201

    # Apply must fail §6.6 (EVAL_ORDER_DUPLICATE) and roll back.
    r = await client.post("/api/v1/config/strategies/steady_paycheck/apply")
    assert r.status_code == 422

    # Live junctions unchanged (still the single original gate).
    live_js = await _live_junctions(client)
    assert len(live_js) == 1
    assert live_js[0]["rule_key"] == "delta_band"

    # The draft survives the rolled-back apply (still has its two gates).
    admin = await client.get("/api/v1/config/strategies/admin")
    assert "steady_paycheck__draft" in _admin_keys(admin.json())


@pytest.mark.asyncio
async def test_apply_without_draft_404(client):
    await _seed(client)
    r = await client.post("/api/v1/config/strategies/steady_paycheck/apply")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_status_reports_restart_pending(client, monkeypatch):
    # Wire the loadable-version comparison: running != persisted ⇒ restart_pending.
    monkeypatch.setattr(
        engine_config_routes,
        "get_engine_runtime",
        lambda: types.SimpleNamespace(loadable_version="RUNNING"),
    )

    async def _fake_persisted(_factory, **_kw):
        return "PERSISTED"

    monkeypatch.setattr(
        engine_config_routes, "compute_persisted_loadable_version", _fake_persisted
    )

    r = await client.get("/api/v1/config/status")
    assert r.status_code == 200
    body = r.json()
    assert body["running_config_version"] == "RUNNING"
    assert body["persisted_config_version"] == "PERSISTED"
    assert body["restart_pending"] is True


@pytest.mark.asyncio
async def test_status_no_restart_when_versions_match(client, monkeypatch):
    monkeypatch.setattr(
        engine_config_routes,
        "get_engine_runtime",
        lambda: types.SimpleNamespace(loadable_version="SAME"),
    )

    async def _fake_persisted(_factory, **_kw):
        return "SAME"

    monkeypatch.setattr(
        engine_config_routes, "compute_persisted_loadable_version", _fake_persisted
    )

    r = await client.get("/api/v1/config/status")
    assert r.status_code == 200
    assert r.json()["restart_pending"] is False
