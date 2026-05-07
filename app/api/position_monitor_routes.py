"""
Position Monitor Agent API endpoints — Phase 3.5 Stream B4.

ENDPOINTS:
  POST /api/v1/agents/position-monitor/run
    Trigger an immediate run. Returns AgentRunResult.
    Tier 2 auth (require_write).

  GET /api/v1/agents/position-monitor/status
    Last run summary + next scheduled run time.
    Tier 1 auth (require_read).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read, require_write
from app.models.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])

# Injected at startup via init_agents_routes()
_position_monitor_agent = None
_next_run_at: Optional[datetime] = None


def init_agents_routes(position_monitor_agent, next_run_at: Optional[datetime] = None):
    """Called from main.py lifespan after the agent is constructed."""
    global _position_monitor_agent, _next_run_at
    _position_monitor_agent = position_monitor_agent
    _next_run_at = next_run_at


def update_next_run_at(dt: datetime):
    """Called by the scheduler after each run to update the next fire time."""
    global _next_run_at
    _next_run_at = dt


def _get_agent():
    if _position_monitor_agent is None:
        raise HTTPException(
            status_code=503,
            detail="Position Monitor Agent not initialized. Check AI provider configuration.",
        )
    return _position_monitor_agent


@router.post("/position-monitor/run")
async def run_position_monitor(
    background_tasks: BackgroundTasks,
    user_id_filter: Optional[str] = Query(
        None,
        description="Limit run to a specific user_id (admin only). Omit for all users.",
    ),
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger an immediate Position Monitor Agent run.

    Runs synchronously and returns the result. If the run takes more than
    ~25s (many positions, slow Schwab), the request may time out — in that
    case the run completes in the background and the result is in agent_run_log.
    """
    agent = _get_agent()

    # Only admins can filter by a different user_id
    requesting_user = user.get("sub", "")
    if user_id_filter and user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only admins can run the monitor for a specific user.",
        )

    target_user = user_id_filter or None  # None = all users

    try:
        result = await agent.run(db=db, user_id=target_user)
    except Exception as e:
        logger.error(f"Position monitor run failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent run failed: {e}")

    return {
        "run_id":               result.run_id,
        "positions_processed":  result.positions_processed,
        "insights_triggered":   result.insights_triggered,
        "run_at":               result.run_at.isoformat(),
        "error":                result.error,
    }


@router.get("/position-monitor/status")
async def get_position_monitor_status(
    user: dict = Depends(require_read),
):
    """Return last run summary and next scheduled run time."""
    agent = _get_agent()
    last = agent._last_run

    return {
        "agent":    "position-monitor",
        "last_run": {
            "run_id":              last.run_id if last else None,
            "positions_processed": last.positions_processed if last else None,
            "insights_triggered":  last.insights_triggered if last else None,
            "run_at":              last.run_at.isoformat() if last else None,
            "error":               last.error if last else None,
        },
        "next_run_at": _next_run_at.isoformat() if _next_run_at else None,
        "schedule":    "Mon-Fri 16:15 ET",
    }
