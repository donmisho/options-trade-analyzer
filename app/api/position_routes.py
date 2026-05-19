# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.

"""
Position Tracking API (Phase 2.10 / 2.11)

Endpoints:
  POST   /api/v1/positions/follow             — Create paper position (FOLLOWING)
  POST   /api/v1/positions/take               — Create live position (LIVE)
  GET    /api/v1/positions                    — List with composable filters
  GET    /api/v1/positions/aggregate          — Aggregate stats only
  GET    /api/v1/positions/current-prices     — Batch live pricing + P&L (OTA-265)
  PATCH  /api/v1/positions/{id}/close         — Close and record outcome
  PATCH  /api/v1/positions/{id}/archive       — Archive (expired / shelved) (OTA-265)
  GET    /api/v1/positions/{id}               — Single position detail
  GET    /api/v1/positions/{id}/assessments   — Versioned assessment history (OTA-265)

Auth tiers:
  - All read endpoints: Tier 1 (require_read)
  - Follow/Take/Close/Archive: Tier 2 (require_write)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read, require_write
from app.models.session import get_db
from app.models.database import Position, PositionAssessment, TradeCandidate
from app.analysis.strategy_routing import get_compatible_strategies, normalize_to_structure
from app.services.symbol_normalization import canonicalize
from app.services.symbol_cache import to_api_symbol_cached
from app.models.schemas import (
    FollowPositionRequest,
    TakePositionRequest,
    ClosePositionRequest,
    PositionResponse,
    PositionListResponse,
    PositionAssessmentResponse,
    PositionCurrentPrice,
    PositionRefreshResponse,
)

# ── Provider factory (injected at startup by init_position_routes) ─────────────
_provider_factory = None


def init_position_routes(factory):
    global _provider_factory
    _provider_factory = factory


def _get_provider():
    """Return the active market data provider (Schwab if connected, else default)."""
    if _provider_factory is None:
        return None
    from app.core.config import settings
    token_mgr = getattr(_provider_factory, '_schwab_token_manager', None)
    if token_mgr and token_mgr.get_status().get('connected'):
        return _provider_factory.get_market_data("schwab")
    return _provider_factory.get_market_data(settings.default_market_data_provider)


def _get_eval_adapter():
    """Lazy-import the configured eval adapter from evaluation_routes (set at startup)."""
    from app.api.evaluation_routes import _eval_adapter
    return _eval_adapter


def _try_parse_refresh_card(raw: str) -> Optional[dict]:
    """
    Parse Claude's position-refresh JSON object response.
    Returns a dict with verdict/score/synopsis/claude_read/exit_levels, or None on failure.
    """
    import re
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    # Extract first {...} block if there is surrounding prose
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        # Normalise: Claude might return exit_plan instead of exit_levels
        if "exit_plan" in data and "exit_levels" not in data:
            data["exit_levels"] = data.pop("exit_plan")
        # Validate required keys
        for key in ("verdict", "score", "claude_read"):
            if key not in data:
                return None
        if data["verdict"] not in ("EXECUTE", "WAIT", "PASS"):
            return None
        return data
    except (ValueError, TypeError):
        return None
# health_grade is Phase 2.10 A4 — guarded import so the app starts before that file ships
try:
    from app.analysis.health_grade import compute_health_grade as _compute_health_grade
except ImportError:
    _compute_health_grade = None  # type: ignore


def compute_health_grade(entry_price, current_price, claude_exit_levels_json=None):
    """Shim: delegates to health_grade module when available, else P&L fallback."""
    if _compute_health_grade is not None:
        return _compute_health_grade(
            entry_price=entry_price,
            current_price=current_price,
            claude_exit_levels_json=claude_exit_levels_json,
        )
    # Simple P&L % fallback until A4 ships
    if current_price is None or entry_price == 0:
        return None
    pct = (current_price - entry_price) / entry_price
    if pct >= 0:
        return "A"
    elif pct >= -0.10:
        return "B"
    elif pct >= -0.25:
        return "C"
    elif pct >= -0.50:
        return "D"
    return "F"

log = logging.getLogger(__name__)

router = APIRouter(prefix="/positions", tags=["Positions"])

# ── Strategy label map ─────────────────────────────────────────────────────────
# Keep in sync with web/src/strategy-configs/index.js
_STRATEGY_LABELS = {
    "verticals":        "Vertical Spreads",
    "long-calls":       "Long Calls",
    "steady-paycheck":  "Steady Paycheck",
    "weekly-grind":     "Weekly Grind",
    "trend-rider":      "Trend Rider",
    "lottery-ticket":   "Lottery Ticket",
}


def _strategy_label(key: str) -> str:
    return _STRATEGY_LABELS.get(key, key.replace("-", " ").title())


def _extract_canonical_structure(trade_structure: dict) -> Optional[str]:
    """
    Extract the canonical compatible_structures value from a position's trade_structure.
    Handles both direct 'structure' field and legacy 'spread_type'/'option_type' fields.
    Returns e.g. 'bull_put_credit', 'bear_put_debit', 'long_call', or None.
    """
    # Direct structure field (from TradeCandidate path)
    structure = trade_structure.get("structure")
    if structure:
        # Normalize: lower-case, underscores
        s = structure.lower().replace("-", "_").replace(" ", "_")
        # Already canonical?
        if s in ("bull_put_credit", "bear_call_credit", "bull_call_debit",
                 "bear_put_debit", "long_call", "long_put"):
            return s
        # Map SINGLE_LONG_CALL / SINGLE_LONG_PUT variants
        if "single_long_call" in s or s == "long_call":
            return "long_call"
        if "single_long_put" in s or s == "long_put":
            return "long_put"
        # Try normalize_to_structure (handles engine spread_type values)
        normalized = normalize_to_structure(spread_type=s)
        if normalized:
            return normalized

    # Legacy: spread_type field (from scan results)
    spread_type = trade_structure.get("spread_type")
    if spread_type:
        s = spread_type.lower().replace("-", "_")
        # spread_type is engine-level: 'bull_put', 'bear_call', 'bull_call', 'bear_put'
        normalized = normalize_to_structure(spread_type=s)
        if normalized:
            return normalized
        # May already be canonical
        if s in ("bull_put_credit", "bear_call_credit", "bull_call_debit", "bear_put_debit"):
            return s

    # Legacy: option_type field for single-leg
    option_type = trade_structure.get("option_type")
    if option_type:
        normalized = normalize_to_structure(option_type=option_type.lower())
        if normalized:
            return normalized

    # Infer from legs if present
    legs = trade_structure.get("legs", [])
    if len(legs) == 1:
        leg = legs[0]
        ot = (leg.get("option_type") or "").lower()
        if ot in ("call", "put"):
            return f"long_{ot}"
    elif len(legs) == 2:
        # Two legs = spread. Determine type from strikes + option_type
        long_leg = next((l for l in legs if (l.get("side") or "").lower() == "long"), None)
        short_leg = next((l for l in legs if (l.get("side") or "").lower() == "short"), None)
        if long_leg and short_leg:
            ot = (long_leg.get("option_type") or "").lower()
            ls = float(long_leg.get("strike", 0))
            ss = float(short_leg.get("strike", 0))
            if ot == "put":
                # long put higher strike = bear put debit, long put lower strike = bull put credit
                if ls > ss:
                    return "bear_put_debit"
                else:
                    return "bull_put_credit"
            elif ot == "call":
                # long call lower strike = bull call debit, long call higher strike = bear call credit
                if ls < ss:
                    return "bull_call_debit"
                else:
                    return "bear_call_credit"

    return None


def _compute_orphan_fields(trade_structure: dict, strategy_key: str) -> dict:
    """
    Compute orphan detection fields for a position.
    Returns dict with is_orphaned, eligible_strategies, best_fit.
    """
    canonical = _extract_canonical_structure(trade_structure)
    if canonical is None:
        # Can't determine structure — not orphaned (defensive)
        return {"is_orphaned": False, "eligible_strategies": [], "best_fit": None}

    eligible = get_compatible_strategies(canonical)
    is_orphaned = strategy_key not in eligible
    best_fit = eligible[0] if eligible else None
    return {
        "is_orphaned": is_orphaned,
        "eligible_strategies": eligible,
        "best_fit": best_fit,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dte_at_entry(trade_structure: dict, entry_date: datetime) -> Optional[int]:
    """
    Compute DTE at time of entry from trade_structure.
    Looks for a top-level 'expiration' key first, then the first leg's expiration.
    """
    expiration = trade_structure.get("expiration")
    if not expiration:
        legs = trade_structure.get("legs")
        if legs and isinstance(legs, list):
            expiration = legs[0].get("expiration")
    if not expiration:
        return None
    try:
        exp_date = datetime.strptime(expiration[:10], "%Y-%m-%d").date()
        entry = entry_date.date() if isinstance(entry_date, datetime) else entry_date
        return max(0, (exp_date - entry).days)
    except (ValueError, TypeError):
        return None


def _days_held(entry_date: datetime, exit_date: Optional[datetime] = None) -> int:
    end = exit_date or datetime.now(timezone.utc)
    if entry_date.tzinfo is None:
        entry_date = entry_date.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, (end - entry_date).days)


def _to_response(pos: Position) -> PositionResponse:
    entry_price = float(pos.entry_price) if pos.entry_price is not None else 0.0
    current_price = float(pos.current_price) if pos.current_price is not None else None
    raw_ts = pos.trade_structure
    trade_struct: dict = json.loads(raw_ts) if isinstance(raw_ts, str) else (raw_ts or {})

    # Recompute health grade on every read so it reflects the latest price
    grade = compute_health_grade(
        entry_price=entry_price,
        current_price=current_price,
        claude_exit_levels_json=pos.claude_exit_levels,
    )

    def _parse_json_field(raw) -> Optional[dict]:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    # OTA-650: compute orphan detection fields
    orphan_fields = _compute_orphan_fields(trade_struct, pos.strategy_key)

    return PositionResponse(
        position_id=pos.position_id,
        symbol=pos.symbol,
        strategy_key=pos.strategy_key,
        strategy_label=_strategy_label(pos.strategy_key),
        source=pos.source,
        status=pos.status,
        entry_price=entry_price,
        entry_date=pos.entry_date.isoformat(),
        entry_underlying_price=float(pos.entry_underlying_price) if pos.entry_underlying_price is not None else 0.0,
        entry_iv_rank=float(pos.entry_iv_rank) if pos.entry_iv_rank is not None else None,
        entry_sma_alignment=_parse_json_field(pos.entry_sma_alignment),
        current_price=current_price,
        current_pnl=float(pos.current_pnl) if pos.current_pnl is not None else None,
        last_monitored_at=pos.last_monitored_at.isoformat() if pos.last_monitored_at is not None else None,
        health_grade=grade,
        claude_score=pos.claude_score,
        claude_verdict=_parse_json_field(pos.claude_verdict),
        claude_exit_levels=_parse_json_field(pos.claude_exit_levels),
        claude_probability_matrix=_parse_json_field(pos.claude_probability_matrix),
        days_held=_days_held(pos.entry_date, pos.exit_date),
        dte_at_entry=_dte_at_entry(trade_struct, pos.entry_date),
        trade_structure=trade_struct,
        is_orphaned=orphan_fields["is_orphaned"],
        eligible_strategies=orphan_fields["eligible_strategies"],
        best_fit=orphan_fields["best_fit"],
        exit_price=float(pos.exit_price) if pos.exit_price is not None else None,
        exit_date=pos.exit_date.isoformat() if pos.exit_date is not None else None,
        exit_reason=pos.exit_reason,
        outcome_pnl=float(pos.outcome_pnl) if pos.outcome_pnl is not None else None,
    )


def _build_aggregate(positions: list[Position]) -> dict:
    """Compute aggregate stats from a list of positions."""
    closed = [p for p in positions if p.status == "CLOSED"]
    active = [p for p in positions if p.status != "CLOSED"]

    wins = [p for p in closed if p.outcome_pnl is not None and float(p.outcome_pnl) > 0]
    win_rate = (len(wins) / len(closed)) if closed else None

    pnls = [float(p.outcome_pnl) for p in closed if p.outcome_pnl is not None]
    avg_pnl = (sum(pnls) / len(pnls)) if pnls else None

    hold_days = [
        _days_held(p.entry_date, p.exit_date)
        for p in closed if p.exit_date is not None
    ]
    avg_hold_days = (sum(hold_days) / len(hold_days)) if hold_days else None

    # Per-strategy breakdown
    strategy_keys = {p.strategy_key for p in positions}
    by_strategy = {}
    for sk in strategy_keys:
        sk_closed = [p for p in closed if p.strategy_key == sk]
        sk_wins = [p for p in sk_closed if p.outcome_pnl is not None and float(p.outcome_pnl) > 0]
        sk_pnls = [float(p.outcome_pnl) for p in sk_closed if p.outcome_pnl is not None]
        by_strategy[sk] = {
            "label": _strategy_label(sk),
            "active": len([p for p in active if p.strategy_key == sk]),
            "closed": len(sk_closed),
            "win_rate": (len(sk_wins) / len(sk_closed)) if sk_closed else None,
            "avg_pnl": (sum(sk_pnls) / len(sk_pnls)) if sk_pnls else None,
        }

    return {
        "active_count": len(active),
        "closed_count": len(closed),
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "avg_hold_days": avg_hold_days,
        "by_strategy": by_strategy,
    }


async def _create_original_assessment(db: AsyncSession, pos: Position, req) -> None:
    """
    Create the first PositionAssessment row (assessment_type='ORIGINAL') when
    a position is followed or taken. Copies evaluation data from the request.
    """
    verdict_data = req.claude_verdict or {}
    verdict = verdict_data.get("verdict", "WAIT")
    if verdict not in ("EXECUTE", "WAIT", "PASS"):
        raise HTTPException(
            status_code=422,
            detail=f"Unknown verdict '{verdict}' — must be EXECUTE, WAIT, or PASS",
        )
    score = req.claude_score or verdict_data.get("score", 0) or 0
    claude_read = verdict_data.get("claude_read", "")

    # Build 5-7 word synopsis from claude_read
    synopsis = None
    if claude_read:
        words = claude_read.split()
        synopsis = " ".join(words[:7]) if len(words) > 7 else claude_read

    # Market snapshot from entry data
    market_snapshot = {
        "underlying_price": float(req.entry_underlying_price) if req.entry_underlying_price else None,
        "iv_rank": float(req.entry_iv_rank) if req.entry_iv_rank else None,
        "spread_mark": float(req.entry_price) if req.entry_price else None,
    }

    assessment = PositionAssessment(
        position_id=pos.position_id,
        version_number=1,
        assessment_type="ORIGINAL",
        verdict=verdict,
        score=int(score),
        synopsis=synopsis,
        claude_read=claude_read,
        exit_levels=json.dumps(req.claude_exit_levels) if req.claude_exit_levels else None,
        market_snapshot=json.dumps(market_snapshot),
    )
    db.add(assessment)


def _perf_status(current_pnl: Optional[float], underlying_price: Optional[float],
                 exit_levels: Optional[dict]) -> str:
    """Compute perf_status from current P&L and exit levels."""
    if exit_levels is None:
        exit_levels = {}

    hard_stop = exit_levels.get("hard_stop")
    warning = exit_levels.get("warning_level") or exit_levels.get("exit_warning_price") or exit_levels.get("warning")

    # Red: underlying price has crossed the hard stop threshold
    if hard_stop and underlying_price is not None:
        try:
            if underlying_price <= float(hard_stop):
                return "red"
        except (TypeError, ValueError):
            pass

    if current_pnl is None:
        return "unknown"

    # Amber: losing money OR within 10% of warning level
    if current_pnl < 0:
        return "amber"
    if warning and underlying_price is not None:
        try:
            warn_f = float(warning)
            if warn_f > 0 and abs(underlying_price - warn_f) / warn_f <= 0.10:
                return "amber"
        except (TypeError, ValueError):
            pass

    return "green"


def _apply_filters(stmt, user_id: str, status: Optional[str], source: Optional[str],
                   symbol: Optional[str], strategy_key: Optional[str]):
    from sqlalchemy import or_
    stmt = stmt.where(Position.user_id == user_id)
    if status and status not in ("all", ""):
        # "active" is a virtual status — maps to FOLLOWING + LIVE
        if status.lower() == "active":
            stmt = stmt.where(or_(Position.status == "FOLLOWING", Position.status == "LIVE"))
        else:
            stmt = stmt.where(Position.status == status.upper())
    if source and source != "all":
        stmt = stmt.where(Position.source == source.upper())
    if symbol:
        stmt = stmt.where(Position.symbol == symbol.upper())
    if strategy_key and strategy_key != "all":
        stmt = stmt.where(Position.strategy_key == strategy_key)
    return stmt


async def _resolve_trade_candidate(
    db: AsyncSession, trade_key: str, user_id: str,
) -> TradeCandidate:
    """
    OTA-624: Look up a trade_candidates row by trade_key AND user_id.
    Returns 404 if not found (covers Data Isolation Invariant — cross-user
    attempts return 404, not 403).
    """
    result = await db.execute(
        select(TradeCandidate).where(
            TradeCandidate.trade_key == trade_key,
            TradeCandidate.user_id == user_id,
        )
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Trade candidate not found")
    return candidate


def _candidate_to_follow_fields(candidate: TradeCandidate) -> dict:
    """
    OTA-624: Extract Follow-compatible fields from a persisted TradeCandidate.
    Returns a dict that can populate the Position + assessment.
    """
    legs_data = json.loads(candidate.legs) if candidate.legs else []
    net_metrics = json.loads(candidate.net_metrics) if candidate.net_metrics else {}
    pipeline_comp = json.loads(candidate.pipeline_components) if candidate.pipeline_components else {}
    claude_eval = json.loads(candidate.claude_evaluation) if candidate.claude_evaluation else {}

    # Build trade_structure from legs
    trade_structure = {
        "legs": legs_data,
        "structure": candidate.structure,
    }
    # Add expiration from first leg
    if legs_data:
        trade_structure["expiration"] = legs_data[0].get("expiration")

    # Build entry_greeks from first leg
    entry_greeks = {}
    if legs_data:
        first_leg = legs_data[0]
        entry_greeks = {
            "delta": first_leg.get("delta"),
            "gamma": None,
            "theta": None,
            "vega": None,
        }

    # Build claude_verdict from evaluation
    claude_verdict = None
    if claude_eval:
        claude_verdict = {
            "verdict": claude_eval.get("verdict"),
            "score": claude_eval.get("score"),
            "claude_read": claude_eval.get("claude_read"),
            "key_risks": claude_eval.get("key_risks", []),
            "thesis_invalidators": claude_eval.get("thesis_invalidators", []),
            "auto_pass_reason": claude_eval.get("auto_pass_reason"),
        }

    # Build claude_exit_levels from evaluation
    claude_exit_levels = claude_eval.get("exit_levels") if claude_eval else None

    return {
        "symbol": candidate.symbol,
        "strategy_key": candidate.scan_strategy_key or candidate.structure,
        "trade_structure": trade_structure,
        "entry_price": float(net_metrics.get("entry_price") or 0),
        "entry_greeks": entry_greeks,
        "entry_iv_rank": float(net_metrics.get("iv_rank") or 0),
        "entry_sma_alignment": {},
        "entry_underlying_price": float(candidate.underlying_spot) if candidate.underlying_spot else 0,
        "claude_score": claude_eval.get("score") if claude_eval else None,
        "claude_verdict": claude_verdict,
        "claude_exit_levels": claude_exit_levels,
        "claude_probability_matrix": None,
    }


def _validate_follow_gate(req) -> list[str]:
    """
    OTA-628: Validate follow/take payload. Returns list of failed check
    descriptions (empty list = all checks passed).
    """
    failed = []

    # 1. exit_levels must be present and non-empty
    if not req.claude_exit_levels:
        failed.append("claude_exit_levels is null or empty")

    # 2. verdict must be a canonical value
    verdict_data = req.claude_verdict or {}
    verdict = verdict_data.get("verdict")
    if verdict not in ("EXECUTE", "WAIT", "PASS"):
        failed.append(f"invalid verdict '{verdict}' — must be EXECUTE, WAIT, or PASS")

    # 3. entry_price must be positive
    if req.entry_price is None or req.entry_price <= 0:
        failed.append("entry_price is null or <= 0")

    # 4. auto_pass_reason must not be present
    auto_pass = verdict_data.get("auto_pass_reason")
    if auto_pass:
        failed.append(f"auto_pass_reason present: {auto_pass}")

    return failed


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/follow", response_model=PositionResponse, status_code=201)
async def follow_position(
    req: FollowPositionRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Create a paper-tracked position (source=PAPER, status=FOLLOWING).

    OTA-624: When trade_key is provided, reads the persisted trade snapshot
    from trade_candidates. Single transaction — no second UPDATE row.
    """
    _user_id = user.get("sub", "")
    if not _user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # OTA-624: Resolve trade_key to snapshot if provided
    if req.trade_key:
        candidate = await _resolve_trade_candidate(db, req.trade_key, _user_id)
        fields = _candidate_to_follow_fields(candidate)
        # Populate req fields from snapshot (user overrides win if provided)
        req.symbol = req.symbol or fields["symbol"]
        req.strategy_key = req.strategy_key or fields["strategy_key"]
        req.trade_structure = req.trade_structure or fields["trade_structure"]
        req.entry_price = req.entry_price if req.entry_price is not None else fields["entry_price"]
        req.entry_greeks = req.entry_greeks or fields["entry_greeks"]
        req.entry_iv_rank = req.entry_iv_rank if req.entry_iv_rank is not None else fields["entry_iv_rank"]
        req.entry_sma_alignment = req.entry_sma_alignment or fields["entry_sma_alignment"]
        req.entry_underlying_price = req.entry_underlying_price if req.entry_underlying_price is not None else fields["entry_underlying_price"]
        req.claude_score = req.claude_score if req.claude_score is not None else fields["claude_score"]
        req.claude_verdict = req.claude_verdict or fields["claude_verdict"]
        req.claude_exit_levels = req.claude_exit_levels or fields["claude_exit_levels"]
        req.claude_probability_matrix = req.claude_probability_matrix or fields["claude_probability_matrix"]
    else:
        # Legacy path: validate required fields are present
        if not req.symbol or not req.strategy_key or not req.trade_structure or req.entry_price is None:
            raise HTTPException(
                status_code=422,
                detail="trade_key or full trade payload (symbol, strategy_key, trade_structure, entry_price) required",
            )

    # OTA-628: Follow gate — reject disqualified payloads
    failed_checks = _validate_follow_gate(req)
    if failed_checks:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": f"Follow rejected: {', '.join(failed_checks)}",
                "code": "FOLLOW_GATE_FAIL",
                "failed_checks": failed_checks,
            },
        )

    # OTA-650: Validate strategy_key against eligible_strategies(spread)
    _ts = req.trade_structure or {}
    canonical_structure = _extract_canonical_structure(_ts)
    if canonical_structure and req.strategy_key:
        eligible = get_compatible_strategies(canonical_structure)
        if eligible and req.strategy_key not in eligible:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "incompatible_strategy",
                    "message": (
                        f"strategy_at_entry={req.strategy_key} not in "
                        f"eligible_strategies={eligible} for "
                        f"spread.trade_structure={canonical_structure}"
                    ),
                },
            )

    # OTA-557: ensure trade_structure always has expiration for auto-archive sweep
    if not _ts.get("expiration"):
        legs = _ts.get("legs")
        if legs and isinstance(legs, list) and len(legs) > 0:
            _ts["expiration"] = legs[0].get("expiration")

    pos = Position(
        user_id=_user_id,
        symbol=canonicalize(req.symbol),
        strategy_key=req.strategy_key,
        trade_structure=json.dumps(_ts),
        source="PAPER",
        status="FOLLOWING",
        entry_price=req.entry_price,
        entry_date=datetime.now(timezone.utc),
        entry_greeks=json.dumps(req.entry_greeks or {}),
        entry_iv_rank=req.entry_iv_rank,
        entry_sma_alignment=json.dumps(req.entry_sma_alignment or {}),
        entry_underlying_price=req.entry_underlying_price,
        claude_score=req.claude_score,
        claude_verdict=json.dumps(req.claude_verdict) if req.claude_verdict else None,
        claude_exit_levels=json.dumps(req.claude_exit_levels) if req.claude_exit_levels else None,
        claude_probability_matrix=json.dumps(req.claude_probability_matrix) if req.claude_probability_matrix else None,
        current_price=req.entry_price,
    )
    db.add(pos)
    await db.flush()  # populate position_id before creating assessment
    await _create_original_assessment(db, pos, req)
    await db.commit()
    await db.refresh(pos)
    log.info(f"follow_position: {pos.symbol} {pos.strategy_key} user={_user_id}")
    return _to_response(pos)


@router.post("/take", response_model=PositionResponse, status_code=201)
async def take_position(
    req: TakePositionRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Create a live position (source=LIVE, status=LIVE)."""
    _user_id = user.get("sub", "")
    if not _user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # OTA-624: Resolve trade_key to snapshot if provided
    if req.trade_key:
        candidate = await _resolve_trade_candidate(db, req.trade_key, _user_id)
        fields = _candidate_to_follow_fields(candidate)
        req.symbol = req.symbol or fields["symbol"]
        req.strategy_key = req.strategy_key or fields["strategy_key"]
        req.trade_structure = req.trade_structure or fields["trade_structure"]
        req.entry_price = req.entry_price if req.entry_price is not None else fields["entry_price"]
        req.entry_greeks = req.entry_greeks or fields["entry_greeks"]
        req.entry_iv_rank = req.entry_iv_rank if req.entry_iv_rank is not None else fields["entry_iv_rank"]
        req.entry_sma_alignment = req.entry_sma_alignment or fields["entry_sma_alignment"]
        req.entry_underlying_price = req.entry_underlying_price if req.entry_underlying_price is not None else fields["entry_underlying_price"]
        req.claude_score = req.claude_score if req.claude_score is not None else fields["claude_score"]
        req.claude_verdict = req.claude_verdict or fields["claude_verdict"]
        req.claude_exit_levels = req.claude_exit_levels or fields["claude_exit_levels"]
        req.claude_probability_matrix = req.claude_probability_matrix or fields["claude_probability_matrix"]
    else:
        if not req.symbol or not req.strategy_key or not req.trade_structure or req.entry_price is None:
            raise HTTPException(
                status_code=422,
                detail="trade_key or full trade payload required",
            )

    # OTA-650: Validate strategy_key against eligible_strategies(spread)
    _ts = req.trade_structure or {}
    canonical_structure = _extract_canonical_structure(_ts)
    if canonical_structure and req.strategy_key:
        eligible = get_compatible_strategies(canonical_structure)
        if eligible and req.strategy_key not in eligible:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "incompatible_strategy",
                    "message": (
                        f"strategy_at_entry={req.strategy_key} not in "
                        f"eligible_strategies={eligible} for "
                        f"spread.trade_structure={canonical_structure}"
                    ),
                },
            )

    # OTA-557: ensure trade_structure always has expiration for auto-archive sweep
    if not _ts.get("expiration"):
        legs = _ts.get("legs")
        if legs and isinstance(legs, list) and len(legs) > 0:
            _ts["expiration"] = legs[0].get("expiration")

    pos = Position(
        user_id=_user_id,
        symbol=canonicalize(req.symbol),
        strategy_key=req.strategy_key,
        trade_structure=json.dumps(_ts),
        source="LIVE",
        status="LIVE",
        entry_price=req.entry_price,
        entry_date=datetime.now(timezone.utc),
        entry_greeks=json.dumps(req.entry_greeks or {}),
        entry_iv_rank=req.entry_iv_rank,
        entry_sma_alignment=json.dumps(req.entry_sma_alignment or {}),
        entry_underlying_price=req.entry_underlying_price,
        claude_score=req.claude_score,
        claude_verdict=json.dumps(req.claude_verdict) if req.claude_verdict else None,
        claude_exit_levels=json.dumps(req.claude_exit_levels) if req.claude_exit_levels else None,
        claude_probability_matrix=json.dumps(req.claude_probability_matrix) if req.claude_probability_matrix else None,
        current_price=req.entry_price,
    )
    db.add(pos)
    await db.flush()  # populate position_id before creating assessment
    await _create_original_assessment(db, pos, req)
    await db.commit()
    await db.refresh(pos)
    log.info(f"take_position: {pos.symbol} {pos.strategy_key} user={_user_id}")
    return _to_response(pos)


@router.post("/{position_id}/reroute", response_model=PositionResponse)
async def reroute_position(
    position_id: str,
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    OTA-650: Re-route an orphaned position to its best_fit strategy.
    No request body — server computes best_fit from eligible_strategies(spread).
    Records audit trail (previous strategy_key + timestamp) in position metadata.
    """
    _user_id = user.get("sub", "")
    if not _user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == _user_id,
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    # Parse trade_structure and compute best_fit
    ts_raw = pos.trade_structure
    trade_struct = json.loads(ts_raw) if isinstance(ts_raw, str) else (ts_raw or {})
    canonical = _extract_canonical_structure(trade_struct)

    if not canonical:
        raise HTTPException(
            status_code=409,
            detail={"error": "no_eligible_strategy", "message": "cannot determine trade structure for this position"},
        )

    eligible = get_compatible_strategies(canonical)
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail={"error": "no_eligible_strategy", "message": "no compatible strategy for this position's spread"},
        )

    best_fit = eligible[0]
    previous_strategy = pos.strategy_key

    # Update strategy_key
    pos.strategy_key = best_fit
    pos.updated_at = datetime.now(timezone.utc)

    # Record audit trail in trade_structure metadata
    reroute_audit = trade_struct.get("_reroute_audit", [])
    reroute_audit.append({
        "previous_strategy": previous_strategy,
        "new_strategy": best_fit,
        "rerouted_at": datetime.now(timezone.utc).isoformat(),
    })
    trade_struct["_reroute_audit"] = reroute_audit
    pos.trade_structure = json.dumps(trade_struct)

    await db.commit()
    await db.refresh(pos)
    log.info(f"reroute_position: {pos.symbol} {previous_strategy} → {best_fit} user={_user_id}")
    return _to_response(pos)


@router.get("/symbols")
async def get_position_symbols(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Return distinct symbols with active (FOLLOWING or LIVE) position counts.
    Used by the SymbolSearch component to highlight Tier 1 (symbols with positions).

    Returns [{ symbol, position_count }] ordered by symbol. Empty array if none.
    """
    result = await db.execute(
        select(
            Position.symbol,
            func.count(Position.position_id).label("position_count"),
        )
        .where(
            and_(
                Position.user_id == user["sub"],
                Position.status.in_(["FOLLOWING", "LIVE"]),
            )
        )
        .group_by(Position.symbol)
        .order_by(Position.symbol)
    )
    rows = result.all()
    return [{"symbol": row.symbol, "position_count": row.position_count} for row in rows]


@router.get("/aggregate")
async def get_aggregate(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    strategy_key: Optional[str] = Query(None),
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregate stats only (no position list)."""
    stmt = _apply_filters(
        select(Position), user["sub"], status, source, symbol, strategy_key
    ).order_by(Position.entry_date.desc())
    result = await db.execute(stmt)
    positions = result.scalars().all()
    return _build_aggregate(list(positions))


@router.get("", response_model=PositionListResponse)
async def list_positions(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    strategy_key: Optional[str] = Query(None),
    include_archived: bool = Query(False, description="Include ARCHIVED positions (default: excluded)"),
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """List positions with composable filters. Returns positions + aggregate stats.
    ARCHIVED positions are excluded by default; pass include_archived=true to include them."""
    stmt = _apply_filters(
        select(Position), user["sub"], status, source, symbol, strategy_key
    )
    if not include_archived:
        stmt = stmt.where(Position.status != "ARCHIVED")
    stmt = stmt.order_by(Position.entry_date.desc())
    result = await db.execute(stmt)
    positions = list(result.scalars().all())

    return PositionListResponse(
        positions=[_to_response(p) for p in positions],
        total=len(positions),
        aggregate=_build_aggregate(positions),
    )


@router.post("/update-health-grades")
async def update_health_grades(
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    Recompute health grades for all open positions belonging to the current user.
    Called by the scheduler daily after market close. Also callable on-demand via Swagger.

    Full path: POST /api/v1/positions/update-health-grades
    """
    result = await db.execute(
        select(Position).where(
            Position.user_id == user["sub"],
            Position.status.in_(["FOLLOWING", "LIVE"]),
        )
    )
    positions = list(result.scalars().all())
    if not positions:
        return {"updated": 0, "errors": []}

    # Batch-fetch quotes for unique symbols
    symbols = list({p.symbol for p in positions})
    provider = _get_provider()
    quotes: dict[str, float] = {}
    for sym in symbols:
        try:
            api_sym = to_api_symbol_cached(sym, "schwab")
            q = await provider.get_quote(api_sym)
            quotes[sym] = q.get("price")
        except Exception as exc:
            log.warning(f"update_health_grades: quote error for {sym}: {exc}")

    updated = 0
    errors = []
    for pos in positions:
        current_price = quotes.get(pos.symbol)
        if current_price is None:
            errors.append({"position_id": pos.position_id, "symbol": pos.symbol, "reason": "quote unavailable"})
            continue
        try:
            grade = compute_health_grade(
                entry_price=float(pos.entry_price) if pos.entry_price is not None else 0.0,
                current_price=current_price,
                claude_exit_levels_json=pos.claude_exit_levels,
            )
            pos.health_grade = grade
            pos.updated_at = datetime.now(timezone.utc)
            updated += 1
        except Exception as exc:
            errors.append({"position_id": pos.position_id, "symbol": pos.symbol, "reason": str(exc)})

    await db.commit()
    log.info(f"update_health_grades: {updated} updated, {len(errors)} errors — user={user['sub']}")
    return {"updated": updated, "errors": errors}


@router.get("/current-prices")
async def get_current_prices(
    position_ids: str = Query(..., description="Comma-separated position UUIDs"),
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch live underlying quotes and compute current P&L for a batch of positions.
    Updates current_price and current_pnl on each position row.
    Returns perf_status: 'green' | 'amber' | 'red' | 'unknown'.
    """
    ids = [pid.strip() for pid in position_ids.split(",") if pid.strip()]
    if not ids:
        return []

    result = await db.execute(
        select(Position).where(
            Position.position_id.in_(ids),
            Position.user_id == user["sub"],
        )
    )
    positions = {p.position_id: p for p in result.scalars().all()}

    provider = _get_provider()
    responses: list[PositionCurrentPrice] = []

    for pid in ids:
        pos = positions.get(pid)
        if not pos:
            responses.append(PositionCurrentPrice(
                position_id=pid, perf_status="unknown", error="Position not found"
            ))
            continue

        entry_price = float(pos.entry_price) if pos.entry_price is not None else 0.0
        exit_levels_raw = pos.claude_exit_levels
        exit_levels = None
        if exit_levels_raw:
            try:
                exit_levels = json.loads(exit_levels_raw) if isinstance(exit_levels_raw, str) else exit_levels_raw
            except (ValueError, TypeError):
                pass

        current_premium: Optional[float] = None
        underlying_price: Optional[float] = None

        if provider is None:
            responses.append(PositionCurrentPrice(
                position_id=pid, perf_status="unknown", error="Market data provider not available"
            ))
            continue

        try:
            # Fetch underlying quote
            api_sym = to_api_symbol_cached(pos.symbol, "schwab")
            quote = await provider.get_quote(api_sym)
            underlying_price = quote.get("price") if isinstance(quote, dict) else getattr(quote, "price", None)

            # Determine if this is a spread or single leg
            ts_raw = pos.trade_structure
            trade_struct = json.loads(ts_raw) if isinstance(ts_raw, str) else (ts_raw or {})
            legs = trade_struct.get("legs", [])

            if len(legs) >= 2:
                # Spread: fetch option chain and compute net mid
                expiration = trade_struct.get("expiration") or (legs[0].get("expiration") if legs else None)
                try:
                    chain_resp = await provider.get_option_chain(api_sym, expiration=expiration)
                    contracts = (
                        chain_resp.get("contracts", []) if isinstance(chain_resp, dict)
                        else getattr(chain_resp, "contracts", [])
                    )
                    # Build lookup: (strike, option_type) → mid
                    contract_map = {}
                    for c in contracts:
                        if isinstance(c, dict):
                            k = (float(c.get("strike", 0)), c.get("option_type", "").lower())
                            mid = c.get("mid") or ((c.get("bid", 0) + c.get("ask", 0)) / 2)
                        else:
                            k = (float(getattr(c, "strike", 0)), getattr(c, "option_type", "").lower())
                            mid = getattr(c, "mid", None) or ((getattr(c, "bid", 0) + getattr(c, "ask", 0)) / 2)
                        contract_map[k] = float(mid or 0)

                    net_mid = 0.0
                    for leg in legs:
                        k = (float(leg.get("strike", 0)), leg.get("option_type", "").lower())
                        mid = contract_map.get(k, 0.0)
                        if leg.get("side", "").lower() == "long":
                            net_mid += mid
                        else:
                            net_mid -= mid
                    current_premium = abs(net_mid)
                except Exception as chain_err:
                    log.warning(f"current_prices: chain fetch failed for {pos.symbol}: {chain_err}")

            elif len(legs) == 1:
                # Single leg (naked option): find the contract
                leg = legs[0]
                expiration = leg.get("expiration") or trade_struct.get("expiration")
                try:
                    chain_resp = await provider.get_option_chain(api_sym, expiration=expiration)
                    contracts = (
                        chain_resp.get("contracts", []) if isinstance(chain_resp, dict)
                        else getattr(chain_resp, "contracts", [])
                    )
                    target_strike = float(leg.get("strike", 0))
                    target_type = leg.get("option_type", "").lower()
                    for c in contracts:
                        if isinstance(c, dict):
                            s = float(c.get("strike", 0))
                            t = c.get("option_type", "").lower()
                            mid = c.get("mid") or ((c.get("bid", 0) + c.get("ask", 0)) / 2)
                        else:
                            s = float(getattr(c, "strike", 0))
                            t = getattr(c, "option_type", "").lower()
                            mid = getattr(c, "mid", None) or ((getattr(c, "bid", 0) + getattr(c, "ask", 0)) / 2)
                        if s == target_strike and t == target_type:
                            current_premium = float(mid or 0)
                            break
                except Exception as chain_err:
                    log.warning(f"current_prices: chain fetch failed for {pos.symbol}: {chain_err}")

        except Exception as e:
            log.warning(f"current_prices: quote fetch failed for {pos.symbol}: {e}")
            responses.append(PositionCurrentPrice(
                position_id=pid, perf_status="unknown", error=str(e)
            ))
            continue

        # Compute P&L
        current_pnl: Optional[float] = None
        pnl_pct: Optional[float] = None
        if current_premium is not None and entry_price != 0:
            current_pnl = current_premium - entry_price
            pnl_pct = current_pnl / entry_price

        perf = _perf_status(current_pnl, underlying_price, exit_levels)

        # Persist updates
        if current_premium is not None:
            pos.current_price = current_premium
        if current_pnl is not None:
            pos.current_pnl = current_pnl
        pos.last_monitored_at = datetime.now(timezone.utc)
        pos.updated_at = datetime.now(timezone.utc)

        responses.append(PositionCurrentPrice(
            position_id=pid,
            current_premium=current_premium,
            current_pnl=current_pnl,
            pnl_pct=pnl_pct,
            perf_status=perf,
        ))

    await db.commit()
    return responses


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return a single position by ID."""
    result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == user["sub"],
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return _to_response(pos)


@router.post("/{position_id}/health", response_model=PositionResponse)
async def refresh_health(
    position_id: str,
    current_price: Optional[float] = None,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Recompute health grade for an open position.
    Optionally accepts current_price to update mark-to-market first.
    Called on-demand from UI or by the Position Monitor Agent.
    """
    result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == user["sub"],
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    if current_price is not None:
        entry = float(pos.entry_price) if pos.entry_price is not None else 0.0
        pos.current_price = current_price
        pos.current_pnl = current_price - entry
        pos.last_monitored_at = datetime.now(timezone.utc)

    grade = compute_health_grade(
        entry_price=float(pos.entry_price) if pos.entry_price is not None else 0.0,
        current_price=float(pos.current_price) if pos.current_price is not None else None,
        claude_exit_levels_json=pos.claude_exit_levels,
    )
    pos.health_grade = grade
    pos.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pos)
    log.info(f"refresh_health: {pos.symbol} grade={grade} user={user['sub']}")
    return _to_response(pos)


@router.post("/{position_id}/refresh", response_model=PositionRefreshResponse)
async def refresh_position(
    position_id: str,
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-evaluate an open position with current market data and Claude.

    Prompts: POSITION_REFRESH_SYSTEM (system) + POSITION_REFRESH_USER (user)
    from app/skills/claude-trade-agent/SKILL.md — "Position Refresh Assessment" section.

    Flow:
    1. Load position (must be FOLLOWING or LIVE)
    2. Fetch current quote + option chain marks
    3. Build POSITION_REFRESH_USER prompt via skill.render() with prior assessment history
    4. Call Claude (POSITION_REFRESH_SYSTEM) → verdict / score / synopsis / exit_levels
    5. Write new PositionAssessment row (type=UPDATE, version=max+1)
    6. Update position current_price / current_pnl / last_monitored_at
    7. Write agent_run_log (non-blocking — failures are logged, not raised)
    """
    from app.skills.skill_loader import get_skill
    from app.analysis.strategy_definitions import STRATEGIES
    from app.models.database import AgentRunLog

    from app.core.config import settings as _settings
    user_id = None if _settings.skip_auth else (user.get("sub") or None)

    # 1. Load position
    result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == user["sub"],
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    if pos.status in ("ARCHIVED", "CLOSED"):
        raise HTTPException(status_code=400, detail=f"Cannot refresh an {pos.status.lower()} position")

    # 2. Check eval adapter
    adapter = _get_eval_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="AI evaluation provider not configured")

    # 3. Check market data provider
    provider = _get_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail="Market data unavailable — Schwab not connected")

    # 4. Fetch current market data
    ts_raw = pos.trade_structure
    trade_struct = json.loads(ts_raw) if isinstance(ts_raw, str) else (ts_raw or {})
    legs = trade_struct.get("legs", [])

    current_premium: Optional[float] = None
    underlying_price: Optional[float] = None
    iv_approx: Optional[float] = None

    try:
        api_sym = to_api_symbol_cached(pos.symbol, "schwab")
        quote = await provider.get_quote(api_sym)
        underlying_price = quote.get("price") if isinstance(quote, dict) else getattr(quote, "price", None)
        iv_approx = quote.get("implied_volatility") if isinstance(quote, dict) else getattr(quote, "implied_volatility", None)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Market data fetch failed: {e}")

    # Fetch option chain for spread/leg marks
    expiration = trade_struct.get("expiration") or (legs[0].get("expiration") if legs else None)
    if legs and expiration:
        try:
            chain_resp = await provider.get_option_chain(api_sym, expiration=expiration)
            contracts = (
                chain_resp.get("contracts", []) if isinstance(chain_resp, dict)
                else getattr(chain_resp, "contracts", [])
            )
            # Build mid lookup
            contract_map: dict = {}
            for c in contracts:
                if isinstance(c, dict):
                    k = (float(c.get("strike", 0)), c.get("option_type", "").lower())
                    iv_approx = iv_approx or c.get("implied_volatility")
                    mid = c.get("mid") or ((c.get("bid", 0) + c.get("ask", 0)) / 2)
                else:
                    k = (float(getattr(c, "strike", 0)), getattr(c, "option_type", "").lower())
                    iv_approx = iv_approx or getattr(c, "implied_volatility", None)
                    mid = getattr(c, "mid", None) or ((getattr(c, "bid", 0) + getattr(c, "ask", 0)) / 2)
                contract_map[k] = float(mid or 0)

            if len(legs) >= 2:
                net_mid = 0.0
                for leg in legs:
                    k = (float(leg.get("strike", 0)), leg.get("option_type", "").lower())
                    m = contract_map.get(k, 0.0)
                    net_mid += m if leg.get("side", "").lower() == "long" else -m
                current_premium = abs(net_mid)
            elif len(legs) == 1:
                leg = legs[0]
                k = (float(leg.get("strike", 0)), leg.get("option_type", "").lower())
                current_premium = contract_map.get(k)
        except Exception as chain_err:
            log.warning(f"refresh_position: chain fetch failed for {pos.symbol}: {chain_err}")

    # 5. Load prior assessments
    assess_result = await db.execute(
        select(PositionAssessment)
        .where(PositionAssessment.position_id == position_id)
        .order_by(PositionAssessment.version_number)
    )
    prior_assessments = list(assess_result.scalars().all())
    next_version = (max(a.version_number for a in prior_assessments) + 1) if prior_assessments else 1

    # 6. Build prompt and call Claude
    strategy_def = STRATEGIES.get(pos.strategy_key)
    strategy_label = strategy_def.label if strategy_def else pos.strategy_key
    current_date_str = datetime.now(timezone.utc).strftime("%m-%d-%Y")
    current_market_data = {
        "date": current_date_str,
        "underlying_price": underlying_price,
        "spread_mark": current_premium,
        "iv": round(iv_approx, 4) if iv_approx else None,
    }

    skill = get_skill("claude-trade-agent")
    system_prompt = skill.get("POSITION_REFRESH_SYSTEM")

    # Build prior_assessments block (pre-formatted, injected as a single variable)
    if prior_assessments:
        pa_lines = []
        for i, a in enumerate(sorted(prior_assessments, key=lambda x: x.version_number), 1):
            date_str = a.created_at.strftime("%m-%d-%Y") if a.created_at else "N/A"
            pa_lines.append(f"Assessment {i} ({date_str}):")
            pa_lines.append(f"  Verdict: {a.verdict} | Score: {a.score}")
            if a.synopsis:
                pa_lines.append(f"  Synopsis: {a.synopsis}")
            pa_lines.append(f"  Claude's Read: {a.claude_read}")
        prior_assessments_block = "\n".join(pa_lines)
    else:
        prior_assessments_block = "No prior assessments — this is the first review."

    # Build optional SMA context line
    entry_sma = json.loads(pos.entry_sma_alignment) if isinstance(pos.entry_sma_alignment, str) and pos.entry_sma_alignment else (pos.entry_sma_alignment or {})
    if entry_sma:
        sma_ctx = (
            f"Entry SMA Alignment: SMA8={entry_sma.get('sma_8','N/A')} | "
            f"SMA21={entry_sma.get('sma_21','N/A')} | SMA50={entry_sma.get('sma_50','N/A')} | "
            f"Trend={entry_sma.get('alignment', entry_sma.get('ma_alignment','N/A'))}\n"
        )
    else:
        sma_ctx = ""

    user_message = skill.render(
        "POSITION_REFRESH_USER",
        symbol=pos.symbol,
        strategy_label=strategy_label,
        entry_date=pos.entry_date.strftime("%m-%d-%Y") if pos.entry_date else "N/A",
        entry_underlying_price=pos.entry_underlying_price or "N/A",
        entry_price=pos.entry_price or "N/A",
        entry_iv_rank=pos.entry_iv_rank or "N/A",
        trade_structure=json.dumps(trade_struct, indent=2),
        current_date=current_date_str,
        current_price=underlying_price or "N/A",
        spread_mark=current_premium or "N/A",
        current_iv=round(iv_approx, 4) if iv_approx else "N/A",
        sma_context=sma_ctx,
        prior_assessments=prior_assessments_block,
    )

    import uuid as _uuid
    run_id = str(_uuid.uuid4())
    try:
        result_ai = await adapter.chat(system_prompt, user_message, max_tokens=1200)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI evaluation failed: {e}")

    raw_text = result_ai.get("text", "") if isinstance(result_ai, dict) else str(result_ai)
    card = _try_parse_refresh_card(raw_text)

    # Retry once on parse failure
    if card is None:
        try:
            retry = await adapter.chat(
                system_prompt,
                user_message,
                max_tokens=1200,
                extra_messages=[
                    {"role": "assistant", "content": raw_text},
                    {
                        "role": "user",
                        "content": (
                            "Your response was not valid JSON. "
                            "Return ONLY a single JSON object matching the POSITION_REFRESH_SYSTEM schema. "
                            "No preamble, no markdown fences, no explanation."
                        ),
                    },
                ],
            )
            raw_text = retry.get("text", "") if isinstance(retry, dict) else str(retry)
            card = _try_parse_refresh_card(raw_text)
        except Exception:
            pass

    if card is None:
        raise HTTPException(
            status_code=502,
            detail="AI returned malformed JSON for position refresh after retry.",
        )

    # Enforce verdict band
    score = int(card.get("score", 0))
    if score >= 70:
        verdict = "EXECUTE"
    elif score >= 50:
        verdict = "WAIT"
    else:
        verdict = "PASS"

    synopsis = card.get("synopsis") or ""
    claude_read = card.get("claude_read", "")
    exit_levels_dict = card.get("exit_levels") or {}

    # 7. Write new PositionAssessment row
    market_snap = {
        "underlying_price": underlying_price,
        "iv": iv_approx,
        "spread_mark": current_premium,
    }
    new_assessment = PositionAssessment(
        position_id=position_id,
        version_number=next_version,
        assessment_type="UPDATE",
        verdict=verdict,
        score=score,
        synopsis=synopsis,
        claude_read=claude_read,
        exit_levels=json.dumps(exit_levels_dict) if exit_levels_dict else None,
        market_snapshot=json.dumps(market_snap),
        agent_run_id=run_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_assessment)

    # 8. Update position current values
    entry_price = float(pos.entry_price) if pos.entry_price is not None else 0.0
    if current_premium is not None:
        pos.current_price = current_premium
        pos.current_pnl = current_premium - entry_price
    pos.last_monitored_at = datetime.now(timezone.utc)
    pos.updated_at = datetime.now(timezone.utc)

    # OTA-630: Mirror assessment verdict/score/exit_levels to parent positions row
    pos.claude_verdict = json.dumps({"verdict": verdict, "score": score, "synopsis": synopsis, "claude_read": claude_read})
    pos.claude_score = score
    if exit_levels_dict:
        pos.claude_exit_levels = json.dumps(exit_levels_dict)

    # 9. Write agent_run_log (non-blocking — catch any failures)
    try:
        db.add(AgentRunLog(
            run_id=run_id,
            agent_name="claude-trade-agent",
            stage="position_refresh",
            symbol=pos.symbol,
            user_id=user_id,
            prompt_system=system_prompt,
            prompt_user=user_message,
            prompt_version=skill.prompt_version,
            market_snapshot=current_market_data,
            trade_snapshot={"position_id": position_id, "strategy_key": pos.strategy_key},
            model_response_raw=raw_text,
            verdict=verdict,
            verdict_summary=synopsis,
            input_tokens=result_ai.get("input_tokens", 0) if isinstance(result_ai, dict) else 0,
            output_tokens=result_ai.get("output_tokens", 0) if isinstance(result_ai, dict) else 0,
            model_name=result_ai.get("model", "") if isinstance(result_ai, dict) else "",
            created_at=datetime.now(timezone.utc),
        ))
    except Exception as log_err:
        log.warning(f"refresh_position: agent_run_log write failed (non-fatal): {log_err}")

    await db.commit()
    await db.refresh(new_assessment)

    log.info(f"refresh_position: {pos.symbol} v{next_version} verdict={verdict} score={score} user={user['sub']}")

    # Build response
    current_pnl = float(pos.current_pnl) if pos.current_pnl is not None else 0.0
    current_prem = float(current_premium) if current_premium is not None else entry_price
    pnl_pct = (current_prem - entry_price) / entry_price if entry_price else 0.0

    def _parse_json_field(raw) -> Optional[dict]:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    return PositionRefreshResponse(
        assessment=PositionAssessmentResponse(
            assessment_id=new_assessment.assessment_id,
            position_id=new_assessment.position_id,
            version_number=new_assessment.version_number,
            assessment_type=new_assessment.assessment_type,
            verdict=new_assessment.verdict,
            score=new_assessment.score,
            synopsis=new_assessment.synopsis,
            claude_read=new_assessment.claude_read,
            exit_levels=_parse_json_field(new_assessment.exit_levels),
            market_snapshot=_parse_json_field(new_assessment.market_snapshot),
            agent_run_id=new_assessment.agent_run_id,
            created_at=new_assessment.created_at,
        ),
        current_premium=current_prem,
        current_pnl=current_pnl,
        pnl_pct=round(pnl_pct, 4),
        perf_status=_perf_status(current_pnl, underlying_price, exit_levels_dict or None),
    )


@router.patch("/{position_id}/close", response_model=PositionResponse)
async def close_position(
    position_id: str,
    req: ClosePositionRequest,
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """Close a position, record exit data and compute outcome P&L."""
    result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == user["sub"],
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    if pos.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Position is already closed")

    entry_price = float(pos.entry_price) if pos.entry_price is not None else 0.0
    outcome_pnl = (req.exit_price - entry_price) * 100  # 1 contract = 100 multiplier

    pos.status = "CLOSED"
    pos.exit_price = req.exit_price
    pos.exit_date = datetime.now(timezone.utc)
    pos.exit_reason = req.exit_reason.upper()
    pos.outcome_pnl = outcome_pnl
    pos.current_price = req.exit_price
    pos.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pos)
    log.info(f"close_position: {pos.symbol} exit_reason={pos.exit_reason} pnl={outcome_pnl:.2f} user={user['sub']}")
    return _to_response(pos)


@router.patch("/{position_id}/archive", response_model=PositionResponse)
async def archive_position(
    position_id: str,
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    Archive a position (status → ARCHIVED). Use for expired or manually shelved
    positions. Archived positions are excluded from the default list view.
    Different from CLOSED: no P&L recorded, no exit price required.
    """
    result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == user["sub"],
        )
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    if pos.status in ("CLOSED", "ARCHIVED"):
        raise HTTPException(status_code=409, detail=f"Position is already {pos.status.lower()}")

    pos.status = "ARCHIVED"
    pos.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pos)
    log.info(f"archive_position: {pos.symbol} user={user['sub']}")
    return _to_response(pos)


@router.get("/{position_id}/assessments", response_model=list[PositionAssessmentResponse])
async def list_assessments(
    position_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return all Claude assessments for a position, newest first."""
    # Verify the position belongs to this user
    pos_result = await db.execute(
        select(Position).where(
            Position.position_id == position_id,
            Position.user_id == user["sub"],
        )
    )
    if not pos_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Position not found")

    result = await db.execute(
        select(PositionAssessment)
        .where(PositionAssessment.position_id == position_id)
        .order_by(PositionAssessment.created_at.desc())
    )
    assessments = result.scalars().all()

    def _parse(raw) -> Optional[dict]:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    return [
        PositionAssessmentResponse(
            assessment_id=a.assessment_id,
            position_id=a.position_id,
            version_number=a.version_number,
            assessment_type=a.assessment_type,
            verdict=a.verdict,
            score=a.score,
            synopsis=a.synopsis,
            claude_read=a.claude_read,
            exit_levels=_parse(a.exit_levels),
            market_snapshot=_parse(a.market_snapshot),
            agent_run_id=a.agent_run_id,
            created_at=a.created_at,
        )
        for a in assessments
    ]
