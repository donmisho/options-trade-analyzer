"""
CSRF middleware for the BFF session-cookie auth pattern (OTA-463).

WHY: Session cookies are automatically sent by the browser on every request,
making them vulnerable to Cross-Site Request Forgery. The mitigation is the
Synchronizer Token Pattern:
  1. GET /auth/me returns a random csrf_token tied to the session
  2. The SPA stores it (e.g. in memory or sessionStorage — NOT localStorage)
  3. Every state-changing request must include it as X-CSRF-Token header
  4. This middleware verifies the header matches the session's csrf_token

An attacker's site can trigger the browser to send the cookie automatically,
but cannot read the csrf_token (same-origin policy) and therefore cannot
include the correct header.

EXEMPTIONS (routes where CSRF is not checked):
  - All /api/v1/auth/* routes (login/callback are unauthenticated; logout
    is POST but the session cookie presence is the only auth it needs)
  - /api/v1/health/* routes
  - Swagger UI routes (/docs, /openapi.json, /redoc)
  - Requests without a session cookie (they'll 401 at the route level anyway)
  - skip_auth=True (local dev)

OPTIMIZATION: When this middleware validates a session, it stores the session
dict in request.state.bff_session so the route's get_session_user dependency
can skip the second DB round-trip.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)

_STATE_CHANGING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

_CSRF_EXEMPT_PREFIXES = (
    "/api/v1/auth/",        # all identity and legacy auth routes
    "/api/v1/health",       # health checks
    "/docs",                # Swagger UI
    "/openapi.json",
    "/redoc",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Enforce CSRF token header on all state-changing requests that carry a
    session cookie.

    Added to the FastAPI app at creation time (before lifespan). The session
    manager reference is resolved lazily via get_session_manager() to avoid
    a circular startup dependency.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip non-state-changing methods
        if request.method not in _STATE_CHANGING_METHODS:
            return await call_next(request)

        # Skip exempt route prefixes
        path = request.url.path
        for prefix in _CSRF_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Skip when auth is globally disabled (local dev)
        if settings.skip_auth:
            return await call_next(request)

        # No session cookie → route will return 401 anyway; no CSRF check needed
        session_id = request.cookies.get(settings.session_cookie_name)
        if not session_id:
            return await call_next(request)

        # Resolve session manager lazily (set after lifespan starts)
        from app.auth.dependencies import get_session_manager
        session_manager = get_session_manager()
        if session_manager is None:
            # App not fully initialized — let the request through
            return await call_next(request)

        session = await session_manager.get_session(session_id)
        if session is None:
            # Expired or invalid session → let the route return 401
            return await call_next(request)

        # Cache session in request state to avoid a second DB hit in get_session_user
        request.state.bff_session = session

        # Verify CSRF token
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_header or csrf_header != session["csrf_token"]:
            logger.warning(
                f"CSRF: Token mismatch on {request.method} {path} "
                f"for user {session.get('email', 'unknown')}"
            )
            return JSONResponse(
                {"detail": "CSRF token missing or invalid"},
                status_code=403,
            )

        return await call_next(request)
