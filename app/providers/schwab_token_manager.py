"""
Schwab OAuth Token Manager — handles token storage, refresh, and auto-refresh.

WHY A SEPARATE SERVICE: The Schwab OAuth flow involves multiple moving parts:
  - Access tokens expire every 30 minutes
  - Refresh tokens expire every 7 days (hard limit from Schwab)
  - Tokens need to be stored securely (Key Vault in prod, .env in dev)
  - Every API call needs a valid access token

This service centralizes all of that. The Schwab market data adapter just
calls `await token_manager.get_access_token()` and gets back a valid token,
without knowing anything about refresh logic or storage.

TOKEN LIFECYCLE:
  1. User clicks "Connect Schwab" → redirected to Schwab login
  2. Schwab redirects back with auth code → we exchange for tokens
  3. Access token used for API calls (30 min lifetime)
  4. When access token expires → auto-refresh using refresh token
  5. When refresh token expires (7 days) → user must re-login

STORAGE STRATEGY:
  - Production (Azure): Key Vault stores tokens as secrets
  - Local dev: In-memory cache + .env fallback
  - Token data stored as JSON string with metadata (expiry times)
"""

import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.secrets import SecretsManager

logger = logging.getLogger(__name__)

# Schwab OAuth endpoints
SCHWAB_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


class SchwabTokenManager:
    """
    Manages Schwab OAuth tokens: storage, retrieval, and auto-refresh.

    Usage:
        manager = SchwabTokenManager(secrets_manager)

        # Get a valid access token (auto-refreshes if needed)
        token = await manager.get_access_token()

        # Check if connected
        status = manager.get_status()
    """

    def __init__(self, secrets_manager: SecretsManager):
        self.secrets = secrets_manager
        self._http_client = httpx.AsyncClient(timeout=30.0)

        # In-memory token cache for fast access
        # WHY: We don't want to hit Key Vault on every single API call.
        # Tokens are cached here after first retrieval and updated on refresh.
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._access_token_expires_at: Optional[datetime] = None
        self._refresh_token_expires_at: Optional[datetime] = None

        # Load any existing tokens from storage on init
        self._load_tokens_from_storage()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_authorization_url(self) -> str:
        """
        Build the URL that the user visits to log into Schwab.

        WHY: Schwab's OAuth requires the user to authenticate on Schwab's
        own website (not ours). This URL sends them there with our app's
        credentials. After they log in, Schwab redirects back to our
        callback URL with an authorization code.
        """
        app_key = self._get_app_key()
        callback_url = settings.schwab_callback_url

        url = (
            f"{SCHWAB_AUTH_URL}"
            f"?client_id={app_key}"
            f"&redirect_uri={quote(callback_url, safe='')}"
        )
        logger.info(f"SchwabTokenManager: Generated auth URL (callback: {callback_url})")
        return url

    async def exchange_code_for_tokens(self, auth_code: str) -> dict:
        """
        Exchange an authorization code for access + refresh tokens.

        This is called once after the user logs into Schwab and gets
        redirected back to our callback URL with a code in the URL.

        Args:
            auth_code: The authorization code from Schwab's redirect URL.
                       NOTE: Schwab codes contain special characters including '@'.

        Returns:
            dict with: access_token, refresh_token, expires_in, token_type

        WHY base64 auth: Schwab requires HTTP Basic Authentication for
        the token endpoint. We send app_key:app_secret as a Base64-encoded
        string in the Authorization header. This is standard OAuth 2.0.
        """
        app_key = self._get_app_key()
        app_secret = self._get_app_secret()

        # Build Basic Auth header (base64 of "app_key:app_secret")
        credentials = f"{app_key}:{app_secret}"
        b64_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

        headers = {
            "Authorization": f"Basic {b64_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": settings.schwab_callback_url,
        }

        logger.info("SchwabTokenManager: Exchanging auth code for tokens...")

        resp = await self._http_client.post(
            SCHWAB_TOKEN_URL,
            headers=headers,
            data=payload,
        )

        if resp.status_code != 200:
            error_detail = resp.text
            logger.error(f"SchwabTokenManager: Token exchange failed ({resp.status_code}): {error_detail}")
            raise Exception(f"Schwab token exchange failed: {resp.status_code} - {error_detail}")

        token_data = resp.json()
        logger.info("SchwabTokenManager: Token exchange successful!")

        # Store the tokens
        self._store_tokens(token_data)

        return {
            "access_token": token_data["access_token"],
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_in": token_data.get("expires_in", 1800),
            "refresh_token_expires_in": 604800,  # 7 days in seconds
            "scope": token_data.get("scope", ""),
        }

    async def get_access_token(self) -> str:
        """
        Get a valid access token, auto-refreshing if needed.

        This is the main method that the Schwab market data adapter calls.
        It handles all the complexity of token lifecycle:
          1. If we have a valid cached token → return it
          2. If access token expired but refresh token valid → refresh
          3. If refresh token expired → raise error (user must re-login)

        Returns:
            A valid Schwab access token string.

        Raises:
            Exception if no valid tokens exist (user needs to re-authenticate).
        """
        # Check if we have a valid access token
        if self._access_token and self._access_token_expires_at:
            # Give ourselves a 60-second buffer before expiry
            # WHY: If the token expires between when we check and when
            # Schwab receives our API call, the call would fail.
            buffer = timedelta(seconds=60)
            if datetime.now(timezone.utc) < (self._access_token_expires_at - buffer):
                return self._access_token

        # Access token expired or missing — try to refresh
        if self._refresh_token:
            if self._refresh_token_expires_at:
                if datetime.now(timezone.utc) >= self._refresh_token_expires_at:
                    logger.warning("SchwabTokenManager: Refresh token expired. User must re-authenticate.")
                    raise Exception(
                        "Schwab refresh token expired (7-day limit). "
                        "Please reconnect your Schwab account."
                    )

            logger.info("SchwabTokenManager: Access token expired, refreshing...")
            await self._refresh_access_token()
            return self._access_token

        # No tokens at all
        raise Exception(
            "No Schwab tokens available. Please connect your Schwab account "
            "by visiting /api/v1/auth/schwab/login"
        )

    async def refresh_tokens(self) -> dict:
        """
        Manually trigger a token refresh.

        Returns the new token metadata (not the tokens themselves — those
        are stored securely and not exposed via API).
        """
        if not self._refresh_token:
            raise Exception("No refresh token available. Please re-authenticate.")

        await self._refresh_access_token()

        return {
            "status": "refreshed",
            "access_token_expires_at": self._access_token_expires_at.isoformat()
            if self._access_token_expires_at
            else None,
            "refresh_token_expires_at": self._refresh_token_expires_at.isoformat()
            if self._refresh_token_expires_at
            else None,
        }

    def get_status(self) -> dict:
        """
        Check the current state of Schwab authentication.

        Returns a dict describing whether tokens exist, when they expire,
        and whether the user needs to re-authenticate.
        """
        now = datetime.now(timezone.utc)

        has_access = self._access_token is not None
        has_refresh = self._refresh_token is not None

        access_valid = False
        refresh_valid = False
        access_expires_in = None
        refresh_expires_in = None

        if has_access and self._access_token_expires_at:
            access_valid = now < self._access_token_expires_at
            access_expires_in = int(
                (self._access_token_expires_at - now).total_seconds()
            )

        if has_refresh and self._refresh_token_expires_at:
            refresh_valid = now < self._refresh_token_expires_at
            refresh_expires_in = int(
                (self._refresh_token_expires_at - now).total_seconds()
            )

        return {
            "connected": has_refresh and refresh_valid,
            "access_token_valid": access_valid,
            "access_token_expires_in_seconds": max(access_expires_in, 0)
            if access_expires_in
            else None,
            "refresh_token_valid": refresh_valid,
            "refresh_token_expires_in_seconds": max(refresh_expires_in, 0)
            if refresh_expires_in
            else None,
            "needs_reauth": not (has_refresh and refresh_valid),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_app_key(self) -> str:
        """Retrieve Schwab app key from Key Vault (falls back to SCHWAB_APP_KEY env var)."""
        key = self.secrets.get("schwab-app-key")
        if not key:
            raise Exception(
                "Schwab app key not configured. "
                "Add schwab-app-key to Key Vault."
            )
        return key

    def _get_app_secret(self) -> str:
        """Retrieve Schwab app secret from Key Vault (falls back to SCHWAB_APP_SECRET env var)."""
        secret = self.secrets.get("schwab-app-secret")
        if not secret:
            raise Exception(
                "Schwab app secret not configured. "
                "Add schwab-app-secret to Key Vault."
            )
        return secret

    def _load_tokens_from_storage(self):
        """
        Try to load existing tokens from SecretsManager on startup.

        WHY: If you restart the server, you don't want to lose your tokens
        and have to re-authenticate with Schwab. Tokens are persisted as a
        JSON blob in Key Vault (prod) or .env (dev).
        """
        token_json = self.secrets.get("schwab-token-data")
        if not token_json:
            logger.info("SchwabTokenManager: No stored tokens found")
            return

        try:
            data = json.loads(token_json)
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")

            if data.get("access_token_expires_at"):
                self._access_token_expires_at = datetime.fromisoformat(
                    data["access_token_expires_at"]
                )
            if data.get("refresh_token_expires_at"):
                self._refresh_token_expires_at = datetime.fromisoformat(
                    data["refresh_token_expires_at"]
                )

            logger.info(
                f"SchwabTokenManager: Loaded stored tokens. "
                f"Refresh token expires: {self._refresh_token_expires_at}"
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"SchwabTokenManager: Failed to load stored tokens: {e}")

    def _store_tokens(self, token_data: dict):
        """
        Store tokens in memory cache AND persistent storage.

        The token_data comes from Schwab's token endpoint and contains:
          - access_token: The short-lived token for API calls
          - refresh_token: The longer-lived token for getting new access tokens
          - expires_in: Seconds until access token expires (usually 1800 = 30 min)
        """
        now = datetime.now(timezone.utc)

        self._access_token = token_data["access_token"]
        self._refresh_token = token_data["refresh_token"]

        # Calculate expiry times
        expires_in = token_data.get("expires_in", 1800)  # Default 30 min
        self._access_token_expires_at = now + timedelta(seconds=expires_in)

        # Refresh token: 7 days from the ORIGINAL grant, not from refresh.
        # On initial auth, set it. On refresh, keep the original expiry.
        if not self._refresh_token_expires_at:
            self._refresh_token_expires_at = now + timedelta(days=7)

        # Persist to storage (Key Vault in prod, memory in dev)
        storage_data = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "access_token_expires_at": self._access_token_expires_at.isoformat(),
            "refresh_token_expires_at": self._refresh_token_expires_at.isoformat(),
            "updated_at": now.isoformat(),
        }

        self.secrets.set("schwab-token-data", json.dumps(storage_data))
        logger.info(
            f"SchwabTokenManager: Tokens stored. "
            f"Access expires: {self._access_token_expires_at}, "
            f"Refresh expires: {self._refresh_token_expires_at}"
        )

    async def _refresh_access_token(self):
        """
        Use the refresh token to get a new access token from Schwab.

        WHY: Access tokens only last 30 minutes. Rather than making the
        user re-login every half hour, we use the refresh token to silently
        get a new access token. This happens automatically when
        get_access_token() detects the current one has expired.
        """
        app_key = self._get_app_key()
        app_secret = self._get_app_secret()

        credentials = f"{app_key}:{app_secret}"
        b64_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

        headers = {
            "Authorization": f"Basic {b64_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        resp = await self._http_client.post(
            SCHWAB_TOKEN_URL,
            headers=headers,
            data=payload,
        )

        if resp.status_code != 200:
            error_detail = resp.text
            logger.error(
                f"SchwabTokenManager: Token refresh failed ({resp.status_code}): {error_detail}"
            )
            # If refresh fails, clear tokens so status shows needs_reauth
            self._access_token = None
            self._refresh_token = None
            raise Exception(
                f"Schwab token refresh failed: {resp.status_code}. "
                "Please reconnect your Schwab account."
            )

        token_data = resp.json()
        logger.info("SchwabTokenManager: Token refresh successful!")

        # Preserve the original refresh token expiry
        original_refresh_expiry = self._refresh_token_expires_at
        self._store_tokens(token_data)
        # Restore original expiry (7-day clock started at initial auth)
        if original_refresh_expiry:
            self._refresh_token_expires_at = original_refresh_expiry

    async def disconnect(self):
        """
        Clear all stored tokens. Used when user wants to disconnect Schwab.
        """
        self._access_token = None
        self._refresh_token = None
        self._access_token_expires_at = None
        self._refresh_token_expires_at = None
        self.secrets.delete("schwab-token-data")
        logger.info("SchwabTokenManager: Disconnected — all tokens cleared")

    async def close(self):
        """Clean up HTTP client."""
        await self._http_client.aclose()
