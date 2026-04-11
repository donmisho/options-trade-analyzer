"""
OIDC identity routes for BFF (Backend-for-Frontend) auth pattern (OTA-462).

FLOW:
  GET  /api/v1/auth/login              → redirect to IdP authorize endpoint
  GET  /api/v1/auth/entra/callback     → exchange code + PKCE → create session → set cookie
  GET  /api/v1/auth/me                 → return current user profile from session
  POST /api/v1/auth/logout             → delete session + clear cookie
  GET  /api/v1/auth/session/status     → lightweight session health check (no sensitive data)

STATE SECURITY:
  The OAuth state parameter is a signed payload (itsdangerous URLSafeTimedSerializer)
  that carries { provider, return_url, nonce }. The signature prevents CSRF on the
  callback endpoint. Max age is 10 minutes.

PKCE:
  code_verifier and code_challenge (S256) are generated per-login and the verifier
  is stored server-side keyed by state. This prevents authorization code interception.

CREDENTIAL TYPE:
  Certificate-based client assertion (no client_secret). See client_assertion.py.
"""

import base64
import hashlib
import logging
import secrets
import time
from typing import Optional

import httpx
import jwt  # PyJWT — decode id_token claims only, no verification needed
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])

# Injected at startup via init_identity_routes()
_session_manager = None
_assertion_builder = None
_secrets_manager = None

# Short-lived PKCE cache: state_str → (code_verifier, created_at_unix)
# TTL is 10 minutes (matches state token max_age). Stale entries are pruned on access.
_pkce_cache: dict[str, tuple[str, float]] = {}
_PKCE_TTL = 600  # seconds


def init_identity_routes(session_manager, assertion_builder, secrets_manager) -> None:
    """Called once at app startup to inject dependencies."""
    global _session_manager, _assertion_builder, _secrets_manager
    _session_manager = session_manager
    _assertion_builder = assertion_builder
    _secrets_manager = secrets_manager


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _get_redirect_uri() -> str:
    if settings.app_env == "production":
        return settings.entra_redirect_uri_prod
    return settings.entra_redirect_uri_dev


def _get_signing_key() -> str:
    """Return the signing key for state parameter serialization."""
    key = _secrets_manager.get("jwt-signing-key") if _secrets_manager else None
    if not key:
        # Fallback for local dev without Key Vault
        key = "ota-state-signing-key-dev"
    return key


def _make_code_challenge(verifier: str) -> str:
    """SHA-256 PKCE code challenge (S256 method)."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _prune_pkce_cache() -> None:
    """Remove stale PKCE entries to prevent unbounded growth."""
    now = time.time()
    stale = [k for k, (_, ts) in _pkce_cache.items() if now - ts > _PKCE_TTL]
    for k in stale:
        _pkce_cache.pop(k, None)


# ------------------------------------------------------------------
# GET /auth/login
# ------------------------------------------------------------------

@router.get("/auth/login")
async def login(request: Request, provider: str = "entra"):
    """
    Redirect the browser to the identity provider's authorization endpoint.

    Generates PKCE verifier/challenge and a signed state token, stores the
    verifier server-side, then builds the full authorization URL.
    """
    if not settings.entra_tenant_id or not settings.entra_client_id:
        return JSONResponse(
            {"detail": "Identity provider not configured"},
            status_code=503,
        )

    from app.auth.providers import get_provider_config
    from itsdangerous import URLSafeTimedSerializer

    config = get_provider_config(provider, settings)

    # PKCE
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _make_code_challenge(code_verifier)

    # State: signed payload that will be verified in the callback
    return_url = request.query_params.get("return_url", "/")
    state_data = {
        "return_url": return_url,
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
    }
    serializer = URLSafeTimedSerializer(_get_signing_key())
    state = serializer.dumps(state_data, salt="ota-oidc-state")

    # Store verifier server-side keyed by state
    _prune_pkce_cache()
    _pkce_cache[state] = (code_verifier, time.time())

    scopes = " ".join(config["scopes"])
    redirect_uri = _get_redirect_uri()

    authorize_url = (
        f"{config['authorize_url']}"
        f"?client_id={config['client_id']}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&response_mode=query"
    )

    logger.info(f"Identity: Redirecting to {provider} login")
    return RedirectResponse(url=authorize_url)


# ------------------------------------------------------------------
# GET /auth/entra/callback
# ------------------------------------------------------------------

@router.get("/auth/entra/callback")
async def entra_callback(request: Request):
    """
    Handle Entra's OIDC callback.

    Validates state, retrieves PKCE verifier, exchanges the authorization
    code for tokens using a JWT client assertion, creates a server-side
    session, and sets an httponly session cookie.
    """
    error = request.query_params.get("error")
    if error:
        error_desc = request.query_params.get("error_description", "Unknown error")
        logger.warning(f"Identity: Entra callback error: {error} — {error_desc}")
        return RedirectResponse(
            url=f"/?auth_error={error}&auth_error_desc={error_desc}"
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        return RedirectResponse(url="/?auth_error=missing_params")

    # -- 1. Validate state (CSRF protection) --
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
    try:
        serializer = URLSafeTimedSerializer(_get_signing_key())
        state_data = serializer.loads(state, salt="ota-oidc-state", max_age=_PKCE_TTL)
    except SignatureExpired:
        logger.warning("Identity: State token expired")
        return RedirectResponse(url="/?auth_error=state_expired")
    except BadSignature:
        logger.warning("Identity: Invalid state token")
        return RedirectResponse(url="/?auth_error=invalid_state")

    provider = state_data.get("provider", "entra")
    return_url = state_data.get("return_url", "/")

    # -- 2. Retrieve and clear PKCE verifier --
    entry = _pkce_cache.pop(state, None)
    if entry is None:
        logger.warning("Identity: PKCE verifier not found for state")
        return RedirectResponse(url="/?auth_error=invalid_state")
    code_verifier, _ = entry

    # -- 3. Exchange code for tokens using JWT client assertion --
    from app.auth.providers import get_provider_config
    config = get_provider_config(provider, settings)
    token_url = config["token_url"]
    redirect_uri = _get_redirect_uri()

    try:
        assertion = await _assertion_builder.build_assertion(token_url)
    except Exception as e:
        logger.error(f"Identity: Failed to build client assertion: {e}")
        return RedirectResponse(url="/?auth_error=server_error")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": config["client_id"],
                    "client_assertion_type": (
                        "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                    ),
                    "client_assertion": assertion,
                    "code_verifier": code_verifier,
                },
            )
    except Exception as e:
        logger.error(f"Identity: Token exchange HTTP error: {e}")
        return RedirectResponse(url="/?auth_error=server_error")

    if resp.status_code != 200:
        logger.error(
            f"Identity: Token exchange failed ({resp.status_code}): {resp.text[:200]}"
        )
        return RedirectResponse(url="/?auth_error=token_exchange_failed")

    token_data = resp.json()

    # -- 4. Extract user profile from id_token claims --
    id_token = token_data.get("id_token", "")
    try:
        # No signature verification needed — token came directly from Entra over HTTPS
        claims = jwt.decode(
            id_token,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
    except Exception as e:
        logger.error(f"Identity: Failed to decode id_token: {e}")
        return RedirectResponse(url="/?auth_error=server_error")

    user_profile = {
        "user_id": claims.get("oid", claims.get("sub", "")),
        "email": claims.get("preferred_username", claims.get("email", "")),
        "display_name": claims.get("name", ""),
    }

    # -- 5. Create server-side session --
    try:
        session_id = await _session_manager.create_session(
            user_profile=user_profile,
            tokens=token_data,
            provider=provider,
        )
    except Exception as e:
        logger.error(f"Identity: Failed to create session: {e}")
        return RedirectResponse(url="/?auth_error=server_error")

    # -- 6. Set cookie and redirect to SPA --
    response = RedirectResponse(url=return_url, status_code=302)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_hours * 3600,
    )

    logger.info(
        f"Identity: Login complete for {user_profile.get('email')} "
        f"via {provider}"
    )
    return response


# ------------------------------------------------------------------
# GET /auth/me
# ------------------------------------------------------------------

@router.get("/auth/me")
async def get_me(request: Request):
    """
    Return the current user profile from the server-side session.

    The CSRF token returned here must be stored by the SPA and sent
    as the X-CSRF-Token header on all POST/PATCH/PUT/DELETE requests.
    """
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    session = await _session_manager.get_session(session_id)
    if session is None:
        response = JSONResponse({"detail": "Session expired"}, status_code=401)
        response.delete_cookie(key=settings.session_cookie_name, path="/")
        return response

    return JSONResponse({
        "user_id": session["user_id"],
        "email": session["email"],
        "display_name": session["display_name"],
        "provider": session["provider"],
        "csrf_token": session["csrf_token"],
        "session_expires_at": session["session_expires_at"],
    })


# ------------------------------------------------------------------
# POST /auth/logout
# ------------------------------------------------------------------

@router.post("/auth/logout")
async def logout(request: Request):
    """
    Invalidate the current session and clear the session cookie.
    """
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        await _session_manager.delete_session(session_id)

    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return response


# ------------------------------------------------------------------
# GET /auth/session/status
# ------------------------------------------------------------------

@router.get("/auth/session/status")
async def session_status(request: Request):
    """
    Lightweight session health check. Returns no sensitive data.

    Used by the SPA to decide whether to show the login page or not,
    and to display the remaining session time.
    """
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        return JSONResponse({"authenticated": False})

    session = await _session_manager.get_session(session_id)
    if session is None:
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(key=settings.session_cookie_name, path="/")
        return response

    from datetime import datetime, timezone
    try:
        expires_at = datetime.fromisoformat(
            session["session_expires_at"].rstrip("Z")
        ).replace(tzinfo=timezone.utc)
        expires_in_seconds = int(
            (expires_at - datetime.now(timezone.utc)).total_seconds()
        )
    except Exception:
        expires_in_seconds = 0

    return JSONResponse({
        "authenticated": True,
        "expires_in_seconds": max(expires_in_seconds, 0),
        "provider": session["provider"],
        "user": session["display_name"] or session["email"],
    })
