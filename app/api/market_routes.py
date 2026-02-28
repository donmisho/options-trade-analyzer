"""
Market data endpoints: quotes, option chains, expirations.

These are Tier 1 (read-only) — any authenticated user can access them.
MCP tools will call these endpoints too.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.models.schemas import Quote, OptionChainResponse
from app.auth.dependencies import require_read
from app.providers.factory import ProviderFactory
from app.core.config import settings

router = APIRouter(prefix="/market", tags=["Market Data"])

# Initialized in main.py at startup
_provider_factory: Optional[ProviderFactory] = None


def init_market_routes(factory: ProviderFactory):
    global _provider_factory
    _provider_factory = factory


def _get_factory() -> ProviderFactory:
    if _provider_factory is None:
        raise RuntimeError("Provider factory not initialized")
    return _provider_factory


@router.get("/quote/{symbol}", response_model=Quote)
async def get_quote(
    symbol: str,
    user: dict = Depends(require_read),
):
    """
    Get current price data for a symbol.
    
    Uses the authenticated user's configured market data provider.
    For most users, this will be Tradier. The provider adapter
    normalizes the response regardless of source.
    """
    factory = _get_factory()
    # TODO: look up user's provider preference from DB
    # For now, use Tradier
    provider = factory.get_market_data(
        settings.default_market_data_provider,
        user_id=user.get("sub"),
    )

    try:
        data = await provider.get_quote(symbol.upper())
        return Quote(**data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")


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
    provider = factory.get_market_data(
        settings.default_market_data_provider,
        user_id=user.get("sub"),
    )

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
    provider = factory.get_market_data(
        settings.default_market_data_provider,
        user_id=user.get("sub"),
    )

    try:
        expirations = await provider.get_expirations(symbol.upper())
        return {"symbol": symbol.upper(), "expirations": expirations}
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
    provider = factory.get_market_data(
        settings.default_market_data_provider,
        user_id=user.get("sub"),
    )

    try:
        strikes = await provider.get_strikes(symbol.upper(), expiration)
        return {"symbol": symbol.upper(), "expiration": expiration, "strikes": strikes}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")
