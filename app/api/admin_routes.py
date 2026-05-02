"""
Admin endpoints — user management.

All endpoints require admin role (Tier 2 + role == "admin").

Role changes take effect on the user's NEXT login — the JWT caches the role
for its lifetime (configured by JWT_ACCESS_TOKEN_EXPIRE_MINUTES).

To change a user's role or status without waiting for token expiry, the user
must log out and log back in. Alternatively you can shorten the token TTL in
settings.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.models.database import User, UserConfig, AuditLog
from app.models.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

VALID_ROLES = {"admin", "trader", "viewer"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserSummary(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    mfa_enabled: bool
    mfa_verified: bool
    market_data_provider: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class UserPatch(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserSummary])
async def list_users(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users with their current role and status.

    Role changes made here take effect on the user's next login.
    """
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return [
        UserSummary(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            mfa_enabled=u.mfa_enabled,
            mfa_verified=u.mfa_verified,
            market_data_provider=u.market_data_provider,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: str,
    payload: UserPatch,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a user's role and/or active status.

    - role: "admin" | "trader" | "viewer"
    - is_active: false to block login without deleting the account

    The change takes effect on the user's next login (JWT caches the role).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role is not None and payload.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{payload.role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    # Prevent admin from demoting themselves
    if payload.role is not None and user_id == admin["sub"] and payload.role != "admin":
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role",
        )

    changes = {}
    if payload.role is not None and payload.role != user.role:
        changes["role"] = {"old": user.role, "new": payload.role}
        user.role = payload.role

    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = {"old": user.is_active, "new": payload.is_active}
        user.is_active = payload.is_active

    if changes:
        user.updated_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            user_id=admin["sub"],
            event_type="admin_user_update",
            detail={"target_user_id": user_id, "changes": changes},
        ))
        await db.commit()
        await db.refresh(user)
        logger.info(f"Admin {admin['username']} updated user {user.username}: {changes}")

    return UserSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        mfa_verified=user.mfa_verified,
        market_data_provider=user.market_data_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/stats")
async def admin_stats(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Quick summary counts — total users, by role, active vs inactive."""
    result = await db.execute(
        select(User.role, User.is_active, func.count(User.id))
        .group_by(User.role, User.is_active)
    )
    rows = result.all()

    total = sum(r[2] for r in rows)
    by_role = {}
    active_count = 0
    for role, is_active, count in rows:
        by_role[role] = by_role.get(role, 0) + count
        if is_active:
            active_count += count

    return {
        "total_users": total,
        "active_users": active_count,
        "inactive_users": total - active_count,
        "by_role": by_role,
    }
