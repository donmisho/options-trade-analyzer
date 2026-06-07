"""
OTA-792 — config change audit trail.

Exercises the audit recording + query surface through ``engine_config_routes`` /
``engine_config_store`` against in-memory SQLite (repo no-Azure-SQL convention),
mirroring ``test_engine_config_apply``. The real save-time validation path runs
(``_commit_with_validation`` → ``validate_pending``), so the recorded
``loadable_version`` is a real loadable-set hash and the audit row is staged in
the change's own transaction.

Coverage (verification steps, ticket §Verification):
  - a CRUD write records actor / timestamp / before-after, with the right
    entity_type / operation / target_stage;
  - a draft junction edit is tagged ``draft``; a live change is tagged ``live``
    and carries a loadable_version;
  - Apply emits exactly ONE ``apply`` row (not a per-junction replay) tagged
    ``live`` with the new stamp;
  - the trail is queryable per strategy and by id; isolation is by owning app,
    not actor (no user filter, no cross-user 404);
  - a validation-rejected write (422) leaves NO audit row (atomic rollback).
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


def _user_dep(sub: str = "u1", username: str = "dev"):
    async def _dep():
        return {"sub": sub, "username": username, "role": "admin", "mfa": True}

    return _dep


def _build_app(sub: str = "u1", username: str = "dev") -> FastAPI:
    from app.auth.dependencies import get_current_user, require_read, require_write
    from app.models.session import get_db

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    dep = _user_dep(sub, username)
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
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Seed bodies (mirror test_engine_config_apply) ──────────────────────────

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


async def _audit(client, **params) -> list[dict]:
    r = await client.get("/api/v1/config/audit", params=params)
    assert r.status_code == 200
    return r.json()


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_create_records_actor_timestamp_after_and_stamp(client):
    r = await client.post("/api/v1/config/strategies", json=_STRATEGY)
    assert r.status_code == 201

    rows = await _audit(client, entity_type="strategy")
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_type"] == "strategy"
    assert row["operation"] == "create"
    assert row["target_stage"] == "live"
    assert row["strategy_key"] == "steady_paycheck"
    # actor + timestamp
    assert row["user_id"] == "u1"
    assert row["actor_label"] == "dev"
    assert row["occurred_at"]  # non-empty ISO timestamp
    # before/after of the changed fields
    assert row["before_json"] is None  # create has no before
    assert row["after_json"]["display_name"] == "Steady Paycheck"
    # version stamp the change produces (loadable-set hash)
    assert isinstance(row["loadable_version"], str) and row["loadable_version"]


@pytest.mark.asyncio
async def test_update_records_before_and_after(client):
    await _seed(client)
    body = {k: v for k, v in _STRATEGY.items() if k != "strategy_key"}
    body["display_name"] = "Renamed"
    assert (
        await client.put("/api/v1/config/strategies/steady_paycheck", json=body)
    ).status_code == 200

    rows = await _audit(client, entity_type="strategy", strategy_key="steady_paycheck")
    upd = next(r for r in rows if r["operation"] == "update")
    assert upd["before_json"]["display_name"] == "Steady Paycheck"
    assert upd["after_json"]["display_name"] == "Renamed"
    assert upd["target_stage"] == "live"


@pytest.mark.asyncio
async def test_draft_junction_edit_tagged_draft(client):
    await _seed(client)
    assert (
        await client.post("/api/v1/config/strategies/steady_paycheck/draft")
    ).status_code == 201
    # Edit the DRAFT's junction — this is a save-to-draft write.
    assert (
        await client.put(
            "/api/v1/config/junction/steady_paycheck__draft/delta_band",
            json={"evaluation_order": 1, "stop_if_fail": True, "parameters": {"threshold": 0.9}},
        )
    ).status_code == 200

    rows = await _audit(client, strategy_key="steady_paycheck__draft")
    edit = next(r for r in rows if r["entity_type"] == "junction" and r["operation"] == "update")
    assert edit["target_stage"] == "draft"
    assert edit["rule_key"] == "delta_band"
    assert edit["before_json"]["parameters"] == {"threshold": 0.2}
    assert edit["after_json"]["parameters"] == {"threshold": 0.9}
    # Taking the draft (scaffolding) is NOT audited — no draft strategy-create row.
    assert not [r for r in rows if r["entity_type"] == "strategy"]


@pytest.mark.asyncio
async def test_apply_emits_single_live_row_with_stamp(client):
    await _seed(client)
    assert (
        await client.post("/api/v1/config/strategies/steady_paycheck/draft")
    ).status_code == 201
    assert (
        await client.put(
            "/api/v1/config/junction/steady_paycheck__draft/delta_band",
            json={"evaluation_order": 1, "stop_if_fail": True, "parameters": {"threshold": 0.9}},
        )
    ).status_code == 200

    assert (
        await client.post("/api/v1/config/strategies/steady_paycheck/apply")
    ).status_code == 200

    # Exactly ONE apply row, tagged live, carrying a stamp — NOT a per-junction
    # replay (the junction edits were audited at draft-write time).
    apply_rows = await _audit(client, entity_type="strategy")
    applies = [r for r in apply_rows if r["operation"] == "apply"]
    assert len(applies) == 1
    ap = applies[0]
    assert ap["target_stage"] == "live"
    assert ap["strategy_key"] == "steady_paycheck"
    assert isinstance(ap["loadable_version"], str) and ap["loadable_version"]
    # No live-tagged junction rows were minted by the promotion itself.
    live_junction_writes = [
        r
        for r in await _audit(client, entity_type="junction")
        if r["target_stage"] == "live" and r["strategy_key"] == "steady_paycheck"
    ]
    # only the original seed junction create on live (1), nothing from Apply
    assert len(live_junction_writes) == 1
    assert live_junction_writes[0]["operation"] == "create"


@pytest.mark.asyncio
async def test_query_trail_per_strategy_and_by_id(client):
    await _seed(client)
    per = await client.get("/api/v1/config/audit/strategies/steady_paycheck")
    assert per.status_code == 200
    assert per.json()  # strategy create + its junction create
    first_id = per.json()[0]["audit_id"]

    one = await client.get(f"/api/v1/config/audit/{first_id}")
    assert one.status_code == 200
    assert one.json()["audit_id"] == first_id

    assert (await client.get("/api/v1/config/audit/999999")).status_code == 404


@pytest.mark.asyncio
async def test_trail_is_shared_not_actor_filtered(client):
    # u1 makes changes.
    await _seed(client)
    # A DIFFERENT admin (u2) reads the trail — sees u1's entries (app-scoped,
    # not actor-scoped). Decision: isolate by owner_app_id, not actor.
    transport = ASGITransport(app=_build_app(sub="u2", username="other"))
    async with AsyncClient(transport=transport, base_url="http://test") as c2:
        rows = (await c2.get("/api/v1/config/audit")).json()
    assert any(r["user_id"] == "u1" for r in rows)


@pytest.mark.asyncio
async def test_rejected_write_leaves_no_audit(client):
    await _seed(client)
    assert (
        await client.post("/api/v1/config/strategies/steady_paycheck/draft")
    ).status_code == 201
    # Bind a second gate at a DUPLICATE evaluation_order on the draft; the draft
    # is excluded from validation so this persists, but Apply onto live fails
    # §6.6 (EVAL_ORDER_DUPLICATE) and rolls back.
    assert (
        await client.post(
            "/api/v1/config/junction",
            json={
                "strategy_key": "steady_paycheck__draft",
                "rule_key": "iv_band",
                "evaluation_order": 1,
                "stop_if_fail": True,
                "parameters": {"threshold": 0.3},
            },
        )
    ).status_code == 201

    assert (
        await client.post("/api/v1/config/strategies/steady_paycheck/apply")
    ).status_code == 422

    # The rolled-back Apply staged its audit row in the same txn → discarded.
    assert not [r for r in await _audit(client, entity_type="strategy") if r["operation"] == "apply"]
