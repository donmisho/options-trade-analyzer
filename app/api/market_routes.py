"""
Market data endpoints: quotes, option chains, expirations.

These are Tier 1 (read-only) — any authenticated user can access them.
MCP tools will call these endpoints too.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Quote, OptionChainResponse
from app.models.session import get_db
from app.models.database import SymbolQuote
from app.auth.dependencies import require_read, require_write
from app.providers.factory import ProviderFactory
from app.core.config import settings

router = APIRouter(prefix="/market", tags=["Market Data"])
log = logging.getLogger(__name__)

# Initialized in main.py at startup
_provider_factory: Optional[ProviderFactory] = None


def init_market_routes(factory: ProviderFactory):
    global _provider_factory
    _provider_factory = factory


def _get_factory() -> ProviderFactory:
    if _provider_factory is None:
        raise RuntimeError("Provider factory not initialized")
    return _provider_factory


def _get_provider(factory: ProviderFactory, user_id: Optional[str]):
    """
    Return the market data provider to use for this request.

    Schwab is the primary provider. If Schwab is connected (OAuth tokens
    present), use it. Otherwise fall back to the configured default
    (Tradier) so dev/testing still works without Schwab credentials.
    """
    token_mgr = getattr(factory, '_schwab_token_manager', None)
    if token_mgr and token_mgr.get_status().get('connected'):
        return factory.get_market_data("schwab", user_id=user_id)
    return factory.get_market_data(settings.default_market_data_provider, user_id=user_id)


@router.get("/quote/{symbol}", response_model=Quote)
async def get_quote(
    symbol: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current price data for a symbol.

    Uses Schwab if connected (includes earnings/dividend dates), falls back to Tradier.
    Every successful quote is persisted to symbol_quotes for historical analysis.
    """
    factory = _get_factory()
    user_id = user.get("sub")
    sym = symbol.upper()

    try:
        provider = _get_provider(factory, user_id)
        data = await provider.get_quote(sym)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    # Persist quote snapshot (fire-and-forget — never fail the request over this)
    try:
        db.add(SymbolQuote(
            user_id=user_id,
            symbol=sym,
            price=data.get("price"),
            bid=data.get("bid"),
            ask=data.get("ask"),
            change=data.get("change"),
            change_pct=data.get("change_pct"),
            volume=data.get("volume"),
            provider=data.get("provider", "unknown"),
        ))
        await db.commit()
    except Exception as e:
        log.warning(f"Failed to persist quote for {sym}: {e}")

    return Quote(**data)


@router.get("/chain/{symbol}", response_model=OptionChainResponse)
async def get_option_chain(
    symbol: str,
    min_dte: int = Query(14, ge=0, le=365),
    max_dte: int = Query(45, ge=1, le=730),
    strike_range_pct: float = Query(10.0, ge=1, le=50),
    option_type: Optional[str] = Query(None, pattern="^(call|put)$"),
    user: dict = Depends(require_read),
):
    """
    Fetch a filtered options chain.

    Filters applied:
      - DTE range: only expirations within min_dte to max_dte days
      - Strike range: only strikes within ±strike_range_pct% of current price
      - Option type: optionally filter to calls only or puts only

    The user's config defaults are used if no query params are provided.
    Query params override config defaults for this request.
    """
    factory = _get_factory()
    provider = _get_provider(factory, user.get("sub"))

    try:
        data = await provider.get_chain(
            symbol=symbol.upper(),
            min_dte=min_dte,
            max_dte=max_dte,
            strike_range_pct=strike_range_pct,
            option_type=option_type,
        )
        return OptionChainResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")


@router.get("/expirations/{symbol}")
async def get_expirations(
    symbol: str,
    user: dict = Depends(require_read),
):
    """List available expiration dates for a symbol."""
    factory = _get_factory()
    provider = _get_provider(factory, user.get("sub"))

    try:
        expirations = await provider.get_expirations(symbol.upper())
        return {"symbol": symbol.upper(), "expirations": expirations}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")


@router.get("/history/{symbol}")
async def get_symbol_history(
    symbol: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    user: dict = Depends(require_read),
):
    """
    Get the closing price for a symbol on a specific date.
    Used by the dashboard to compute YTD returns.
    """
    factory = _get_factory()
    provider = _get_provider(factory, user.get("sub"))

    if not hasattr(provider, "get_daily_close"):
        raise HTTPException(status_code=501, detail="Historical data not supported by this provider")

    try:
        close = await provider.get_daily_close(symbol.upper(), date)
        return {"symbol": symbol.upper(), "date": date, "close": close}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")


@router.get("/strikes/{symbol}/{expiration}")
async def get_strikes(
    symbol: str,
    expiration: str,
    user: dict = Depends(require_read),
):
    """List available strike prices for a specific expiration."""
    factory = _get_factory()
    provider = _get_provider(factory, user.get("sub"))

    try:
        strikes = await provider.get_strikes(symbol.upper(), expiration)
        return {"symbol": symbol.upper(), "expiration": expiration, "strikes": strikes}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")


@router.get("/overview")
async def get_market_overview(
    user: dict = Depends(require_read),
):
    """
    Fetch live quotes for the four market overview symbols (SPY, QQQ, IWM, VIX).
    Used by the MarketOverviewWidget as the live data source.

    Full path: GET /api/v1/market/overview
    """
    factory = _get_factory()
    provider = _get_provider(factory, user.get("sub"))
    symbols = ["SPY", "QQQ", "IWM", "VIX"]
    quotes = {}
    for sym in symbols:
        try:
            quotes[sym] = await provider.get_quote(sym)
        except Exception:
            quotes[sym] = None
    return {"quotes": quotes, "fetched_at": datetime.now(timezone.utc).isoformat()}


@router.get("/instruments")
async def search_instruments(
    symbol: str = Query(..., min_length=1, description="Symbol prefix or full symbol to search"),
    user: dict = Depends(require_read),
):
    """
    Search for instruments by symbol prefix using Schwab's instrument search API.
    Falls back to an empty list if Schwab is unavailable.

    Full path: GET /api/v1/market/instruments?symbol={query}
    Returns: [{ symbol, name, type }]
    """
    factory = _get_factory()
    provider = _get_provider(factory, user.get("sub"))

    if not hasattr(provider, "search_instruments"):
        return {"instruments": []}

    try:
        results = await provider.search_instruments(symbol)
        return {"instruments": results}
    except Exception as e:
        log.warning(f"Instrument search failed for '{symbol}': {e}")
        return {"instruments": []}


@router.post("/collect-chains")
async def trigger_chain_collection(
    symbols: list[str],
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_write),
):
    """
    On-demand daily chain snapshot collection. Provide a list of symbols.
    Idempotent — a second call on the same day returns status: skipped for each.
    Scheduler calls this nightly; manual trigger available for testing.

    Full path: POST /api/v1/market/collect-chains
    """
    from app.analysis.chain_collection import collect_chain_snapshot

    factory = _get_factory()
    results = []
    for symbol in symbols:
        result = await collect_chain_snapshot(symbol.upper(), db, factory)
        results.append(result)

    return {
        "collected": len([r for r in results if r["status"] == "inserted"]),
        "skipped": len([r for r in results if r["status"] == "skipped"]),
        "errors": len([r for r in results if r["status"] == "error"]),
        "details": results,
    }
