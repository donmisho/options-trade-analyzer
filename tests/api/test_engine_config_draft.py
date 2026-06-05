"""
OTA-791 — draft strategy substrate (create-on-edit, resume, refresh, discard).

Exercises ``app/api/engine_config_routes.py`` draft endpoints end-to-end through
``app/api/engine_config_store.py`` against in-memory SQLite (the repo's
no-Azure-SQL test convention), mirroring ``test_engine_config_write.py``.

Coverage (QA high — the draft lifecycle is the operationally risky bit):
  - create clones the live header + junctions onto ``<key>__draft`` (status=draft,
    enabled=0); the live row is untouched.
  - resume returns the existing draft and never silently re-clones (decision B).
  - refresh discards + re-clones fresh from live.
  - discard removes the draft (404 when none exists).
  - a draft key cannot itself be drafted (422); a missing live strategy → 404.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, insert, select
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


# ── Seed bodies (same loadable shapes proven by test_engine_config_write) ──

_STRATEGY = {
    "strategy_key": "steady_paycheck",
    "display_name": "Steady Paycheck",
    "consumer_surface": "SCREENING",
    "compatible_structures": ["bull_put_credit"],
    "verdict_band_set": [{"verdict": "EXECUTE", "min_score": 70, "max_score": 100}],
    "dte_min": 30,
    "dte_max": 45,
}

# A GATE rule — excluded from the scoring-weight-sum check, so a single binding
# leaves the config loadable without needing weights to sum to 1.0.
_RULE = {
    "rule_key": "delta_band",
    "phase": "gate",
    "tier": "RAW",
    "intent": "Delta at or above floor",
    "condition_expression": ">=",
    "referenced_named_values": ["delta"],
    "parameter_schema": {"threshold": {"type": "number"}},
}

_JUNCTION = {
    "strategy_key": "steady_paycheck",
    "rule_key": "delta_band",
    "evaluation_order": 1,
    "stop_if_fail": True,
    "score_penalty": -10.0,
    "parameters": {"threshold": 0.2},
    "rationale": "core gate",
}


async def _seed(client):
    assert (await client.post("/api/v1/config/strategies", json=_STRATEGY)).status_code == 201
    assert (await client.post("/api/v1/config/rules", json=_RULE)).status_code == 201
    assert (await client.post("/api/v1/config/junction", json=_JUNCTION)).status_code == 201


async def _draft_junction_rows() -> list[dict]:
    async with _test_session_factory() as s:
        draft = (
            await s.execute(
                select(store.engine_strategies).where(
                    store.engine_strategies.c.strategy_key == "steady_paycheck__draft"
                )
            )
        ).mappings().first()
        if draft is None:
            return []
        rows = (
            await s.execute(
                select(store.engine_junction).where(
                    store.engine_junction.c.strategy_id == draft["strategy_id"]
                )
            )
        ).mappings().all()
        return [dict(r) for r in rows]


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_draft_clones_header_and_junctions(client):
    await _seed(client)

    r = await client.post("/api/v1/config/strategies/steady_paycheck/draft")
    assert r.status_code == 201
    draft = r.json()
    assert draft["strategy_key"] == "steady_paycheck__draft"
    assert draft["status"] == "draft"
    assert draft["enabled"] is False
    # Header cloned verbatim from live
    assert draft["display_name"] == "Steady Paycheck"
    assert draft["compatible_structures"] == ["bull_put_credit"]
    assert draft["dte_min"] == 30 and draft["dte_max"] == 45

    # Junctions cloned (repointed to the draft strategy_id), params verbatim
    jrows = await _draft_junction_rows()
    assert len(jrows) == 1
    assert json.loads(jrows[0]["parameters"]) == {"threshold": 0.2}
    assert jrows[0]["evaluation_order"] == 1
    assert bool(jrows[0]["stop_if_fail"]) is True

    # Live row is untouched (still active/enabled)
    live = await client.get("/api/v1/config/strategies/admin")
    live_row = next(x for x in live.json() if x["strategy_key"] == "steady_paycheck")
    assert live_row["status"] == "active"
    assert live_row["enabled"] is True


@pytest.mark.asyncio
async def test_resume_does_not_overwrite(client):
    await _seed(client)
    assert (await client.post("/api/v1/config/strategies/steady_paycheck/draft")).status_code == 201

    # Change the LIVE strategy after the draft was taken.
    put = await client.put(
        "/api/v1/config/strategies/steady_paycheck",
        json={**{k: v for k, v in _STRATEGY.items() if k != "strategy_key"},
              "display_name": "LIVE CHANGED"},
    )
    assert put.status_code == 200

    # Re-POST draft → RESUME the existing draft (200, not 201) — no re-clone.
    r = await client.post("/api/v1/config/strategies/steady_paycheck/draft")
    assert r.status_code == 201  # endpoint status_code is fixed; body proves resume
    assert r.json()["display_name"] == "Steady Paycheck"  # original, NOT "LIVE CHANGED"


@pytest.mark.asyncio
async def test_refresh_reclones_from_live(client):
    await _seed(client)
    assert (await client.post("/api/v1/config/strategies/steady_paycheck/draft")).status_code == 201

    put = await client.put(
        "/api/v1/config/strategies/steady_paycheck",
        json={**{k: v for k, v in _STRATEGY.items() if k != "strategy_key"},
              "display_name": "LIVE V2"},
    )
    assert put.status_code == 200

    r = await client.post("/api/v1/config/strategies/steady_paycheck/draft/refresh")
    assert r.status_code == 200
    assert r.json()["display_name"] == "LIVE V2"  # re-cloned from live
    # Junctions still present after the discard+re-clone
    assert len(await _draft_junction_rows()) == 1


@pytest.mark.asyncio
async def test_discard_draft(client):
    await _seed(client)
    assert (await client.post("/api/v1/config/strategies/steady_paycheck/draft")).status_code == 201

    r = await client.delete("/api/v1/config/strategies/steady_paycheck/draft")
    assert r.status_code == 200
    assert r.json()["strategy_key"] == "steady_paycheck__draft"

    # Draft gone — its junctions too; second discard 404s.
    assert await _draft_junction_rows() == []
    assert (await client.delete("/api/v1/config/strategies/steady_paycheck/draft")).status_code == 404

    # Live strategy survives the draft discard.
    live = await client.get("/api/v1/config/strategies/admin")
    assert any(x["strategy_key"] == "steady_paycheck" for x in live.json())


@pytest.mark.asyncio
async def test_cannot_draft_a_draft(client):
    await _seed(client)
    r = await client.post("/api/v1/config/strategies/steady_paycheck__draft/draft")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_draft_of_missing_strategy_404(client):
    r = await client.post("/api/v1/config/strategies/nope/draft")
    assert r.status_code == 404
