"""
Options Analyzer API — Main Application

This is the entry point. It wires together:
  - Security: SecretsManager → AuthService → middleware
  - Database: SQLAlchemy models → async sessions
  - Providers: ProviderFactory → Tradier/Schwab adapters
  - Routes: Auth, Market Data, Config, (Analysis, Portfolio, Trading later)
  
Run locally:
    uvicorn app.main:app --reload

WHY FastAPI: It's the fastest Python web framework with built-in async support,
automatic API documentation (Swagger UI at /docs), request validation via
Pydantic, and dependency injection. It's the natural choice for a modern
Python API that will serve a web app, Excel Python, and MCP.
"""

import logging
import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.secrets import SecretsManager
from app.models.session import init_db
from app.auth.dependencies import init_auth
from app.providers.factory import ProviderFactory
from app.api.auth_routes import router as auth_router
from app.api.market_routes import router as market_router, init_market_routes
from app.api.config_routes import router as config_router
from app.api.analysis_routes import router as analysis_router, init_analysis_routes
from app.api.schwab_auth_routes import router as schwab_auth_router, init_schwab_auth_routes
from app.providers.schwab_token_manager import SchwabTokenManager
from app.api.evaluation_routes import router as evaluation_router, init_evaluation_routes
from app.api.user_routes import router as user_router
from app.api.entra_auth_routes import router as entra_auth_router
from app.api.agent_routes import router as agent_router, init_agent_routes
from app.api.admin_routes import router as admin_router
from app.providers.ai import AnthropicAdapter, FoundryAdapter
from app.ai.foundry_adapter import FoundryEvalAdapter
from app.agents.telemetry import init_agent_telemetry


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _install_odbc_if_needed():
    """
    Install ODBC Driver 18 for SQL Server on Azure App Service Linux containers.

    App Service Python images don't pre-install ODBC Driver 18. Rather than
    using a bash startup script (which loses the Python venv PATH), we install
    it here — after Python is already running — via subprocess. This runs
    synchronously at startup before any DB connections are attempted.

    No-op on Windows or systems without apt-get (local dev).
    """
    if sys.platform != "linux" or not shutil.which("apt-get"):
        return

    odbc_lib_dir = "/opt/microsoft/msodbcsql18/lib64"
    try:
        if os.path.isdir(odbc_lib_dir) and any(
            f.startswith("libmsodbcsql-18") for f in os.listdir(odbc_lib_dir)
        ):
            logger.info("ODBC Driver 18: already installed")
            return
    except OSError:
        pass

    logger.info("ODBC Driver 18: not found — installing (this takes ~60s)...")

    r = subprocess.run(
        ["curl", "-fsSL", "https://packages.microsoft.com/keys/microsoft.asc",
         "-o", "/etc/apt/trusted.gpg.d/microsoft.asc"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        logger.error(f"ODBC install: MS signing key download failed: {r.stderr.strip()}")
        return

    if os.path.exists("/etc/debian_version"):
        with open("/etc/debian_version") as f:
            deb_ver = f.read().strip().split(".")[0]
        repo_url = f"https://packages.microsoft.com/config/debian/{deb_ver}/prod.list"
    else:
        r2 = subprocess.run(["lsb_release", "-rs"], capture_output=True, text=True)
        ubuntu_ver = r2.stdout.strip() if r2.returncode == 0 else "22.04"
        repo_url = f"https://packages.microsoft.com/config/ubuntu/{ubuntu_ver}/prod.list"

    r = subprocess.run(
        ["curl", "-fsSL", repo_url, "-o", "/etc/apt/sources.list.d/mssql-release.list"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        logger.error(f"ODBC install: MS apt repo setup failed: {r.stderr.strip()}")
        return

    subprocess.run(["apt-get", "update", "-qq"], capture_output=True, text=True)

    env = {**os.environ, "ACCEPT_EULA": "Y"}
    r = subprocess.run(
        ["apt-get", "install", "-y", "-qq", "msodbcsql18"],
        env=env, capture_output=True, text=True,
    )
    if r.returncode != 0:
        logger.error(f"ODBC install: apt-get install failed: {r.stderr.strip()}")
    else:
        logger.info("ODBC Driver 18: installed successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown logic.
    
    WHY lifespan: FastAPI's lifespan context manager runs code once at
    startup (before any requests) and once at shutdown (after all requests
    finish). This is where we initialize singletons like the database,
    secrets manager, and provider factory.
    """
    # --- STARTUP ---
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # 0. Install ODBC Driver 18 if on Azure App Service Linux (needed for Azure SQL)
    _install_odbc_if_needed()

    # 1. Initialize database tables
    await init_db()
    logger.info("Database initialized")

    # 2. Initialize secrets manager (Key Vault or .env fallback)
    secrets_manager = SecretsManager(vault_url=settings.azure_keyvault_url)

    # 3. Initialize auth system with secrets
    init_auth(secrets_manager)
    logger.info("Auth system initialized")

    # 4. Initialize provider factory
    provider_factory = ProviderFactory(secrets_manager)
    init_market_routes(provider_factory)
    init_analysis_routes(provider_factory)

    # 5. Initialize Schwab OAuth token manager
    schwab_token_manager = SchwabTokenManager(secrets_manager)
    init_schwab_auth_routes(schwab_token_manager)
    provider_factory.init_schwab(schwab_token_manager)
    logger.info("Schwab OAuth token manager initialized")

    logger.info(f"Provider factory initialized. Available: {provider_factory.list_providers()}")

    # 6. Initialize AI provider for agent routes (SDK-based: triage, deep-dive, followup)
    if settings.ai_provider == "foundry":
        ai_provider = FoundryAdapter(
            resource=settings.foundry_resource,
            deployment=settings.foundry_deployment,
            api_key=secrets_manager.get("foundry-api-key"),
        )
        logger.info(f"Agent AI provider: Azure Foundry SDK ({settings.foundry_resource})")
    else:
        api_key = secrets_manager.get("anthropic-api-key")
        if not api_key:
            logger.warning("Agent AI provider: No API key found — agent routes disabled")
            ai_provider = None
        else:
            ai_provider = AnthropicAdapter(api_key=api_key)
            logger.info("Agent AI provider: Anthropic (direct)")

    if ai_provider:
        init_agent_routes(ai_provider)

    # 6b. Initialize evaluation adapter (httpx-based, structured outputs via output_format)
    #     API key comes from Key Vault ("foundry-api-key") — no .env needed
    #     Endpoint is non-secret config: set FOUNDRY_ENDPOINT in .env or App Service settings
    foundry_endpoint = settings.foundry_endpoint
    foundry_api_key = secrets_manager.get("foundry-api-key")
    if foundry_endpoint and foundry_api_key:
        eval_adapter = FoundryEvalAdapter(
            api_key=foundry_api_key,
            endpoint=foundry_endpoint,
            model=settings.foundry_model,
        )
        init_evaluation_routes(eval_adapter)
        logger.info(f"Evaluation AI provider: Foundry httpx ({foundry_endpoint})")
    else:
        logger.warning(
            "Evaluation AI provider: FOUNDRY_ENDPOINT or FOUNDRY_API_KEY not set — "
            "/evaluate/trade will return 503"
        )

    # 7. Initialize OpenTelemetry → Application Insights (agent observability)
    appinsights_cs = secrets_manager.get("applicationinsights-connection-string")
    init_agent_telemetry(appinsights_cs)

    logger.info(f"{settings.app_name} ready at http://{settings.host}:{settings.port}")

    yield  # App runs here

    # --- SHUTDOWN ---
    await provider_factory.clear_cache()
    logger.info(f"{settings.app_name} shut down")


# Create the FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Options analysis, portfolio tracking, and trading tools",
    lifespan=lifespan,
)

# --- CORS ---
# Allows the web frontend to call the API from a different origin
# We will change this when we deploy to production to something like https://yourapp.azurestaticapps.net

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://localhost:5173",
        "https://127.0.0.1:5173",
        "https://purple-ground-0d4efed10.4.azurestaticapps.net",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# --- ROUTES ---
app.include_router(auth_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(config_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(schwab_auth_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(entra_auth_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


# --- Health Check ---
@app.get("/health")
async def health_check():
    """Simple health check for monitoring and load balancers."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }
