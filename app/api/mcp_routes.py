"""
MCP Server Foundation — OTA-605.

Mounts the `ota-market-data` MCP server at /mcp inside the existing FastAPI
process. This module provides the transport layer only — no tools are exposed
here. Stories OTA-606 through OTA-608 add @mcp.tool() functions on top.

Auth: Bearer token validated against Key Vault (ADR-2 in mcp-server-spec.md).
The BFF cookie/CSRF path does NOT apply to /mcp — claude.ai is not a browser.

System principal: Every authenticated MCP request resolves to the active admin
user row in the users table (ADR-3). The bearer token does not encode identity.

Observability: mcp_tool_observability() opens an OTel span and writes an
agent_run_log row. Fire-and-forget — failures never block the tool response.
Stories 2–4 call this from their tool functions.
"""

import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.core.secrets import SecretsManager
from app.models.database import AgentRunLog, User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server instance — Stories 2–4 import this to register @mcp.tool()
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "ota-market-data",
    streamable_http_path="/",
    stateless_http=True,
    host="0.0.0.0",  # Disables auto DNS-rebinding protection (prod is behind Cloudflare)
)

# ---------------------------------------------------------------------------
# System principal resolver (ADR-3)
# ---------------------------------------------------------------------------

# Cached after first resolution — no per-request DB hit.
# If multiple admin users ever exist, add an is_system_principal boolean
# column or disambiguate by username.
_system_principal: Optional[User] = None


async def get_system_principal(session: AsyncSession) -> User:
    """Resolve the user_id that MCP tool calls act on behalf of."""
    global _system_principal
    if _system_principal is None:
        result = await session.execute(
            select(User)
            .where(User.role == "admin")
            .where(User.is_active == True)  # noqa: E712
            .limit(1)
        )
        _system_principal = result.scalar_one_or_none()
        if _system_principal is None:
            raise RuntimeError(
                "MCP system principal unresolvable: no active admin user. "
                "Create an admin User row before enabling MCP."
            )
    return _system_principal


# ---------------------------------------------------------------------------
# Bearer token auth middleware (ADR-2)
# ---------------------------------------------------------------------------

_secrets_manager: Optional[SecretsManager] = None


def init_mcp_routes(secrets_manager: SecretsManager) -> None:
    """Called from main.py lifespan to inject the SecretsManager reference."""
    global _secrets_manager
    _secrets_manager = secrets_manager


def _get_bearer_secret_name() -> str:
    """Derive the Key Vault secret name from the current environment."""
    if settings.app_env == "production":
        return "mcp-bearer-token-prod"
    return "mcp-bearer-token-dev"


class MCPBearerAuthMiddleware:
    """
    ASGI middleware that enforces Bearer token auth on all MCP requests.

    Wraps the Starlette app returned by FastMCP.streamable_http_app().
    Missing or invalid token → 401 with no body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            response = Response(status_code=401)
            await response(scope, receive, send)
            return

        token = auth_header[7:]  # Strip "Bearer " prefix

        if _secrets_manager is None:
            logger.error("MCP: SecretsManager not initialized — rejecting request")
            response = Response(status_code=401)
            await response(scope, receive, send)
            return

        expected_token = _secrets_manager.get(_get_bearer_secret_name())
        if not expected_token or token != expected_token:
            response = Response(status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def get_mcp_app() -> ASGIApp:
    """Return the MCP Starlette app wrapped with bearer auth middleware.

    Also initializes the session manager so it can be started in main.py's lifespan
    via start_mcp_session_manager(). FastAPI does not propagate lifespan events to
    mounted sub-apps, so we manage it explicitly.
    """
    return MCPBearerAuthMiddleware(mcp.streamable_http_app())


async def start_mcp_session_manager():
    """Start the MCP session manager's task group. Call from main.py lifespan.

    Returns an async context manager exit callback to shut it down.
    """
    ctx = mcp.session_manager.run()
    await ctx.__aenter__()
    return ctx


# ---------------------------------------------------------------------------
# Observability wrapper (Pattern 3 — Two-Track Observability)
# ---------------------------------------------------------------------------


async def mcp_tool_observability(
    tool_name: str,
    ticker: str | None = None,
    user_id: str | None = None,
    latency_ms: int | None = None,
    success: bool = True,
    error_code: str | None = None,
    db: AsyncSession | None = None,
) -> str | None:
    """
    Open an OTel span and write an agent_run_log row for one MCP tool call.

    Called by Stories 2–4 from inside each @mcp.tool() function.
    Fire-and-forget: failures are logged but never raised.

    Returns the otel_trace_id (or None if tracing is not configured).
    """
    run_id = str(uuid.uuid4())
    otel_trace_id = None

    # --- OTel span (best-effort) ---
    try:
        from app.agents.telemetry import _tracer
        if _tracer is not None:
            from opentelemetry.trace import SpanKind
            with _tracer.start_as_current_span(
                f"mcp/{tool_name}",
                kind=SpanKind.INTERNAL,
            ) as span:
                span.set_attribute("ota.mcp.tool", tool_name)
                if ticker:
                    span.set_attribute("ota.trade.symbol", ticker)
                if latency_ms is not None:
                    span.set_attribute("ota.latency_ms", latency_ms)
                span.set_attribute("ota.mcp.success", success)
                if error_code:
                    span.set_attribute("ota.mcp.error_code", error_code)

                trace_id = span.get_span_context().trace_id
                otel_trace_id = format(trace_id, "032x") if trace_id else None
    except Exception as e:
        logger.debug(f"MCP observability: OTel span failed (non-blocking): {e}")

    # --- agent_run_log row (best-effort) ---
    if db is not None:
        try:
            row = AgentRunLog(
                run_id=run_id,
                agent_name=f"mcp.{tool_name}",
                stage="tool_call",
                symbol=ticker,
                user_id=user_id,
                latency_ms=latency_ms,
                verdict="success" if success else "error",
                verdict_summary=error_code,
                otel_trace_id=otel_trace_id,
            )
            db.add(row)
            await db.commit()
        except Exception as e:
            logger.debug(f"MCP observability: agent_run_log write failed (non-blocking): {e}")
            try:
                await db.rollback()
            except Exception:
                pass

    return otel_trace_id
