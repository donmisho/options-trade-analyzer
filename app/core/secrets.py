"""
Secrets management: Azure Key Vault in production, .env fallback for local dev.

WHY: Brokerage API tokens, JWT signing keys, and TOTP secrets are too sensitive
for config files or environment variables. Key Vault provides encrypted storage
with access logging and automatic rotation support. But for local development,
we fall back to a .env file so you don't need Azure running just to test.

HOW IT WORKS:
  - If AZURE_KEYVAULT_URL is set → authenticate via DefaultAzureCredential
    (which uses Managed Identity in Azure, or `az login` locally)
  - If not set → read from environment variables (loaded from .env by Settings)
  - Secrets are cached in memory after first fetch to avoid repeated API calls
  - Per-user secrets use the naming convention: {secret_name}--{user_id}
"""

import os
import pathlib
import logging
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

_DEV_TOKEN_FILE = pathlib.Path(".schwab_tokens.json")



class SecretsManager:
    def __init__(self, vault_url: Optional[str] = None):
        self._cache: dict[str, str] = {}
        self._client = None

        if vault_url:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                credential = DefaultAzureCredential()
                self._client = SecretClient(
                    vault_url=vault_url, credential=credential
                )
                logger.info(f"SecretsManager: Connected to Key Vault at {vault_url}")
            except Exception as e:
                logger.warning(
                    f"SecretsManager: Key Vault connection failed ({e}), "
                    f"falling back to environment variables"
                )
                self._client = None
        else:
            logger.info(
                "SecretsManager: No Key Vault URL configured, "
                "using environment variables"
            )

    def get(self, name: str, user_id: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a secret by name.

        Args:
            name: Secret name (e.g., "tradier-api-token", "jwt-signing-key")
            user_id: If provided, fetches the per-user version of the secret.
                     Key Vault name becomes: {name}--{user_id}
                     Env var name becomes: {NAME}__{USER_ID}

        Returns:
            The secret value, or None if not found.

        WHY user_id: In multi-user mode, each person has their own brokerage
        tokens stored separately. Your Tradier token is "tradier-api-token--don",
        your friend's is "tradier-api-token--alice". The analysis engine doesn't
        need to know this — it just calls secrets.get("tradier-api-token", user_id).
        """
        # Build the full key name
        full_name = f"{name}--{user_id}" if user_id else name

        # Check cache first
        if full_name in self._cache:
            return self._cache[full_name]

        value = None

        if self._client:
            # Production: fetch from Azure Key Vault
            try:
                secret = self._client.get_secret(full_name)
                value = secret.value
            except Exception as e:
                logger.warning(f"SecretsManager: Key Vault get({full_name}) failed: {e}")
        
        if value is None:
            # Fallback: read from environment variable
            # Convert "tradier-api-token--don" → "TRADIER_API_TOKEN__DON"
            env_name = full_name.replace("-", "_").upper()
            value = os.getenv(env_name)

        # Dev-mode file fallback for Schwab tokens (survives uvicorn --reload restarts)
        if value is None and not self._client and name == "schwab-token-data" and _DEV_TOKEN_FILE.exists():
            try:
                file_value = _DEV_TOKEN_FILE.read_text().strip()
                if file_value:
                    value = file_value
            except Exception:
                pass

        if value is not None:
            self._cache[full_name] = value

        return value

    def set(self, name: str, value: str, user_id: Optional[str] = None) -> bool:
        """
        Store a secret. Used for things like Schwab OAuth token refresh.

        In production, writes to Key Vault. In dev mode, only updates the
        in-memory cache (doesn't write to .env file).
        """
        full_name = f"{name}--{user_id}" if user_id else name

        if self._client:
            try:
                self._client.set_secret(full_name, value)
                self._cache[full_name] = value
                logger.info(f"SecretsManager: Updated {full_name} in Key Vault")
                return True
            except Exception as e:
                logger.error(f"SecretsManager: Key Vault set({full_name}) failed: {e}")
                return False
        else:
            # Dev mode: cache + file persistence for Schwab tokens
            self._cache[full_name] = value
            if name == "schwab-token-data":
                try:
                    _DEV_TOKEN_FILE.write_text(value)
                except Exception:
                    pass  # Fire-and-forget — don't block the main flow
            logger.info(f"SecretsManager: Updated {full_name} in memory cache (dev mode)")
            return True

    def delete(self, name: str, user_id: Optional[str] = None) -> bool:
        """Remove a secret (e.g., when a user disconnects their brokerage)."""
        full_name = f"{name}--{user_id}" if user_id else name
        self._cache.pop(full_name, None)

        if self._client:
            try:
                self._client.begin_delete_secret(full_name)
                return True
            except Exception:
                return False
        return True

    def clear_cache(self):
        """Clear the in-memory cache. Useful for testing."""
        self._cache.clear()
