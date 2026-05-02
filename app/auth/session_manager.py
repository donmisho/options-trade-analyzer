"""
Server-side session management for BFF (Backend-for-Frontend) auth pattern.

WHY: The browser-side MSAL.js approach stored tokens in localStorage, exposing
them to XSS attacks and causing redirect loops when tokens expired mid-session.
This server-side session store keeps tokens encrypted in the database — the
browser only ever holds an httponly cookie with a random session ID.

HOW IT WORKS:
  1. OIDC callback creates a session → returns session_id in an httponly cookie
  2. Every request reads the session from DB by session_id from cookie
  3. Tokens are encrypted at rest using Fernet (AES-128-CBC) with a key from Key Vault
  4. Token refresh happens server-side using the stored refresh_token — browser never
     sees the new access token

CLEANUP: Expired sessions are purged fire-and-forget after each new session creation.
"""

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.models.database import UserSession
from app.models.session import async_session as make_session

if TYPE_CHECKING:
    from app.auth.client_assertion import ClientAssertionBuilder
    from app.core.secrets import SecretsManager

logger = logging.getLogger(__name__)


class SessionManager:
    """Server-side session management for BFF auth pattern."""

    def __init__(
        self,
        secrets_manager: "SecretsManager",
        assertion_builder: Optional["ClientAssertionBuilder"] = None,
    ):
        self._secrets = secrets_manager
        self._assertion_builder = assertion_builder
        self._fernet: Optional[Fernet] = None

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    async def _ensure_fernet(self) -> None:
        """
        Initialize the Fernet cipher from Key Vault (async-safe).

        Uses the async Key Vault client so ManagedIdentityCredential HTTP calls
        run as coroutines instead of blocking the event loop. Must be awaited
        before any call to _encrypt() or _decrypt().
        """
        if self._fernet is not None:
            return

        key = await self._secrets.get_async("session-encryption-key")
        if not key:
            # First run: generate a key and store it in Key Vault
            raw_key = Fernet.generate_key()
            key = raw_key.decode()
            await self._secrets.set_async("session-encryption-key", key)
            logger.info("SessionManager: Generated new session encryption key")

        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def _encrypt(self, value: str) -> str:
        """Encrypt value. Requires _ensure_fernet() to have been awaited first."""
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        """Decrypt value. Requires _ensure_fernet() to have been awaited first."""
        return self._fernet.decrypt(value.encode()).decode()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_session(
        self,
        user_profile: dict,
        tokens: dict,
        provider: str = "entra",
    ) -> str:
        """
        Create a new server-side session. Returns the session_id.

        user_profile fields: user_id (or oid), email, display_name
        tokens fields: access_token, refresh_token, id_token, expires_in
        """
        session_id = secrets.token_urlsafe(64)
        csrf_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=settings.session_ttl_hours)

        await self._ensure_fernet()

        access_token_enc = None
        if tokens.get("access_token"):
            access_token_enc = self._encrypt(tokens["access_token"])

        refresh_token_enc = None
        if tokens.get("refresh_token"):
            refresh_token_enc = self._encrypt(tokens["refresh_token"])

        token_expires_at = None
        if tokens.get("expires_in"):
            token_expires_at = now + timedelta(seconds=int(tokens["expires_in"]))
        elif tokens.get("token_expires_at"):
            token_expires_at = tokens["token_expires_at"]

        user_id = user_profile.get("user_id") or user_profile.get("oid") or ""

        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            provider=provider,
            email=user_profile.get("email", ""),
            display_name=user_profile.get("display_name", ""),
            access_token_encrypted=access_token_enc,
            refresh_token_encrypted=refresh_token_enc,
            id_token=tokens.get("id_token"),
            token_expires_at=token_expires_at,
            csrf_token=csrf_token,
            expires_at=expires_at,
            last_active_at=now,
        )

        async with make_session() as db:
            db.add(session)
            await db.commit()

        logger.info(
            f"SessionManager: Created session for {user_profile.get('email')} "
            f"via {provider} (expires {expires_at.isoformat()})"
        )

        # Fire-and-forget cleanup — don't block the response
        asyncio.create_task(self.cleanup_expired())
        return session_id

    async def get_session(self, session_id: str) -> Optional[dict]:
        """
        Look up an active session by session_id.

        Returns None if not found or expired.
        Schedules a background token refresh if the token is within 5 minutes
        of expiry (fire-and-forget — does not block the request).

        last_active_at is updated via a fire-and-forget atomic conditional UPDATE
        (WHERE last_active_at < now - 5 min). This prevents concurrent SPA requests
        from contending on a row write lock — only the first request in any 5-minute
        window actually writes; the rest are no-ops. The SELECT here is read-only
        (shared lock) and releases its connection before the UPDATE fires.
        """
        now = datetime.now(timezone.utc)

        # --- SELECT: read-only, shared lock, connection released immediately ---
        async with make_session() as db:
            result = await db.execute(
                select(UserSession)
                .where(UserSession.session_id == session_id)
                .where(UserSession.expires_at > now)
            )
            session = result.scalar_one_or_none()

            if session is None:
                return None

            needs_refresh = (
                session.token_expires_at is not None
                and (session.token_expires_at - now) < timedelta(minutes=5)
            )
            session_data = {
                "user_id": session.user_id,
                "email": session.email or "",
                "display_name": session.display_name or "",
                "provider": session.provider,
                "csrf_token": session.csrf_token,
                "session_expires_at": session.expires_at.isoformat() + "Z",
            }

        # --- Fire-and-forget: atomic conditional UPDATE ---
        # Connection from the SELECT is already returned to the pool before this fires.
        asyncio.create_task(self._touch_last_active(session_id, now))

        if needs_refresh:
            asyncio.create_task(self.refresh_tokens(session_id))

        return session_data

    async def _touch_last_active(self, session_id: str, now: datetime) -> None:
        """
        Atomic conditional UPDATE of last_active_at. Fire-and-forget safe.

        The WHERE threshold (5-minute window) means concurrent requests are
        no-ops — only the first request in any 5-minute window actually acquires
        a write lock and updates the row.
        """
        try:
            async with make_session() as db:
                await db.execute(
                    update(UserSession)
                    .where(UserSession.session_id == session_id)
                    .where(UserSession.last_active_at < now - timedelta(minutes=5))
                    .values(last_active_at=now)
                )
                await db.commit()
        except Exception as e:
            logger.debug(f"SessionManager: _touch_last_active failed (non-fatal): {e}")

    async def refresh_tokens(self, session_id: str) -> bool:
        """
        Server-side token refresh using the stored refresh_token.

        Uses a JWT client assertion signed with the certificate from Key Vault
        (same credential type as the initial login callback).

        Returns True on success, False on failure. On failure, the session
        is invalidated — the user must log in again.
        """
        if self._assertion_builder is None:
            logger.warning("SessionManager: No assertion builder configured — cannot refresh tokens")
            return False

        async with make_session() as db:
            result = await db.execute(
                select(UserSession).where(UserSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if session is None or not session.refresh_token_encrypted:
                return False

            try:
                await self._ensure_fernet()
                refresh_token = self._decrypt(session.refresh_token_encrypted)
                provider_name = session.provider
            except Exception as e:
                logger.error(f"SessionManager: Failed to decrypt refresh token: {e}")
                return False

        try:
            from app.auth.providers import get_provider_config
            config = get_provider_config(provider_name, settings)
            token_url = config["token_url"]
            client_id = config["client_id"]

            assertion = await self._assertion_builder.build_assertion(token_url)

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_assertion_type": (
                            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                        ),
                        "client_assertion": assertion,
                    },
                )

            if resp.status_code != 200:
                logger.error(
                    f"SessionManager: Token refresh failed ({resp.status_code}): {resp.text}"
                )
                await self.delete_session(session_id)
                return False

            token_data = resp.json()
            now = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"SessionManager: Token refresh error: {e}")
            return False

        async with make_session() as db:
            result = await db.execute(
                select(UserSession).where(UserSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session.access_token_encrypted = self._encrypt(token_data["access_token"])
                if "refresh_token" in token_data:
                    session.refresh_token_encrypted = self._encrypt(token_data["refresh_token"])
                expires_in = token_data.get("expires_in", 3600)
                session.token_expires_at = now + timedelta(seconds=int(expires_in))
                await db.commit()

        logger.info(f"SessionManager: Token refresh succeeded for session {session_id[:8]}...")
        return True

    async def delete_session(self, session_id: str) -> None:
        """Hard delete a session row (logout or invalidation)."""
        async with make_session() as db:
            await db.execute(
                delete(UserSession).where(UserSession.session_id == session_id)
            )
            await db.commit()
        logger.info(f"SessionManager: Deleted session {session_id[:8]}...")

    async def cleanup_expired(self) -> int:
        """Delete all expired sessions. Returns count deleted. Fire-and-forget safe."""
        now = datetime.now(timezone.utc)
        try:
            async with make_session() as db:
                result = await db.execute(
                    delete(UserSession).where(UserSession.expires_at <= now)
                )
                await db.commit()
                count = result.rowcount or 0
                if count > 0:
                    logger.info(f"SessionManager: Cleaned up {count} expired sessions")
                return count
        except Exception as e:
            logger.warning(f"SessionManager: Cleanup failed (non-fatal): {e}")
            return 0
