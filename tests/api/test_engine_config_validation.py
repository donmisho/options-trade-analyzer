"""
OTA-783 — save-time config validation reusing the OTA-699 engine-load checks.

Every write goes through ``engine_config_store`` → ``_commit_with_validation`` →
``engine_config_validation.validate_pending``, which runs the *same* OTA-698
loader + OTA-699 validator the engine runs at startup. A write that would prevent
a clean engine load is rejected (HTTP 422) carrying the loader/validator's own
structured error identity, and nothing is persisted.

Each of the six AC check classes has a tested rejection path:
  1. weight-sum → 1.0           (SCORING_WEIGHTS_NOT_UNITY)
  2. eval_order uniqueness      (EVAL_ORDER_DUPLICATE)
  3. formula:<name> membership  (FORMULA_MISSING_FROM_LIVE_REGISTRY)
  4. phase membership in domain (loader ValueError on unknown Phase)
  5. junction completeness      (JUNCTION_PARAM_MISSING)
  6. terminal_verdict membership(TERMINAL_VERDICT_UNKNOWN)

Plus: a valid save persists and round-trips; rejected saves leave the tables
unchanged. The formula registry is stubbed empty by tests/api/conftest.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import engine_config_store as store
from app.api.engine_config_routes import router as engine_config_router

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _get_db():
    async with _session_factory() as s:
        try:
            yield s
        finally:
            await s.close()


def _build_app() -> FastAPI:
    from app.auth.dependencies import get_current_user, require_read, require_write
    from app.models.session import get_db

    async def _user():
        return {"sub": "u1", "username": "dev", "role": "admin", "mfa": True}

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    app.dependency_overrides[require_read] = _user
    app.dependency_overrides[require_write] = _user
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _get_db
    return app


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with _engine.begin() as conn:
        await conn.run_sync(store._metadata.create_all)
        await conn.execute(
            insert(store.engine_apps),
            [{"app_id": "OTA", "name": "OTA"}, {"app_id": "SHARED", "name": "Shared"}],
        )
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(store._metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Builders ────────────────────────────────────────────────────────────────


def _strategy(key="sp", surface="SCREENING"):
    return {
        "strategy_key": key,
        "display_name": "Strategy",
        "consumer_surface": surface,
        "verdict_band_set": [
            {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
            {"verdict": "WAIT", "min_score": 50, "max_score": 69.99},
            {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
        ],
    }


def _gate_rule(key, **over):
    base = {
        "rule_key": key,
        "phase": "gate",
        "tier": "RAW",
        "condition_expression": ">=",
        "referenced_named_values": ["delta"],
        "parameter_schema": {"threshold": {"type": "number"}},
    }
    base.update(over)
    return base


async def _count(table) -> int:
    async with _session_factory() as s:
        return await s.scalar(select(func.count()).select_from(table))


def _codes(resp) -> set[str]:
    detail = resp.json()["detail"]
    return {e["code"] for e in detail["errors"]}


# ── Valid save ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_save_round_trips_and_persists(client):
    assert (await client.post("/api/v1/config/strategies", json=_strategy())).status_code == 201
    assert (await client.post("/api/v1/config/rules", json=_gate_rule("delta_band"))).status_code == 201
    r = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "delta_band", "evaluation_order": 1,
              "stop_if_fail": True, "parameters": {"threshold": 0.2}},
    )
    assert r.status_code == 201
    assert r.json()["parameters"] == {"threshold": 0.2}
    assert await _count(store.engine_junction) == 1


# ── 1. weight-sum ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weight_sum_not_unity_rejected(client):
    await client.post("/api/v1/config/strategies", json=_strategy())
    # scoring rule with no expression/formula — isolates the weight-sum check
    await client.post("/api/v1/config/rules",
                      json={"rule_key": "ev", "phase": "scoring", "tier": "COMPUTED"})
    r = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "ev", "evaluation_order": 1,
              "stop_if_fail": False, "weight": 0.5},  # 0.5 ≠ 1.0
    )
    assert r.status_code == 422
    assert "SCORING_WEIGHTS_NOT_UNITY" in _codes(r)
    assert await _count(store.engine_junction) == 0  # nothing persisted


# ── 2. evaluation_order uniqueness ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eval_order_duplicate_rejected(client):
    await client.post("/api/v1/config/strategies", json=_strategy())
    await client.post("/api/v1/config/rules", json=_gate_rule("gate_a"))
    await client.post("/api/v1/config/rules", json=_gate_rule("gate_b"))
    ok = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "gate_a", "evaluation_order": 1,
              "stop_if_fail": True, "parameters": {"threshold": 0.1}},
    )
    assert ok.status_code == 201
    dup = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "gate_b", "evaluation_order": 1,
              "stop_if_fail": True, "parameters": {"threshold": 0.2}},
    )
    assert dup.status_code == 422
    assert "EVAL_ORDER_DUPLICATE" in _codes(dup)
    assert await _count(store.engine_junction) == 1  # only gate_a persisted


# ── 3. formula:<name> registry membership ─────────────────────────────────────


@pytest.mark.asyncio
async def test_formula_not_in_registry_rejected(client):
    await client.post("/api/v1/config/strategies", json=_strategy())
    await client.post(
        "/api/v1/config/rules",
        json={"rule_key": "ghost_rule", "phase": "gate", "tier": "COMPUTED",
              "formula_ref": "formula:ghost"},
    )
    r = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "ghost_rule", "evaluation_order": 1,
              "stop_if_fail": True},
    )
    assert r.status_code == 422
    assert "FORMULA_MISSING_FROM_LIVE_REGISTRY" in _codes(r)
    assert await _count(store.engine_junction) == 0


# ── 4. phase membership in the engine_lookups domain (loader rejects) ──────────


@pytest.mark.asyncio
async def test_unknown_phase_rejected(client):
    r = await client.post(
        "/api/v1/config/rules",
        json={"rule_key": "weird", "phase": "bogus_phase", "condition_expression": ">="},
    )
    assert r.status_code == 422
    # loader-path identity: Phase enum rejects the unknown phase
    detail = r.json()["detail"]
    assert any("Phase" in e["message"] for e in detail["errors"])
    assert await _count(store.engine_rules) == 0


# ── 5. junction completeness (missing schema parameter) ───────────────────────


@pytest.mark.asyncio
async def test_junction_missing_param_rejected(client):
    await client.post("/api/v1/config/strategies", json=_strategy())
    await client.post("/api/v1/config/rules", json=_gate_rule("delta_band"))
    r = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "delta_band", "evaluation_order": 1,
              "stop_if_fail": True},  # threshold not supplied
    )
    assert r.status_code == 422
    assert "JUNCTION_PARAM_MISSING" in _codes(r)
    assert await _count(store.engine_junction) == 0


# ── 6. terminal_verdict membership in the strategy's verdict domain ────────────


@pytest.mark.asyncio
async def test_terminal_verdict_unknown_rejected(client):
    await client.post("/api/v1/config/strategies", json=_strategy())
    await client.post("/api/v1/config/rules", json=_gate_rule("delta_band"))
    r = await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "delta_band", "evaluation_order": 1,
              "stop_if_fail": True, "parameters": {"threshold": 0.2},
              "terminal_verdict": "BOGUS_VERDICT"},
    )
    assert r.status_code == 422
    assert "TERMINAL_VERDICT_UNKNOWN" in _codes(r)
    assert await _count(store.engine_junction) == 0


# ── No-partial-write on a rejected UPDATE ─────────────────────────────────────


@pytest.mark.asyncio
async def test_rejected_update_leaves_prior_state(client):
    """A valid junction, then an update that breaks load, must roll back."""
    await client.post("/api/v1/config/strategies", json=_strategy())
    await client.post("/api/v1/config/rules", json=_gate_rule("delta_band"))
    await client.post(
        "/api/v1/config/junction",
        json={"strategy_key": "sp", "rule_key": "delta_band", "evaluation_order": 1,
              "stop_if_fail": True, "parameters": {"threshold": 0.2}},
    )
    # Update the junction to drop the required param → JUNCTION_PARAM_MISSING
    bad = await client.put(
        "/api/v1/config/junction/sp/delta_band",
        json={"evaluation_order": 1, "stop_if_fail": True, "parameters": {}},
    )
    assert bad.status_code == 422
    assert "JUNCTION_PARAM_MISSING" in _codes(bad)
    # Prior valid state is intact (param still present)
    async with _session_factory() as s:
        raw = await s.scalar(select(store.engine_junction.c.parameters))
    import json
    assert json.loads(raw) == {"threshold": 0.2}
