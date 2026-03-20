"""
Position Tracking API (Phase 2.10)

Five endpoints:
  POST   /api/v1/positions/follow          — Create paper position (FOLLOWING)
  POST   /api/v1/positions/take            — Create live position (LIVE)
  GET    /api/v1/positions                 — List with composable filters
  GET    /api/v1/positions/aggregate       — Aggregate stats only
  PATCH  /api/v1/positions/{id}/close      — Close and record outcome
  GET    /api/v1/positions/{id}            — Single position detail

Auth tiers:
  - All read endpoints: Tier 1 (require_read)
  - Follow/Take/Close:  Tier 2 (require_write)
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
from app.models.database import Position
from app.models.schemas import (
    FollowPositionRequest,
    TakePositionRequest,
    ClosePositionRequest,
    PositionResponse,
    PositionListResponse,
)
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
        current_price=current_price,
        current_pnl=float(pos.current_pnl) if pos.current_pnl is not None else None,
        health_grade=grade,
        claude_score=pos.claude_score,
        claude_verdict=_parse_json_field(pos.claude_verdict),
        claude_exit_levels=_parse_json_field(pos.claude_exit_levels),
        claude_probability_matrix=_parse_json_field(pos.claude_probability_matrix),
        days_held=_days_held(pos.entry_date, pos.exit_date),
        dte_at_entry=_dte_at_entry(trade_struct, pos.entry_date),
        trade_structure=trade_struct,
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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/follow", response_model=PositionResponse, status_code=201)
async def follow_position(
    req: FollowPositionRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Create a paper-tracked position (source=PAPER, status=FOLLOWING)."""
    _sub = user.get("sub", "")
    _user_id = _sub if (len(_sub) == 36 and "-" in _sub) else None
    if _user_id is None:
        raise HTTPException(status_code=401, detail="A real user account is required to create positions. Disable SKIP_AUTH and log in.")

    pos = Position(
        user_id=_user_id,
        symbol=req.symbol.upper(),
        strategy_key=req.strategy_key,
        trade_structure=json.dumps(req.trade_structure),
        source="PAPER",
        status="FOLLOWING",
        entry_price=req.entry_price,
        entry_date=datetime.now(timezone.utc),
        entry_greeks=json.dumps(req.entry_greeks),
        entry_iv_rank=req.entry_iv_rank,
        entry_sma_alignment=json.dumps(req.entry_sma_alignment),
        entry_underlying_price=req.entry_underlying_price,
        claude_score=req.claude_score,
        claude_verdict=json.dumps(req.claude_verdict) if req.claude_verdict else None,
        claude_exit_levels=json.dumps(req.claude_exit_levels) if req.claude_exit_levels else None,
        claude_probability_matrix=json.dumps(req.claude_probability_matrix) if req.claude_probability_matrix else None,
        current_price=req.entry_price,
    )
    db.add(pos)
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
    _sub = user.get("sub", "")
    _user_id = _sub if (len(_sub) == 36 and "-" in _sub) else None
    if _user_id is None:
        raise HTTPException(status_code=401, detail="A real user account is required to create positions. Disable SKIP_AUTH and log in.")

    pos = Position(
        user_id=_user_id,
        symbol=req.symbol.upper(),
        strategy_key=req.strategy_key,
        trade_structure=json.dumps(req.trade_structure),
        source="LIVE",
        status="LIVE",
        entry_price=req.entry_price,
        entry_date=datetime.now(timezone.utc),
        entry_greeks=json.dumps(req.entry_greeks),
        entry_iv_rank=req.entry_iv_rank,
        entry_sma_alignment=json.dumps(req.entry_sma_alignment),
        entry_underlying_price=req.entry_underlying_price,
        claude_score=req.claude_score,
        claude_verdict=json.dumps(req.claude_verdict) if req.claude_verdict else None,
        claude_exit_levels=json.dumps(req.claude_exit_levels) if req.claude_exit_levels else None,
        claude_probability_matrix=json.dumps(req.claude_probability_matrix) if req.claude_probability_matrix else None,
        current_price=req.entry_price,
    )
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    log.info(f"take_position: {pos.symbol} {pos.strategy_key} user={_user_id}")
    return _to_response(pos)


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
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """List positions with composable filters. Returns positions + aggregate stats."""
    stmt = _apply_filters(
        select(Position), user["sub"], status, source, symbol, strategy_key
    ).order_by(Position.entry_date.desc())
    result = await db.execute(stmt)
    positions = list(result.scalars().all())

    return PositionListResponse(
        positions=[_to_response(p) for p in positions],
        total=len(positions),
        aggregate=_build_aggregate(positions),
    )


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
