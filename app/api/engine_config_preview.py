"""
Live preview via the draft strategy (OTA-791).

Two responsibilities, both app-layer (the engine package stays domain-free):

1. :func:`evaluate_screening` — the SHARED "evaluate one strategy's rule_set
   against a candidate stream → ranked scores/verdicts" core. It wraps the
   engine's single public ``evaluate`` entry point and joins each result back to
   its candidate for display. This is the one engine-backed screening path
   (decision C): the OTA-757 live-scorecard cutover reuses THIS function with
   the live runtime config — it must not grow a duplicate engine path.

2. :func:`preview_draft` — loads a FRESH, LOCAL config that admits exactly the
   one ``<key>__draft`` strategy (via ``load_config(include_draft_key=...)``),
   runs the full §6.6 validation (failures surface as preview errors, never
   swallowed — decision A), builds candidates for a single symbol's chain
   through the §5 options adapter, and evaluates the draft.

Restart-only invariant (insight_engine.md §6.5):
    The preview config is built in a LOCAL variable and is NEVER stamped onto
    the running runtime — ``set_engine_runtime`` is not called here, and
    ``get_engine_runtime()`` is never mutated. A preview re-reads the tables into
    a new ``AzureSqlConfigSource``; it does not touch the hydrated config the
    engine loaded at start. This is the verified AC.

OTA-791
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.api.engine_config_store import draft_key_for
from app.insight_engine import (
    Candidate,
    EngineConfig,
    FormulaRegistry,
    ResultRecord,
    evaluate,
    load_config,
    validate_and_raise,
)
from app.insight_engine.validation import ConfigValidationError
from app.models.session import async_session
from app.options_rules.screening import get_registry
from app.ota_adapters.engine_runtime import AzureSqlConfigSource
from app.ota_adapters.options_chain.adapter import OptionsChainAdapter

logger = logging.getLogger(__name__)

# OTA stamps every engine call with its source_app_id (insight_engine.md §2).
_SOURCE_APP_ID = "OTA"

# Default scan window when the strategy carries no DTE range.
_DEFAULT_MIN_DTE = 14
_DEFAULT_MAX_DTE = 60
_DEFAULT_STRIKE_RANGE_PCT = 10.0

# Canonical strategy ``compatible_structures`` enum → the options adapter's
# structure_type names (the adapter speaks bull_call/bear_put/…, the strategy
# config speaks bull_call_debit/bull_put_credit/…). Unknown values are dropped.
_STRUCTURE_TO_ADAPTER: dict[str, str] = {
    "bull_put_credit": "bull_put",
    "bear_call_credit": "bear_call",
    "bull_call_debit": "bull_call",
    "bear_put_debit": "bear_put",
    "long_call": "long_call",
    "long_put": "long_put",
}


# ── Typed errors (mapped to HTTP status by the route layer) ───────────────


class PreviewError(Exception):
    """Preview could not run for a non-validation reason (e.g. no draft). → 404/409."""


class PreviewValidationError(Exception):
    """The preview config failed §6.6 validation. → 422 carrying structured errors."""

    def __init__(self, exc: ConfigValidationError) -> None:
        self.errors = [
            {"code": e.code, "message": e.message, "context": e.context}
            for e in exc.report.errors
        ]
        super().__init__(exc.report.summary())


# ── Result shape ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScreeningResult:
    """One evaluated candidate, joined to its display fields and ranked."""

    candidate_id: str
    symbol: str | None
    structure: str | None        # adapter structure name (bull_put, long_call, …)
    structure_label: str | None  # human label ("Bull Put", "Long Call")
    strikes: str | None          # "120/125" (spread) or "120" (naked)
    expiration: str | None
    dte: int | None
    score: float | None          # final adjusted score, null if halted pre-scoring
    verdict: str | None
    terminal_phase: str          # where the candidate exited (gate halt vs. verdict)


# ── Shared evaluate core (decision C — OTA-757 cutover reuses this) ────────


def evaluate_screening(
    *,
    candidates: list[Candidate],
    strategy_key: str,
    config: EngineConfig,
    registry: FormulaRegistry,
    adapter: Any,
) -> list[ScreeningResult]:
    """Evaluate *candidates* against one strategy's rule_set → ranked results.

    Wraps the engine's single public ``evaluate`` (sink=None — preview/screening
    runs are not persisted to bronze), then joins each ResultRecord back to its
    candidate by id (``run_batch`` does not preserve input order) and ranks by
    score descending, halted candidates last.
    """
    records: list[ResultRecord] = evaluate(
        candidates=candidates,
        strategy_key=strategy_key,
        source_app_id=_SOURCE_APP_ID,
        config=config,
        registry=registry,
        adapter=adapter,
        sink=None,
    )
    by_id = {c.candidate_id: c for c in candidates}
    results = [_to_screening_result(r, by_id.get(r.candidate_id)) for r in records]
    results.sort(key=lambda s: (s.score is None, -(s.score if s.score is not None else 0.0)))
    return results


# ── Draft preview (the OTA-791 path) ──────────────────────────────────────


async def preview_draft(
    *,
    live_key: str,
    symbol: str,
    user_id: str | None = None,
    session_factory=async_session,
) -> tuple[list[ScreeningResult], dict[str, Any]]:
    """Evaluate the ``<live_key>__draft`` strategy against *symbol*'s chain.

    Loads a fresh LOCAL config admitting only the one draft key, validates it
    (§6.6), builds candidates via the §5 options adapter, and evaluates. Never
    mutates the running runtime config (restart-only — verified AC).

    Raises
    ------
    PreviewError
        If no draft exists for *live_key*.
    PreviewValidationError
        If the config (including the draft) fails §6.6 validation.
    """
    draft_key = draft_key_for(live_key)

    # Fresh read of the tables into a NEW source — never stamped to runtime.
    source = await AzureSqlConfigSource.load(session_factory)
    config = load_config(
        source, app_ids=("SHARED", "OTA"), include_draft_key=draft_key
    )
    if draft_key not in config.rule_sets:
        raise PreviewError(
            f"No draft exists for {live_key!r}. Create a draft before previewing."
        )

    registry = get_registry()

    # Full §6.6 validation on the draft-inclusive config — surface, don't swallow.
    try:
        validate_and_raise(config, formula_registry=registry, source=source)
    except ConfigValidationError as exc:
        raise PreviewValidationError(exc) from exc

    strat = config.strategies[draft_key]
    adapter = OptionsChainAdapter()
    candidates = await adapter.produce_candidates(
        {
            "symbol": symbol,
            "min_dte": strat.dte_min if strat.dte_min is not None else _DEFAULT_MIN_DTE,
            "max_dte": strat.dte_max if strat.dte_max is not None else _DEFAULT_MAX_DTE,
            "strike_range_pct": _DEFAULT_STRIKE_RANGE_PCT,
            "structure_types": _adapter_structure_types(strat.compatible_structures),
            "user_id": user_id,
        }
    )

    results = evaluate_screening(
        candidates=candidates,
        strategy_key=draft_key,
        config=config,
        registry=registry,
        adapter=adapter,
    )
    meta = {
        "draft_key": draft_key,
        "config_version": config.config_version,
        "underlying_price": adapter.underlying_price,
        "candidates_evaluated": len(candidates),
    }
    logger.info(
        "preview_draft: %s vs %s → %d candidates (config_version=%s)",
        draft_key, symbol, len(candidates), config.config_version,
    )
    return results, meta


# ── Helpers ───────────────────────────────────────────────────────────────


def _adapter_structure_types(
    compatible_structures: tuple[str, ...] | None,
) -> list[str] | None:
    """Map a strategy's compatible_structures to adapter structure_type names.

    Returns None (= all structures) when the strategy declares none, so the
    preview still produces candidates rather than an empty set.
    """
    if not compatible_structures:
        return None
    mapped = [
        _STRUCTURE_TO_ADAPTER[s]
        for s in compatible_structures
        if s in _STRUCTURE_TO_ADAPTER
    ]
    return mapped or None


def _to_screening_result(
    record: ResultRecord, candidate: Candidate | None
) -> ScreeningResult:
    nv = candidate.named_values if candidate is not None else {}
    structure = nv.get("spread_type")
    return ScreeningResult(
        candidate_id=record.candidate_id,
        symbol=candidate.symbol if candidate is not None else None,
        structure=structure,
        structure_label=_structure_label(structure),
        strikes=_strikes(nv),
        expiration=nv.get("expiration"),
        dte=nv.get("dte"),
        score=record.final_score,
        verdict=record.verdict,
        terminal_phase=record.terminal_phase,
    )


def _structure_label(structure: str | None) -> str | None:
    """'bull_put' → 'Bull Put'; None → None."""
    if not structure:
        return None
    return " ".join(w.capitalize() for w in structure.split("_"))


def _strikes(nv: dict[str, Any]) -> str | None:
    """Spread → 'long/short'; naked → 'strike'; else None."""
    long_strike = nv.get("long_strike")
    short_strike = nv.get("short_strike")
    if long_strike is not None and short_strike is not None:
        return f"{_fmt_strike(long_strike)}/{_fmt_strike(short_strike)}"
    strike = nv.get("strike")
    if strike is not None:
        return _fmt_strike(strike)
    return None


def _fmt_strike(value: Any) -> str:
    """Render a strike without a trailing '.0' (120.0 → '120', 122.5 → '122.5')."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f.is_integer() else str(f)
