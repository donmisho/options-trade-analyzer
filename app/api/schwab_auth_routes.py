"""
Schwab OAuth Authentication Routes — browser-based login flow.

FLOW:
  1. GET  /api/v1/auth/schwab/login    → Redirects browser to Schwab login page
  2. GET  /api/v1/auth/schwab/callback  → Schwab sends user back here with auth code
  3. POST /api/v1/auth/schwab/refresh   → Manually trigger token refresh
  4. GET  /api/v1/auth/schwab/status    → Check if tokens are valid
  5. POST /api/v1/auth/schwab/disconnect → Clear all Schwab tokens

WHY SEPARATE FROM auth_routes.py: The existing auth_routes.py handles YOUR
app's authentication (username/password/MFA to log into the Options Analyzer).
This file handles SCHWAB's authentication (OAuth to connect your brokerage).
They're completely different auth flows serving different purposes:
  - auth_routes.py = "who are you?" (your app's security)
  - schwab_auth_routes.py = "can we access your Schwab data?" (brokerage connection)

SECURITY: All endpoints here require at least Tier 1 (READ) authentication,
meaning you must be logged into the Options Analyzer before you can connect
Schwab. The status endpoint is Tier 1 (anyone logged in can check).
The login/callback/refresh are Tier 2 (WRITE) because they modify stored tokens.
During dev with SKIP_AUTH=true, these checks are bypassed.
"""

import logging
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse

from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/schwab", tags=["Schwab OAuth"])

# Initialized in main.py at startup
_token_manager = None


def init_schwab_auth_routes(token_manager):
    """Called once at app startup to inject the token manager."""
    global _token_manager
    _token_manager = token_manager


def _get_token_manager():
    if _token_manager is None:
        raise RuntimeError("Schwab token manager not initialized")
    return _token_manager


# ------------------------------------------------------------------
# 1. Login — Redirect to Schwab
# ------------------------------------------------------------------

@router.get("/debug-url")
async def schwab_debug_url():
    """Temporary public endpoint to verify the exact auth URL being generated."""
    from app.core.config import settings
    manager = _get_token_manager()
    auth_url = manager.get_authorization_url()
    return {
        "callback_url_setting": settings.schwab_callback_url,
        "full_auth_url": auth_url,
    }


@router.get("/get-url")
async def schwab_get_url(user: dict = Depends(get_current_user)):
    """
    Return the Schwab authorization URL as JSON.

    The frontend calls this via authenticated fetch, then opens the URL
    in a popup directly. This avoids the problem of window.open() being
    unable to send Authorization headers to /login.
    """
    manager = _get_token_manager()
    auth_url = manager.get_authorization_url()
    logger.info("Schwab OAuth: Returning authorization URL to frontend")
    return {"authorization_url": auth_url}


@router.get("/login")
async def schwab_login(user: dict = Depends(get_current_user)):
    """
    Redirect the user to Schwab's login page.

    HOW IT WORKS:
      1. You click this link in your browser (or the frontend calls it)
      2. Your browser is redirected to Schwab's website
      3. You log in with your Schwab brokerage credentials (not your app credentials)
      4. You authorize our app to access your market data
      5. Schwab redirects your browser back to /callback with an auth code

    WHY require_read not require_write: We want the login to be easy to
    initiate. The actual token storage happens in the callback, which is
    secured differently (it only accepts Schwab's redirect).
    """
    manager = _get_token_manager()
    auth_url = manager.get_authorization_url()
    logger.info(f"Schwab OAuth: Redirecting user to Schwab login")
    return RedirectResponse(url=auth_url)


# ------------------------------------------------------------------
# 2. Callback — Schwab redirects here after login
# ------------------------------------------------------------------

@router.get("/callback")
async def schwab_callback(request: Request):
    """
    Handle Schwab's OAuth callback after user logs in.

    Schwab redirects the user's browser here with a URL like:
      https://127.0.0.1:8000/api/v1/auth/schwab/callback?code=AUTH_CODE_HERE

    We extract the code from the URL, exchange it with Schwab for tokens,
    and store the tokens securely.

    WHY NO AUTH CHECK: This endpoint is called by Schwab's redirect, not
    by the user directly. The browser follows the redirect from Schwab,
    so there's no auth header. We validate by checking that a valid
    authorization code is present (only Schwab can generate these).

    NOTE ON THE AUTH CODE: Schwab's authorization codes contain special
    characters including '%40' (URL-encoded '@'). We URL-decode the code
    before sending it to the token endpoint.
    """
    manager = _get_token_manager()

    # Extract the authorization code from the URL query params
    code = request.query_params.get("code")

    if not code:
        # Check if Schwab sent an error instead
        error = request.query_params.get("error")
        error_desc = request.query_params.get("error_description", "Unknown error")
        logger.error(f"Schwab OAuth callback error: {error} - {error_desc}")
        return HTMLResponse(
            content=f"""
            <html><body style="font-family: Arial; padding: 40px;">
                <h2 style="color: #d32f2f;">❌ Schwab Authorization Failed</h2>
                <p><strong>Error:</strong> {error}</p>
                <p><strong>Details:</strong> {error_desc}</p>
                <p>Close this window and try again from the app.</p>
            </body></html>
            """,
            status_code=400,
        )

    # URL-decode the code (Schwab encodes the '@' as %40)
    # WHY: The auth code looks like "C0.b3F...something%40" in the URL.
    # The %40 is a URL-encoded '@' character that's part of the code.
    # We need to decode it before sending it to Schwab's token endpoint.
    decoded_code = unquote(code)
    logger.info(f"Schwab OAuth: Received auth code (length: {len(decoded_code)})")

    try:
        result = await manager.exchange_code_for_tokens(decoded_code)

        return HTMLResponse(
            content=f"""
            <html><body style="font-family: Arial; padding: 40px;">
                <h2 style="color: #2e7d32;">✅ Schwab Connected Successfully!</h2>
                <p>Your Schwab account is now linked to the Options Analyzer.</p>
                <p><strong>Access token expires in:</strong> {result['expires_in']} seconds (auto-refreshes)</p>
                <p><strong>Refresh token expires in:</strong> 7 days (you'll need to re-login then)</p>
                <br>
                <p>You can close this window and return to the app.</p>
                <p><em>The app will now use Schwab for market data.</em></p>
                <script>setTimeout(function() {{ window.close(); }}, 500);</script>
            </body></html>
            """,
            status_code=200,
        )

    except Exception as e:
        logger.error(f"Schwab OAuth: Token exchange failed: {e}")
        return HTMLResponse(
            content=f"""
            <html><body style="font-family: Arial; padding: 40px;">
                <h2 style="color: #d32f2f;">❌ Token Exchange Failed</h2>
                <p><strong>Error:</strong> {str(e)}</p>
                <p>This usually means the authorization code expired (they're only valid for 30 seconds).</p>
                <p>Close this window, go back to the app, and try connecting again.</p>
            </body></html>
            """,
            status_code=500,
        )


# ------------------------------------------------------------------
# 3. Refresh — Manually trigger token refresh
# ------------------------------------------------------------------

@router.post("/refresh")
async def schwab_refresh(user: dict = Depends(get_current_user)):
    """
    Manually trigger a Schwab token refresh.

    Normally you don't need to call this — the system auto-refreshes
    when the access token expires. But it's useful for:
      - Testing that refresh works
      - Forcing a refresh before a batch of API calls
      - Debugging token issues

    WHY require_write: Refreshing tokens modifies stored secrets,
    which is a Tier 2 (WRITE) operation.
    """
    manager = _get_token_manager()
    try:
        result = await manager.refresh_tokens()
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


# ------------------------------------------------------------------
# 4. Status — Check token health
# ------------------------------------------------------------------

@router.get("/status")
async def schwab_status(user: dict = Depends(get_current_user)):
    """
    Check the current state of Schwab authentication.

    Returns whether tokens exist, when they expire, and whether
    the user needs to re-authenticate.

    The frontend will call this on load to show the Schwab connection
    status in the UI and prompt for re-auth when needed.
    """
    manager = _get_token_manager()
    return JSONResponse(
        content=manager.get_status(),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


# ------------------------------------------------------------------
# 5. Disconnect — Clear all Schwab tokens
# ------------------------------------------------------------------

@router.post("/disconnect")
async def schwab_disconnect(user: dict = Depends(get_current_user)):
    """
    Disconnect Schwab by clearing all stored tokens.

    After this, the system falls back to whichever provider is configured
    as the default (e.g., Tradier). The user would need to go through
    the login flow again to reconnect.
    """
    manager = _get_token_manager()
    await manager.disconnect()
    return {"status": "disconnected", "message": "Schwab tokens cleared"}
