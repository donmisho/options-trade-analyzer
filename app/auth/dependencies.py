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
from typing import Optional, TYPE_CHECKING

from app.auth.service import AuthService
from app.core.secrets import SecretsManager
from app.core.config import settings

if TYPE_CHECKING:
    from app.auth.session_manager import SessionManager

# Bearer token extraction from Authorization header
security = HTTPBearer(auto_error=False)

# These will be initialized in main.py at startup
_secrets_manager: Optional[SecretsManager] = None
_auth_service: Optional[AuthService] = None
_session_manager: Optional["SessionManager"] = None


def init_auth(secrets_manager: SecretsManager):
    """Called once at app startup to initialize auth with the secrets manager."""
    global _secrets_manager, _auth_service
    _secrets_manager = secrets_manager
    _auth_service = AuthService(secrets_manager)


def init_session(session_manager: "SessionManager"):
    """Called once at startup to register the BFF session manager."""
    global _session_manager
    _session_manager = session_manager


def get_session_manager() -> Optional["SessionManager"]:
    """Return the session manager instance (may be None before startup completes)."""
    return _session_manager


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
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """
    Extract and validate the caller's identity.

    Accepts (in priority order):
      1. BFF session cookie (browser-based OIDC flow — preferred)
      2. JWT Bearer token in Authorization header (API clients, backward compat)

    Returns a normalized dict with sub, username, role, mfa keys so all
    downstream dependencies (require_read, require_write, etc.) work regardless
    of which auth method was used.
    """

    if settings.skip_auth:
        return {
            "sub": "00000000-0000-0000-0000-000000000001",  # UUID-format so position routes accept it
            "username": "dev",
            "role": "admin",
            "mfa": True,
        }

    # -- Try BFF session cookie first --
    # CSRFMiddleware may have already validated the session and cached it in
    # request.state.bff_session — skip the DB round-trip if so.
    if hasattr(request.state, "bff_session") and request.state.bff_session:
        session = request.state.bff_session
        return {
            "sub": session["user_id"],
            "username": session.get("email") or session.get("display_name") or "user",
            "role": "admin",
            "mfa": True,  # Entra OIDC login is inherently MFA-verified (requires Entra to enforce MFA)
        }

    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id and _session_manager is not None:
        session = await _session_manager.get_session(session_id)
        if session is not None:
            return {
                "sub": session["user_id"],
                "username": session.get("email") or session.get("display_name") or "user",
                "role": "admin",
                "mfa": True,
            }

    # -- Fall back to JWT Bearer (API clients, existing flows) --
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


