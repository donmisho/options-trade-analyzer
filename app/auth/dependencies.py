"""
Authentication dependencies for FastAPI endpoint protection.

HOW TO USE: Add the appropriate dependency to any endpoint:

    @router.get("/data")
    async def get_data(user = Depends(require_read)):      # Tier 1
        ...

    @router.put("/config")
    async def update_config(user = Depends(require_write)): # Tier 2
        ...

    # Tier 3 (trade) doesn't use a dependency — it uses the
    # per-trade challenge-response flow in the trade endpoints.

WHY dependencies: FastAPI's Depends() system runs before your endpoint code.
If the user isn't authenticated or doesn't have the right tier, the request
is rejected with a 401/403 before your code even runs. This makes it
impossible to accidentally expose an unprotected endpoint.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.auth.service import AuthService
from app.core.secrets import SecretsManager
from app.core.config import settings

# Bearer token extraction from Authorization header
security = HTTPBearer(auto_error=False)

# These will be initialized in main.py at startup
_secrets_manager: Optional[SecretsManager] = None
_auth_service: Optional[AuthService] = None


def init_auth(secrets_manager: SecretsManager):
    """Called once at app startup to initialize auth with the secrets manager."""
    global _secrets_manager, _auth_service
    _secrets_manager = secrets_manager
    _auth_service = AuthService(secrets_manager)


def get_auth_service() -> AuthService:
    """Dependency to get the auth service instance."""
    if _auth_service is None:
        raise RuntimeError("Auth service not initialized")
    return _auth_service


def get_secrets_manager() -> SecretsManager:
    """Dependency to get the secrets manager instance."""
    if _secrets_manager is None:
        raise RuntimeError("Secrets manager not initialized")
    return _secrets_manager


async def get_current_user(
    
    
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """
    Extract and validate the JWT from the Authorization header.
    Returns the token payload (user_id, role, mfa status, etc.)
    
    This is the base dependency — it only checks that the token is valid.
    It does NOT check MFA status or role. Use require_read/require_write
    for tier-specific checks.
    """

    if settings.skip_auth:
        return {
            "sub": "dev-user",
            "username": "dev",
            "role": "admin",
            "mfa": True,
        }

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = auth.verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def require_read(user: dict = Depends(get_current_user)) -> dict:
    """
    Tier 1 — READ access.
    
    Requires: valid JWT (any role, MFA not required for read-only data).
    Used by: market data, chain data, analysis results, MCP tools.
    """
    return user


async def require_write(user: dict = Depends(get_current_user)) -> dict:
    """
    Tier 2 — WRITE access.
    
    Requires: valid JWT with MFA verified.
    Used by: config changes, trade journaling, provider management.
    """
    if not user.get("mfa"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required for this action",
        )
    return user


async def require_admin(user: dict = Depends(require_write)) -> dict:
    """
    Admin-only access.
    
    Requires: Tier 2 + admin role.
    Used by: user management, invite codes, system settings.
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_trader(user: dict = Depends(require_write)) -> dict:
    """
    Trader-level access (but NOT trade execution — that uses per-trade MFA).
    
    Requires: Tier 2 + trader or admin role.
    Used by: provider connection, portfolio viewing, trade previews.
    """
    if user.get("role") not in ("admin", "trader"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trader access required",
        )
    return user
