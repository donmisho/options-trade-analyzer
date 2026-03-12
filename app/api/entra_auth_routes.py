"""
Entra ID (Azure AD) token exchange endpoint.

Flow:
  1. Frontend (MSAL) gets an id_token from Microsoft
  2. POST /auth/entra/token with that id_token (no auth required — this IS login)
  3. We validate it against Microsoft's JWKS
  4. We look up or create the user in our DB (keyed by Entra OID)
  5. We return our standard JWT → all existing require_read/require_write
     dependencies continue to work with zero changes.

WHY this bridge pattern:
  Entra ID becomes the *login method* without touching any existing API endpoints.
  The Entra OID becomes the user's ID in our database, so each user's data is
  naturally isolated (UserConfig, UserWatchlist, UserFavorite all key on user_id).
"""

import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt as jose_jwt, jwk as jose_jwk, JWTError
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_auth_service
from app.auth.service import AuthService
from app.core.config import settings
from app.models.database import User, UserConfig
from app.models.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/entra", tags=["entra-auth"])

# Simple in-process JWKS cache — avoids fetching on every login request.
# Refreshed automatically when a new signing key is seen (key rotation).
_jwks_cache: dict | None = None


class EntraTokenRequest(BaseModel):
    entra_token: str


class EntraTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


async def _get_microsoft_jwks(tenant_id: str) -> dict:
    """Fetch Microsoft's JWKS for the given tenant. Result is cached in-process."""
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache

    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url, timeout=10.0)
        resp.raise_for_status()

    _jwks_cache = resp.json()
    return _jwks_cache


@router.post("/token", response_model=EntraTokenResponse)
async def exchange_entra_token(
    body: EntraTokenRequest,
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Exchange a Microsoft Entra ID id_token for our application JWT.

    No authentication required — this IS the login endpoint.
    """
    global _jwks_cache

    if not settings.entra_tenant_id or not settings.entra_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Entra ID authentication is not configured on this server.",
        )

    # ── 1. Validate the Entra token against Microsoft's JWKS ──────────────
    try:
        jwks = await _get_microsoft_jwks(settings.entra_tenant_id)

        # Find the signing key matching the token's kid
        unverified_header = jose_jwt.get_unverified_header(body.entra_token)
        kid = unverified_header.get("kid")
        keys = jwks.get("keys", [])
        matching_key = next((k for k in keys if k.get("kid") == kid), None)

        if not matching_key:
            # Cache may be stale (key rotation) — refresh once and retry
            _jwks_cache = None
            jwks = await _get_microsoft_jwks(settings.entra_tenant_id)
            keys = jwks.get("keys", [])
            matching_key = next((k for k in keys if k.get("kid") == kid), None)

        if not matching_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token signing key not found in Microsoft JWKS",
            )

        public_key = jose_jwk.construct(matching_key, algorithm="RS256")
        expected_issuer = (
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
        )

        payload = jose_jwt.decode(
            body.entra_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.entra_client_id,
            issuer=expected_issuer,
        )

    except JWTError as e:
        logger.warning(f"Entra token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired Microsoft token: {e}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Entra token exchange error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation failed",
        )

    # ── 2. Extract identity claims ─────────────────────────────────────────
    oid = payload.get("oid")
    if not oid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required 'oid' claim",
        )

    name = payload.get("name") or payload.get("preferred_username", "").split("@")[0]
    email = payload.get("email") or payload.get("preferred_username", "")

    # ── 3. Look up or create user ──────────────────────────────────────────
    result = await db.execute(select(User).where(User.id == oid))
    user = result.scalar_one_or_none()

    if user is None:
        # First user in the system becomes admin; all subsequent users are viewers.
        count_result = await db.execute(select(func.count(User.id)))
        user_count = count_result.scalar()
        role = "admin" if user_count == 0 else "viewer"

        user = User(
            id=oid,
            username=name[:50],
            email=email,
            password_hash=None,   # Entra users have no local password
            role=role,
            is_active=True,
            mfa_enabled=False,
            mfa_verified=False,
        )
        db.add(user)
        db.add(UserConfig(user_id=oid))  # Default config — required for /config to work
        await db.commit()
        await db.refresh(user)
        logger.info(f"Created Entra user: {email} (role={role})")
    else:
        # Keep display name / email in sync with Entra directory
        if user.username != name[:50] or user.email != email:
            user.username = name[:50]
            user.email = email
            user.updated_at = datetime.utcnow()
            await db.commit()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact the administrator.",
        )

    # ── 4. Mint our standard JWT ───────────────────────────────────────────
    # mfa_verified=True: Entra login (backed by Microsoft MFA) satisfies our
    # Tier 2 requirement so users can update config without a separate MFA step.
    access_token, expires_in = auth_service.create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        mfa_verified=True,
    )

    logger.info(f"Entra login: {email} ({user.role})")

    return EntraTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user={"name": name, "email": email, "role": user.role},
    )
