"""
Insight Engine API endpoints — Phase 3.6 Stream A3 / C3.

ENDPOINTS:
  GET  /api/v1/insights
    Returns ACTIVE insights filtered by domain and optionally entity_id.
    Sorted by severity (CRITICAL > WARNING > INFO) then created_at desc.
    Query params: domain (default 'options'), status (default 'ACTIVE'), entity_id (optional)
    Tier 1 auth (require_read).

  PATCH /api/v1/insights/{insight_id}/dismiss
    Mark insight as DISMISSED. Optimistic dismiss from frontend.
    Tier 1 auth (require_read).

  PATCH /api/v1/insights/{insight_id}/act
    Mark insight as ACTED_ON (user navigated to the entity).
    Tier 1 auth (require_read).
"""

import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.models.database import Insight
from app.models.session import get_db
from app.models.schemas import InsightResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["Insights"])

_SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def _to_response(insight: Insight) -> InsightResponse:
    """Map an Insight ORM row to InsightResponse."""
    actions = None
    if insight.recommended_actions:
        try:
            actions = json.loads(insight.recommended_actions)
        except Exception:
            pass
    return InsightResponse(
        insight_id=insight.insight_id,
        domain=insight.domain,
        entity_id=insight.entity_id,
        entity_label=insight.entity_label,
        deviation_score=insight.deviation_score,
        deviation_type=insight.deviation_type,
        title=insight.title,
        body=insight.body,
        severity=insight.severity,
        recommended_actions=actions,
        status=insight.status,
        agent_run_id=insight.agent_run_id,
        created_at=insight.created_at,
    )


@router.get("", response_model=List[InsightResponse])
async def list_insights(
    domain: str = Query(default="options", description="Domain to filter by"),
    status: str = Query(default="ACTIVE", description="Status filter: ACTIVE|DISMISSED|ACTED_ON"),
    entity_id: Optional[str] = Query(default=None, description="Filter by entity (e.g., position_id)"),
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Return insights for the given domain + status.

    Sorted by severity (CRITICAL first) then created_at descending.
    """
    conditions = [
        Insight.domain == domain,
        Insight.status == status,
    ]
    if entity_id:
        conditions.append(Insight.entity_id == entity_id)

    result = await db.execute(
        select(Insight)
        .where(and_(*conditions))
        .order_by(Insight.created_at.desc())
    )
    rows = list(result.scalars().all())

    # Sort by severity then created_at (most recent first)
    rows.sort(
        key=lambda i: (_SEVERITY_ORDER.get(i.severity, 9), -i.created_at.timestamp()),
    )

    return [_to_response(r) for r in rows]


@router.patch("/{insight_id}/dismiss", response_model=InsightResponse)
async def dismiss_insight(
    insight_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Mark an insight as DISMISSED."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Insight).where(Insight.insight_id == insight_id)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")

    insight.status = "DISMISSED"
    insight.dismissed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(f"Insight {insight_id} dismissed by user {user.get('sub', '')}")
    return _to_response(insight)


@router.patch("/{insight_id}/act", response_model=InsightResponse)
async def act_on_insight(
    insight_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Mark an insight as ACTED_ON (user navigated to the entity)."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Insight).where(Insight.insight_id == insight_id)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")

    insight.status = "ACTED_ON"
    insight.acted_on_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(f"Insight {insight_id} acted on by user {user.get('sub', '')}")
    return _to_response(insight)
