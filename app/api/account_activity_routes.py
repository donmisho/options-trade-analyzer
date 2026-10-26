"""
Account activity routes (OTA-855).

  POST /api/v1/account-activity/run      run the poller now (Tier 2)
  GET  /api/v1/account-activity/status   last run, next scheduled run, last recorded runs (Tier 1)
  GET  /api/v1/account-activity/fills    the stored fills in the dashboard's row shape (Tier 1)

Every read is scoped to the authenticated user (Data Isolation Invariant).
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read, require_write
from app.models.database import BrokerSyncRun
from app.models.session import get_db
from app.services.trade_fills import list_fill_rows, parse_day

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account-activity", tags=["Account activity"])

_sync = None
_next_run_at: Optional[datetime] = None
SCHEDULE_TEXT = "Mon-Fri every 15 minutes, 09:30-16:45 ET"


def init_account_activity_routes(sync, next_run_at: Optional[datetime] = None) -> None:
    """Called from main.py's lifespan once the poller exists (or with None when disabled)."""
    global _sync, _next_run_at
    _sync = sync
    _next_run_at = next_run_at


def _get_sync():
    if _sync is None:
        raise HTTPException(status_code=503, detail="Account activity poller is not enabled (BROKER_ACTIVITY_POLL_ENABLED).")
    return _sync


@router.post("/run")
async def run_account_activity(user: dict = Depends(require_write), db: AsyncSession = Depends(get_db)):
    """Pull transactions, orders and fill context now, whatever the time of day."""
    sync = _get_sync()
    result = await sync.run(db, trigger="manual", force=True)
    return {
        "status": result.status,
        "run_id": result.run_id,
        "accounts": result.accounts,
        "transactions_new": result.transactions_new,
        "orders_upserted": result.orders_upserted,
        "contexts_captured": result.contexts_captured,
        "message": result.message,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat() if result.finished_at else None,
    }


@router.get("/status")
async def account_activity_status(user: dict = Depends(require_read), db: AsyncSession = Depends(get_db)):
    """The poller's last run in memory, its next scheduled run, and the last ten recorded runs."""
    last = _sync.last_run if _sync is not None else None
    recorded = (await db.execute(select(BrokerSyncRun).order_by(BrokerSyncRun.started_at.desc()).limit(10))).scalars().all()
    return {
        "enabled": _sync is not None,
        "schedule": SCHEDULE_TEXT,
        "next_run_at": _next_run_at.isoformat() if _next_run_at else None,
        "last_run": None if last is None else {
            "status": last.status, "run_id": last.run_id, "accounts": last.accounts,
            "transactions_new": last.transactions_new, "orders_upserted": last.orders_upserted,
            "contexts_captured": last.contexts_captured, "message": last.message,
            "started_at": last.started_at.isoformat(),
            "finished_at": last.finished_at.isoformat() if last.finished_at else None,
        },
        "runs": [{
            "id": r.id, "status": r.status, "trigger": r.trigger,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "accounts": r.accounts, "transactions_new": r.transactions_new,
            "orders_upserted": r.orders_upserted, "contexts_captured": r.contexts_captured, "message": r.message,
        } for r in recorded],
    }


@router.get("/fills")
async def account_activity_fills(
    start: Optional[str] = Query(None, description="First trade date, YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="Last trade date, YYYY-MM-DD"),
    account: Optional[str] = Query(None, description="Account label, e.g. Options or IRA"),
    limit: int = Query(5000, ge=1, le=20000),
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """The stored fills as the dashboard's rows: statement columns plus ATR used and spread."""
    user_id = user.get("sub") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user in session")
    try:
        return await list_fill_rows(db, user_id, parse_day(start), parse_day(end), account, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Bad date: {e}")
