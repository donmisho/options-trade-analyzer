# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.

"""
Claude Trade Agent endpoints — Phase 2.6

Three-stage AI evaluation pipeline:
  Stage 1 — POST /agent/triage       Batch rank 1-10 trades STRONG/MEDIUM/WEAK
  Stage 2 — POST /agent/deep-dive    Full single-trade analysis + verdict
  Stage 3 — POST /agent/followup     Contextual follow-up on a prior verdict

Persistence CRUD:
  GET    /agent/recommendations            List saved verdicts (filter by symbol)
  GET    /agent/recommendations/{key}      Single saved verdict
  PUT    /agent/recommendations/{key}      Save/update a verdict
  DELETE /agent/recommendations/{key}      Clear a saved verdict

WHY this structure:
- Triage is fast and cheap (800 tokens). Run it over all checked trades at once.
- Deep Dive is expensive (1200 tokens). Run it on one trade the user cares about.
- Followup keeps the conversation going without repeating the full trade context.
- Persistence means Claude remembers the last verdict on a trade and can compare
  what changed since — enabling the RECALLED state in the UI.

Every AI call:
  1. Loads system + user prompts from SKILL.md via skill_loader (no hardcoded text)
  2. Is wrapped in invoke_with_tracing() for OpenTelemetry span + Application Insights
  3. Writes a full input/output row to agent_run_log in Azure SQL
  4. Deep Dive additionally writes/updates trade_recommendations
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.models.session import get_db
from app.models.database import AgentRunLog, TradeRecommendation
from app.ai.base import AIAdapter
from app.skills.skill_loader import get_skill
from app.agents.telemetry import invoke_with_tracing
from app.services.symbol_normalization import canonicalize

router = APIRouter(prefix="/agent", tags=["Claude Trade Agent"])
log = logging.getLogger(__name__)

# Injected from main.py at startup — same provider used by /evaluate routes
_ai_provider: Optional[AIAdapter] = None


def init_agent_routes(ai_provider: AIAdapter):
    """Called from main.py to inject the AI provider."""
    global _ai_provider
    _ai_provider = ai_provider


def _get_ai() -> AIAdapter:
    if _ai_provider is None:
        raise HTTPException(
            status_code=503,
            detail="AI provider not configured. Check AI_PROVIDER in .env"
        )
    return _ai_provider


# ─── Helper ──────────────────────────────────────────────────────────────────

def _make_trade_key(symbol: str, spread_label: str, expiration: str) -> str:
    """Build the canonical trade key used for recommendation lookup and storage."""
    return f"{symbol}:{spread_label}:{expiration}"


async def _write_run_log(
    db: AsyncSession,
    *,
    run_id: str,
    agent_name: str,
    stage: str,
    trade_key: Optional[str],
    symbol: Optional[str],
    user_id: Optional[str],
    prompt_system: str,
    prompt_user: str,
    prompt_version: str,
    market_snapshot: Optional[dict],
    trade_snapshot: Optional[dict],
    model_response_raw: str,
    verdict: Optional[str],
    verdict_summary: Optional[str],
    otel_trace_id: Optional[str],
    input_tokens: int,
    output_tokens: int,
    model_name: str,
    latency_ms: Optional[int] = None,
):
    """
    Insert one row into agent_run_log.

    WHY write everything: OpenTelemetry traces expire after 90 days.
    This table is the permanent audit trail — every prompt sent, every
    response received, every token used — queryable forever.
    """
    row = AgentRunLog(
        run_id=run_id,
        agent_name=agent_name,
        stage=stage,
        trade_key=trade_key,
        symbol=symbol,
        user_id=user_id,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_version=prompt_version,
        market_snapshot=market_snapshot,
        trade_snapshot=trade_snapshot,
        model_response_raw=model_response_raw,
        verdict=verdict,
        verdict_summary=verdict_summary,
        otel_trace_id=otel_trace_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_name=model_name,
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()


# ─── Stage 1: Batch Triage ───────────────────────────────────────────────────

class TradeItem(BaseModel):
    """One trade in a triage batch."""
    trade_id: str
    symbol: str
    spread_type: str
    spread_label: str
    expiration: str
    dte: float  # float to handle fractional days from long call engine
    net_debit: float
    max_profit: Optional[float] = None   # None for long calls (unlimited upside)
    reward_risk_ratio: Optional[float] = None  # None for long calls
    prob_of_profit: float
    composite_score: Optional[float] = None
    direction: str


class TriageRequest(BaseModel):
    symbol: str
    underlying_price: float
    sma_8: float
    sma_21: float
    sma_50: float
    ma_alignment: str
    vix: Optional[float] = None
    trades: list[TradeItem] = Field(..., min_length=1, max_length=10)
    run_id: Optional[str] = None  # Caller can supply; generated here if not


class TriageRanking(BaseModel):
    trade_id: str
    rank: str
    reason: str
    explore_further: bool


class TriageResponse(BaseModel):
    run_id: str
    rankings: list[TriageRanking]
    triage_summary: str
    input_tokens: int
    output_tokens: int
    provider: str


@router.post("/triage", response_model=TriageResponse)
async def triage(
    request: TriageRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Stage 1: Rank a batch of 1-10 trades as STRONG / MEDIUM / WEAK.

    The frontend sends all checked trades in the results table. Claude
    does a fast first-pass scan and flags which ones are worth a deep dive.
    The run_id returned here is passed to /deep-dive to link the stages
    in agent_run_log and Application Insights traces.
    """
    ai = _get_ai()
    skill = get_skill("claude-trade-agent")

    run_id = request.run_id or str(uuid.uuid4())
    user_id = user.get("sub")

    system_prompt = skill.get("BATCH_TRIAGE_SYSTEM")
    user_message = skill.render(
        "BATCH_TRIAGE_USER",
        trade_count=len(request.trades),
        symbol=request.symbol,
        current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        underlying_price=request.underlying_price,
        sma_8=request.sma_8,
        sma_21=request.sma_21,
        sma_50=request.sma_50,
        ma_alignment=request.ma_alignment,
        trade_list_json=json.dumps([t.model_dump() for t in request.trades], indent=2),
    )

    market_snapshot = {
        "underlying_price": request.underlying_price,
        "sma_8": request.sma_8,
        "sma_21": request.sma_21,
        "sma_50": request.sma_50,
        "ma_alignment": request.ma_alignment,
        "vix": request.vix,
    }

    async with invoke_with_tracing(
        "claude-trade-agent", "triage",
        symbol=request.symbol,
        session_id=run_id,
        prompt_version=skill.prompt_version,
    ) as span_ctx:
        try:
            result = await ai.chat(system_prompt, user_message, max_tokens=800)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI triage failed: {e}")

        span_ctx["input_tokens"] = result["input_tokens"]
        span_ctx["output_tokens"] = result["output_tokens"]

    # Parse JSON response from Claude.
    # Models sometimes wrap JSON in ```json ... ``` — strip the fences if present.
    import re as _re
    raw_text_for_parse = result["text"].strip()
    fence_match = _re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text_for_parse, _re.DOTALL)
    if fence_match:
        raw_text_for_parse = fence_match.group(1)
    try:
        parsed = json.loads(raw_text_for_parse)
        rankings_raw = parsed.get("rankings", [])
        triage_summary = parsed.get("triage_summary", "")
    except json.JSONDecodeError:
        log.warning(f"triage: JSON parse failed, raw: {result['text'][:500]}")
        raise HTTPException(status_code=502, detail="AI returned malformed JSON for triage")

    await _write_run_log(
        db,
        run_id=run_id,
        agent_name="claude-trade-agent",
        stage="triage",
        trade_key=None,
        symbol=canonicalize(request.symbol),
        user_id=user_id,
        prompt_system=system_prompt,
        prompt_user=user_message,
        prompt_version=skill.prompt_version,
        market_snapshot=market_snapshot,
        trade_snapshot={"trade_count": len(request.trades)},
        model_response_raw=result["text"],
        verdict=None,
        verdict_summary=triage_summary,
        otel_trace_id=span_ctx.get("otel_trace_id"),
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        model_name=result["model"],
    )

    return TriageResponse(
        run_id=run_id,
        rankings=[TriageRanking(**r) for r in rankings_raw],
        triage_summary=triage_summary,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        provider=result["provider"],
    )


# ─── Stage 2: Deep Dive ──────────────────────────────────────────────────────

class DeepDiveRequest(BaseModel):
    # Market context
    symbol: str
    current_price: float
    sma_8: float
    sma_21: float
    sma_50: float
    ma_alignment: str
    vix: Optional[float] = None

    # Trader thesis
    direction: str = "Bullish"
    timeframe_days: int = 30
    price_target: Optional[float] = None
    conviction: str = "Medium"

    # Trade details
    spread_type_label: str
    spread_label: str
    expiration: str
    dte: float
    net_debit: float
    max_profit: Optional[float] = None
    reward_risk_ratio: Optional[float] = None
    prob_of_profit: float
    composite_score: Optional[float] = None

    # Risk management
    risk_budget: float = 500.0
    num_contracts: int = 1
    total_cost: float

    # Pre-calculated exit levels (computed in frontend per SKILL.md formula)
    exit_stop_loss: float
    exit_warning: float
    exit_scale_out: float
    exit_full_profit: float
    exit_underlying_stop: float
    exit_time_stop: int

    # System variable snapshot — records which exit thresholds were active for this eval
    system_vars: Optional[dict] = None

    # Session linkage
    run_id: Optional[str] = None


class DeepDiveResponse(BaseModel):
    trade_key: str
    run_id: str
    verdict: str
    analysis: str
    had_prior_recommendation: bool
    input_tokens: int
    output_tokens: int
    provider: str


@router.post("/deep-dive", response_model=DeepDiveResponse)
async def deep_dive(
    request: DeepDiveRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Stage 2: Full single-trade analysis with EXECUTE / WAIT / PASS verdict.

    Before calling the model, checks trade_recommendations for a prior verdict
    on this trade key. If found, the prior verdict and change summary are injected
    into the DEEP_DIVE_USER prompt so Claude can compare then vs. now.

    After a successful call, writes/updates trade_recommendations so future
    deep dives on the same trade see the prior context (the RECALLED state).
    """
    ai = _get_ai()
    skill = get_skill("claude-trade-agent")

    run_id = request.run_id or str(uuid.uuid4())
    user_id = user.get("sub")
    trade_key = _make_trade_key(request.symbol, request.spread_label, request.expiration)

    # Check for prior recommendation scoped to this user
    result_prior = await db.execute(
        select(TradeRecommendation).where(
            TradeRecommendation.trade_key == trade_key,
            TradeRecommendation.user_id == user_id,
        )
    )
    prior = result_prior.scalar_one_or_none()
    had_prior = prior is not None

    # Build change summary if prior exists
    change_summary = None
    if prior:
        lines = []
        prior_price = (prior.market_snapshot or {}).get("underlying_price", 0)
        price_delta = request.current_price - prior_price
        if abs(price_delta) > 0.5:
            lines.append(f"Price moved {'+' if price_delta > 0 else ''}${price_delta:.2f} since evaluation")
        prior_dte = (prior.trade_snapshot or {}).get("dte", request.dte)
        dte_delta = request.dte - prior_dte
        if dte_delta != 0:
            lines.append(f"DTE changed by {dte_delta} days")
        prior_rr = (prior.trade_snapshot or {}).get("reward_risk_ratio", request.reward_risk_ratio)
        rr_delta = request.reward_risk_ratio - prior_rr
        if abs(rr_delta) > 0.05:
            lines.append(f"R:R shifted from {prior_rr:.2f} to {request.reward_risk_ratio:.2f}")
        change_summary = "; ".join(lines) if lines else "No significant changes detected"

    system_prompt = skill.get("DEEP_DIVE_SYSTEM")
    user_message = skill.render(
        "DEEP_DIVE_USER",
        current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        symbol=request.symbol,
        current_price=request.current_price,
        sma_8=request.sma_8,
        sma_21=request.sma_21,
        sma_50=request.sma_50,
        ma_alignment=request.ma_alignment,
        vix=request.vix or "N/A",
        direction=request.direction,
        timeframe_days=request.timeframe_days,
        price_target=request.price_target or "Not specified",
        conviction=request.conviction,
        spread_type_label=request.spread_type_label,
        spread_label=request.spread_label,
        expiration=request.expiration,
        net_debit=request.net_debit,
        max_profit=request.max_profit,
        reward_risk_ratio=request.reward_risk_ratio,
        prob_pct=round(request.prob_of_profit * 100, 1),
        composite_score=request.composite_score or "N/A",
        risk_budget=request.risk_budget,
        num_contracts=request.num_contracts,
        total_cost=request.total_cost,
        exit_stop_loss=request.exit_stop_loss,
        exit_warning=request.exit_warning,
        exit_scale_out=request.exit_scale_out,
        exit_full_profit=request.exit_full_profit,
        exit_underlying_stop=request.exit_underlying_stop,
        exit_time_stop=request.exit_time_stop,
        # Prior recommendation block (only rendered if prior exists)
        prior_recommendation=had_prior,
        prior_date=prior.evaluated_at.strftime("%Y-%m-%d") if prior else "",
        prior_verdict=prior.verdict if prior else "",
        prior_summary=prior.verdict_summary if prior else "",
        change_summary=change_summary or "",
    )

    market_snapshot = {
        "underlying_price": request.current_price,
        "sma_8": request.sma_8,
        "sma_21": request.sma_21,
        "sma_50": request.sma_50,
        "ma_alignment": request.ma_alignment,
        "vix": request.vix,
    }
    trade_snapshot = {
        "spread_label": request.spread_label,
        "expiration": request.expiration,
        "dte": request.dte,
        "net_debit": request.net_debit,
        "max_profit": request.max_profit,
        "reward_risk_ratio": request.reward_risk_ratio,
        "prob_of_profit": request.prob_of_profit,
        "composite_score": request.composite_score,
        **({"system_vars": request.system_vars} if request.system_vars else {}),
    }

    async with invoke_with_tracing(
        "claude-trade-agent", "deep_dive",
        trade_key=trade_key,
        symbol=request.symbol,
        session_id=run_id,
        prompt_version=skill.prompt_version,
    ) as span_ctx:
        try:
            result = await ai.chat(system_prompt, user_message, max_tokens=1200)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI deep dive failed: {e}")

        span_ctx["input_tokens"] = result["input_tokens"]
        span_ctx["output_tokens"] = result["output_tokens"]

    # Parse verdict from response text
    raw_text = result["text"]
    import re
    verdict_match = re.search(r"VERDICT[:\s]+(EXECUTE|WAIT|PASS)", raw_text.upper())
    verdict = verdict_match.group(1) if verdict_match else "WAIT"
    span_ctx["verdict"] = verdict

    # Extract first paragraph as verdict_summary
    paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    verdict_summary = paragraphs[0] if paragraphs else raw_text[:500]

    # Write/update trade_recommendations
    now = datetime.now(timezone.utc)
    if prior:
        prior.verdict = verdict
        prior.verdict_summary = verdict_summary
        prior.market_snapshot = market_snapshot
        prior.trade_snapshot = trade_snapshot
        prior.run_id = run_id
        prior.prompt_version = skill.prompt_version
        prior.updated_at = now
    else:
        db.add(TradeRecommendation(
            user_id=user_id,
            trade_key=trade_key,
            symbol=canonicalize(request.symbol),
            spread_label=request.spread_label,
            expiration=request.expiration,
            verdict=verdict,
            verdict_summary=verdict_summary,
            market_snapshot=market_snapshot,
            trade_snapshot=trade_snapshot,
            run_id=run_id,
            prompt_version=skill.prompt_version,
            evaluated_at=now,
            updated_at=now,
        ))

    await _write_run_log(
        db,
        run_id=run_id,
        agent_name="claude-trade-agent",
        stage="deep_dive",
        trade_key=trade_key,
        symbol=canonicalize(request.symbol),
        user_id=user_id,
        prompt_system=system_prompt,
        prompt_user=user_message,
        prompt_version=skill.prompt_version,
        market_snapshot=market_snapshot,
        trade_snapshot=trade_snapshot,
        model_response_raw=raw_text,
        verdict=verdict,
        verdict_summary=verdict_summary,
        otel_trace_id=span_ctx.get("otel_trace_id"),
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        model_name=result["model"],
    )

    return DeepDiveResponse(
        trade_key=trade_key,
        run_id=run_id,
        verdict=verdict,
        analysis=raw_text,
        had_prior_recommendation=had_prior,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        provider=result["provider"],
    )


# ─── Stage 3: Follow-up ──────────────────────────────────────────────────────

class FollowUpRequest(BaseModel):
    trade_key: str
    symbol: str
    spread_label: str
    expiration: str
    verdict: str
    verdict_summary: str
    user_question: str
    run_id: Optional[str] = None


class FollowUpResponse(BaseModel):
    response: str
    run_id: str
    input_tokens: int
    output_tokens: int
    provider: str


@router.post("/followup", response_model=FollowUpResponse)
async def followup(
    request: FollowUpRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Stage 3: Contextual follow-up on a prior deep-dive verdict.

    The frontend passes the prior verdict and summary so Claude has
    context without needing to re-run the full deep dive. This keeps
    follow-ups fast and cheap (600 tokens).
    """
    ai = _get_ai()
    skill = get_skill("claude-trade-agent")

    run_id = request.run_id or str(uuid.uuid4())
    user_id = user.get("sub")

    system_prompt = skill.get("FOLLOWUP_SYSTEM")
    user_message = skill.render(
        "FOLLOWUP_USER",
        spread_label=request.spread_label,
        symbol=request.symbol,
        expiration=request.expiration,
        verdict=request.verdict,
        verdict_summary=request.verdict_summary,
        user_question=request.user_question,
    )

    async with invoke_with_tracing(
        "claude-trade-agent", "followup",
        trade_key=request.trade_key,
        symbol=request.symbol,
        session_id=run_id,
        prompt_version=skill.prompt_version,
    ) as span_ctx:
        try:
            result = await ai.chat(system_prompt, user_message, max_tokens=600)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI follow-up failed: {e}")

        span_ctx["input_tokens"] = result["input_tokens"]
        span_ctx["output_tokens"] = result["output_tokens"]

    await _write_run_log(
        db,
        run_id=run_id,
        agent_name="claude-trade-agent",
        stage="followup",
        trade_key=request.trade_key,
        symbol=canonicalize(request.symbol),
        user_id=user_id,
        prompt_system=system_prompt,
        prompt_user=user_message,
        prompt_version=skill.prompt_version,
        market_snapshot=None,
        trade_snapshot={"user_question": request.user_question},
        model_response_raw=result["text"],
        verdict=request.verdict,
        verdict_summary=None,
        otel_trace_id=span_ctx.get("otel_trace_id"),
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        model_name=result["model"],
    )

    return FollowUpResponse(
        response=result["text"],
        run_id=run_id,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        provider=result["provider"],
    )


# ─── Recommendations CRUD ─────────────────────────────────────────────────────

class RecommendationOut(BaseModel):
    trade_key: str
    symbol: str
    spread_label: str
    expiration: str
    verdict: str
    rank: Optional[str]
    verdict_summary: str
    market_snapshot: dict
    trade_snapshot: dict
    run_id: Optional[str]
    prompt_version: Optional[str]
    evaluated_at: datetime
    updated_at: Optional[datetime]


@router.get("/recommendations", response_model=list[RecommendationOut])
async def list_recommendations(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """List saved trade verdicts for the current user, optionally filtered by symbol."""
    user_id = user.get("sub")
    q = select(TradeRecommendation).where(TradeRecommendation.user_id == user_id)
    if symbol:
        q = q.where(TradeRecommendation.symbol == symbol.upper())
    q = q.order_by(TradeRecommendation.updated_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return [_rec_to_out(r) for r in rows]


@router.get("/recommendations/{trade_key:path}", response_model=RecommendationOut)
async def get_recommendation(
    trade_key: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Get a single saved verdict by trade key for the current user."""
    row = await _fetch_rec(db, trade_key, user_id=user.get("sub"))
    if not row:
        raise HTTPException(status_code=404, detail=f"No recommendation for {trade_key}")
    return _rec_to_out(row)


class RecommendationUpdate(BaseModel):
    verdict: str
    verdict_summary: str
    rank: Optional[str] = None


@router.put("/recommendations/{trade_key:path}", response_model=RecommendationOut)
async def save_recommendation(
    trade_key: str,
    body: RecommendationUpdate,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Manually save or update a verdict for a trade key for the current user."""
    row = await _fetch_rec(db, trade_key, user_id=user.get("sub"))
    if not row:
        raise HTTPException(status_code=404, detail=f"No recommendation for {trade_key}")
    row.verdict = body.verdict
    row.verdict_summary = body.verdict_summary
    if body.rank is not None:
        row.rank = body.rank
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _rec_to_out(row)


@router.delete("/recommendations/{trade_key:path}", status_code=204)
async def delete_recommendation(
    trade_key: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Clear a saved recommendation (user wants a fresh evaluation)."""
    row = await _fetch_rec(db, trade_key, user_id=user.get("sub"))
    if not row:
        raise HTTPException(status_code=404, detail=f"No recommendation for {trade_key}")
    await db.execute(
        delete(TradeRecommendation).where(
            TradeRecommendation.trade_key == trade_key,
            TradeRecommendation.user_id == user.get("sub"),
        )
    )
    await db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _fetch_rec(db: AsyncSession, trade_key: str, user_id: str) -> Optional[TradeRecommendation]:
    q = select(TradeRecommendation).where(
        TradeRecommendation.trade_key == trade_key,
        TradeRecommendation.user_id == user_id,
    )
    result = await db.execute(q)
    return result.scalar_one_or_none()


def _rec_to_out(r: TradeRecommendation) -> RecommendationOut:
    return RecommendationOut(
        trade_key=r.trade_key,
        symbol=r.symbol,
        spread_label=r.spread_label,
        expiration=r.expiration,
        verdict=r.verdict,
        rank=r.rank,
        verdict_summary=r.verdict_summary,
        market_snapshot=r.market_snapshot or {},
        trade_snapshot=r.trade_snapshot or {},
        run_id=r.run_id,
        prompt_version=r.prompt_version,
        evaluated_at=r.evaluated_at,
        updated_at=r.updated_at,
    )
