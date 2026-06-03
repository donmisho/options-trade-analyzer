"""
Engine config read API (OTA-762).

Exposes the hydrated, validated engine configuration over HTTP for frontend
consumers (OTA-660 score-color thresholds, OTA-821 dual-source removal).

Read-only. The single source is the in-process accessor
``get_engine_runtime().config`` (OTA-818 keystone). This module NEVER opens a
new connection to the ``engine_*`` tables — ``AzureSqlConfigSource`` remains the
only runtime reader of those tables (grep-enforced; see acceptance criteria).

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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import require_read
from app.insight_engine.models import Phase
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
