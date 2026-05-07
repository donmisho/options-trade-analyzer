"""
MCP Server — OTA-605 foundation + OTA-606 market-data tools + OTA-607 SMA tool.

Mounts the `ota-market-data` MCP server at /mcp inside the existing FastAPI
process. Exposes get_quote, get_option_chain, and get_smas tools that wrap
the active market-data provider adapter (Pattern 1 / ADR-4 pass-through).

Auth: Bearer token validated against Key Vault (ADR-2 in mcp-server-spec.md).
The BFF cookie/CSRF path does NOT apply to /mcp — claude.ai is not a browser.

System principal: Every authenticated MCP request resolves to the active admin
user row in the users table (ADR-3). The bearer token does not encode identity.

Observability: mcp_tool_observability() opens an OTel span and writes an
agent_run_log row. Fire-and-forget — failures never block the tool response.
"""

import logging
import math
import time
import uuid
from datetime import datetime, timezone
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
from app.models.session import async_session

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
_provider_factory = None


def init_mcp_routes(secrets_manager: SecretsManager) -> None:
    """Called from main.py lifespan to inject the SecretsManager reference."""
    global _secrets_manager
    _secrets_manager = secrets_manager


def init_mcp_provider(provider_factory) -> None:
    """Called from main.py lifespan after ProviderRegistry is ready."""
    global _provider_factory
    _provider_factory = provider_factory


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


# ---------------------------------------------------------------------------
# Helper — resolve market-data provider (ADR-4 pass-through)
# ---------------------------------------------------------------------------


def _get_provider():
    """Return the active market-data provider via ProviderRegistry."""
    if _provider_factory is None:
        raise RuntimeError("MCP: ProviderRegistry not initialized")
    return _provider_factory.get_market_data(settings.default_market_data_provider)


# ---------------------------------------------------------------------------
# MCP Tools — OTA-606
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_quote(ticker: str) -> dict:
    """Get a real-time price quote for a stock or ETF.

    Returns the last traded price, daily change, volume, 52-week range,
    and previous close for the given ticker symbol. Use this to check
    current prices before analyzing option chains.

    Args:
        ticker: Stock or ETF symbol (e.g. "QQQ", "AAPL", "SPY").

    Returns:
        A dict with ticker, price, volume, prev_close, change_pct,
        52-week high/low, volume_ratio, and timestamp. Returns an error
        object with error_code if the ticker is not found or the upstream
        provider is unavailable.
    """
    t0 = time.monotonic()
    user_id = None

    try:
        # Resolve system principal for observability
        async with async_session() as db:
            try:
                principal = await get_system_principal(db)
                user_id = str(principal.id)
            except Exception:
                pass  # Non-blocking — observability only

        provider = _get_provider()
        result = await provider.get_quote(ticker)

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Translate adapter shape → MCP spec shape
        response = {
            "ticker": result["symbol"],
            "price": result["price"],
            "bid": None,  # Not in Schwab quote adapter
            "ask": None,
            "volume": result["volume"],
            "prev_close": result.get("previous_close"),
            "change_pct": result.get("change_pct"),
            "timestamp": result["timestamp"].isoformat() if hasattr(result.get("timestamp", ""), "isoformat") else str(result.get("timestamp", "")),
            "market_state": None,  # Not in adapter; omitted per Phase 1 decision
        }

        # Fire-and-forget observability
        async with async_session() as db:
            await mcp_tool_observability(
                "get_quote", ticker=ticker, user_id=user_id,
                latency_ms=latency_ms, success=True, db=db,
            )

        return response

    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        err_str = str(e).lower()

        if "not found" in err_str or "no data" in err_str or "symbol" in err_str:
            error_code = "TICKER_NOT_FOUND"
        else:
            error_code = "SCHWAB_UNAVAILABLE"

        # Fire-and-forget observability
        try:
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_quote", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code=error_code, db=db,
                )
        except Exception:
            pass

        return {"error": True, "error_code": error_code, "message": str(e)}


@mcp.tool()
async def get_option_chain(
    ticker: str,
    expiration: str,
    option_type: str = "both",
    strike_range_pct: float = 0.15,
) -> dict:
    """Get the option chain for a ticker filtered to a specific expiration date.

    Returns all option contracts (calls, puts, or both) for the given ticker
    and expiration, filtered to strikes within a percentage range of the
    underlying price. Each contract includes bid, ask, mid, last, volume,
    open interest, implied volatility (as decimal), and full greeks.

    Args:
        ticker: Stock or ETF symbol (e.g. "QQQ", "AAPL").
        expiration: Expiration date in YYYY-MM-DD format (e.g. "2026-06-20").
        option_type: "call", "put", or "both" (default "both").
        strike_range_pct: Fraction of underlying price to filter strikes.
            0.15 means ±15% of current price. Default 0.15.

    Returns:
        A dict with ticker, underlying_price, expiration, dte, and an options
        array. Each option has occ_symbol, strike, type, bid, ask, mid, last,
        volume, open_interest, iv, delta, gamma, theta, vega. Returns an error
        object with error_code on failure.
    """
    t0 = time.monotonic()
    user_id = None

    try:
        # Resolve system principal for observability
        async with async_session() as db:
            try:
                principal = await get_system_principal(db)
                user_id = str(principal.id)
            except Exception:
                pass

        # Compute DTE from expiration string
        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        except ValueError:
            return {
                "error": True,
                "error_code": "EXPIRATION_INVALID",
                "message": f"Invalid date format: {expiration}. Use YYYY-MM-DD.",
            }

        today = datetime.now(timezone.utc).date()
        dte = (exp_date - today).days

        if dte < 0:
            return {
                "error": True,
                "error_code": "EXPIRATION_INVALID",
                "message": f"Expiration {expiration} is in the past.",
            }

        # Convert MCP strike_range_pct (decimal fraction) to adapter scale (percentage)
        adapter_strike_pct = strike_range_pct * 100  # 0.15 → 15.0

        # Map option_type for the adapter
        adapter_option_type = None  # "both" → None (adapter returns all)
        if option_type in ("call", "put"):
            adapter_option_type = option_type

        provider = _get_provider()
        chain = await provider.get_chain(
            symbol=ticker,
            min_dte=dte,
            max_dte=dte,
            strike_range_pct=adapter_strike_pct,
            option_type=adapter_option_type,
        )

        underlying_price = chain["underlying_price"]

        # Filter contracts to the exact expiration date
        # (adapter may return nearby dates if DTE math is off by a day)
        filtered = []
        for c in chain.get("contracts", []):
            if c.get("expiration") != expiration:
                continue
            filtered.append({
                "occ_symbol": c["symbol"],
                "strike": c["strike"],
                "type": c["option_type"],
                "bid": c["bid"],
                "ask": c["ask"],
                "mid": c["mid"],
                "last": c.get("last"),
                "volume": c["volume"],
                "open_interest": c["open_interest"],
                "iv": c.get("implied_volatility"),
                "delta": c.get("delta"),
                "gamma": c.get("gamma"),
                "theta": c.get("theta"),
                "vega": c.get("vega"),
            })

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Check if we got any contracts — if not, expiration may be invalid
        if not filtered and expiration not in chain.get("expirations_available", []):
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_option_chain", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code="EXPIRATION_INVALID", db=db,
                )
            return {
                "error": True,
                "error_code": "EXPIRATION_INVALID",
                "message": f"Expiration {expiration} is not available for {ticker}.",
                "available_expirations": chain.get("expirations_available", [])[:10],
            }

        response = {
            "ticker": chain["underlying"],
            "underlying_price": underlying_price,
            "expiration": expiration,
            "dte": dte,
            "options": filtered,
        }

        # Fire-and-forget observability
        async with async_session() as db:
            await mcp_tool_observability(
                "get_option_chain", ticker=ticker, user_id=user_id,
                latency_ms=latency_ms, success=True, db=db,
            )

        return response

    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        err_str = str(e).lower()

        if "not found" in err_str or "no data" in err_str or "symbol" in err_str:
            error_code = "TICKER_NOT_FOUND"
        else:
            error_code = "SCHWAB_UNAVAILABLE"

        try:
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_option_chain", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code=error_code, db=db,
                )
        except Exception:
            pass

        return {"error": True, "error_code": error_code, "message": str(e)}


# ---------------------------------------------------------------------------
# MCP Tools — OTA-607
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_smas(ticker: str, periods: list[int] | None = None) -> dict:
    """Get simple moving averages and trend alignment for a stock or ETF.

    Returns SMA values for the requested periods, the percentage distance
    between current price and each SMA, and an overall alignment signal
    (bullish, bearish, mixed, or neutral). Use this to check trend
    alignment before evaluating option trades — for example, the
    "extended >5% below 50-day SMA" flag uses the price_vs_sma_pct field.

    Args:
        ticker: Stock or ETF symbol (e.g. "QQQ", "AAPL", "SPY").
        periods: List of SMA periods in trading days (e.g. [8, 21, 50]).
            Defaults to [8, 21, 50] if not provided.

    Returns:
        A dict with ticker, current_price, smas (keyed by period with
        value and price_vs_sma_pct), alignment, and as_of date. Returns
        an error object with error_code if the ticker is not found, the
        provider is unavailable, or insufficient price history exists
        for a requested period.
    """
    t0 = time.monotonic()
    user_id = None

    if periods is None:
        periods = [8, 21, 50]

    try:
        # Resolve system principal for observability
        async with async_session() as db:
            try:
                principal = await get_system_principal(db)
                user_id = str(principal.id)
            except Exception:
                pass

        provider = _get_provider()

        # Determine how many months of daily history to request.
        # ~20 trading days per month; request enough to cover the longest period.
        max_period = max(periods)
        needed_months = math.ceil(max_period / 20) + 1  # +1 for safety margin
        # Schwab month periodType accepts: 1, 2, 3, 6
        valid_months = [1, 2, 3, 6]
        request_months = next((m for m in valid_months if m >= needed_months), None)

        if request_months is None:
            # Periods requiring > 6 months (~120 trading days) exceed
            # what the provider returns as daily candles.
            latency_ms = int((time.monotonic() - t0) * 1000)
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_smas", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code="INSUFFICIENT_HISTORY", db=db,
                )
            return {
                "error": True,
                "error_code": "INSUFFICIENT_HISTORY",
                "message": (
                    f"Period {max_period} exceeds available daily price history. "
                    f"Maximum supported period is approximately 120 trading days."
                ),
            }

        # Fetch price history and current quote
        candles = await provider.get_price_history(ticker, num_periods=request_months)
        quote = await provider.get_quote(ticker)

        current_price = quote.get("price", 0)
        if not current_price or current_price <= 0:
            latency_ms = int((time.monotonic() - t0) * 1000)
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_smas", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code="TICKER_NOT_FOUND", db=db,
                )
            return {
                "error": True,
                "error_code": "TICKER_NOT_FOUND",
                "message": f"Could not resolve current price for {ticker}.",
            }

        closes = [c["close"] for c in candles if isinstance(c.get("close"), (int, float))]

        # Compute each requested SMA
        smas = {}
        insufficient = []
        for period in periods:
            if len(closes) < period:
                insufficient.append(period)
                continue
            sma_value = round(sum(closes[-period:]) / period, 2)
            pct = round(((current_price - sma_value) / sma_value) * 100, 2)
            smas[str(period)] = {
                "value": sma_value,
                "price_vs_sma_pct": pct,
            }

        if insufficient:
            latency_ms = int((time.monotonic() - t0) * 1000)
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_smas", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code="INSUFFICIENT_HISTORY", db=db,
                )
            return {
                "error": True,
                "error_code": "INSUFFICIENT_HISTORY",
                "message": (
                    f"Only {len(closes)} trading days of history available. "
                    f"Insufficient for period(s): {insufficient}."
                ),
            }

        # Compute alignment
        above = [current_price > smas[str(p)]["value"] for p in periods]
        if all(above):
            alignment = "bullish"
        elif not any(above):
            alignment = "bearish"
        else:
            alignment = "mixed"

        latency_ms = int((time.monotonic() - t0) * 1000)

        response = {
            "ticker": ticker.upper(),
            "current_price": current_price,
            "smas": smas,
            "alignment": alignment,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }

        # Fire-and-forget observability
        async with async_session() as db:
            await mcp_tool_observability(
                "get_smas", ticker=ticker, user_id=user_id,
                latency_ms=latency_ms, success=True, db=db,
            )

        return response

    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        err_str = str(e).lower()

        if "not found" in err_str or "no data" in err_str or "symbol" in err_str:
            error_code = "TICKER_NOT_FOUND"
        else:
            error_code = "SCHWAB_UNAVAILABLE"

        try:
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_smas", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code=error_code, db=db,
                )
        except Exception:
            pass

        return {"error": True, "error_code": error_code, "message": str(e)}
