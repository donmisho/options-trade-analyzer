"""
Authentication and authorization service.

Handles: password hashing, JWT tokens, TOTP MFA, tiered authorization,
and per-trade challenge-response verification.

SECURITY TIERS:
  Tier 1 (READ)  - View data, run analysis. Requires valid JWT.
  Tier 2 (WRITE) - Change config, log trades. Requires authenticated session.
  Tier 3 (TRADE) - Place orders. Requires per-trade challenge + TOTP.
"""

import uuid
import hashlib
import json
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings
from app.core.secrets import SecretsManager

logger = logging.getLogger(__name__)

# Password hashing using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, secrets_manager: SecretsManager):
        self.secrets = secrets_manager

    # ------------------------------------------------------------------
    # Passwords
    # ------------------------------------------------------------------

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    # ------------------------------------------------------------------
    # JWT Tokens
    # ------------------------------------------------------------------

    def _get_jwt_secret(self) -> str:
        """Retrieve JWT signing key from Key Vault / env."""
        secret = self.secrets.get("jwt-signing-key")
        if not secret:
            # First run: generate and store a key
            secret = secrets.token_hex(32)
            self.secrets.set("jwt-signing-key", secret)
            logger.warning("AuthService: Generated new JWT signing key")
        return secret

    def create_access_token(
        self,
        user_id: str,
        username: str,
        role: str,
        mfa_verified: bool = False,
    ) -> tuple[str, int]:
        """
        Create a JWT access token.

        Returns:
            (token_string, expires_in_seconds)

        WHY separate mfa_verified: After password auth, the token is issued
        with mfa_verified=False. Once the user provides their TOTP code,
        we issue a new token with mfa_verified=True. This way the frontend
        can check the token to know if MFA is still needed.
        """
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
        expire = datetime.now(timezone.utc) + expires_delta

        payload = {
            "sub": user_id,
            "username": username,
            "role": role,
            "mfa": mfa_verified,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),  # Unique token ID for audit trail
        }

        token = jwt.encode(
            payload, self._get_jwt_secret(), algorithm=settings.jwt_algorithm
        )
        return token, int(expires_delta.total_seconds())

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Decode and validate a JWT token.

        Returns:
            The payload dict if valid, None if invalid/expired.
        """
        try:
            payload = jwt.decode(
                token,
                self._get_jwt_secret(),
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except JWTError:
            return None

    # ------------------------------------------------------------------
    # TOTP / MFA
    # ------------------------------------------------------------------

    def generate_totp_secret(self, user_id: str, email: str) -> str:
        """
        Generate a new TOTP secret for a user and store it in Key Vault.

        Returns:
            The otpauth:// URI for QR code generation. The user scans this
            with Microsoft Authenticator (or any TOTP app).

        WHY return URI not secret: The raw secret should never be displayed
        as text. The URI encodes it into a format that authenticator apps
        understand when scanned as a QR code.
        """
        secret = pyotp.random_base32()

        # Store in Key Vault under per-user key
        self.secrets.set("totp-secret", secret, user_id=user_id)

        # Build the otpauth URI that authenticator apps scan
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name=email,
            issuer_name=settings.totp_issuer_name,
        )
        return uri

    def verify_totp(self, user_id: str, code: str) -> bool:
        """
        Verify a 6-digit TOTP code from the user's authenticator app.

        Allows ±1 time window (30 seconds each side) to account for
        clock drift between server and phone.
        """
        secret = self.secrets.get("totp-secret", user_id=user_id)
        if not secret:
            logger.warning(f"TOTP verify failed: no secret for user {user_id}")
            return False

        totp = pyotp.TOTP(secret)
        # valid_window=1 means accept current code ± 1 period (30s each)
        return totp.verify(code, valid_window=1)

    # ------------------------------------------------------------------
    # Per-Trade Challenge-Response
    # ------------------------------------------------------------------

    def create_trade_challenge(
        self, user_id: str, trade_params: dict
    ) -> tuple[str, str]:
        """
        Generate a per-trade MFA challenge.

        Args:
            user_id: Who is trading
            trade_params: The full trade parameters (symbol, legs, quantity, etc.)

        Returns:
            (challenge_number, challenge_token)
            - challenge_number: 4-digit number to display on screen
            - challenge_token: Signed JWT that binds the challenge to this trade

        HOW IT WORKS:
        1. Generate a random 4-digit number
        2. Hash the trade parameters (so we can detect tampering)
        3. Bundle everything into a signed JWT with a short expiry
        4. The user must submit this token + the challenge number + their TOTP
           to the execute endpoint
        """
        challenge_number = f"{secrets.randbelow(9000) + 1000}"

        # Hash the trade parameters to detect tampering
        trade_json = json.dumps(trade_params, sort_keys=True)
        trade_hash = hashlib.sha256(trade_json.encode()).hexdigest()

        expire = datetime.now(timezone.utc) + timedelta(
            seconds=settings.trade_challenge_expire_seconds
        )

        payload = {
            "type": "trade_challenge",
            "sub": user_id,
            "challenge": challenge_number,
            "trade_hash": trade_hash,
            "trade": trade_params,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }

        token = jwt.encode(
            payload, self._get_jwt_secret(), algorithm=settings.jwt_algorithm
        )
        return challenge_number, token

    def verify_trade_challenge(
        self,
        user_id: str,
        challenge_token: str,
        challenge_number: str,
        totp_code: str,
    ) -> tuple[bool, Optional[dict], str]:
        """
        Verify a per-trade MFA challenge.

        Returns:
            (success, trade_params, error_message)

        Checks ALL of:
        1. Challenge token is valid and not expired (2 min window)
        2. Challenge number matches what was generated
        3. Token was issued to this user
        4. TOTP code is valid (from their authenticator app)
        5. Trade parameters haven't been tampered with
        """
        # Decode the challenge token
        payload = self.verify_token(challenge_token)
        if not payload:
            return False, None, "Challenge expired or invalid"

        if payload.get("type") != "trade_challenge":
            return False, None, "Invalid challenge token type"

        if payload.get("sub") != user_id:
            return False, None, "Challenge belongs to a different user"

        if payload.get("challenge") != challenge_number:
            return False, None, "Challenge number does not match"

        # Verify TOTP from authenticator app
        if not self.verify_totp(user_id, totp_code):
            return False, None, "Invalid authenticator code"

        trade_params = payload.get("trade")
        return True, trade_params, "Verified"
