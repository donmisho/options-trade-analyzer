"""
Watchlist CRUD endpoints — OTA-258.

Replaces the bulk PUT /user/watchlist approach with fine-grained add/delete,
so the frontend never accidentally overwrites DB state with stale localStorage.

GET    /api/v1/watchlist           → symbol list ordered by sort_order
POST   /api/v1/watchlist           → add a symbol (or move to top if already present)
DELETE /api/v1/watchlist/{symbol}  → remove a symbol
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserWatchlist
from app.models.schemas import WatchlistSymbol, WatchlistResponse
from app.models.session import get_db
from app.auth.dependencies import require_read

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's watchlist symbols ordered by sort_order (position)."""
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user["sub"])
        .order_by(UserWatchlist.position)
    )
    rows = result.scalars().all()
    return WatchlistResponse(symbols=[r.symbol for r in rows])


@router.post("", status_code=201)
async def add_symbol(
    payload: WatchlistSymbol,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a symbol to the top of the watchlist.

    Idempotent: if the symbol already exists, it is removed from its current
    position and re-inserted at position 0 (move-to-top semantics).
    All other rows are shifted down by 1 to make room.
    """
    user_id = user["sub"]
    symbol = payload.symbol.upper().strip()

    # Shift existing rows down by 1
    await db.execute(
        update(UserWatchlist)
        .where(UserWatchlist.user_id == user_id)
        .values(position=UserWatchlist.position + 1)
    )

    # Remove any existing row for this symbol (handles the move-to-top case)
    await db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.user_id == user_id,
            UserWatchlist.symbol == symbol,
        )
    )

    # Insert at position 0
    db.add(UserWatchlist(user_id=user_id, symbol=symbol, position=0))
    await db.commit()
    return {"added": symbol}


@router.delete("/{symbol}")
async def remove_symbol(
    symbol: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Remove a symbol from the watchlist. Returns 404 if not found."""
    result = await db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.user_id == user["sub"],
            UserWatchlist.symbol == symbol.upper().strip(),
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Symbol not found in watchlist")
    return {"removed": symbol.upper().strip()}
