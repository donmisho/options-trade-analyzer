# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.

"""
Named Watchlists API — OTA-444, OTA-445

Endpoints:
  GET    /api/v1/watchlists                                  — List all watchlists (lazy-creates default)
  POST   /api/v1/watchlists                                  — Create a new watchlist
  GET    /api/v1/watchlists/sources                          — Scan source options (watchlists + builtins)
  PUT    /api/v1/watchlists/{watchlist_id}                   — Rename a watchlist
  DELETE /api/v1/watchlists/{watchlist_id}                   — Delete a watchlist (not default)
  GET    /api/v1/watchlists/{watchlist_id}/symbols           — List symbols in a watchlist
  POST   /api/v1/watchlists/{watchlist_id}/symbols           — Add a symbol (with Schwab validation)
  DELETE /api/v1/watchlists/{watchlist_id}/symbols/{symbol}  — Remove a symbol

IMPORTANT — route ordering: /sources is registered before /{watchlist_id} so that
"sources" is never mistakenly treated as a watchlist_id path parameter.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.services.symbol_cache import to_api_symbol_cached
from app.models.session import get_db
from app.models.database import NamedWatchlist, WatchlistEntry, Position
from app.models.schemas import (
    NamedWatchlistCreate,
    NamedWatchlistRename,
    NamedWatchlistSymbolAdd,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlists", tags=["Named Watchlists"])

_provider_factory = None


def init_named_watchlist_routes(provider_factory) -> None:
    global _provider_factory
    _provider_factory = provider_factory


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _ensure_default(user_id: str, db: AsyncSession) -> list:
    """Return all watchlists for user; lazy-create 'My Watchlist' if none exist."""
    result = await db.execute(
        select(NamedWatchlist)
        .where(NamedWatchlist.user_id == user_id)
        .order_by(NamedWatchlist.is_default.desc(), NamedWatchlist.created_at)
    )
    watchlists = result.scalars().all()
    if not watchlists:
        default = NamedWatchlist(user_id=user_id, name="My Watchlist", is_default=True)
        db.add(default)
        await db.commit()
        await db.refresh(default)
        watchlists = [default]
    return watchlists


async def _symbol_counts(watchlists: list, db: AsyncSession) -> list[dict]:
    """Attach symbol_count to each watchlist dict — single GROUP BY query."""
    if not watchlists:
        return []
    wl_ids = [wl.id for wl in watchlists]
    counts_result = await db.execute(
        select(WatchlistEntry.watchlist_id, func.count(WatchlistEntry.id).label("cnt"))
        .where(WatchlistEntry.watchlist_id.in_(wl_ids))
        .group_by(WatchlistEntry.watchlist_id)
    )
    counts_map = {row.watchlist_id: row.cnt for row in counts_result.all()}
    return [
        {
            "id": wl.id,
            "name": wl.name,
            "is_default": bool(wl.is_default),
            "symbol_count": counts_map.get(wl.id, 0),
            "created_at": wl.created_at,
            "updated_at": wl.updated_at,
        }
        for wl in watchlists
    ]


async def _get_watchlist_or_404(watchlist_id: str, user_id: str, db: AsyncSession):
    result = await db.execute(
        select(NamedWatchlist).where(
            NamedWatchlist.id == watchlist_id,
            NamedWatchlist.user_id == user_id,
        )
    )
    wl = result.scalar_one_or_none()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return wl


# ── GET /watchlists ───────────────────────────────────────────────────────────

@router.get("")
async def list_watchlists(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return all watchlists for the user. Creates 'My Watchlist' on first call."""
    watchlists = await _ensure_default(user["sub"], db)
    return await _symbol_counts(watchlists, db)


# ── GET /watchlists/sources  (must be before /{watchlist_id}) ────────────────

@router.get("/sources")
async def get_scan_sources(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns available scan sources for the Security Strategies page.

    Response:
      watchlists: [{id, name, symbol_count}]
      builtin:    [{id: "all-positions", name: "All Positions", symbol_count: N}]
    """
    watchlists = await _ensure_default(user["sub"], db)
    wl_items = await _symbol_counts(watchlists, db)

    pos_count = (
        await db.execute(
            select(func.count(func.distinct(Position.symbol))).where(
                Position.user_id == user["sub"],
                Position.status.in_(["FOLLOWING", "LIVE"]),
            )
        )
    ).scalar() or 0

    return {
        "watchlists": [
            {"id": w["id"], "name": w["name"], "symbol_count": w["symbol_count"]}
            for w in wl_items
        ],
        "builtin": [
            {"id": "all-positions", "name": "All Positions", "symbol_count": pos_count}
        ],
    }


# ── POST /watchlists ──────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_watchlist(
    payload: NamedWatchlistCreate,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Create a new named watchlist for the authenticated user."""
    wl = NamedWatchlist(
        user_id=user["sub"],
        name=payload.name.strip(),
        is_default=False,
    )
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    return {
        "id": wl.id,
        "name": wl.name,
        "is_default": False,
        "symbol_count": 0,
        "created_at": wl.created_at,
    }


# ── PUT /watchlists/{watchlist_id} ────────────────────────────────────────────

@router.put("/{watchlist_id}")
async def rename_watchlist(
    watchlist_id: str,
    payload: NamedWatchlistRename,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Rename a watchlist. Must belong to the authenticated user."""
    wl = await _get_watchlist_or_404(watchlist_id, user["sub"], db)
    wl.name = payload.name.strip()
    wl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": wl.id, "name": wl.name, "updated_at": wl.updated_at}


# ── DELETE /watchlists/{watchlist_id} ─────────────────────────────────────────

@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Delete a watchlist and all its symbols. Cannot delete the default watchlist."""
    wl = await _get_watchlist_or_404(watchlist_id, user["sub"], db)
    if wl.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default watchlist")
    await db.delete(wl)  # cascade handles watchlist_symbols
    await db.commit()


# ── GET /watchlists/{watchlist_id}/symbols ────────────────────────────────────

@router.get("/{watchlist_id}/symbols")
async def list_symbols(
    watchlist_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return all symbols in a watchlist, ordered by most recently added."""
    await _get_watchlist_or_404(watchlist_id, user["sub"], db)
    result = await db.execute(
        select(WatchlistEntry)
        .where(WatchlistEntry.watchlist_id == watchlist_id)
        .order_by(WatchlistEntry.added_at.desc())
    )
    entries = result.scalars().all()
    return [{"symbol": e.symbol, "added_at": e.added_at} for e in entries]


# ── POST /watchlists/{watchlist_id}/symbols ───────────────────────────────────

@router.post("/{watchlist_id}/symbols")
async def add_symbol(
    watchlist_id: str,
    payload: NamedWatchlistSymbolAdd,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a symbol to a watchlist.

    Validates the symbol via Schwab quote lookup. Duplicate adds return 200
    with the existing record — no error.
    """
    await _get_watchlist_or_404(watchlist_id, user["sub"], db)
    symbol = payload.symbol.upper().strip()

    # ── Symbol validation via market data provider ────────────────────
    if _provider_factory is not None:
        from app.core.config import settings
        try:
            provider = _provider_factory.get_market_data(
                settings.default_market_data_provider,
                user_id=user.get("sub"),
            )
            api_sym = to_api_symbol_cached(symbol, "schwab")
            quote = await provider.get_quote(api_sym)
            if not quote or not quote.get("price"):
                raise HTTPException(status_code=400, detail=f"Symbol not found: {symbol}")
        except HTTPException:
            raise
        except Exception as exc:
            # Provider unavailable (auth not set up, network error, etc.)
            # Log and proceed so a provider outage doesn't block watchlist adds.
            logger.warning("Symbol validation skipped for %s: %s", symbol, exc)

    # ── Idempotent insert ─────────────────────────────────────────────
    existing = (
        await db.execute(
            select(WatchlistEntry).where(
                WatchlistEntry.watchlist_id == watchlist_id,
                WatchlistEntry.symbol == symbol,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return {"symbol": existing.symbol, "added_at": existing.added_at}

    entry = WatchlistEntry(watchlist_id=watchlist_id, symbol=symbol)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"symbol": entry.symbol, "added_at": entry.added_at}


# ── DELETE /watchlists/{watchlist_id}/symbols/{symbol} ───────────────────────

@router.delete("/{watchlist_id}/symbols/{symbol}", status_code=204)
async def remove_symbol(
    watchlist_id: str,
    symbol: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Remove a symbol from a watchlist. Returns 404 if not found."""
    await _get_watchlist_or_404(watchlist_id, user["sub"], db)
    result = await db.execute(
        delete(WatchlistEntry).where(
            WatchlistEntry.watchlist_id == watchlist_id,
            WatchlistEntry.symbol == symbol.upper().strip(),
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Symbol not found in watchlist")
