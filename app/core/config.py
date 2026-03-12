"""
Application settings loaded from environment variables.

WHY: pydantic-settings gives us validated, typed configuration that loads
from .env files in development and from environment variables in production.
This is the non-secret config. Secrets (API tokens, JWT keys) come from
the SecretsManager which talks to Azure Key Vault.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "Options Analyzer"
    app_version: str = "0.1.0"
    debug: bool = False

    skip_auth: bool = False  # Set to true in .env to bypass auth during development

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Database ---
    # SQLite for now; swap to PostgreSQL connection string later
    database_url: str = "sqlite+aiosqlite:///./options_analyzer.db"

    # --- Azure Key Vault ---
    # If set, secrets come from Key Vault. If empty, falls back to .env file.
    azure_keyvault_url: Optional[str] = None

    # --- Auth ---
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    # The actual JWT secret comes from SecretsManager, not here

    # --- TOTP / MFA ---
    totp_issuer_name: str = "Options Analyzer"
    # Trade challenge expiry in seconds
    trade_challenge_expire_seconds: int = 120

    # --- Provider Defaults ---
    # Which provider handles each role (can be overridden per-user)
    default_market_data_provider: str = "schwab"
    default_account_provider: Optional[str] = None
    default_trading_provider: Optional[str] = None

    # --- Tradier (non-secret settings) ---
    tradier_environment: str = "sandbox"  # "sandbox" or "production"

    # --- Schwab (non-secret settings) ---
    # App key and secret come from Key Vault ("schwab-app-key", "schwab-app-secret")
    schwab_callback_url: str = "https://127.0.0.1:8000/api/v1/auth/schwab/callback"

    # --- SSL for local HTTPS (Schwab OAuth requires it) ---
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None

    # --- Rate Limiting ---
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Entra ID (Azure AD) Authentication ---
    entra_tenant_id: str = ""
    entra_client_id: str = ""

    # --- AI Provider ---
    # "anthropic" = direct to Anthropic API (uses ANTHROPIC_API_KEY)
    # "foundry"   = Azure Foundry (uses FOUNDRY_RESOURCE + Entra ID)
    ai_provider: str = "anthropic"

    # --- Anthropic Direct ---
    anthropic_api_key: Optional[str] = None

    # --- Azure Foundry (SDK-based, used by agent routes) ---
    foundry_resource: Optional[str] = None
    foundry_deployment: str = "claude-sonnet-4-6"
    foundry_api_key: Optional[str] = None

    # --- Azure Foundry (httpx-based, used by evaluation routes for structured output) ---
    # Full URL: https://<resource>.services.ai.azure.com/anthropic/v1/messages
    foundry_endpoint: Optional[str] = None
    foundry_model: str = "claude-sonnet-4-6"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


# Singleton instance
settings = Settings()
