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


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
    logger.info(f"Provider factory initialized. Available: {provider_factory.list_providers()}")

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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# --- ROUTES ---
app.include_router(auth_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(config_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")


# --- Health Check ---
@app.get("/health")
async def health_check():
    """Simple health check for monitoring and load balancers."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }
