"""
Changelog routes — deploy history viewer (OTA-602).

Two endpoints:
  POST /changelog/record — write endpoint, authed by deploy token (X-Deploy-Token header)
  GET  /changelog         — read endpoint, authed by standard BFF session cookie

Data Isolation Invariant exception: deploy_log is observability data, not
user-scoped. Both endpoints operate on the table as a whole — no user_id filter.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import SecretsManager
from app.models.database import DeployLog
from app.models.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/changelog", tags=["changelog"])

_secrets_manager: SecretsManager | None = None


def init_changelog_routes(secrets_manager: SecretsManager) -> None:
    global _secrets_manager
    _secrets_manager = secrets_manager


# ─── Schemas ──────────────────────────────────────────────────────────────────


class DeployRecordRequest(BaseModel):
    build_id: str
    environment: Literal["dev", "prod"]
    commit_sha: str
    ticket_keys: list[str] = []
    notes: Optional[str] = None

    @field_validator("build_id")
    @classmethod
    def build_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("build_id must be non-empty")
        return v.strip()

    @field_validator("commit_sha")
    @classmethod
    def commit_sha_valid(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", v):
            raise ValueError("commit_sha must be exactly 40 hex characters")
        return v

    @field_validator("ticket_keys")
    @classmethod
    def ticket_keys_valid(cls, v: list[str]) -> list[str]:
        for key in v:
            if not re.fullmatch(r"OTA-\d+", key):
                raise ValueError(f"Invalid ticket key: {key!r} (must match OTA-NNN)")
        return v


class DeployRecordResponse(BaseModel):
    id: int


class DeployLogEntry(BaseModel):
    id: int
    build_id: str
    environment: str
    deployed_at: str
    commit_sha: str
    ticket_keys: list[str]
    notes: Optional[str]
    created_at: str


# ─── Auth helper ──────────────────────────────────────────────────────────────


def _verify_deploy_token(x_deploy_token: str = Header(...)) -> str:
    """Validate X-Deploy-Token header against Key Vault secret."""
    if _secrets_manager is None:
        raise HTTPException(status_code=500, detail="Secrets manager not initialized")
    expected = _secrets_manager.get("deploy-recorder-token")
    if not expected or x_deploy_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing deploy token")
    return x_deploy_token


# ─── Ticket-key parser ───────────────────────────────────────────────────────


def parse_ticket_keys(commit_message: str) -> list[str]:
    """Extract OTA-NNN ticket keys from a commit message. Uppercase only, deduplicated."""
    return list(dict.fromkeys(re.findall(r"OTA-\d+", commit_message)))


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/record", status_code=201, response_model=DeployRecordResponse)
async def record_deploy(
    body: DeployRecordRequest,
    _token: str = Depends(_verify_deploy_token),
    db: AsyncSession = Depends(get_db),
):
    """Record a successful deployment. Called by GitHub Actions workflows."""
    row = DeployLog(
        build_id=body.build_id,
        environment=body.environment,
        deployed_at=datetime.now(timezone.utc),
        commit_sha=body.commit_sha,
        ticket_keys=",".join(body.ticket_keys),
        notes=body.notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info(
        f"Deploy recorded: build_id={body.build_id} environment={body.environment}"
    )
    return DeployRecordResponse(id=row.id)


@router.get("", response_model=list[DeployLogEntry])
async def get_changelog(
    limit: int = Query(default=50, ge=1, le=200),
    environment: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Return deploy history in reverse-chronological order.

    Data Isolation Invariant exception: deploy_log is observability data,
    not user-scoped. No user_id filter applied.
    """
    stmt = select(DeployLog).order_by(DeployLog.deployed_at.desc())
    if environment is not None:
        if environment not in ("dev", "prod"):
            raise HTTPException(status_code=400, detail="environment must be 'dev' or 'prod'")
        stmt = stmt.where(DeployLog.environment == environment)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        DeployLogEntry(
            id=r.id,
            build_id=r.build_id,
            environment=r.environment,
            deployed_at=r.deployed_at.isoformat() if r.deployed_at else "",
            commit_sha=r.commit_sha,
            ticket_keys=r.ticket_keys.split(",") if r.ticket_keys else [],
            notes=r.notes,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
