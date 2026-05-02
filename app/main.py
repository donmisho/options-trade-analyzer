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

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

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
from app.api.watchlist_routes import router as watchlist_router
from app.api.named_watchlist_routes import router as named_watchlist_router, init_named_watchlist_routes
from app.api.entra_auth_routes import router as entra_auth_router
from app.api.identity_routes import router as identity_router, init_identity_routes
from app.auth.session_manager import SessionManager
from app.auth.client_assertion import ClientAssertionBuilder
from app.auth.dependencies import init_session
from app.api.agent_routes import router as agent_router, init_agent_routes
from app.api.admin_routes import router as admin_router
from app.api.position_routes import router as position_router, init_position_routes
from app.api.agents_routes import router as agents_router, init_agents_routes, update_next_run_at
from app.api.insight_routes import router as insight_router
from app.api.validation_routes import router as validation_router
from app.api.dashboard_routes import router as dashboard_router
from app.api.health_routes import router as health_router, init_health_routes
from app.api.service_routes import router as service_router, init_service_routes
from app.providers.ai import AnthropicAdapter, FoundryAdapter
from app.middleware.csrf import CSRFMiddleware

# Dev-only test routes — imported and registered only outside production
if settings.app_env != "production":
    from app.api.test_routes import router as test_router, init_test_routes as _init_test_routes  # noqa: E402
from app.ai.foundry_adapter import FoundryEvalAdapter
from app.agents.telemetry import init_agent_telemetry


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_app_startup_start: float | None = None


def _log_startup_timing(step: str, start_time: float) -> None:
    """Log a structured startup timing event (grep-friendly, pipe-separated)."""
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"STARTUP_TIMING | step={step} | elapsed_ms={elapsed_ms} | timestamp={timestamp}")


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
    global _app_startup_start
    _app_startup_start = time.monotonic()
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    _log_startup_timing("app_start", _app_startup_start)
    _log_startup_timing("routers_registered", _app_startup_start)

    # ODBC driver install moved to repo-root startup.sh (OTA-545).
    # App Service Configuration > General Settings > Startup Command must reference startup.sh.

    # 1. Initialize database tables
    await init_db()
    logger.info("Database initialized")
    _log_startup_timing("database_connected", _app_startup_start)

    # 2. Initialize secrets manager (Key Vault or .env fallback)
    secrets_manager = SecretsManager(vault_url=settings.azure_keyvault_url)

    # 3. Initialize auth system with secrets
    init_auth(secrets_manager)
    logger.info("Auth system initialized")

    # 3b. Initialize BFF session manager + client assertion builder (OTA-461/462)
    assertion_builder = None
    session_manager = None
    if settings.entra_client_id and settings.azure_keyvault_url:
        assertion_builder = ClientAssertionBuilder(
            vault_url=settings.azure_keyvault_url,
            cert_name="entra-bff-cert",
            client_id=settings.entra_client_id,
        )
        logger.info("BFF: ClientAssertionBuilder initialized (entra-bff-cert)")
    else:
        logger.warning(
            "BFF: ENTRA_CLIENT_ID or AZURE_KEYVAULT_URL not set — "
            "certificate-based assertion disabled (OIDC login will not work)"
        )

    session_manager = SessionManager(secrets_manager, assertion_builder)
    init_session(session_manager)
    init_identity_routes(session_manager, assertion_builder, secrets_manager)
    logger.info("BFF: SessionManager initialized")

    # 4. Initialize provider factory
    provider_factory = ProviderFactory(secrets_manager)
    init_market_routes(provider_factory)
    init_analysis_routes(provider_factory)
    init_position_routes(provider_factory)
    init_named_watchlist_routes(provider_factory)
    if settings.app_env != "production":
        _init_test_routes(provider_factory)

    # 5. Initialize Schwab OAuth token manager + proactive background refresh
    schwab_token_manager = SchwabTokenManager(secrets_manager)
    init_schwab_auth_routes(schwab_token_manager)
    init_service_routes(schwab_token_manager)
    provider_factory.init_schwab(schwab_token_manager)
    token_refresh_task = asyncio.create_task(schwab_token_manager.start_background_refresh())
    logger.info("Schwab OAuth token manager initialized (background refresh started)")

    logger.info(f"Provider factory initialized. Available: {provider_factory.list_providers()}")
    _log_startup_timing("providers_initialized", _app_startup_start)

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
    #     Prefers Foundry (FOUNDRY_ENDPOINT + foundry-api-key from Key Vault).
    #     Falls back to the already-initialized ai_provider (Anthropic) so that
    #     /evaluate/structured works in local dev without a Foundry deployment.
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
    elif ai_provider is not None:
        # AnthropicAdapter.chat() matches the FoundryEvalAdapter.chat() signature
        init_evaluation_routes(ai_provider)
        logger.info("Evaluation AI provider: Anthropic fallback (no FOUNDRY_ENDPOINT set)")
    else:
        logger.warning(
            "Evaluation AI provider: neither Foundry nor Anthropic configured — "
            "/evaluate/structured will return 503"
        )

    # 6c. Register hard gates (OTA-502+). Gates must be registered ONCE at startup,
    #     in evaluation order. First triggered gate wins (first-match-wins).
    from app.analysis.hard_gates import register_gate
    from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
    from app.analysis.hard_gates.negative_ev_gate import NegativeEVGate
    register_gate(EarningsInWindowGate())   # OTA-502: earnings-in-window (first — catalyst risk)
    register_gate(NegativeEVGate())         # OTA-503: negative EV (second — math quality gate)
    logger.info("Hard gates registered: earnings_in_window, negative_ev (OTA-502/503)")

    # 7. Initialize OpenTelemetry → Application Insights (agent observability)
    appinsights_cs = secrets_manager.get("applicationinsights-connection-string")
    init_agent_telemetry(appinsights_cs)

    # 8. Initialize Position Monitor Agent + APScheduler
    scheduler = None
    _eval_adapter_for_monitor = eval_adapter if (foundry_endpoint and foundry_api_key) else None
    if _eval_adapter_for_monitor is not None:
        from app.agents.position_monitor import PositionMonitorAgent
        from app.providers.schwab_context_source import SchwabPriceContextSource
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        # Build context source list — grows as new sources are added
        schwab_provider = provider_factory.get_market_data(
            settings.default_market_data_provider
        ) if settings.default_market_data_provider == "schwab" else None
        context_sources = []
        if schwab_provider is not None:
            context_sources.append(SchwabPriceContextSource(schwab_provider))

        position_monitor = PositionMonitorAgent(
            ai_adapter=_eval_adapter_for_monitor,
            context_sources=context_sources,
        )

        # Scheduled job — runs at 4:15pm ET Mon-Fri after market close
        async def _scheduled_monitor_run():
            from app.models.session import async_session
            async with async_session() as db:
                try:
                    result = await position_monitor.run(db=db)
                    logger.info(
                        f"Scheduled position monitor: {result.positions_processed} positions, "
                        f"{result.insights_triggered} escalations"
                    )
                except Exception as e:
                    logger.error(f"Scheduled position monitor failed: {e}")

        scheduler = AsyncIOScheduler()
        trigger = CronTrigger(
            day_of_week="mon-fri",
            hour=16,
            minute=15,
            timezone="America/New_York",
        )
        scheduler.add_job(_scheduled_monitor_run, trigger, id="position_monitor")
        scheduler.start()

        # Expose next fire time to the status endpoint
        job = scheduler.get_job("position_monitor")
        next_run = job.next_run_time if job else None
        init_agents_routes(position_monitor, next_run_at=next_run)
        logger.info(
            f"Position Monitor Agent ready. "
            f"Next scheduled run: {next_run}"
        )
    else:
        logger.warning(
            "Position Monitor Agent: no eval adapter configured — "
            "agent disabled (set FOUNDRY_ENDPOINT + foundry-api-key)"
        )
        init_agents_routes(None)

    # 9. Wire health routes — inject startup time + token manager for uptime/Schwab checks
    init_health_routes(_app_startup_start, schwab_token_manager)

    logger.info(f"{settings.app_name} ready at http://{settings.host}:{settings.port}")
    _log_startup_timing("startup_complete", _app_startup_start)

    yield  # App runs here

    # --- SHUTDOWN ---
    token_refresh_task.cancel()
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await provider_factory.clear_cache()
    logger.info(f"{settings.app_name} shut down")


# Create the FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Options analysis, portfolio tracking, and trading tools",
    lifespan=lifespan,
    redirect_slashes=False,
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
        "https://oa.tmtctech.ai",
        "https://oa-dev.tmtctech.ai",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF protection for BFF session-cookie auth (OTA-463).
# Validates X-CSRF-Token header on state-changing requests that carry a session cookie.
# The session manager is resolved lazily inside the middleware so this can be registered
# before the lifespan starts (where the session manager is created).
app.add_middleware(CSRFMiddleware)



# --- ROUTES ---
# identity_router must be registered BEFORE auth_router: both have GET /auth/me
# and the session-cookie version (identity) should take precedence during BFF migration.
app.include_router(identity_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(config_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(schwab_auth_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(watchlist_router, prefix="/api/v1")
app.include_router(named_watchlist_router, prefix="/api/v1")
app.include_router(entra_auth_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(position_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(insight_router, prefix="/api/v1")
app.include_router(validation_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(service_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
if settings.app_env != "production":
    app.include_router(test_router, prefix="/api/v1/test")


# --- Health Check ---
@app.get("/health")
async def health_check():
    """Simple health check for monitoring and load balancers."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


# --- Static Frontend (must be LAST — catch-all for SPA routing) ---
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_static_dir = Path(__file__).resolve().parent.parent / "static"

if _static_dir.is_dir() and (_static_dir / "index.html").exists():
    # Serve static assets (JS, CSS, images) from /assets/
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    # SPA fallback: any non-API path serves index.html
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve the React SPA. API routes take priority (registered first)."""
        file_path = _static_dir / path
        if file_path.is_file() and ".." not in path:
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))
