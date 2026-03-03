"""
User preferences endpoints: watchlist and favorites persistence.

Watchlist and favorites were previously localStorage-only on the frontend.
These endpoints let the backend own the data so it survives browser clears,
works across devices, and is ready for multi-user scenarios.

Tier 1 (READ) for all operations — watchlist/favorites are personal preferences,
not sensitive financial data.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime

from app.models.database import UserWatchlist, UserFavorite
from app.models.session import get_db
from app.auth.dependencies import require_read

router = APIRouter(prefix="/user", tags=["User Preferences"])


# ─── Schemas ────────────────────────────────────────────────────────

class WatchlistEntry(BaseModel):
    symbol: str
    name: Optional[str] = ""

class WatchlistPayload(BaseModel):
    symbols: list[WatchlistEntry]

class FavoritePayload(BaseModel):
    id: str           # Unique trade key built by frontend
    symbol: str
    label: Optional[str] = ""
    strategy: Optional[str] = ""
    trade_data: dict[str, Any]  # Full trade snapshot

class FavoriteResponse(BaseModel):
    id: str
    symbol: str
    label: Optional[str]
    strategy: Optional[str]
    trade_data: dict[str, Any]
    saved_at: datetime


# ─── Watchlist ───────────────────────────────────────────────────────

@router.get("/watchlist")
async def get_watchlist(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's watchlist in saved order."""
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user["sub"])
        .order_by(UserWatchlist.position)
    )
    rows = result.scalars().all()
    return [{"symbol": r.symbol, "name": r.name or ""} for r in rows]


@router.put("/watchlist")
async def save_watchlist(
    payload: WatchlistPayload,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Replace the user's entire watchlist.

    WHY replace-all: The frontend manages ordering by rewriting the full list
    on every change (add, remove, reorder). Matching that with a replace-all
    strategy is simpler than tracking individual add/remove/reorder operations.
    """
    user_id = user["sub"]

    # Delete existing rows for this user
    await db.execute(
        delete(UserWatchlist).where(UserWatchlist.user_id == user_id)
    )

    # Insert the new ordered list
    for pos, entry in enumerate(payload.symbols):
        db.add(UserWatchlist(
            user_id=user_id,
            symbol=entry.symbol.upper(),
            name=entry.name or "",
            position=pos,
        ))

    await db.commit()
    return {"saved": len(payload.symbols)}


# ─── Favorites ───────────────────────────────────────────────────────

@router.get("/favorites", response_model=list[FavoriteResponse])
async def get_favorites(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return all saved favorites for the current user, newest first."""
    result = await db.execute(
        select(UserFavorite)
        .where(UserFavorite.user_id == user["sub"])
        .order_by(UserFavorite.saved_at.desc())
    )
    rows = result.scalars().all()
    return [
        FavoriteResponse(
            id=r.trade_id,
            symbol=r.symbol,
            label=r.label,
            strategy=r.strategy,
            trade_data=r.trade_data,
            saved_at=r.saved_at,
        )
        for r in rows
    ]


@router.post("/favorites", status_code=201)
async def add_favorite(
    payload: FavoritePayload,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Save a trade to favorites. Idempotent — silently ignores duplicates.
    """
    user_id = user["sub"]

    # Check for duplicate
    result = await db.execute(
        select(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.trade_id == payload.id,
        )
    )
    if result.scalar_one_or_none():
        return {"status": "already_saved"}

    db.add(UserFavorite(
        user_id=user_id,
        trade_id=payload.id,
        symbol=payload.symbol.upper(),
        label=payload.label,
        strategy=payload.strategy,
        trade_data=payload.trade_data,
    ))
    await db.commit()
    return {"status": "saved"}


@router.delete("/favorites/{trade_id:path}")
async def remove_favorite(
    trade_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Remove a specific favorite by its trade_id."""
    result = await db.execute(
        delete(UserFavorite).where(
            UserFavorite.user_id == user["sub"],
            UserFavorite.trade_id == trade_id,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "removed"}
