"""
Trade Evaluation API endpoints — Phase 2.11 structured output.

ENDPOINTS:
  POST /api/v1/evaluate/structured — Multi-strategy AI evaluation (Phase 2.11)
  POST /api/v1/evaluate/trade      — DEPRECATED (410)
  POST /api/v1/evaluate/follow-up  — DEPRECATED (410) → use /agent/followup
  GET  /api/v1/evaluate/health     — Check if AI provider is reachable

STRUCTURED OUTPUTS:
  /evaluate/structured calls adapter.chat() with the DEEP_DIVE_SYSTEM prompt
  from SKILL.md. The adapter is FoundryEvalAdapter (httpx) when FOUNDRY_ENDPOINT
  is set, or AnthropicAdapter (SDK) as a fallback for local dev. Both expose a
  compatible chat(system, user, max_tokens, extra_messages) interface.
  Claude returns a JSON array of TradeEvaluationCard objects validated by Pydantic.
  Retries once with correction context on JSON parse failure.
  Writes every call to agent_run_log.
"""

import asyncio
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Any, Optional, List

import httpx

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.core.config import settings
from app.ai.base import AIAdapter
from app.models.session import get_db
from app.models.database import AgentRunLog
from app.models.schemas import (
    TradeEvaluationCard,
    ExitScenarioRequest, ExitScenarioRow, ExitScenarioResponse,
    TradeVerdictRequest, TradeVerdictResponse,
)
from app.skills.skill_loader import get_skill
from app.agents.telemetry import invoke_with_tracing
from app.analysis.black_scholes import compute_probability_matrix
from app.models.session import async_session
from app.validators.narrative_grounding import EvaluationFields, validate_narrative
from app.analysis.hard_gates import evaluate_hard_gates, GateTradeContext
from app.analysis.scoring_factors.asymmetry import (
    asymmetry_penalty as _asymmetry_penalty,
    asymmetry_ratio as _asymmetry_ratio,
)
from app.analysis.strategy_classifier import classify_best_strategy
from app.analysis.strategy_scorer import StrategyScore

router = APIRouter(prefix="/evaluate", tags=["Trade Evaluation"])

# Initialized in main.py at startup — any AIAdapter implementation.
_eval_adapter: Optional[AIAdapter] = None


def init_evaluation_routes(adapter: AIAdapter):
    """Called from main.py to inject the AI adapter."""
    global _eval_adapter
    _eval_adapter = adapter


def _get_adapter() -> Any:
    if _eval_adapter is None:
        raise HTTPException(
            status_code=503,
            detail="Evaluation AI not configured. Set FOUNDRY_ENDPOINT and FOUNDRY_API_KEY in .env"
        )
    return _eval_adapter


# ─── Helpers ─────────────────────────────────────────────────────

def calculate_dte(expiration_str: str) -> int:
    """Parse expiration date string in any common format and return days to expiration."""
    if not expiration_str:
        return 0
    for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            exp_date = datetime.strptime(expiration_str, fmt).date()
            return max(0, (exp_date - date.today()).days)
        except ValueError:
            continue
    return 0


def _extract_json_array(text: str) -> str:
    """Strip markdown code fences and return bare JSON array."""
    text = text.strip()
    # Match ``` fences anywhere in the response (handles preamble text before fence)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence_match:
        return fence_match.group(1).strip()
    # Fallback: extract from first [ to last ] to ignore any surrounding prose
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _try_parse_cards(raw: str) -> Optional[List[TradeEvaluationCard]]:
    """Attempt to parse raw text into a list of TradeEvaluationCard. Returns None on failure."""
    try:
        data = json.loads(_extract_json_array(raw))
        cards = []
        for item in data:
            # Defensive extraction: Claude may return exit levels nested under exit_plan
            # or at the top level. Check both locations.
            exit_plan = item.get("exit_plan", {}) or {}
            take_profit = exit_plan.get("take_profit") or item.get("take_profit")
            warning_level = exit_plan.get("warning_level") or item.get("warning_level")
            hard_stop = exit_plan.get("hard_stop") or item.get("hard_stop")
            # Flatten into top-level fields for schema validation
            item["take_profit"] = take_profit
            item["warning_level"] = warning_level
            item["hard_stop"] = hard_stop
            logger.info(
                f"Exit levels — strategy: {item.get('strategy_key')}, "
                f"take_profit: {take_profit}, warning_level: {warning_level}, hard_stop: {hard_stop}"
            )
            cards.append(TradeEvaluationCard(**item))
        return cards
    except Exception:
        return None


def _assign_verdict(score: float) -> str:
    """Enforce strict score band → verdict mapping. This is the ONLY place verdicts are assigned from scores."""
    if score >= 70:
        return "EXECUTE"
    elif score >= 50:
        return "WAIT"
    else:
        return "PASS"


async def _log_validator_event(
    run_id: str,
    symbol: str,
    user_id,
    validator_data: dict,
    prompt_version: str,
) -> None:
    """
    Fire-and-forget: write a narrative grounding validation failure to agent_run_log.
    Uses its own session so the caller is never blocked.
    """
    try:
        async with async_session() as db:
            db.add(AgentRunLog(
                run_id=run_id,
                agent_name="narrative_grounding_validator",
                stage="validate_narrative",
                symbol=symbol,
                user_id=user_id,
                prompt_system="VALIDATOR",
                prompt_user="VALIDATOR",
                prompt_version=prompt_version,
                market_snapshot=validator_data,
                trade_snapshot={},
                model_response_raw="",
                verdict=None,
                verdict_summary=(
                    f"validator=narrative_grounding "
                    f"errors={[e['code'] for e in validator_data.get('errors', [])]} "
                    f"retry={validator_data.get('retry_triggered')} "
                    f"fallback={validator_data.get('fallback_used')}"
                ),
                otel_trace_id=None,
                input_tokens=0,
                output_tokens=0,
                model_name="none",
                created_at=datetime.now(timezone.utc),
            ))
            await db.commit()
    except Exception as exc:
        logger.warning(f"_log_validator_event failed (non-fatal): {exc}")


def _build_structured_user_message(
    symbol: str,
    current_price: float,
    iv: float,
    sma_alignment: dict,
    strategy_keys: List[str],
    scores: Optional[dict],
    trade: Optional[dict],
    current_date: str,
    dte: int = 30,
    strategy_specs: Optional[dict] = None,
) -> str:
    """Build the user prompt for the structured evaluation call.

    OTA-616: Adds COMPUTED METRICS section with reconciled field names.
    OTA-618: Adds STRATEGY SPEC section per strategy when strategy_specs provided.
    """
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
    ]

    # ── OTA-616: Computed metrics section ──────────────────────────────────────
    if trade:
        lines.append("=== COMPUTED METRICS ===")
        lines.append(f"dte: {dte}")

        # total_ev / scenario_weighted_ev: prefer total_ev, fall back to ev_raw
        _total_ev = trade.get("total_ev")
        _ev_raw = trade.get("ev_raw")
        _ev = _total_ev if _total_ev is not None else _ev_raw
        if _ev is not None:
            try:
                _ev_f = float(_ev)
                lines.append(f"total_ev: {_ev_f:.2f}")
                lines.append(f"scenario_weighted_ev: {_ev_f:.2f}")
            except (TypeError, ValueError):
                pass

        # net_bid_ask: debit spreads = long_ask - short_bid; credit = short_bid - long_ask
        _long_ask = trade.get("long_ask")
        _short_bid = trade.get("short_bid")
        _net_debit = trade.get("net_debit")
        if _long_ask is not None and _short_bid is not None:
            try:
                _la = float(_long_ask)
                _sb = float(_short_bid)
                _nd = float(_net_debit) if _net_debit is not None else 0
                if _nd < 0:  # credit spread
                    _nba = _sb - _la
                else:  # debit spread
                    _nba = _la - _sb
                lines.append(f"net_bid_ask: {_nba:.4f}")
            except (TypeError, ValueError):
                pass

        # debit_pct_of_width: debit spreads only (max-loss-as-fraction-of-width)
        _spread_width = trade.get("spread_width")
        if _net_debit is not None and _spread_width is not None:
            try:
                _nd_f = float(_net_debit)
                _sw_f = float(_spread_width)
                if _sw_f > 0 and _nd_f > 0:  # debit spread
                    _dpow = _nd_f / _sw_f
                    lines.append(f"debit_pct_of_width: {_dpow:.4f}")
            except (TypeError, ValueError):
                pass

        # cushion_pct: credit spreads only (distance from short strike to price / price)
        _short_strike = trade.get("short_strike")
        if _short_strike is not None and _net_debit is not None:
            try:
                _ss = float(_short_strike)
                _nd_f = float(_net_debit)
                if _nd_f < 0 and current_price > 0:  # credit spread
                    _cpct = abs(current_price - _ss) / current_price
                    lines.append(f"cushion_pct: {_cpct:.4f}")
            except (TypeError, ValueError):
                pass

        # Surface p_max_loss / p_max_profit explicitly
        _pml = trade.get("p_max_loss")
        _pmp = trade.get("p_max_profit")
        if _pml is not None:
            lines.append(f"p_max_loss: {_pml}")
        if _pmp is not None:
            lines.append(f"p_max_profit: {_pmp}")

        lines.append("")

    lines.append("=== STRATEGIES TO EVALUATE ===")

    for key in strategy_keys:
        label = key.replace("-", " ").title()
        score = (scores or {}).get(key)
        lines.append("")
        lines.append(f"Strategy key: {key}")
        lines.append(f"Strategy label: {label}")
        if score is not None:
            lines.append(f"Score: {score} / 100")

        # OTA-618: Inject strategy_spec per strategy
        if strategy_specs and key in strategy_specs:
            spec = strategy_specs[key]
            lines.append(f"strategy_spec: {json.dumps(spec)}")

        if trade:
            # OTA-558: Safely serialize trade dict (handles NaN/Infinity from scoring)
            try:
                trade_json = json.dumps(trade, default=str, allow_nan=False)
            except (ValueError, TypeError):
                trade_json = json.dumps(
                    {k: v for k, v in trade.items() if not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))},
                    default=str,
                )
            lines.append(f"Trade data: {trade_json}")

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
    strategy_fit: Optional[dict] = None   # OTA-506: classifier result + DTE metadata


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
    # In SKIP_AUTH dev mode the sub is a synthetic UUID with no matching users row.
    # Pass None so AgentRunLog's nullable FK doesn't blow up.
    user_id = None if settings.skip_auth else (user.get("sub") or None)
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Derive DTE for the probability matrix
    dte = 30  # default
    if request.trade:
        raw_dte = request.trade.get("dte")
        if raw_dte and int(raw_dte) > 0:
            dte = int(raw_dte)
        elif request.trade.get("expiration"):
            computed = calculate_dte(request.trade["expiration"])
            if computed > 0:
                dte = computed

    # Capture nominal DTE before any gate override (OTA-506)
    nominal_dte = dte

    # ─── Hard Gate Evaluation (OTA-502+) ─────────────────────────────────────
    # Runs BEFORE all inline gates. Registered gates are evaluated in order;
    # first triggered gate forces PASS. Non-triggered gates may inject
    # effective_dte_override and penalty_points used later in scoring.
    auto_pass_reason = None
    dte_warning_msg = None
    credit_pct_of_width = None
    debit_pct_of_width = None
    _gate_result = None
    _gate_penalty_points = 0

    _expiry_date = None
    if request.trade and request.trade.get("expiration"):
        for _fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
            try:
                _expiry_date = datetime.strptime(request.trade["expiration"], _fmt).date()
                break
            except ValueError:
                continue

    _gate_ev = None
    if request.trade:
        try:
            _raw_ev = request.trade.get("total_ev")
            _gate_ev = float(_raw_ev) if _raw_ev is not None else None
        except (TypeError, ValueError):
            _gate_ev = None

    _gate_ctx = GateTradeContext(
        symbol=request.symbol,
        entry_date=date.today(),
        expiry_date=_expiry_date,
        dte=dte,
        trade=request.trade,
        db=db,
        expected_value=_gate_ev,
    )
    _gate_result = await evaluate_hard_gates(_gate_ctx)
    _wait_for_earnings = False  # OTA-515: set when verdict is WAIT_FOR_EARNINGS

    if _gate_result and _gate_result.triggered:
        if _gate_result.verdict == "WAIT_FOR_EARNINGS":
            # OTA-515: Route 2 or 3 — short-circuit with WAIT_FOR_EARNINGS cards
            _wait_for_earnings = True
            auto_pass_reason = _gate_result.reason
        else:
            # Hard block (PASS) — feed into the existing auto-pass short-circuit
            auto_pass_reason = _gate_result.reason
    elif _gate_result and not _gate_result.triggered:
        # Modifier-only result (Route 4: pre-earnings momentum play)
        if _gate_result.effective_dte_override is not None:
            dte = _gate_result.effective_dte_override
        if _gate_result.penalty_points:
            _gate_penalty_points = _gate_result.penalty_points

    # ─── Pipeline Gate 1: DTE Hard Filter ─────────────────────────────────────
    # Fires BEFORE any scoring logic. 0-7 DTE has binary gamma exposure.
    if dte <= 7:
        auto_pass_reason = (
            f"Insufficient time remaining for active management. "
            f"This trade expires in {dte} day(s). "
            "Minimum 8 DTE required to enter any position."
        )
    elif dte <= 13:
        dte_warning_msg = (
            f"{dte} DTE — Below recommended minimum. "
            "20-point penalty applied. Exit management time is limited."
        )

    # ─── Pipeline Gate 2: Credit/Debit Quality ────────────────────────────────
    # Fires BEFORE scoring. Hard disqualifier if credit < 30% or debit > 40% of width.
    if auto_pass_reason is None and request.trade:
        _net_debit = float(request.trade.get("net_debit") or 0)
        _spread_width = float(request.trade.get("spread_width") or 0)

        if _spread_width > 0:
            if _net_debit < 0:  # credit spread — net_debit stored negative
                _net_credit = abs(_net_debit)
                credit_pct_of_width = round(_net_credit / _spread_width, 4)
                if credit_pct_of_width < 0.30:
                    auto_pass_reason = (
                        f"Credit of ${_net_credit:.2f} represents {credit_pct_of_width * 100:.1f}% of the "
                        f"${_spread_width:.0f} spread width. "
                        f"Minimum 30% required (${_spread_width * 0.30:.2f} minimum credit)."
                    )
            elif _net_debit > 0:  # debit spread
                debit_pct_of_width = round(_net_debit / _spread_width, 4)
                if debit_pct_of_width > 0.40:
                    auto_pass_reason = (
                        f"Debit of ${_net_debit:.2f} represents {debit_pct_of_width * 100:.1f}% of the "
                        f"${_spread_width:.0f} spread width. "
                        f"Maximum 40% permitted (${_spread_width * 0.40:.2f} maximum debit)."
                    )

    # ─── Auto-PASS / WAIT_FOR_EARNINGS: return immediately, NO Claude API call ─
    if auto_pass_reason:
        _verdict = "WAIT_FOR_EARNINGS" if _wait_for_earnings else "PASS"
        logger.info(
            f"Auto-{_verdict} for {request.symbol} (strategy_keys={request.strategy_keys}): {auto_pass_reason[:80]}"
        )

        # OTA-515: Build claude_read differentiated by debit/credit when WAIT_FOR_EARNINGS
        _claude_read = ""
        if _wait_for_earnings:
            _is_credit = (request.trade or {}).get("net_debit", 0)
            if isinstance(_is_credit, (int, float)) and _is_credit < 0:
                _claude_read = "Wait trades premium for safety — credit will be smaller but gap risk eliminated."
            else:
                _claude_read = "Wait is strictly better — entry improves post-crush."

        auto_pass_cards = []
        for _key in request.strategy_keys:
            _label = _key.replace("-", " ").title()
            _trade_structure = (request.trade.get("spread_label") or "") if request.trade else ""
            auto_pass_cards.append(TradeEvaluationCard(
                strategy_key=_key,
                strategy_label=_label,
                trade_structure=_trade_structure,
                entry_price=0.0,
                max_profit=0.0,
                max_loss=0.0,
                exit_warning_price=0.0,
                exit_warning_pnl=0.0,
                exit_target_debit=0.0,
                exit_stop_debit=0.0,
                probability_matrix={},
                score=0,
                verdict=_verdict,
                claude_read=_claude_read,
                key_risks=[],
                thesis_invalidators=[],
                auto_pass_reason=auto_pass_reason,
                credit_pct_of_width=credit_pct_of_width,
                debit_pct_of_width=debit_pct_of_width,
                dte_after_earnings=_gate_result._dte_after_earnings if _wait_for_earnings and _gate_result else None,
                reevaluate_on=_gate_result._reevaluate_on if _wait_for_earnings and _gate_result else None,
            ))

        db.add(AgentRunLog(
            run_id=run_id,
            agent_name="claude-trade-agent",
            stage="auto_pass",
            symbol=request.symbol,
            user_id=user_id,
            prompt_system="AUTO_PASS",
            prompt_user="AUTO_PASS",
            prompt_version=skill.prompt_version,
            market_snapshot={"symbol": request.symbol, "underlying_price": request.current_price, "iv": request.iv},
            trade_snapshot={"strategy_keys": request.strategy_keys, "trade": request.trade},
            model_response_raw=auto_pass_reason,
            verdict=None,
            verdict_summary=f"AUTO_{_verdict}: {auto_pass_reason[:120]}",
            otel_trace_id=None,
            input_tokens=0,
            output_tokens=0,
            model_name="none",
            created_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        return StructuredEvaluationResponse(
            evaluations=auto_pass_cards,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            agent_run_id=run_id,
        )

    logger.info(f"Evaluation request payload: symbol={request.symbol}, price={request.current_price}, "
                f"iv={request.iv}, strategies={request.strategy_keys}, dte={dte}, "
                f"trade_keys={list(request.trade.keys()) if request.trade else None}")

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

    # ── OTA-618: Build strategy_spec per strategy ────────────────────────────
    from app.analysis.strategy_definitions import STRATEGIES as _STRATEGIES
    _strategy_specs = {}
    for _sk in request.strategy_keys:
        _sdef = _STRATEGIES.get(_sk)
        if _sdef:
            _credit_types = {"bull_put_credit", "bear_call_credit"}
            _is_credit = bool(_credit_types & set(_sdef.compatible_structures))
            _strategy_specs[_sk] = {
                "preferred_dte_window": [_sdef.dte_min, _sdef.dte_max],
                "preferred_structure": "credit" if _is_credit else "debit",
                "compatible_structures": _sdef.compatible_structures,
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
        dte=dte,
        strategy_specs=_strategy_specs,
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
            # OTA-558: Surface full error details for diagnosis
            err_details = {
                "exception_type": type(e).__name__,
                "message": str(e),
                "symbol": request.symbol,
                "strategy_keys": request.strategy_keys,
                "trade_type": request.trade.get("option_type") or request.trade.get("spread_type") if request.trade else None,
                "user_message_preview": user_message[:500],
            }
            if isinstance(e, httpx.HTTPStatusError):
                err_details["status_code"] = e.response.status_code
                err_details["response_body"] = e.response.text[:1000]
            logger.error(
                f"AI evaluation failed for {request.symbol} "
                f"(strategies={request.strategy_keys}): "
                f"{type(e).__name__}: {e}",
                extra={"eval_error_details": err_details},
            )
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
        except Exception as retry_exc:
            # OTA-558: Log retry failure for diagnosis
            logger.warning(
                f"AI evaluation retry failed for {request.symbol}: "
                f"{type(retry_exc).__name__}: {retry_exc}"
            )

    if evaluations is None:
        raise HTTPException(
            status_code=502,
            detail="AI returned malformed JSON for structured evaluation after retry.",
        )

    # ─── Fix 3: Verdict Band Enforcement + Inject Pipeline Metrics ────────────
    # Extract asymmetry inputs once — same trade data for all strategy cards.
    _p_max_loss   = None
    _p_max_profit = None
    if request.trade:
        try:
            _raw_pml = request.trade.get("p_max_loss")
            _raw_pmp = request.trade.get("p_max_profit")
            _p_max_loss   = float(_raw_pml) if _raw_pml is not None else None
            _p_max_profit = float(_raw_pmp) if _raw_pmp is not None else None
        except (TypeError, ValueError):
            pass  # leave as None → 0 penalty

    _asym_penalty = _asymmetry_penalty(_p_max_loss, _p_max_profit)
    _asym_ratio   = _asymmetry_ratio(_p_max_loss, _p_max_profit)

    for card in evaluations:
        # Apply DTE penalty for 8-13 DTE
        if dte_warning_msg and 8 <= dte <= 13:
            card.score = max(0, card.score - 20)
            card.dte_warning = dte_warning_msg

        # Apply earnings gate penalty (OTA-502 — warning band, 8-13 biz days to earnings)
        if _gate_penalty_points:
            card.score = max(0, card.score - _gate_penalty_points)

        # Apply probability asymmetry penalty (OTA-505 — graduated, post-score pre-band)
        if _asym_penalty:
            card.score = max(0, card.score - _asym_penalty)
        card.asymmetry_penalty = _asym_penalty
        card.asymmetry_ratio   = _asym_ratio

        # Enforce strict score band → verdict (ONLY place this happens)
        correct_verdict = _assign_verdict(card.score)
        if card.verdict != correct_verdict:
            logger.info(
                f"Verdict corrected for {card.strategy_key}: {card.verdict} → {correct_verdict} "
                f"(score={card.score})"
            )
            card.verdict = correct_verdict

        # Inject credit/debit quality metrics
        if credit_pct_of_width is not None:
            card.credit_pct_of_width = credit_pct_of_width
        if debit_pct_of_width is not None:
            card.debit_pct_of_width = debit_pct_of_width

        # Export effective DTE for downstream consumers (OTA-506)
        card.effective_dte = dte

    # Inject the pre-computed probability matrix into every card
    for card in evaluations:
        card.probability_matrix = pm_dict

    # ─── Narrative Grounding Validation (OTA-504) ──────────────────────────────
    # Validate claude_read prose against computed inputs before emission.
    # Max 1 retry on failure; template fallback if retry also fails.
    _raw_sma_8  = request.sma_alignment.get("sma_8")
    _raw_sma_21 = request.sma_alignment.get("sma_21")
    _raw_sma_50 = request.sma_alignment.get("sma_50")
    _raw_ev     = request.trade.get("total_ev") if request.trade else None

    def _to_float(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return math.nan

    _computed_fields = EvaluationFields(
        price=request.current_price,
        sma_8=_to_float(_raw_sma_8),
        sma_21=_to_float(_raw_sma_21),
        sma_50=_to_float(_raw_sma_50),
        expected_value=_to_float(_raw_ev),
    )

    _grounding_errors = []
    for card in evaluations:
        if card.claude_read:
            _grounding_errors.extend(validate_narrative(card.claude_read, _computed_fields))

    _retry_triggered = False
    _fallback_used = False

    if _grounding_errors:
        _retry_triggered = True
        logger.warning(
            f"Narrative grounding errors for {request.symbol} (run_id={run_id}): "
            f"{[e.code for e in _grounding_errors]}"
        )

        # One retry — same prompt, same context
        _retry_evals = None
        try:
            _retry_result = await adapter.chat(system_prompt, user_message, max_tokens=3000)
            result["input_tokens"] += _retry_result["input_tokens"]
            result["output_tokens"] += _retry_result["output_tokens"]
            _retry_evals = _try_parse_cards(_retry_result["text"])
        except Exception as _retry_exc:
            logger.warning(f"Narrative grounding retry call failed: {_retry_exc}")

        if _retry_evals is not None:
            # Re-apply all post-parse fixes to retry cards
            for card in _retry_evals:
                if dte_warning_msg and 8 <= dte <= 13:
                    card.score = max(0, card.score - 20)
                    card.dte_warning = dte_warning_msg
                if _gate_penalty_points:
                    card.score = max(0, card.score - _gate_penalty_points)
                _correct_verdict = _assign_verdict(card.score)
                if card.verdict != _correct_verdict:
                    card.verdict = _correct_verdict
                if credit_pct_of_width is not None:
                    card.credit_pct_of_width = credit_pct_of_width
                if debit_pct_of_width is not None:
                    card.debit_pct_of_width = debit_pct_of_width
                card.effective_dte = dte
            for card in _retry_evals:
                card.probability_matrix = pm_dict

            # Re-validate retry output
            _retry_errors = []
            for card in _retry_evals:
                if card.claude_read:
                    _retry_errors.extend(validate_narrative(card.claude_read, _computed_fields))

            if not _retry_errors:
                evaluations = _retry_evals
                logger.info(f"Narrative grounding retry succeeded for {request.symbol} (run_id={run_id})")
            else:
                _fallback_used = True
                logger.warning(
                    f"Narrative grounding fallback applied for {request.symbol} (run_id={run_id}): "
                    f"retry errors={[e.code for e in _retry_errors]}"
                )
                for card in evaluations:
                    card.claude_read = (
                        "Structured evaluation complete. See computed fields for details. "
                        "Narrative unavailable this cycle."
                    )
        else:
            _fallback_used = True
            logger.warning(f"Narrative grounding retry parse failed for {request.symbol} (run_id={run_id})")
            for card in evaluations:
                card.claude_read = (
                    "Structured evaluation complete. See computed fields for details. "
                    "Narrative unavailable this cycle."
                )

        # Fire-and-forget observability — never block emission
        _validator_log = {
            "validator": "narrative_grounding",
            "errors": [
                {"code": e.code, "field": e.field_context, "msg": e.message}
                for e in _grounding_errors
            ],
            "retry_triggered": _retry_triggered,
            "fallback_used": _fallback_used,
        }
        asyncio.create_task(
            _log_validator_event(run_id, request.symbol, user_id, _validator_log, skill.prompt_version)
        )

    # ─── Strategy Classifier (OTA-506) ────────────────────────────────────────
    # Run after Claude scoring is final. Uses effective DTE (post gate-override).
    # Builds StrategyScore proxies from the evaluated cards so the classifier
    # can filter by DTE eligibility and rank by Claude's scores.
    _clf_candidates = [
        StrategyScore(
            strategy_key=card.strategy_key,
            label=card.strategy_label,
            score=card.score,
            best_trade=None,
            signal_summary="",
            metric_scores={},
        )
        for card in evaluations
    ]
    _classification = classify_best_strategy(_clf_candidates, effective_dte=dte)
    _strategy_fit = {
        "best_fit":    _classification.best_fit,
        "reason":      _classification.reason,
        "nominal_dte": nominal_dte,
        "effective_dte": dte,
        "dte_source":  "earnings_in_window" if dte != nominal_dte else "nominal",
    }

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
        trade_snapshot={
            "strategy_keys": request.strategy_keys,
            "trade": request.trade,
            "gate_result": {
                "gate_id": _gate_result.gate_id,
                "triggered": _gate_result.triggered,
                "penalty_points": _gate_result.penalty_points,
                "effective_dte_override": _gate_result.effective_dte_override,
                "reason": _gate_result.reason,
            } if _gate_result else None,
        },
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
        strategy_fit=_strategy_fit,
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


# ─── OTA-292: Exit Scenario Engine ───────────────────────────────────────────

def _is_debit(spread_type: str) -> bool:
    return spread_type.upper().endswith("DEBIT")


def _spread_value(spread_type: str, long_strike: float, short_strike: float, S: float) -> float:
    """Intrinsic value of the spread at underlying price S (at expiry)."""
    st = spread_type.upper()
    if st == "BEAR_PUT_DEBIT":
        # Long higher put, short lower put
        return max(0.0, long_strike - S) - max(0.0, short_strike - S)
    elif st == "BULL_CALL_DEBIT":
        # Long lower call, short higher call
        return max(0.0, S - long_strike) - max(0.0, S - short_strike)
    elif st == "BEAR_CALL_CREDIT":
        # Short lower call (short_strike), long higher call (long_strike) — value to close
        return max(0.0, S - short_strike) - max(0.0, S - long_strike)
    elif st == "BULL_PUT_CREDIT":
        # Short higher put (short_strike), long lower put (long_strike) — value to close
        return max(0.0, short_strike - S) - max(0.0, long_strike - S)
    return 0.0


def _compute_breakeven(spread_type: str, long_strike: float, short_strike: float, entry_price: float) -> float:
    st = spread_type.upper()
    if st == "BEAR_PUT_DEBIT":
        return round(long_strike - entry_price, 4)
    elif st == "BULL_CALL_DEBIT":
        return round(long_strike + entry_price, 4)
    elif st == "BEAR_CALL_CREDIT":
        return round(short_strike + entry_price, 4)
    elif st == "BULL_PUT_CREDIT":
        return round(short_strike - entry_price, 4)
    return 0.0


def _max_profit_loss(spread_type: str, long_strike: float, short_strike: float, entry_price: float):
    """Returns (max_profit, max_loss) in dollar terms per contract (x100)."""
    spread_width = abs(long_strike - short_strike)
    if _is_debit(spread_type):
        return round((spread_width - entry_price) * 100, 2), round(entry_price * 100, 2)
    else:
        return round(entry_price * 100, 2), round((spread_width - entry_price) * 100, 2)


def _pdf_prob(S0: float, K: float, dte: int, iv: float, r: float, step: float = 5.0) -> float:
    """Discrete PDF probability: P(underlying in [K-step/2, K+step/2] at expiry)."""
    from app.analysis.black_scholes import black_scholes_probability
    T = max(dte / 365.0, 0.001)
    p_lo = black_scholes_probability(S0, K - step / 2, T, r, iv)
    p_hi = black_scholes_probability(S0, K + step / 2, T, r, iv)
    return round(max(0.0, p_lo - p_hi), 6)


def _exit_zone(
    spread_type: str,
    long_strike: float,
    short_strike: float,
    breakeven: float,
    underlying_price: float,
    price: float,
) -> str:
    """Classify a price level into one of: max_profit | profit | entry | warning | max_loss."""
    if abs(price - underlying_price) < 2.51:
        return "entry"
    bearish = spread_type.upper().startswith("BEAR")
    lo = min(long_strike, short_strike)
    hi = max(long_strike, short_strike)
    if bearish:
        if price <= lo:
            return "max_profit"
        if price < breakeven:
            return "profit"
        if price < hi:
            return "warning"
        return "max_loss"
    else:
        if price >= hi:
            return "max_profit"
        if price > breakeven:
            return "profit"
        if price > lo:
            return "warning"
        return "max_loss"


def _build_exit_rows(
    spread_type: str,
    long_strike: float,
    short_strike: float,
    expiry: str,
    entry_price: float,
    underlying_price: float,
    iv: float,
    risk_free_rate: float,
) -> tuple:
    """
    Compute all exit scenario rows.
    Returns (rows, breakeven, max_profit_price, max_loss_price, dte, time_exit_date_str).
    """
    # ── DTE ──────────────────────────────────────────────────────────────────
    dte = calculate_dte(expiry)

    # ── Economics ──────────────────────────────────────────────────────────
    max_profit, max_loss = _max_profit_loss(spread_type, long_strike, short_strike, entry_price)
    breakeven = _compute_breakeven(spread_type, long_strike, short_strike, entry_price)

    bearish = spread_type.upper().startswith("BEAR")
    lo = min(long_strike, short_strike)
    hi = max(long_strike, short_strike)

    # Max profit / max loss price boundaries
    max_profit_price = lo if bearish else hi
    max_loss_price   = hi if bearish else lo

    # ── Price range ─────────────────────────────────────────────────────────
    start = lo - 5.0
    end   = hi + 5.0
    step  = 5.0
    prices = []
    p = start
    while p <= end + step / 10:
        prices.append(round(p, 2))
        p = round(p + step, 2)

    # ── Key level → exit_signal label mapping ───────────────────────────────
    # Priority: MAX PROFIT > STOP > BREAKEVEN > ENTRY
    # Find the closest price level for each key level.
    def _closest(target: float) -> float:
        return min(prices, key=lambda x: abs(x - target))

    key_signals: dict[float, str] = {}
    for target, label in [
        (max_profit_price, "MAX PROFIT"),
        (max_loss_price,   "STOP"),
        (breakeven,        "BREAKEVEN"),
        (underlying_price, "ENTRY"),
    ]:
        closest = _closest(target)
        if closest not in key_signals:  # first one wins (priority order)
            key_signals[closest] = label

    # ── Build rows ──────────────────────────────────────────────────────────
    rows: list[ExitScenarioRow] = []
    for price in prices:
        sv   = round(_spread_value(spread_type, long_strike, short_strike, price), 4)
        if _is_debit(spread_type):
            pl_contract = round((sv - entry_price) * 100, 2)
        else:
            pl_contract = round((entry_price - sv) * 100, 2)
        pl_pct   = round(pl_contract / max_loss, 6) if max_loss != 0 else 0.0
        prob     = _pdf_prob(underlying_price, price, dte, iv, risk_free_rate)
        ev       = round(pl_contract * prob, 4)
        zone     = _exit_zone(spread_type, long_strike, short_strike, breakeven, underlying_price, price)
        signal   = key_signals.get(price, "")

        rows.append(ExitScenarioRow(
            underlying_price=price,
            spread_value=sv,
            pl_per_contract=pl_contract,
            pl_pct=pl_pct,
            probability=prob,
            expected_value=ev,
            zone=zone,
            exit_signal=signal,
        ))

    # ── TIME EXIT row ────────────────────────────────────────────────────────
    # Use today's underlying price; DTE-7 for probability.
    time_exit_dte = max(dte - 7, 0)
    sv_te  = round(_spread_value(spread_type, long_strike, short_strike, underlying_price), 4)
    if _is_debit(spread_type):
        pl_te = round((sv_te - entry_price) * 100, 2)
    else:
        pl_te = round((entry_price - sv_te) * 100, 2)
    pl_pct_te = round(pl_te / max_loss, 6) if max_loss != 0 else 0.0
    prob_te   = _pdf_prob(underlying_price, underlying_price, time_exit_dte, iv, risk_free_rate)
    ev_te     = round(pl_te * prob_te, 4)
    zone_te   = _exit_zone(spread_type, long_strike, short_strike, breakeven, underlying_price, underlying_price)

    rows.append(ExitScenarioRow(
        underlying_price=underlying_price,
        spread_value=sv_te,
        pl_per_contract=pl_te,
        pl_pct=pl_pct_te,
        probability=prob_te,
        expected_value=ev_te,
        zone=zone_te,
        exit_signal="TIME EXIT",
    ))

    # Time exit date string (mm-dd-yyyy)
    try:
        exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    except ValueError:
        exp_date = date.today()
    te_date = exp_date - timedelta(days=7)
    te_date_str = te_date.strftime("%m-%d-%Y")

    total_ev = round(sum(r.expected_value for r in rows), 4)

    return rows, breakeven, max_profit_price, max_loss_price, dte, te_date_str, total_ev


@router.post("/exit-scenario", response_model=ExitScenarioResponse)
async def exit_scenario(
    request: ExitScenarioRequest,
    user: dict = Depends(require_read),
):
    """
    OTA-292 — Exit scenario computation engine.

    Returns a row-by-row breakdown of P&L, probability, and expected value
    for a vertical spread across all meaningful price levels at expiry.
    Pure math — no AI involved.
    """
    rows, breakeven, max_profit_price, max_loss_price, dte, time_exit_date, total_ev = _build_exit_rows(
        spread_type=request.spread_type,
        long_strike=request.long_strike,
        short_strike=request.short_strike,
        expiry=request.expiry,
        entry_price=request.entry_price,
        underlying_price=request.underlying_price,
        iv=request.iv,
        risk_free_rate=request.risk_free_rate,
    )
    return ExitScenarioResponse(
        rows=rows,
        breakeven=breakeven,
        max_profit_price=max_profit_price,
        max_loss_price=max_loss_price,
        total_ev=total_ev,
        dte=dte,
        time_exit_date=time_exit_date,
    )


# ─── OTA-297: Trade Verdict — AI Structured Evaluation ───────────────────────

def _extract_verdict_json(text: str) -> Optional[dict]:
    """Extract and parse TradeVerdictResponse JSON from raw AI output."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    else:
        start = text.find("{")
        end   = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception:
        return None


@router.post("/trade-verdict", response_model=TradeVerdictResponse)
async def trade_verdict(
    request: TradeVerdictRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    OTA-297 — Single-trade structured verdict from Claude.

    Accepts pre-computed spread economics (from /evaluate/exit-scenario or client-side).
    Loads TRADE_VERDICT_SYSTEM + TRADE_VERDICT_USER from SKILL.md.
    Returns a TradeVerdictResponse with ev_commentary, key_level, iv_context,
    verdict (EXECUTE | WATCH | PASS), and verdict_rationale.

    agent_run_log write is fire-and-forget — failure never propagates to caller.
    """
    adapter = _get_adapter()
    skill   = get_skill("claude-trade-agent")
    run_id  = str(uuid.uuid4())
    user_id = None if settings.skip_auth else (user.get("sub") or None)

    # ── Build prompts ──────────────────────────────────────────────────────
    system_prompt = skill.get("TRADE_VERDICT_SYSTEM")

    reward_risk = round(request.max_profit / request.max_loss, 2) if request.max_loss else 0.0
    user_message = skill.render(
        "TRADE_VERDICT_USER",
        spread_type=request.spread_type,
        long_strike=request.long_strike,
        short_strike=request.short_strike,
        expiry=request.expiry,
        dte=request.dte,
        entry_price=request.entry_price,
        max_profit=request.max_profit,
        max_loss=request.max_loss,
        breakeven=request.breakeven,
        reward_risk=reward_risk,
        p_max_profit=round(request.p_max_profit * 100, 2),
        p_breakeven_or_better=round(request.p_breakeven_or_better * 100, 2),
        p_max_loss=round(request.p_max_loss * 100, 2),
        total_ev=request.total_ev,
        ev_pct_of_risk=round(request.ev_pct_of_risk, 2),
        iv=round(request.iv * 100, 1),
    )

    # ── Call AI ─────────────────────────────────────────────────────────────
    try:
        result = await adapter.chat(system_prompt, user_message, max_tokens=800)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI evaluation unavailable: {e}")

    raw_text = result["text"]
    data     = _extract_verdict_json(raw_text)

    if data is None:
        raise HTTPException(
            status_code=422,
            detail="AI returned malformed JSON for trade verdict.",
        )

    try:
        verdict_response = TradeVerdictResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"AI response did not match TradeVerdictResponse schema: {e}",
        )

    # ── Fire-and-forget: agent_run_log ───────────────────────────────────────
    try:
        db.add(AgentRunLog(
            run_id=run_id,
            agent_name="claude-trade-agent",
            stage="trade_verdict",
            symbol=f"{request.spread_type} {request.long_strike}/{request.short_strike}",
            user_id=user_id,
            prompt_system=system_prompt,
            prompt_user=user_message,
            prompt_version=skill.prompt_version,
            market_snapshot={"iv": request.iv, "dte": request.dte},
            trade_snapshot={
                "spread_type": request.spread_type,
                "long_strike": request.long_strike,
                "short_strike": request.short_strike,
                "entry_price": request.entry_price,
                "total_ev": request.total_ev,
            },
            model_response_raw=raw_text,
            verdict=verdict_response.verdict,
            verdict_summary=verdict_response.verdict_rationale[:120],
            otel_trace_id=None,
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            model_name=result.get("model", "unknown"),
            created_at=datetime.now(timezone.utc),
        ))
        await db.commit()
    except Exception as e:
        logger.warning(f"agent_run_log write failed (non-fatal): {e}")

    return verdict_response
