"""
OTA-543: Verify lifespan startup → immediate shutdown produces no resource leaks.

Run with:
    pytest tests/lifespan/test_shutdown.py -v -W error::RuntimeWarning
"""

import asyncio
import warnings

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_settings():
    """Provide minimal settings that skip real infra (DB, Key Vault, Schwab)."""
    with patch("app.core.config.settings") as s:
        s.app_name = "OTA-Test"
        s.app_version = "0.0.1"
        s.app_env = "development"
        s.skip_auth = True
        s.debug = False
        s.host = "127.0.0.1"
        s.port = 8000
        s.azure_keyvault_url = None
        s.entra_client_id = ""
        s.entra_tenant_id = ""
        s.default_market_data_provider = "schwab"
        s.ai_provider = "anthropic"
        s.foundry_endpoint = None
        s.foundry_resource = None
        s.foundry_deployment = "test"
        s.foundry_model = "test"
        s.foundry_api_key = None
        s.anthropic_api_key = None
        s.session_cookie_name = "ota_session"
        s.session_ttl_hours = 24
        s.azure_storage_account_name = "test"
        s.azure_storage_dashboard_container = "test"
        s.azure_storage_sas_expiry_minutes = 15
        s.schwab_callback_url = "https://localhost/callback"
        s.jwt_algorithm = "HS256"
        s.jwt_access_token_expire_minutes = 30
        s.totp_issuer_name = "Test"
        s.trade_challenge_expire_seconds = 120
        s.database_url = "sqlite+aiosqlite://"
        s.ssl_certfile = None
        s.ssl_keyfile = None
        s.login_max_attempts = 5
        s.login_lockout_minutes = 15
        s.cors_origins = []
        s.entra_cert_thumbprint = ""
        s.entra_redirect_uri_dev = ""
        s.entra_redirect_uri_prod = ""
        s.default_account_provider = None
        s.default_trading_provider = None
        yield s


@pytest.mark.asyncio
async def test_lifespan_no_unclosed_resources(mock_settings):
    """
    Exercise startup → immediate teardown. Fail on any RuntimeWarning
    about unclosed connectors, transports, or tasks.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        from app.main import app, lifespan

        async with lifespan(app):
            pass  # immediate shutdown

        resource_warnings = [
            w for w in caught
            if issubclass(w.category, RuntimeWarning)
            and ("unclosed" in str(w.message).lower()
                 or "pending task" in str(w.message).lower())
        ]
        assert resource_warnings == [], (
            f"Unclosed resource warnings during shutdown: "
            f"{[str(w.message) for w in resource_warnings]}"
        )
