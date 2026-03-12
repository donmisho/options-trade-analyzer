"""
Trade Evaluation API endpoints — structured output version.

ENDPOINTS:
  POST /api/v1/evaluate/trade      — Evaluate a proposed trade via Claude
  POST /api/v1/evaluate/follow-up  — Ask a follow-up about an evaluation
  GET  /api/v1/evaluate/health     — Check if AI provider is reachable

WHY BACKEND (not frontend calling Claude directly):
  - API key stays on the server, never exposed to the browser
  - Rate limiting and cost controls happen server-side
  - Evaluations are logged for the trade journal
  - Same endpoint works for both Anthropic and Foundry

STRUCTURED OUTPUTS:
  This version uses FoundryEvalAdapter (httpx-based) which passes
  output_format to the Anthropic API, guaranteeing typed JSON back.
  No more regex parsing of Claude's text response.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from app.auth.dependencies import require_read
from app.ai.foundry_adapter import FoundryEvalAdapter
from app.ai.message_builder import build_trade_evaluation_message
from app.providers.ai.prompts import pre_screen_trade, compute_exit_levels
from app.providers.ai.base import TradeContext

router = APIRouter(prefix="/evaluate", tags=["Trade Evaluation"])

# Initialized in main.py at startup
_eval_adapter: Optional[FoundryEvalAdapter] = None


def init_evaluation_routes(adapter: FoundryEvalAdapter):
    """Called from main.py to inject the evaluation adapter."""
    global _eval_adapter
    _eval_adapter = adapter


def _get_adapter() -> FoundryEvalAdapter:
    if _eval_adapter is None:
        raise HTTPException(
            status_code=503,
            detail="Evaluation AI not configured. Set FOUNDRY_ENDPOINT and FOUNDRY_API_KEY in .env"
        )
    return _eval_adapter


# ─── Request Schemas ─────────────────────────────────────────────


class ThesisInput(BaseModel):
    direction: str = Field("Bullish", description="Bullish / Bearish / Neutral")
    timeframe_days: int = Field(30, ge=1, le=365)
    price_target: Optional[float] = None
    expected_move_target: Optional[float] = None  # backward compat alias
    conviction: str = Field("Medium", description="Low / Medium / High")
    risk_budget: float = Field(500, ge=50)


class EvaluateTradeRequest(BaseModel):
    """
    Trade evaluation request.

    Supports both old field names (long_strike/short_strike/net_debit/debit_paid)
    and new field names (buy_strike/sell_strike/net_cost) during the transition
    to the credit-spread engine display overhaul.
    """
    # Market context
    symbol: str
    current_price: float
    sma_8: Optional[float] = None
    sma_21: Optional[float] = None
    sma_50: Optional[float] = None
    # Also accept sma_short/mid/long for backward compat
    sma_short: Optional[float] = None
    sma_mid: Optional[float] = None
    sma_long: Optional[float] = None
    ma_alignment: str = "mixed"
    vix: Optional[float] = None

    # Trade details — new field names
    buy_strike: Optional[float] = None
    sell_strike: Optional[float] = None
    net_cost: Optional[float] = None   # positive=debit, negative=credit
    is_credit: bool = False

    # Trade details — old field names (backward compat)
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    net_debit: Optional[float] = None
    debit_paid: Optional[float] = None

    # Common trade fields
    option_type: Optional[str] = None  # "call" or "put"
    spread_type: Optional[str] = None  # "bull_call" or "bear_put"
    strategy_type: str = "Vertical Spread"
    strategy_label: Optional[str] = None
    spread: Optional[str] = None       # old: "440/445 Call Debit Spread"
    expiration: str
    max_profit: float
    max_loss: Optional[float] = None
    reward_risk_ratio: Optional[float] = None
    rr_ratio: Optional[float] = None   # backward compat
    prob_of_profit: float
    composite_score: Optional[float] = None
    breakeven: Optional[float] = None
    num_contracts: int = 1

    # Thesis
    thesis: ThesisInput

    # Pre-calculated exit levels (optional — computed server-side if not provided)
    exit_levels: Optional[dict] = None


# ─── Response Schemas ────────────────────────────────────────────


class PreScreenFlag(BaseModel):
    level: str
    msg: str


class EvaluateTradeResponse(BaseModel):
    # Phase 2.7 Thesis Matrix format
    verdict: str                 # "EXECUTE" | "WAIT"
    thesisInsights: dict         # ThesisInsights: 5 grouped rows
    executionPlan: dict          # ExecutionPlan: criteria + alerts or ladder

    # Meta
    pre_screen_flags: List[PreScreenFlag] = []
    provider: str = "foundry"


class FollowUpRequest(BaseModel):
    question: str
    original_trade_context: str  # The user message from the evaluate call
    original_verdict: str        # "EXECUTE" | "WAIT" | "PASS"


class FollowUpResponse(BaseModel):
    answer: str
    updated_verdict: Optional[str] = None
    updated_rationale: Optional[str] = None
    provider: str = "foundry"


# ─── Endpoints ───────────────────────────────────────────────────


@router.post("/trade", response_model=EvaluateTradeResponse)
async def evaluate_trade(request: EvaluateTradeRequest, user=Depends(require_read)):
    """
    Evaluate a proposed trade using Claude with structured output.

    Frontend sends trade details + thesis. Backend:
    1. Runs pre-screen flags (instant, rule-based)
    2. Builds the user message from trade data
    3. Calls Claude via Foundry with output_format (structured JSON)
    4. Returns typed TradeVerdict — no text parsing needed
    """
    adapter = _get_adapter()

    # ── Normalize field names (old → new) ──────────────────────
    buy_strike = request.buy_strike or request.long_strike or 0.0
    sell_strike = request.sell_strike or request.short_strike or 0.0
    net_cost = request.net_cost or request.net_debit or request.debit_paid or 0.0
    rr = request.reward_risk_ratio or request.rr_ratio or 0.0
    sma_8 = request.sma_8 or request.sma_short or 0.0
    sma_21 = request.sma_21 or request.sma_mid or 0.0
    sma_50 = request.sma_50 or request.sma_long or 0.0

    # Derive option_type from spread_type if not provided
    option_type = request.option_type
    if not option_type and request.spread_type:
        option_type = "call" if request.spread_type == "bull_call" else "put"
    option_type = option_type or "call"

    # Derive strategy label
    strategy_label = request.strategy_label or request.strategy_type
    if not strategy_label and request.spread_type:
        strategy_label = "Bull Call Spread" if request.spread_type == "bull_call" else "Bear Put Spread"

    max_loss = request.max_loss or abs(net_cost)
    breakeven = request.breakeven or (buy_strike + abs(net_cost) if not request.is_credit else 0.0)
    price_target = request.thesis.price_target or request.thesis.expected_move_target

    # ── Pre-screen (rule-based, instant) ───────────────────────
    # Build a TradeContext just for pre-screening
    pre_context = TradeContext(
        symbol=request.symbol,
        current_price=request.current_price,
        sma_short=sma_8,
        sma_mid=sma_21,
        sma_long=sma_50,
        sma_periods={"short": 8, "mid": 21, "long": 50},
        ma_alignment=request.ma_alignment,
        direction=request.thesis.direction,
        timeframe_days=request.thesis.timeframe_days,
        expected_move_target=price_target,
        conviction=request.thesis.conviction,
        debit_paid=abs(net_cost),
        max_profit=request.max_profit,
        rr_ratio=rr,
        prob_of_profit=request.prob_of_profit,
        risk_budget=request.thesis.risk_budget,
        num_contracts=request.num_contracts,
        total_cost=abs(net_cost) * 100 * request.num_contracts,
    )
    flags = pre_screen_trade(pre_context)

    # ── Compute exit levels (if not provided by frontend) ──────
    exit_levels = request.exit_levels
    if not exit_levels:
        computed = compute_exit_levels(pre_context)
        exit_levels = computed

    # ── Build user message ──────────────────────────────────────
    user_message = build_trade_evaluation_message(
        symbol=request.symbol,
        current_price=request.current_price,
        sma_8=sma_8,
        sma_21=sma_21,
        sma_50=sma_50,
        ma_alignment=request.ma_alignment,
        direction=request.thesis.direction,
        conviction=request.thesis.conviction,
        price_target=price_target or request.current_price,
        timeframe_days=request.thesis.timeframe_days,
        risk_budget=request.thesis.risk_budget,
        strategy_label=strategy_label,
        buy_strike=buy_strike,
        sell_strike=sell_strike,
        option_type=option_type,
        expiration=request.expiration,
        net_cost=net_cost,
        max_profit=request.max_profit,
        max_loss=max_loss,
        breakeven=breakeven,
        reward_risk_ratio=rr,
        prob_of_profit=request.prob_of_profit,
        composite_score=request.composite_score or 0.0,
        is_credit=request.is_credit,
        exit_levels=exit_levels,
    )

    try:
        verdict = await adapter.evaluate_trade(user_message)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI evaluation failed: {str(e)}"
        )

    return EvaluateTradeResponse(
        verdict=verdict.verdict,
        thesisInsights=verdict.thesisInsights.model_dump(),
        executionPlan=verdict.executionPlan.model_dump(),
        pre_screen_flags=[PreScreenFlag(**f) for f in flags],
        provider="foundry",
    )


@router.post("/follow-up", response_model=FollowUpResponse)
async def follow_up(request: FollowUpRequest, user=Depends(require_read)):
    """Ask a follow-up question about a previous evaluation."""
    adapter = _get_adapter()

    try:
        result = await adapter.follow_up(
            original_trade_context=request.original_trade_context,
            original_verdict=request.original_verdict,
            question=request.question,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI follow-up failed: {str(e)}"
        )

    return FollowUpResponse(
        answer=result.answer,
        updated_verdict=result.updated_verdict,
        updated_rationale=result.updated_rationale,
        provider="foundry",
    )


@router.get("/health")
async def ai_health():
    """Check if the evaluation AI provider is reachable."""
    adapter = _get_adapter()
    ok = await adapter.health_check()
    if not ok:
        raise HTTPException(status_code=503, detail="Evaluation AI provider unavailable")
    return {"status": "ok", "provider": "foundry"}
