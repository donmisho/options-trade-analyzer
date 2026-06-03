"""
Engine config read API (OTA-762).

Exposes the hydrated, validated engine configuration over HTTP for frontend
consumers (OTA-660 score-color thresholds, OTA-821 dual-source removal).

The READ path is sourced from the in-process accessor
``get_engine_runtime().config`` (OTA-818 keystone): ``get_engine_strategies``
NEVER opens a connection to the ``engine_*`` tables — ``AzureSqlConfigSource``
remains the only reader on the **runtime / engine-load** path.

OTA-782 adds the config WRITE side to this module (below). The write transport
reads and writes the ``engine_*`` tables directly (via
``app.api.engine_config_store``) to maintain configuration; that is the durable
maintenance surface and is distinct from the engine-load read path above. A
write does not refresh the hydrated runtime config — engine pickup is restart-
gated (``insight_engine.md`` §6.5).

Two-source serialization (Relevant Context §2):
  - Strategy-level fields come from ``config.strategies[key]`` (a ``Strategy``).
  - Per-criterion scoring weights are NOT on ``Strategy``; they live on the
    scoring-phase junction bindings: walk ``config.rule_sets[key].bindings[]``
    and read ``binding.junction.weight`` for bindings whose rule is in the
    SCORING phase.

This is a NEW router sharing the ``/config`` prefix with the per-user settings
router in ``config_routes.py`` (FastAPI permits two routers on one prefix).
OTA-782 (F13) will hang the write endpoints for engine config on this module.

OTA-762
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import engine_config_store as store
from app.api.engine_config_store import (
    DuplicateKeyError,
    EngineConfigError,
    InUseError,
    NotFoundError,
    SharedRowError,
)
from app.api.engine_config_validation import ConfigSaveValidationError
from app.auth.dependencies import require_read, require_write
from app.insight_engine.models import Phase
from app.models.session import get_db
from app.ota_adapters.engine_runtime import get_engine_runtime

router = APIRouter(prefix="/config", tags=["Engine Config"])

# Only screening strategies are exposed by this endpoint (the four scorecard
# lenses). Other consumer surfaces (POSITION_HEALTH, DIRECTIONAL) are not part
# of the strategy-admin / scorecard contract this endpoint serves.
_SCREENING_SURFACE = "SCREENING"


class VerdictBand(BaseModel):
    """One score→verdict band, passed through from ``verdict_band_set``."""

    verdict: str
    min_score: float
    max_score: float


class StrategyConfigResponse(BaseModel):
    """Serialized engine config for one screening strategy."""

    strategy_key: str
    display_name: str
    consumer_surface: str
    compatible_structures: list[str] | None = None
    dte_min: int | None = None
    dte_max: int | None = None
    # Per-criterion scoring weights, keyed by scoring rule_key, sourced from the
    # scoring-phase junction bindings — never from a Strategy attribute.
    weights: dict[str, float] = Field(default_factory=dict)
    # Score→verdict bands, exposed as-is. EXECUTE/WAIT min_score surface the
    # score-color thresholds (e.g. 70/50) for OTA-660.
    verdict_band_set: list[VerdictBand] = Field(default_factory=list)


@router.get("/strategies", response_model=list[StrategyConfigResponse])
async def get_engine_strategies(
    user: dict = Depends(require_read),
) -> list[StrategyConfigResponse]:
    """Return the screening strategies serialized from the hydrated engine config.

    Strategy-level fields come from ``config.strategies``; per-criterion weights
    come from each strategy's scoring-phase junction bindings. No ``engine_*``
    SQL read happens here — the accessor is the only source.
    """
    config = get_engine_runtime().config

    responses: list[StrategyConfigResponse] = []
    for strategy_key, strategy in config.strategies.items():
        if strategy.consumer_surface != _SCREENING_SURFACE:
            continue

        # Per-criterion weights from scoring-phase junction bindings (§2).
        weights: dict[str, float] = {}
        rule_set = config.rule_sets.get(strategy_key)
        if rule_set is not None:
            for binding in rule_set.bindings:
                if binding.rule.phase is Phase.SCORING and binding.junction.weight is not None:
                    weights[binding.rule.rule_key] = binding.junction.weight

        responses.append(
            StrategyConfigResponse(
                strategy_key=strategy.strategy_key,
                display_name=strategy.display_name,
                consumer_surface=strategy.consumer_surface,
                compatible_structures=(
                    list(strategy.compatible_structures)
                    if strategy.compatible_structures is not None
                    else None
                ),
                dte_min=strategy.dte_min,
                dte_max=strategy.dte_max,
                weights=weights,
                verdict_band_set=[
                    VerdictBand(
                        verdict=band["verdict"],
                        min_score=band["min_score"],
                        max_score=band["max_score"],
                    )
                    for band in strategy.verdict_band_set
                ],
            )
        )

    return responses


# ===========================================================================
#  Write side (OTA-782) — CRUD over the four editable engine_* tables.
#
#  These endpoints return the FULL canonical row of each entity (not the
#  OTA-762 derived projection above, which has no shape for rules / junction /
#  lookups). Writes are app-scoped to owner_app_id='OTA'; SHARED rows are
#  read-only here. Per insight_engine.md §6.5 a write does not affect the live
#  engine until restart, so GET /config/strategies (in-memory projection) will
#  not reflect a write until then — each write returns the persisted row for an
#  immediate round-trip. Save-time engine-load validation is OTA-783 (seam:
#  engine_config_store.run_save_validation), not implemented here.
# ===========================================================================


# ── Canonical response shapes (full row mirrors of the DDL) ───────────────


class StrategyRow(BaseModel):
    strategy_id: int
    owner_app_id: str
    strategy_key: str
    display_name: str
    consumer_surface: str
    description: str | None = None
    compatible_structures: Any | None = None
    verdict_band_set: Any
    dte_min: int | None = None
    dte_max: int | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None


class RuleRow(BaseModel):
    rule_id: int
    owner_app_id: str
    rule_key: str
    phase: str
    tier: str | None = None
    intent: str | None = None
    condition_expression: str | None = None
    formula_ref: str | None = None
    referenced_named_values: Any | None = None
    parameter_schema: Any | None = None
    null_semantics: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None


class JunctionRow(BaseModel):
    junction_id: int
    strategy_id: int
    rule_id: int
    strategy_key: str
    rule_key: str
    evaluation_order: int
    stop_if_fail: bool
    score_penalty: float | None = None
    weight: float | None = None
    parameters: Any | None = None
    terminal_verdict: str | None = None
    rationale: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None


class LookupRow(BaseModel):
    lookup_id: int
    owner_app_id: str
    lookup_set: str
    lookup_key: str
    payload: Any
    sort_order: int | None = None
    enabled: bool
    created_at: datetime


# ── Request bodies. owner_app_id is optional ONLY so a SHARED-targeting
#    request is detectable and rejectable; it is never honoured — every write
#    is forced to OTA. ─────────────────────────────────────────────────────


class StrategyCreate(BaseModel):
    owner_app_id: str | None = None
    strategy_key: str
    display_name: str
    consumer_surface: str
    description: str | None = None
    compatible_structures: Any | None = None
    verdict_band_set: Any
    dte_min: int | None = None
    dte_max: int | None = None
    enabled: bool = True


class StrategyUpdate(BaseModel):
    owner_app_id: str | None = None
    display_name: str
    consumer_surface: str
    description: str | None = None
    compatible_structures: Any | None = None
    verdict_band_set: Any
    dte_min: int | None = None
    dte_max: int | None = None
    enabled: bool = True


class RuleCreate(BaseModel):
    owner_app_id: str | None = None
    rule_key: str
    phase: str
    tier: str | None = None
    intent: str | None = None
    condition_expression: str | None = None
    formula_ref: str | None = None
    referenced_named_values: Any | None = None
    parameter_schema: Any | None = None
    null_semantics: str | None = None
    enabled: bool = True


class RuleUpdate(BaseModel):
    owner_app_id: str | None = None
    phase: str
    tier: str | None = None
    intent: str | None = None
    condition_expression: str | None = None
    formula_ref: str | None = None
    referenced_named_values: Any | None = None
    parameter_schema: Any | None = None
    null_semantics: str | None = None
    enabled: bool = True


class JunctionCreate(BaseModel):
    strategy_key: str
    rule_key: str
    evaluation_order: int
    stop_if_fail: bool
    score_penalty: float | None = None
    weight: float | None = None
    parameters: Any | None = None
    terminal_verdict: str | None = None
    rationale: str | None = None
    enabled: bool = True


class JunctionUpdate(BaseModel):
    evaluation_order: int
    stop_if_fail: bool
    score_penalty: float | None = None
    weight: float | None = None
    parameters: Any | None = None
    terminal_verdict: str | None = None
    rationale: str | None = None
    enabled: bool = True


class LookupCreate(BaseModel):
    owner_app_id: str | None = None
    lookup_set: str
    lookup_key: str
    payload: Any
    sort_order: int | None = None
    enabled: bool = True


class LookupUpdate(BaseModel):
    owner_app_id: str | None = None
    payload: Any
    sort_order: int | None = None
    enabled: bool = True


# ── Store-error → HTTP-status mapping ─────────────────────────────────────

_STATUS_BY_ERROR: dict[type[EngineConfigError], int] = {
    SharedRowError: status.HTTP_403_FORBIDDEN,
    DuplicateKeyError: status.HTTP_409_CONFLICT,
    InUseError: status.HTTP_409_CONFLICT,
    NotFoundError: status.HTTP_404_NOT_FOUND,
}


def _http(exc: EngineConfigError) -> NoReturn:
    code = _STATUS_BY_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(status_code=code, detail=str(exc))


async def _run(coro) -> Any:
    """Await a store coroutine, mapping its typed errors to HTTP responses.

    EngineConfigError subclasses map to 403/404/409. A save that would fail
    engine load (OTA-783) maps to 422 carrying the loader/validator's structured
    error identity (same codes/messages OTA-699 emits) — not a re-spelled copy.
    A JSON ``ValueError`` from the write path also maps to 422.
    """
    try:
        return await coro
    except ConfigSaveValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Config validation failed", "errors": exc.errors},
        )
    except EngineConfigError as exc:
        _http(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


# ── Strategies ────────────────────────────────────────────────────────────


@router.post("/strategies", response_model=StrategyRow, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    body: StrategyCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.create_strategy(db, body.model_dump()))


@router.put("/strategies/{strategy_key}", response_model=StrategyRow)
async def update_strategy(
    strategy_key: str,
    body: StrategyUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.update_strategy(db, strategy_key, body.model_dump()))


@router.delete("/strategies/{strategy_key}", response_model=StrategyRow)
async def delete_strategy(
    strategy_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.delete_strategy(db, strategy_key))


# ── Rules ─────────────────────────────────────────────────────────────────


@router.post("/rules", response_model=RuleRow, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.create_rule(db, body.model_dump()))


@router.put("/rules/{rule_key}", response_model=RuleRow)
async def update_rule(
    rule_key: str,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.update_rule(db, rule_key, body.model_dump()))


@router.delete("/rules/{rule_key}", response_model=RuleRow)
async def delete_rule(
    rule_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.delete_rule(db, rule_key))


# ── Junction ──────────────────────────────────────────────────────────────


@router.post("/junction", response_model=JunctionRow, status_code=status.HTTP_201_CREATED)
async def create_junction(
    body: JunctionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.create_junction(db, body.model_dump()))


@router.put("/junction/{strategy_key}/{rule_key}", response_model=JunctionRow)
async def update_junction(
    strategy_key: str,
    rule_key: str,
    body: JunctionUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.update_junction(db, strategy_key, rule_key, body.model_dump()))


@router.delete("/junction/{strategy_key}/{rule_key}", response_model=JunctionRow)
async def delete_junction(
    strategy_key: str,
    rule_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.delete_junction(db, strategy_key, rule_key))


# ── Lookups ───────────────────────────────────────────────────────────────


@router.post("/lookups", response_model=LookupRow, status_code=status.HTTP_201_CREATED)
async def create_lookup(
    body: LookupCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.create_lookup(db, body.model_dump()))


@router.put("/lookups/{lookup_set}/{lookup_key}", response_model=LookupRow)
async def update_lookup(
    lookup_set: str,
    lookup_key: str,
    body: LookupUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.update_lookup(db, lookup_set, lookup_key, body.model_dump()))


@router.delete("/lookups/{lookup_set}/{lookup_key}", response_model=LookupRow)
async def delete_lookup(
    lookup_set: str,
    lookup_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    return await _run(store.delete_lookup(db, lookup_set, lookup_key))
