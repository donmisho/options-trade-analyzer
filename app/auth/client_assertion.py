"""
JWT client assertion builder for certificate-based confidential client auth.

WHY: Azure Entra tenant policy blocks client secrets. Instead, the backend
signs a short-lived JWT with the private key from the Key Vault certificate
`entra-bff-cert`. Entra validates the assertion against the uploaded public key.

This replaces the client_secret parameter in all token exchange requests.

SPEC: RFC 7521 / OIDC client_assertion_type = jwt-bearer
Header: { "alg": "RS256", "typ": "JWT", "x5t": "<sha1 thumbprint base64url>" }
Payload: { iss, sub, aud, jti, exp, iat, nbf }
"""

import base64
import hashlib
import logging
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


class ClientAssertionBuilder:
    """
    Loads the signing certificate from Key Vault once (lazy, cached) and
    builds fresh JWT assertions on demand.

    Instantiated once at app startup and shared across identity routes and
    SessionManager for token refresh.
    """

    def __init__(self, vault_url: str, cert_name: str, client_id: str):
        self.vault_url = vault_url
        self.cert_name = cert_name
        self.client_id = client_id
        self._private_key = None
        self._x5t: Optional[str] = None

    async def _load_certificate(self) -> None:
        """Load the PFX from Key Vault and cache the private key + x5t thumbprint."""
        if self._private_key is not None:
            return

        from azure.identity.aio import DefaultAzureCredential
        from azure.keyvault.secrets.aio import SecretClient
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding

        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=self.vault_url, credential=credential)

        try:
            # Key Vault exposes the certificate's PFX as a base64-encoded secret
            # with the same name as the certificate object.
            cert_secret = await secret_client.get_secret(self.cert_name)
            pfx_bytes = base64.b64decode(cert_secret.value)

            private_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, None)
            self._private_key = private_key

            # x5t: SHA-1 fingerprint of the DER-encoded certificate, base64url-encoded.
            # This goes in the JWT header so Entra knows which key to verify with.
            cert_der = cert.public_bytes(Encoding.DER)
            thumbprint = hashlib.sha1(cert_der).digest()
            self._x5t = (
                base64.urlsafe_b64encode(thumbprint).rstrip(b"=").decode()
            )

            logger.info(
                f"ClientAssertionBuilder: Loaded certificate {self.cert_name!r} "
                f"from {self.vault_url} (x5t={self._x5t[:8]}...)"
            )
        finally:
            await credential.close()
            await secret_client.close()

    async def build_assertion(self, token_url: str) -> str:
        """
        Build a fresh JWT client assertion for a token exchange request.

        The assertion is valid for 5 minutes — short-lived by design so
        a compromised assertion is useless within seconds.

        Args:
            token_url: The Entra token endpoint URL (used as the `aud` claim).

        Returns:
            A signed JWT string to pass as client_assertion in the token request.
        """
        await self._load_certificate()

        import jwt  # PyJWT

        now = int(time.time())
        payload = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": token_url,
            "jti": str(uuid.uuid4()),
            "exp": now + 300,   # 5 minutes
            "iat": now,
            "nbf": now,
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm="RS256",
            headers={"x5t": self._x5t},
        )
