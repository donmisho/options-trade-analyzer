"""
Analysis API endpoints (Phase 2)

THREE ENDPOINTS:
  POST /api/v1/analyze/verticals     — Score vertical spreads
  POST /api/v1/analyze/long-calls    — Score long call candidates
  POST /api/v1/analyze/directional   — Compare strategies for a thesis

ALL THREE follow the same pattern:
  1. Receive request with symbol + optional overrides
  2. Fetch the options chain from the market data provider
  3. Run the analysis engine
  4. Return ranked results

WHY POST not GET: The request body can include scoring weight
overrides, filter customization, and thesis parameters. This is
too complex for query strings and semantically these are "compute
this for me" requests, not simple resource retrievals.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.auth.dependencies import require_read
from app.providers.factory import ProviderFactory
from app.analysis.vertical_engine import (
    VerticalSpreadEngine, ScoringWeights, SpreadFilters
)
from app.analysis.long_call_engine import (
    LongCallEngine, LongCallWeights, LongCallFilters
)
from app.analysis.directional_engine import DirectionalEngine, Thesis

router = APIRouter(prefix="/analyze", tags=["Analysis"])

# Initialized in main.py at startup
_provider_factory: Optional[ProviderFactory] = None


def init_analysis_routes(factory: ProviderFactory):
    global _provider_factory
    _provider_factory = factory


def _get_factory() -> ProviderFactory:
    if _provider_factory is None:
        raise RuntimeError("Provider factory not initialized")
    return _provider_factory


# ─── Request Schemas ──────────────────────────────────────────────

class VerticalRequest(BaseModel):
    symbol: str
    spread_types: list[str] = Field(
        default=["bull_call", "bear_put"],
        description="Which spread types to analyze"
    )
    max_results: Optional[int] = Field(
        default=20,
        description="Max spreads to return"
    )
    # Optional weight overrides
    ev_weight: Optional[float] = None
    rr_weight: Optional[float] = None
    prob_weight: Optional[float] = None
    liq_weight: Optional[float] = None
    theta_weight: Optional[float] = None
    # Optional filter overrides
    min_dte: int = Field(default=14, ge=0, le=365)
    max_dte: int = Field(default=60, ge=1, le=730)
    strike_range_pct: float = Field(default=10.0, ge=1, le=50)


class LongCallRequest(BaseModel):
    symbol: str
    option_types: list[str]
    max_results: Optional[int] = Field(default=15)
    min_dte: int = Field(default=14, ge=0, le=365)
    max_dte: int = Field(default=60, ge=1, le=730)
    strike_range_pct: float = Field(default=10.0, ge=1, le=50)
    max_premium: Optional[float] = Field(
        default=1500.0,
        description="Max premium per contract in dollars"
    )


class DirectionalRequest(BaseModel):
    symbol: str
    direction: str = Field(
        description="'bullish' or 'bearish'"
    )
    target_price: float = Field(
        description="Where you think the stock is going"
    )
    timeframe_days: int = Field(
        default=30,
        description="Expected timeframe in days"
    )
    risk_budget: float = Field(
        description="Maximum dollars to risk on this trade"
    )
    min_dte: int = Field(default=14)
    max_dte: int = Field(default=90)
    strike_range_pct: float = Field(default=15.0)


# ─── Helper: Fetch Chain ──────────────────────────────────────────

async def _fetch_chain(
    symbol: str,
    user: dict,
    min_dte: int = 14,
    max_dte: int = 60,
    strike_range_pct: float = 10.0,
    option_type: Optional[str] = None,
) -> tuple[list[dict], float]:
    """
    Fetch options chain and underlying price from the provider.
    Returns (contracts, underlying_price).
    
    WHY this is a shared helper: All three endpoints need chain data.
    Extracting it avoids duplicating the provider lookup + error handling.
    """
    factory = _get_factory()
    provider = factory.get_market_data("tradier", user_id=user.get("sub"))
    
    try:
        chain_data = await provider.get_chain(
            symbol=symbol.upper(),
            min_dte=min_dte,
            max_dte=max_dte,
            strike_range_pct=strike_range_pct,
            option_type=option_type,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")
    
    contracts = chain_data.get("contracts", [])
    underlying_price = chain_data.get("underlying_price", 0)
    
    if not contracts:
        raise HTTPException(
            status_code=404,
            detail=f"No options contracts found for {symbol.upper()}"
        )
    if underlying_price <= 0:
        raise HTTPException(
            status_code=502,
            detail=f"Could not determine underlying price for {symbol.upper()}"
        )
    
    return contracts, underlying_price


# ─── Endpoints ────────────────────────────────────────────────────

@router.post("/verticals")
async def analyze_verticals(
    req: VerticalRequest,
    user: dict = Depends(require_read),
):
    """
    Score and rank all valid vertical spreads for a symbol.
    
    Replaces the "Vertical Spreads" sheet from the Excel tool.
    Returns spreads ranked by composite score (weighted combination
    of EV, reward:risk, probability, liquidity, and theta efficiency).
    """
    contracts, price = await _fetch_chain(
        req.symbol, user,
        min_dte=req.min_dte,
        max_dte=req.max_dte,
        strike_range_pct=req.strike_range_pct,
    )
    
    # Build weights (use overrides if provided, else defaults)
    weights = ScoringWeights()
    if req.ev_weight is not None:
        weights.expected_value = req.ev_weight
    if req.rr_weight is not None:
        weights.reward_risk = req.rr_weight
    if req.prob_weight is not None:
        weights.probability = req.prob_weight
    if req.liq_weight is not None:
        weights.liquidity = req.liq_weight
    if req.theta_weight is not None:
        weights.theta_efficiency = req.theta_weight
    
    try:
        weights.validate()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    
    filters = SpreadFilters(spread_types=req.spread_types)
    engine = VerticalSpreadEngine(weights=weights, filters=filters)
    
    result = engine.analyze(
        contracts=contracts,
        underlying_price=price,
        max_results=req.max_results,
    )
    
    result["symbol"] = req.symbol.upper()
    return result


@router.post("/long-calls")
async def analyze_long_calls(
    req: LongCallRequest,
    user: dict = Depends(require_read),
):
    """
    Score and rank long call candidates for a symbol.
    
    Replaces the "Naked Calls" sheet from the Excel tool.
    Returns calls ranked by composite score (weighted combination
    of delta alignment, theta efficiency, IV value, R:R, liquidity).
    """
    chain_type = None
    if len(req.option_types) == 1:
        chain_type = req.option_types[0]
    
    contracts, price = await _fetch_chain(
        req.symbol, user,
        min_dte=req.min_dte,
        max_dte=req.max_dte,
        strike_range_pct=req.strike_range_pct,
        option_type=chain_type,
    )
    
    filters = LongCallFilters(
        max_premium=req.max_premium or 1500.0,
        min_days_to_exp=req.min_dte,
        max_days_to_exp=req.max_dte,
        option_types=req.option_types,
    )
    engine = LongCallEngine(filters=filters)
    
    result = engine.analyze(
        contracts=contracts,
        underlying_price=price,
        max_results=req.max_results,
    )
    
    result["symbol"] = req.symbol.upper()
    return result


@router.post("/directional")
async def analyze_directional(
    req: DirectionalRequest,
    user: dict = Depends(require_read),
):
    """
    Compare strategies for a directional thesis.
    
    NEW functionality — takes your trade thesis and returns a
    structured comparison of 2-4 strategies, each evaluated for
    cost, max profit, breakeven, probability, and thesis fit.
    One strategy is flagged as "recommended."
    """
    if req.direction not in ("bullish", "bearish"):
        raise HTTPException(
            status_code=422,
            detail="Direction must be 'bullish' or 'bearish'"
        )
    
    contracts, price = await _fetch_chain(
        req.symbol, user,
        min_dte=req.min_dte,
        max_dte=req.max_dte,
        strike_range_pct=req.strike_range_pct,
    )
    
    thesis = Thesis(
        symbol=req.symbol.upper(),
        direction=req.direction,
        target_price=req.target_price,
        timeframe_days=req.timeframe_days,
        risk_budget=req.risk_budget,
        current_price=price,
    )
    
    engine = DirectionalEngine()
    result = engine.compare(thesis=thesis, contracts=contracts)
    
    return result
