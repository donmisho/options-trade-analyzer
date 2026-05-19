"""
MCP Server — OTA-605 Entra OAuth 2.1 Resource Server + OTA-606/607/608 tools.

Mounts the `ota-market-data` MCP server at /mcp inside the existing FastAPI
process. Auth follows the OAuth 2.1 Resource Server pattern: Microsoft Entra
is the Authorization Server; OTA's /mcp is the Resource Server. The MCP Python
SDK's TokenVerifier validates each access token (JWKS signature, audience,
scope, expiry). User identity is resolved from the JWT's oid claim to a User
row in the users table (User.id == Entra OID).

The BFF cookie/CSRF path does NOT apply to /mcp — claude.ai is not a browser.

Observability: mcp_tool_observability() opens an OTel span and writes an
agent_run_log row per request with the resolved user_id. Fire-and-forget —
failures never block the tool response.
"""

import contextvars
import logging
import math
import time
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import jwt
from jwt import PyJWKClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

from app.core.config import settings
from app.services.symbol_cache import to_api_symbol_cached
from app.core.secrets import SecretsManager
from app.models.database import AgentRunLog, User
from app.models.session import async_session
from app.providers.factory import CONTEXT_SOURCE_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contextvar: resolved user_id for the current MCP request
# ---------------------------------------------------------------------------
# Set during token verification; read by tool handlers for observability.
_mcp_user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_user_id", default=None
)


# ---------------------------------------------------------------------------
# Entra JWT Token Verifier (implements MCP SDK TokenVerifier protocol)
# ---------------------------------------------------------------------------

class EntraTokenVerifier:
    """Validate Entra-issued JWTs for the MCP Resource Server.

    Implements the mcp.server.auth.provider.TokenVerifier protocol:
        async def verify_token(self, token: str) -> AccessToken | None

    Validates: JWKS signature (RS256), audience, issuer, expiry, required scope.
    Resolves: oid claim → User row (User.id == Entra OID). Returns None if the
    user is not provisioned — the SDK treats this as a 401.
    """

    def __init__(self):
        self._jwks_url = (
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
            f"/discovery/v2.0/keys"
        )
        # Accept both v1.0 and v2.0 issuer formats. Which one Entra uses depends
        # on the accessTokenAcceptedVersion in the app registration manifest.
        # az CLI issues v1.0 tokens; claude.ai may issue either.
        tenant = settings.entra_tenant_id
        self._valid_issuers = [
            f"https://login.microsoftonline.com/{tenant}/v2.0",
            f"https://sts.windows.net/{tenant}/",
        ]
        self._audience = settings.entra_mcp_application_id_uri
        self._required_scope = settings.entra_mcp_required_scope
        self._jwks_client = PyJWKClient(self._jwks_url, cache_keys=True)

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return access info if valid."""
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._valid_issuers,
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            logger.debug("MCP auth: token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"MCP auth: token validation failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"MCP auth: unexpected error during token validation: {e}")
            return None

        # Check required scope (Entra JWT uses short form e.g. "mcp.invoke")
        scopes_short = claims.get("scp", "").split()
        if self._required_scope not in scopes_short:
            logger.warning(
                f"MCP auth: token missing required scope '{self._required_scope}' "
                f"(has: {scopes_short})"
            )
            return None

        # Resolve oid → User
        oid = claims.get("oid")
        if not oid:
            logger.warning("MCP auth: token missing oid claim")
            return None

        try:
            async with async_session() as db:
                result = await db.execute(select(User).where(User.id == oid))
                user = result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"MCP auth: DB lookup failed for oid {oid}: {e}")
            return None

        if user is None:
            logger.warning(f"MCP auth: oid {oid} not provisioned in users table")
            return None

        # Store resolved user_id in contextvar for tool handlers
        _mcp_user_id_var.set(str(user.id))

        # Include both short ("mcp.invoke") and fully qualified
        # ("api://<client-id>/mcp.invoke") scope forms. Entra JWT uses
        # short form; SDK middleware checks against AuthSettings.required_scopes
        # which uses the fully qualified form.
        scopes_full = scopes_short + [
            f"{self._audience}/{s}" for s in scopes_short
        ]

        return AccessToken(
            token=token,
            client_id=claims.get("appid", claims.get("azp", "")),
            scopes=scopes_full,
            expires_at=claims.get("exp"),
        )


# ---------------------------------------------------------------------------
# FastMCP server instance — Stories 2–4 import this to register @mcp.tool()
# ---------------------------------------------------------------------------

def _get_resource_server_url() -> str:
    """Derive the MCP resource server URL from the environment."""
    if settings.app_env == "production":
        return "https://oa.tmtctech.ai/mcp"
    elif settings.app_env != "development" or settings.azure_keyvault_url:
        # Deployed dev/staging environment
        return "https://oa-dev.tmtctech.ai/mcp"
    return "https://127.0.0.1:8000/mcp"


_token_verifier = EntraTokenVerifier()

mcp = FastMCP(
    "ota-market-data",
    token_verifier=_token_verifier,
    auth=AuthSettings(
        issuer_url=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        resource_server_url=_get_resource_server_url(),
        required_scopes=[f"{settings.entra_mcp_application_id_uri}/{settings.entra_mcp_required_scope}"],
    ),
    streamable_http_path="/",
    stateless_http=True,
    host="0.0.0.0",  # Disables auto DNS-rebinding protection (prod is behind Cloudflare)
)


# ---------------------------------------------------------------------------
# Initialization — called from main.py lifespan
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


def get_mcp_app() -> ASGIApp:
    """Return the MCP Starlette app with Entra OAuth auth.

    The SDK's streamable_http_app() automatically wires:
    - BearerAuthBackend (validates JWT via EntraTokenVerifier)
    - AuthContextMiddleware (populates auth_context_var)
    - RequireAuthMiddleware (checks scopes, returns 401/403 with WWW-Authenticate)
    """
    return mcp.streamable_http_app()


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


def _get_mcp_user_id() -> str | None:
    """Return the resolved user_id from the current MCP request context.

    Set by EntraTokenVerifier.verify_token() during auth. Returns None if
    called outside an authenticated MCP request (e.g., during startup).
    """
    return _mcp_user_id_var.get()


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
    user_id = _get_mcp_user_id()

    try:
        provider = _get_provider()
        api_ticker = to_api_symbol_cached(ticker, "schwab")
        result = await provider.get_quote(api_ticker)

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
    user_id = _get_mcp_user_id()

    try:
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
        api_ticker = to_api_symbol_cached(ticker, "schwab")
        chain = await provider.get_chain(
            symbol=api_ticker,
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
    user_id = _get_mcp_user_id()

    if periods is None:
        periods = [8, 21, 50]

    try:
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
        api_ticker = to_api_symbol_cached(ticker, "schwab")
        candles = await provider.get_price_history(api_ticker, num_periods=request_months)
        quote = await provider.get_quote(api_ticker)

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


# ---------------------------------------------------------------------------
# MCP Tools — OTA-608
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_earnings_date(ticker: str) -> dict:
    """Get the next confirmed earnings date for a stock, or confirm ETF status.

    For equities and ADRs, returns the next scheduled earnings date from
    Finnhub's confirmed-events feed, the time of day (before open / after
    close), and the number of calendar days until the event. Use this to
    check the no-earnings-holds rule before recommending option trades.

    For ETFs and other non-equity security types, returns immediately with
    next_earnings: null and is_etf: true — ETFs don't report earnings and
    automatically satisfy the no-earnings-holds rule.

    Args:
        ticker: Stock or ETF symbol (e.g. "MSFT", "QQQ", "SPY").

    Returns:
        For equities: ticker, next_earnings (date, time, confirmed, source),
        and days_until. For ETFs: ticker, next_earnings null, is_etf true.
        Returns an error object if the ticker is not in the symbol reference
        database or if Finnhub has no earnings record for the ticker.
    """
    t0 = time.monotonic()
    user_id = _get_mcp_user_id()

    try:
        # Step 1: Look up security type from symbol_reference (no ORM model)
        async with async_session() as db:
            result = await db.execute(
                text("SELECT asset_type FROM symbol_reference WHERE symbol = :sym"),
                {"sym": ticker.upper()},
            )
            row = result.fetchone()

        if row is None:
            latency_ms = int((time.monotonic() - t0) * 1000)
            try:
                async with async_session() as db:
                    await mcp_tool_observability(
                        "get_earnings_date", ticker=ticker, user_id=user_id,
                        latency_ms=latency_ms, success=False,
                        error_code="TICKER_NOT_FOUND", db=db,
                    )
            except Exception:
                pass
            return {
                "error": True,
                "error_code": "TICKER_NOT_FOUND",
                "message": f"Ticker {ticker.upper()} not found in symbol reference.",
            }

        asset_type = row[0]

        # Step 2: Non-equity, non-ADR → ETF short-circuit (no Finnhub call)
        if asset_type not in ("Equity", "ADR"):
            latency_ms = int((time.monotonic() - t0) * 1000)
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_earnings_date", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=True, db=db,
                )
            return {
                "ticker": ticker.upper(),
                "next_earnings": None,
                "is_etf": True,
            }

        # Step 3: Equity/ADR → call FinnhubEarnings adapter
        source = CONTEXT_SOURCE_REGISTRY.get("finnhub_earnings")
        if source is None:
            latency_ms = int((time.monotonic() - t0) * 1000)
            try:
                async with async_session() as db:
                    await mcp_tool_observability(
                        "get_earnings_date", ticker=ticker, user_id=user_id,
                        latency_ms=latency_ms, success=False,
                        error_code="EARNINGS_DATA_UNAVAILABLE", db=db,
                    )
            except Exception:
                pass
            return {
                "error": True,
                "error_code": "EARNINGS_DATA_UNAVAILABLE",
                "message": "Finnhub earnings provider not registered.",
            }

        raw = await source.fetch(ticker.upper())
        normalized = source.normalize(raw)

        earnings_date_str = normalized.get("next_earnings_date")

        if not earnings_date_str:
            latency_ms = int((time.monotonic() - t0) * 1000)
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_earnings_date", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code="EARNINGS_DATA_UNAVAILABLE", db=db,
                )
            return {
                "error": True,
                "error_code": "EARNINGS_DATA_UNAVAILABLE",
                "message": f"No upcoming earnings date found for {ticker.upper()}.",
            }

        # Compute days_until
        earnings_date = date.fromisoformat(earnings_date_str)
        today = date.today()
        days_until = (earnings_date - today).days

        # Map Finnhub time_of_day codes to spec labels
        time_map = {"bmo": "before_open", "amc": "after_close", "dmh": "during_market_hours"}
        time_label = time_map.get(normalized.get("time_of_day"), normalized.get("time_of_day"))

        latency_ms = int((time.monotonic() - t0) * 1000)

        response = {
            "ticker": ticker.upper(),
            "next_earnings": {
                "date": earnings_date_str,
                "time": time_label,
                "confirmed": True,
                "source": "finnhub",
            },
            "days_until": days_until,
        }

        async with async_session() as db:
            await mcp_tool_observability(
                "get_earnings_date", ticker=ticker, user_id=user_id,
                latency_ms=latency_ms, success=True, db=db,
            )

        return response

    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)

        try:
            async with async_session() as db:
                await mcp_tool_observability(
                    "get_earnings_date", ticker=ticker, user_id=user_id,
                    latency_ms=latency_ms, success=False,
                    error_code="EARNINGS_DATA_UNAVAILABLE", db=db,
                )
        except Exception:
            pass

        return {
            "error": True,
            "error_code": "EARNINGS_DATA_UNAVAILABLE",
            "message": str(e),
        }
