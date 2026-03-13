"""
Trade Evaluation API endpoints — Phase 2.11 structured output.

ENDPOINTS:
  POST /api/v1/evaluate/structured — Multi-strategy AI evaluation (Phase 2.11)
  POST /api/v1/evaluate/trade      — DEPRECATED (410)
  POST /api/v1/evaluate/follow-up  — DEPRECATED (410) → use /agent/followup
  GET  /api/v1/evaluate/health     — Check if AI provider is reachable

STRUCTURED OUTPUTS:
  /evaluate/structured uses FoundryEvalAdapter.chat() with the DEEP_DIVE_SYSTEM
  prompt from SKILL.md. Claude returns a JSON array of TradeEvaluationCard
  objects validated by Pydantic. Retries once with correction context on
  JSON parse failure. Writes every call to agent_run_log.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.ai.foundry_adapter import FoundryEvalAdapter
from app.ai.message_builder import build_trade_evaluation_message
from app.providers.ai.prompts import pre_screen_trade, compute_exit_levels
from app.providers.ai.base import TradeContext
from app.models.session import get_db
from app.models.database import AgentRunLog
from app.models.schemas import TradeEvaluationCard
from app.skills.skill_loader import get_skill
from app.agents.telemetry import invoke_with_tracing
from app.analysis.black_scholes import compute_probability_matrix

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


# ─── Helpers ─────────────────────────────────────────────────────

def _extract_json_array(text: str) -> str:
    """Strip markdown code fences and return bare JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence line; strip closing fence if present
        inner = "\n".join(lines[1:]).strip()
        if inner.endswith("```"):
            inner = inner[:-3].strip()
        text = inner
    return text


def _try_parse_cards(raw: str) -> Optional[List[TradeEvaluationCard]]:
    """Attempt to parse raw text into a list of TradeEvaluationCard. Returns None on failure."""
    try:
        data = json.loads(_extract_json_array(raw))
        return [TradeEvaluationCard(**item) for item in data]
    except Exception:
        return None


def _build_structured_user_message(
    symbol: str,
    current_price: float,
    iv: float,
    sma_alignment: dict,
    strategy_keys: List[str],
    scores: Optional[dict],
    trade: Optional[dict],
    current_date: str,
) -> str:
    """Build the user prompt for the structured evaluation call."""
    sma_8 = sma_alignment.get("sma_8", "N/A")
    sma_21 = sma_alignment.get("sma_21", "N/A")
    sma_50 = sma_alignment.get("sma_50", "N/A")
    alignment = sma_alignment.get("alignment", sma_alignment.get("ma_alignment", "mixed"))

    lines = [
        f"Evaluate {len(strategy_keys)} strategies for {symbol}. "
        "Return a JSON array with one TradeEvaluationCard per strategy.",
        "",
        f"Current date: {current_date}",
        "",
        "=== MARKET CONTEXT ===",
        f"Symbol: {symbol} | Price: {current_price}",
        f"SMA 8: {sma_8} | SMA 21: {sma_21} | SMA 50: {sma_50}",
        f"Trend alignment: {alignment}",
        f"IV (annualized): {iv:.1%}",
        "",
        "=== STRATEGIES TO EVALUATE ===",
    ]

    for key in strategy_keys:
        label = key.replace("-", " ").title()
        score = (scores or {}).get(key)
        lines.append("")
        lines.append(f"Strategy key: {key}")
        lines.append(f"Strategy label: {label}")
        if score is not None:
            lines.append(f"Score: {score} / 100")
        if trade:
            lines.append(f"Trade data: {json.dumps(trade)}")

    lines += [
        "",
        "Populate all TradeEvaluationCard fields for each strategy.",
        "Set verdict from score (>=70 EXECUTE, 50-69 WAIT, <50 PASS).",
        "claude_read: 2-3 sentences, specific, no generic statements.",
        "key_risks: exactly 2-3 items, each under 15 words.",
        "thesis_invalidators: exactly 2-3 specific price/event conditions.",
    ]
    return "\n".join(lines)


# ─── Structured Evaluation Schemas ───────────────────────────────

class StructuredEvaluationRequest(BaseModel):
    """
    Request for structured multi-strategy AI evaluation.

    sma_alignment dict keys: sma_8, sma_21, sma_50, alignment (or ma_alignment).
    scores dict maps strategy_key → int 0-100 (from scorecard; optional).
    trade dict contains the pre-built trade proposal (optional; Claude infers if omitted).
    """
    symbol: str
    current_price: float = Field(..., gt=0)
    iv: float = Field(..., gt=0, description="Annualized IV as decimal (0.25 = 25%)")
    sma_alignment: dict
    strategy_keys: List[str] = Field(..., min_length=1, max_length=5)
    scores: Optional[dict] = None       # {strategy_key: int}
    trade: Optional[dict] = None        # pre-populated trade proposal


class StructuredEvaluationResponse(BaseModel):
    evaluations: List[TradeEvaluationCard]
    evaluated_at: str
    agent_run_id: str


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


@router.post("/structured", response_model=StructuredEvaluationResponse)
async def evaluate_structured(
    request: StructuredEvaluationRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 2.11 — Structured multi-strategy AI evaluation.

    For each strategy_key:
      1. Computes a Black-Scholes probability matrix (iv + derived dte)
      2. Builds a prompt using the DEEP_DIVE_SYSTEM from SKILL.md
      3. Calls Claude via Foundry and parses JSON into TradeEvaluationCard list
      4. Retries once with correction context if JSON parsing fails
      5. Writes the full input/output to agent_run_log
    """
    adapter = _get_adapter()
    skill = get_skill("claude-trade-agent")
    run_id = str(uuid.uuid4())
    # Treat synthetic dev-user (SKIP_AUTH) as anonymous — FK requires a real users.id
    _sub = user.get("sub", "")
    user_id = _sub if (len(_sub) == 36 and "-" in _sub) else None
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Derive DTE for the probability matrix
    dte = 30  # default
    if request.trade:
        if "dte" in request.trade:
            dte = int(request.trade["dte"])
        elif "expiration" in request.trade:
            from datetime import date
            try:
                exp = date.fromisoformat(request.trade["expiration"])
                dte = max(1, (exp - date.today()).days)
            except ValueError:
                pass

    # Compute probability matrix once (same IV/price/DTE across all strategies)
    pm = compute_probability_matrix(
        current_price=request.current_price,
        iv=request.iv,
        dte=dte,
    )
    pm_dict = {
        "price_levels": pm.price_levels,
        "dates": [d.isoformat() for d in pm.dates],
        "matrix": pm.matrix,
    }

    system_prompt = skill.get("DEEP_DIVE_SYSTEM")
    user_message = _build_structured_user_message(
        symbol=request.symbol,
        current_price=request.current_price,
        iv=request.iv,
        sma_alignment=request.sma_alignment,
        strategy_keys=request.strategy_keys,
        scores=request.scores,
        trade=request.trade,
        current_date=current_date,
    )

    market_snapshot = {
        "symbol": request.symbol,
        "underlying_price": request.current_price,
        "iv": request.iv,
        **request.sma_alignment,
    }

    async with invoke_with_tracing(
        "claude-trade-agent", "structured_eval",
        symbol=request.symbol,
        session_id=run_id,
        prompt_version=skill.prompt_version,
    ) as span_ctx:
        try:
            result = await adapter.chat(system_prompt, user_message, max_tokens=3000)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI evaluation failed: {e}")

        span_ctx["input_tokens"] = result["input_tokens"]
        span_ctx["output_tokens"] = result["output_tokens"]

    raw_text = result["text"]
    evaluations = _try_parse_cards(raw_text)

    # Retry once with correction context if initial parse failed
    if evaluations is None:
        try:
            retry_result = await adapter.chat(
                system_prompt,
                user_message,
                max_tokens=3000,
                extra_messages=[
                    {"role": "assistant", "content": raw_text},
                    {
                        "role": "user",
                        "content": (
                            "Your response was not valid JSON. "
                            "Return ONLY a JSON array of TradeEvaluationCard objects. "
                            "No preamble, no markdown fences, no explanation."
                        ),
                    },
                ],
            )
            raw_text = retry_result["text"]
            result["input_tokens"] += retry_result["input_tokens"]
            result["output_tokens"] += retry_result["output_tokens"]
            evaluations = _try_parse_cards(raw_text)
        except Exception:
            pass  # fall through to error below

    if evaluations is None:
        raise HTTPException(
            status_code=502,
            detail="AI returned malformed JSON for structured evaluation after retry.",
        )

    # Inject the pre-computed probability matrix into every card
    for card in evaluations:
        card.probability_matrix = pm_dict

    # Write to agent_run_log
    verdicts_summary = ", ".join(f"{c.strategy_key}={c.verdict}" for c in evaluations)
    db.add(AgentRunLog(
        run_id=run_id,
        agent_name="claude-trade-agent",
        stage="structured_eval",
        symbol=request.symbol,
        user_id=user_id,
        prompt_system=system_prompt,
        prompt_user=user_message,
        prompt_version=skill.prompt_version,
        market_snapshot=market_snapshot,
        trade_snapshot={"strategy_keys": request.strategy_keys, "trade": request.trade},
        model_response_raw=raw_text,
        verdict=None,
        verdict_summary=verdicts_summary,
        otel_trace_id=span_ctx.get("otel_trace_id"),
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        model_name=result["model"],
        created_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    return StructuredEvaluationResponse(
        evaluations=evaluations,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        agent_run_id=run_id,
    )


@router.post("/trade")
async def evaluate_trade_deprecated():
    """Deprecated. Use POST /api/v1/evaluate/structured instead."""
    return JSONResponse(
        status_code=410,
        content={"detail": "Deprecated. Use POST /api/v1/evaluate/structured"},
    )


@router.post("/follow-up")
async def follow_up_deprecated():
    """Deprecated. Use POST /api/v1/agent/followup instead."""
    return JSONResponse(
        status_code=410,
        content={"detail": "Deprecated. Use POST /api/v1/agent/followup"},
    )


@router.get("/health")
async def ai_health():
    """Check if the evaluation AI provider is reachable."""
    adapter = _get_adapter()
    ok = await adapter.health_check()
    if not ok:
        raise HTTPException(status_code=503, detail="Evaluation AI provider unavailable")
    return {"status": "ok", "provider": "foundry"}
