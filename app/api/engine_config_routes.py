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

from app.api import engine_config_preview as preview
from app.api import engine_config_store as store
from app.api.engine_config_preview import PreviewError, PreviewValidationError
from app.api.engine_config_store import (
    DuplicateKeyError,
    EngineConfigError,
    InUseError,
    NotFoundError,
    SharedRowError,
)
from app.api.engine_config_validation import ConfigSaveValidationError
from app.auth.dependencies import require_read, require_write
from app.insight_engine.expressions import extract_formula_name, is_formula_ref
from app.insight_engine.models import Phase
from app.models.session import get_db
from app.options_rules.screening import get_registry
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
    status: str
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None


class AdminStrategyRow(BaseModel):
    """Current-state admin view of one ``engine_strategies`` row (OTA-823).

    Spans all owners and all consumer surfaces. ``owner_app_id`` drives the
    selector's editable (OTA) vs read-only (SHARED) treatment.
    """

    owner_app_id: str
    strategy_key: str
    display_name: str
    # description rides on the admin row so the strategy-admin editor (OTA-784)
    # can round-trip it on a header save. update_strategy is a full-row replace,
    # so omitting description from the PUT body would null it; the store already
    # returns it (_row_to_dict) — surfacing it here makes the save non-destructive.
    description: str | None = None
    enabled: bool
    status: str
    consumer_surface: str
    compatible_structures: Any | None = None
    dte_min: int | None = None
    dte_max: int | None = None
    verdict_band_set: Any


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


class RuleAdminRow(RuleRow):
    """Owner-spanning rule-catalog row (OTA-825): the full ``engine_rules`` row
    plus a computed formula-registry status. Derives from ``RuleRow`` so the
    column set is single-sourced and never drifts from the canonical shape.

    ``formula_registered`` is tri-state (see the route): ``None`` when the rule
    carries no ``formula_ref`` (n/a, not an error), ``True``/``False`` otherwise.
    """

    formula_registered: bool | None = None


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


class StrategyJunctionRow(BaseModel):
    """One junction binding for a strategy, joined to its rule's display metadata
    (OTA-826).

    The full junction shape (the editable mechanical fields + the variable
    ``parameters`` JSON) plus the bound rule's ``phase`` / ``intent`` /
    ``parameter_schema`` so the editor's Hard Gates / Scoring / Adjustments tabs
    can group, label, and form-render each binding without a second fetch. The
    rule fields are joined read-only context — not part of the binding itself.
    """

    junction_id: int
    strategy_id: int
    strategy_key: str
    rule_id: int
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
    # Joined rule display metadata (read-only).
    phase: str
    intent: str | None = None
    parameter_schema: Any | None = None


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
    # status is the lifecycle input of record (OTA-824). enabled is NOT a
    # client field — it is derived from status server-side. Omitted → 'active'.
    status: str | None = None


class StrategyUpdate(BaseModel):
    owner_app_id: str | None = None
    display_name: str
    consumer_surface: str
    description: str | None = None
    compatible_structures: Any | None = None
    verdict_band_set: Any
    dte_min: int | None = None
    dte_max: int | None = None
    # status drives enabled (derived server-side). Omitted → 'active'.
    status: str | None = None


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


# ── Draft preview shapes (OTA-791) ────────────────────────────────────────


class PreviewRequest(BaseModel):
    """Evaluate the strategy's draft against one symbol's option chain."""

    symbol: str


class PreviewResultItem(BaseModel):
    """One evaluated candidate from a draft preview, ranked by score."""

    candidate_id: str
    symbol: str | None = None
    structure: str | None = None
    structure_label: str | None = None
    strikes: str | None = None
    expiration: str | None = None
    dte: int | None = None
    score: float | None = None
    verdict: str | None = None
    terminal_phase: str


class PreviewResponse(BaseModel):
    """Draft preview output: ranked candidates + run metadata."""

    draft_key: str
    config_version: str
    underlying_price: float
    candidates_evaluated: int
    results: list[PreviewResultItem]


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


@router.get("/strategies/admin", response_model=list[AdminStrategyRow])
async def list_strategies_admin(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_read),
) -> Any:
    """List every strategy (all owners + surfaces) from CURRENT DB state.

    Distinct from ``GET /config/strategies`` (OTA-762: hydrated, restart-gated,
    SCREENING-only). This reads ``engine_strategies`` directly via the injected
    session, so just-saved writes appear without a restart, and tags each row by
    ``owner_app_id`` for the editor (OTA editable, SHARED read-only).
    """
    return await store.list_strategies_admin(db)


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


@router.get(
    "/strategies/{strategy_key}/junctions",
    response_model=list[StrategyJunctionRow],
)
async def list_strategy_junctions(
    strategy_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_read),
) -> Any:
    """List every junction binding for a strategy (live key or ``<key>__draft``).

    Resolves the strategy within OTA scope (404 if absent), then returns its
    bindings ordered by ``evaluation_order``, each joined to its rule's
    ``phase`` / ``intent`` / ``parameter_schema``. Reads
    ``engine_strategy_rule_junction`` directly via the injected session — NOT the
    restart-gated ``AzureSqlConfigSource`` — so just-saved bindings and freshly
    cloned drafts (OTA-791) appear without a restart. No ``enabled`` filter:
    disabled bindings surface so the editor can show them. Read-only.
    """
    return await _run(store.list_strategy_junctions(db, strategy_key))


# ── Draft substrate + live preview (OTA-791) ──────────────────────────────
#
# The draft is the write target for all editing (OTA-781 save-to-draft); the
# live row is untouched until Apply (OTA-790). Draft rows are status='draft'
# (enabled=0) so the runtime loader skips them — they never enter the running
# config. ``preview`` is the ONLY reader that admits the draft, via a fresh
# LOCAL config load that never touches the running runtime (restart-only).


@router.post(
    "/strategies/{strategy_key}/draft",
    response_model=StrategyRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_resume_draft(
    strategy_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    """Create the draft from the live strategy, or resume an existing one.

    Clones the live header + junctions onto ``<key>__draft`` only if no draft
    exists; otherwise resumes the existing draft (no silent overwrite).
    """
    return await _run(store.create_or_resume_draft(db, strategy_key))


@router.post("/strategies/{strategy_key}/draft/refresh", response_model=StrategyRow)
async def refresh_draft_from_live(
    strategy_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    """Discard the existing draft and re-clone it fresh from the live strategy."""
    return await _run(store.refresh_draft_from_live(db, strategy_key))


@router.delete("/strategies/{strategy_key}/draft", response_model=StrategyRow)
async def delete_draft(
    strategy_key: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
) -> Any:
    """Discard the draft for a strategy (404 if none exists)."""
    return await _run(store.delete_draft(db, strategy_key))


@router.post("/strategies/{strategy_key}/preview", response_model=PreviewResponse)
async def preview_draft(
    strategy_key: str,
    body: PreviewRequest,
    user: dict = Depends(require_read),
) -> Any:
    """Evaluate the strategy's draft against one symbol's chain → scores/verdicts.

    Loads a fresh LOCAL config that admits only this draft key, validates it,
    and runs the engine. The running runtime config is never mutated
    (restart-only, insight_engine.md §6.5). A missing draft → 409; a config that
    fails §6.6 validation → 422 with structured errors.
    """
    try:
        results, meta = await preview.preview_draft(
            live_key=strategy_key,
            symbol=body.symbol,
            user_id=user.get("sub"),
        )
    except PreviewValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Draft failed config validation", "errors": exc.errors},
        )
    except PreviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return PreviewResponse(
        draft_key=meta["draft_key"],
        config_version=meta["config_version"],
        underlying_price=meta["underlying_price"],
        candidates_evaluated=meta["candidates_evaluated"],
        results=[PreviewResultItem(**vars(r)) for r in results],
    )


# ── Rules ─────────────────────────────────────────────────────────────────


def _formula_registered(formula_ref: str | None) -> bool | None:
    """Tri-state formula-registry status for one rule's ``formula_ref``.

    - ``None``  — no ``formula_ref`` (a pure condition-expression rule; n/a, not
      an error).
    - ``True``  — a ``formula:<name>`` ref whose ``<name>`` is in the live
      screening registry.
    - ``False`` — a ref that is present but unresolvable: unregistered name, or
      malformed (not a ``formula:`` ref at all).

    Queries the live ``get_registry()`` (the same object the engine-load
    validator checks against); read-only — no engine state is mutated.
    """
    if formula_ref is None:
        return None
    if not is_formula_ref(formula_ref):
        return False  # present but malformed
    return get_registry().has(extract_formula_name(formula_ref))


@router.get("/rules/admin", response_model=list[RuleAdminRow])
async def list_rules_admin(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_read),
) -> Any:
    """List the OTA + SHARED rule catalog from CURRENT DB state (OTA-825).

    Owner-spanning over OTA's bindable rule set (OTA-or-SHARED, OTA-782), read
    straight from ``engine_rules`` via the injected session — no ``enabled``
    filter (disabled rules surface as unavailable), and distinct from the
    restart-gated runtime reader. Each row is the full canonical rule row plus a
    computed ``formula_registered`` status (see ``_formula_registered``).
    """
    rows = await store.list_rules_admin(db)
    return [{**row, "formula_registered": _formula_registered(row.get("formula_ref"))} for row in rows]


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
