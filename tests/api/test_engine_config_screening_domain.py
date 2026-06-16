"""OTA-841 — contract guard: GET /api/v1/config/strategies emits the canonical
SCREENING value domain (hyphen strategy keys + lowercase compatible_structures).

The OTA-762 read endpoint is a pure pass-through of the hydrated engine config,
which the loader hydrates verbatim from the ``engine_*`` tables the seed writes.
So "the OTA-762 emitted domain" == "the seed-emitted domain". This test boots the
REAL seed (``build_all_rows`` over the workbook) the way ``init_engine_runtime``
does — ``load_config`` → ``set_engine_runtime`` — then exercises the actual HTTP
route and asserts the emitted SCREENING domain equals the system canonical domain
defined by ``strategy_definitions.STRATEGIES``. If the seed ever drifts back to
underscore keys or UPPERCASE structures, this fails in CI rather than at a build.

Scope is SCREENING-only by design: the endpoint filters to the SCREENING surface,
so the three DIRECTIONAL strategies (``directional_income`` …, intentionally
underscore — a separate surface with no canonical hyphen form) never surface here.
The guard asserts the screening domain specifically and asserts directional keys
are absent; it does NOT assert "all engine keys are hyphen".
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.analysis.strategy_definitions import STRATEGIES as CANONICAL_STRATEGIES
from app.insight_engine import InMemoryConfigSource, load_config
from app.ota_adapters.engine_runtime import (
    BronzeSqlSink,
    EngineRuntime,
    _reset_engine_runtime,
    set_engine_runtime,
)
from scripts.seed_engine_config import DEFAULT_XLSX, build_all_rows

pytestmark = pytest.mark.skipif(
    not DEFAULT_XLSX.exists(),
    reason=f"seed workbook not available at {DEFAULT_XLSX}",
)

# The canonical SCREENING domain — the single source the seed must agree with.
CANONICAL_SCREENING_KEYS = set(CANONICAL_STRATEGIES.keys())


def _build_rows():
    """Full seed row set with synthetic ids (DB IDENTITY stand-ins).

    Mirrors ``tests/insight_engine/test_full_seed_boot._build_rows``: junctions
    bind by ``strategy_id`` / ``rule_id`` FKs, so the synthetic ids must agree
    across the three tables.
    """
    rules, strategies, junctions, lookups, _ = build_all_rows(DEFAULT_XLSX)
    rule_id = {r["rule_key"]: 1000 + i for i, r in enumerate(rules)}
    strat_id = {s["strategy_key"]: 100 + i for i, s in enumerate(strategies)}
    rules = [{**r, "rule_id": rule_id[r["rule_key"]]} for r in rules]
    strategies = [{**s, "strategy_id": strat_id[s["strategy_key"]]} for s in strategies]
    junctions = [
        {**j, "rule_id": rule_id[j["rule_key"]], "strategy_id": strat_id[j["strategy_key"]]}
        for j in junctions
    ]
    return rules, strategies, junctions, lookups


def _hydrate_runtime() -> EngineRuntime:
    rules, strategies, junctions, lookups = _build_rows()
    source = InMemoryConfigSource(
        apps=[
            {"app_id": "SHARED", "name": "Shared", "enabled": True},
            {"app_id": "OTA", "name": "OTA", "enabled": True},
        ],
        rules=rules,
        strategies=strategies,
        junction=junctions,
        lookups=lookups,
    )
    config = load_config(source)
    return EngineRuntime(
        config=config,
        sink=BronzeSqlSink(session_factory=None, loop=asyncio.new_event_loop()),
        source=source,
        config_version=config.config_version,
        loadable_version=config.loadable_version,
    )


def _build_authed_app() -> FastAPI:
    from app.api.engine_config_routes import router as engine_config_router
    from app.auth.dependencies import require_read

    async def _read_user():
        return {"sub": "u1", "username": "dev", "role": "admin", "mfa": True}

    app = FastAPI()
    app.include_router(engine_config_router, prefix="/api/v1")
    app.dependency_overrides[require_read] = _read_user
    return app


@pytest_asyncio.fixture
async def client():
    set_engine_runtime(_hydrate_runtime())
    app = _build_authed_app()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        _reset_engine_runtime()


@pytest.mark.asyncio
async def test_screening_keys_are_canonical_hyphen_domain(client):
    """Every emitted SCREENING strategy_key is the canonical hyphen form, and the
    set equals strategy_definitions.STRATEGIES exactly (the cross-check)."""
    r = await client.get("/api/v1/config/strategies")
    assert r.status_code == 200
    rows = r.json()
    assert rows, "expected the four SCREENING strategies"

    returned_keys = {row["strategy_key"] for row in rows}
    for key in returned_keys:
        assert "_" not in key, f"OTA-841: strategy_key {key!r} is not hyphen-canonical"
        assert key in CANONICAL_SCREENING_KEYS, (
            f"OTA-841: strategy_key {key!r} not in strategy_definitions.STRATEGIES "
            f"{sorted(CANONICAL_SCREENING_KEYS)}"
        )
    # Endpoint is SCREENING-only → it emits exactly the canonical screening set.
    assert returned_keys == CANONICAL_SCREENING_KEYS


@pytest.mark.asyncio
async def test_compatible_structures_are_lowercase(client):
    """compatible_structures emit the canonical lowercase domain, never UPPERCASE."""
    r = await client.get("/api/v1/config/strategies")
    assert r.status_code == 200
    for row in r.json():
        for struct in row.get("compatible_structures") or []:
            assert struct == struct.lower(), (
                f"OTA-841: compatible_structure {struct!r} for "
                f"{row['strategy_key']!r} is not lowercase"
            )


@pytest.mark.asyncio
async def test_directional_keys_never_surface_on_screening_endpoint(client):
    """DIRECTIONAL strategies keep underscore keys and a separate surface; the
    SCREENING-only OTA-762 endpoint must not surface them (scope boundary)."""
    r = await client.get("/api/v1/config/strategies")
    assert r.status_code == 200
    assert not any(
        row["strategy_key"].startswith("directional") for row in r.json()
    )
