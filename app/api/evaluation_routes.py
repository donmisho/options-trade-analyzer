"""
Trade Evaluation API endpoint.

ONE ENDPOINT:
  POST /api/v1/evaluate/trade      — Evaluate a proposed trade via Claude
  POST /api/v1/evaluate/follow-up  — Ask a follow-up about an evaluation
  GET  /api/v1/evaluate/health     — Check if AI provider is reachable

WHY BACKEND (not frontend calling Claude directly):
  - API key stays on the server, never exposed to the browser
  - Rate limiting and cost controls happen server-side
  - Evaluations are logged for the trade journal
  - Same endpoint works for both Anthropic and Foundry
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from app.auth.dependencies import require_read
from app.providers.ai.base import AIProvider, TradeContext
from app.providers.ai.prompts import compute_exit_levels, pre_screen_trade

router = APIRouter(prefix="/evaluate", tags=["Trade Evaluation"])

# Initialized in main.py at startup
_ai_provider: Optional[AIProvider] = None


def init_evaluation_routes(ai_provider: AIProvider):
    """Called from main.py to inject the AI provider."""
    global _ai_provider
    _ai_provider = ai_provider


def _get_ai() -> AIProvider:
    if _ai_provider is None:
        raise HTTPException(
            status_code=503,
            detail="AI provider not configured. Check AI_PROVIDER in .env"
        )
    return _ai_provider


# ─── Request Schemas ─────────────────────────────────────────────

class ThesisInput(BaseModel):
    direction: str = Field("Bullish", description="Bullish / Bearish / Neutral")
    timeframe_days: int = Field(30, ge=1, le=365)
    expected_move_target: Optional[float] = None
    conviction: str = Field("Medium", description="Low / Medium / High")
    risk_budget: float = Field(500, ge=50)


class TradeInput(BaseModel):
    # Market context
    symbol: str
    current_price: float
    sma_short: float
    sma_mid: float
    sma_long: float
    sma_periods: dict = Field(default={"short": 8, "mid": 21, "long": 50})
    vix: Optional[float] = None

    # Trade details
    strategy_type: str = "Vertical Spread"
    spread: str
    expiration: str
    debit_paid: float
    max_profit: float
    rr_ratio: float
    prob_of_profit: float
    composite_score: Optional[float] = None
    num_contracts: int = 1

    # Thesis
    thesis: ThesisInput


# ─── Response Schemas ────────────────────────────────────────────

class PreScreenFlag(BaseModel):
    level: str
    msg: str


class EvaluationResponse(BaseModel):
    verdict: str
    analysis: str
    exit_levels: dict
    pre_screen_flags: List[PreScreenFlag]
    model_used: str
    provider: str
    input_tokens: int
    output_tokens: int


class FollowUpRequest(BaseModel):
    question: str
    conversation_history: List[dict]


class FollowUpResponse(BaseModel):
    response: str
    provider: str


# ─── Endpoints ───────────────────────────────────────────────────

@router.post("/trade", response_model=EvaluationResponse)
async def evaluate_trade(request: TradeInput, user=Depends(require_read)):
    """
    Evaluate a proposed trade.

    Frontend sends trade details + thesis. Backend:
    1. Runs pre-screen flags (instant, rule-based)
    2. Builds the TradeContext
    3. Calls Claude via the configured AI provider
    4. Returns verdict + analysis + exit levels
    """
    ai = _get_ai()

    total_cost = request.debit_paid * 100 * request.num_contracts
    context = TradeContext(
        symbol=request.symbol,
        current_price=request.current_price,
        sma_short=request.sma_short,
        sma_mid=request.sma_mid,
        sma_long=request.sma_long,
        sma_periods=request.sma_periods,
        ma_alignment="",
        vix=request.vix,
        direction=request.thesis.direction,
        timeframe_days=request.thesis.timeframe_days,
        expected_move_target=request.thesis.expected_move_target,
        conviction=request.thesis.conviction,
        strategy_type=request.strategy_type,
        spread=request.spread,
        expiration=request.expiration,
        debit_paid=request.debit_paid,
        max_profit=request.max_profit,
        rr_ratio=request.rr_ratio,
        prob_of_profit=request.prob_of_profit,
        composite_score=request.composite_score,
        risk_budget=request.thesis.risk_budget,
        num_contracts=request.num_contracts,
        total_cost=total_cost,
    )

    exit_levels = compute_exit_levels(context)
    context.exit_levels = exit_levels

    flags = pre_screen_trade(context)

    try:
        result = await ai.evaluate_trade(context)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI evaluation failed: {str(e)}"
        )

    return EvaluationResponse(
        verdict=result.verdict,
        analysis=result.raw_response,
        exit_levels=result.exit_levels,
        pre_screen_flags=[PreScreenFlag(**f) for f in flags],
        model_used=result.model_used,
        provider=result.provider,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


@router.post("/follow-up", response_model=FollowUpResponse)
async def follow_up(request: FollowUpRequest, user=Depends(require_read)):
    """Ask a follow-up question about a previous evaluation."""
    ai = _get_ai()

    try:
        response = await ai.follow_up(
            question=request.question,
            conversation_history=request.conversation_history,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI follow-up failed: {str(e)}"
        )

    return FollowUpResponse(
        response=response,
        provider=ai.__class__.__name__,
    )


@router.get("/health")
async def ai_health():
    """Check if the AI provider is reachable."""
    ai = _get_ai()
    ok = await ai.health_check()
    if not ok:
        raise HTTPException(status_code=503, detail="AI provider unavailable")
    return {"status": "ok", "provider": ai.__class__.__name__}