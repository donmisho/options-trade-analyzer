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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.core.config import settings
from app.ai.base import AIAdapter
from app.models.session import get_db
from app.models.database import AgentRunLog, TradeCandidate
from app.models.schemas import (
    TradeEvaluationCard,
    ExitScenarioRequest, ExitScenarioRow, ExitScenarioResponse,
    TradeVerdictRequest, TradeVerdictResponse,
)
from app.skills.skill_loader import get_skill
from app.agents.telemetry import invoke_with_tracing
from app.analysis.black_scholes import compute_probability_matrix
from app.ota_adapters._shared.black_scholes import (
    compute_naked_long_option_ev as _compute_naked_long_option_ev,
    pdf_prob as _pdf_prob,
)
from app.models.session import async_session
from app.validators.narrative_grounding import EvaluationFields, validate_narrative
from app.analysis.hard_gates import ACTION_BLOCK, ACTION_DEFER, GateTradeContext
from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
from app.insight_engine.models import Candidate
from app.services.symbol_normalization import canonicalize
from app.analysis.scoring_factors.asymmetry import (
    asymmetry_ratio as _asymmetry_ratio,
)
from app.analysis.strategy_classifier import classify_best_strategy
from app.analysis.strategy_routing import normalize_to_structure
from app.analysis.strategy_definitions import StrategyScore
# OTA-760: engine-precedence rewire — engine produces verdict+score, Claude narrates survivors.
from app.ota_adapters.engine_runtime import get_engine_runtime
from app.ota_adapters.options_chain.adapter import OptionsChainAdapter
from app.options_rules.screening import get_registry as get_screening_registry
from app.api.engine_config_preview import evaluate_screening

router = APIRouter(prefix="/evaluate", tags=["Trade Evaluation"])


async def _update_trade_candidate_evaluation(
    db: AsyncSession, trade_key: str, user_id: str, cards: list,
) -> None:
    """OTA-624: Update trade_candidates row with claude_evaluation after AI eval."""
    if not trade_key:
        return
    try:
        result = await db.execute(
            select(TradeCandidate).where(
                TradeCandidate.trade_key == trade_key,
                TradeCandidate.user_id == user_id,
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate and cards:
            card = cards[0]
            evaluation = {
                "verdict": card.verdict,
                "score": card.score,
                "exit_levels": {
                    "take_profit": card.take_profit,
                    "warning_level": card.warning_level,
                    "hard_stop": card.hard_stop,
                },
                "claude_read": card.claude_read,
                "key_risks": card.key_risks,
                "thesis_invalidators": card.thesis_invalidators,
                "auto_pass_reason": card.auto_pass_reason,
            }
            candidate.claude_evaluation = json.dumps(evaluation)
    except Exception as e:
        logger.warning(f"_update_trade_candidate_evaluation failed (non-fatal): {e}")

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


# ─── OTA-760: engine-rewire helpers ──────────────────────────────────────
#
# _assign_verdict (the in-route 70/50 band literal) is DELETED. Under
# LLM-precedence (insight_engine.md §2.6) the engine owns the verdict and the
# score: both come from the engine ResultRecord's Phase-7 band lookup against
# the per-strategy verdict_band_set (§3.8). No route/app code assigns a verdict.

_earnings_gate_singleton = None


def _get_earnings_gate() -> EarningsInWindowGate:
    """Lazily build the retained EarningsInWindowGate (§2 residual, OTA-760).

    The engine reproduces dte / credit-debit / negative-EV gating, so those
    app-layer gates were removed from this route. EarningsInWindowGate is
    RETAINED unchanged as a PRE-ENGINE short-circuit because the engine's
    earnings gate is currently INERT — no next_earnings_date producer is wired
    into the options-chain adapter (catalog marks earnings "nullable until
    wired"), so its route formulas never fire. Removing this gate would silently
    drop live earnings protection. When an adapter earnings-input producer
    lands, this retained gate MUST be removed in the SAME change, or the app
    gate will mask the engine gate (the producer's earnings logic never fires).
    """
    global _earnings_gate_singleton
    if _earnings_gate_singleton is None:
        _earnings_gate_singleton = EarningsInWindowGate()
    return _earnings_gate_singleton


def _to_float_safe(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def _credit_debit_pct(trade: Optional[dict]) -> tuple[Optional[float], Optional[float]]:
    """Reproduce CreditDebitQualityGate's display metrics from net_debit/width.

    The engine credit/debit gates enforce the floor/ceiling; these values are
    display-only (no effect on verdict/score). Credit spread → net_debit < 0.
    """
    if not trade:
        return None, None
    try:
        net_debit = float(trade.get("net_debit") or 0)
        spread_width = float(trade.get("spread_width") or 0)
    except (TypeError, ValueError):
        return None, None
    if spread_width <= 0:
        return None, None
    if net_debit < 0:
        return round(abs(net_debit) / spread_width, 4), None
    if net_debit > 0:
        return None, round(net_debit / spread_width, 4)
    return None, None


_DTE_WARNING_LOW = 8
_DTE_WARNING_HIGH = 13


def _dte_warning_message(dte: Optional[int]) -> Optional[str]:
    """Reproduce DTEGate's 8-13 warning string (display only).

    The score penalty is applied by the engine's dte_warning_penalty rule; this
    is purely the user-facing banner the legacy strategy-agnostic gate showed
    for any 8-13 DTE trade.
    """
    if dte is None:
        return None
    if _DTE_WARNING_LOW <= dte <= _DTE_WARNING_HIGH:
        return (
            f"{dte} DTE — below recommended minimum. Exit-management time is "
            "limited; a near-expiry score penalty applies."
        )
    return None


def _asymmetry_ratio_from_candidate(candidate) -> Optional[float]:
    """p_max_loss / p_max_profit diagnostic from the engine candidate's COMPUTED
    values (populated by the adapter callback during evaluate). Display only —
    the score impact is the engine's probability_asymmetry_penalty adjustment.
    """
    nv = getattr(candidate, "named_values", {}) or {}
    pml = nv.get("p_max_loss")
    pmp = nv.get("p_max_profit")
    try:
        pml = float(pml) if pml is not None else None
        pmp = float(pmp) if pmp is not None else None
    except (TypeError, ValueError):
        return None
    return _asymmetry_ratio(pml, pmp)


def _halt_claude_read(screening_result) -> str:
    """Templated read for a candidate the engine halted at a gate (non-survivor).

    No Claude call is made for halted candidates (§2.6); the verdict is the
    engine's terminal_verdict.
    """
    return (
        "Did not pass screening — the engine halted this trade at a hard gate "
        f"before scoring (terminal_phase={screening_result.terminal_phase}). "
        "See the engine decision trace for the failing rule."
    )


def _build_engine_candidate(request, strategy_key: str, dte: int, run_id: str) -> Candidate:
    """Build one engine Candidate from the request's pre-chosen trade (DECISION 1
    approach A).

    The legacy /analyze trade dicts (ScoredSpread / ScoredNakedOption) use field
    names that already mirror the options adapter's canonical named values, so the
    trade dict seeds named_values directly; market context comes from the request.
    Verified by the OTA-760 named-value parity pass (PASS). COMPUTED values
    (total_ev, probability_matrix, p_max_loss/p_max_profit) are populated by the
    adapter callback during engine.evaluate. This route does NOT re-fetch the
    chain (approach B rejected) and does NOT re-run _compute_derived (which would
    zero net_theta from absent per-leg thetas).
    """
    trade = dict(request.trade or {})
    nv = dict(trade)

    # Naked trades carry option_type but no spread_type; the engine/adapter use
    # long_call / long_put as the structure key.
    if not nv.get("spread_type") and trade.get("option_type"):
        nv["spread_type"] = f"long_{trade['option_type']}"

    # Core market context (request-supplied; "engine-sourced" per DECISION 1).
    nv["underlying_price"] = request.current_price
    nv["stock_price"] = request.current_price
    nv["dte"] = dte
    if trade.get("expiration"):
        nv["expiration"] = trade["expiration"]
        nv["expiry_date"] = trade["expiration"]

    _iv = trade.get("iv") if trade.get("iv") is not None else request.iv
    nv["iv"] = _iv
    nv["atm_iv"] = _iv  # iv_rank proxy when a true percentile is absent

    sma = request.sma_alignment or {}
    if sma.get("sma_8") is not None:
        nv["sma_8"] = sma.get("sma_8")
    if sma.get("sma_21") is not None:
        nv["sma_21"] = sma.get("sma_21")
    if sma.get("sma_50") is not None:
        nv["sma_50"] = sma.get("sma_50")
    _align = sma.get("alignment") or sma.get("ma_alignment")
    if _align:
        nv["sma_alignment"] = str(_align).upper()
        nv["sma_alignment_classification"] = str(_align).upper()

    return Candidate(
        candidate_id=f"{run_id}:{strategy_key}",
        candidate_type="options_trade",
        named_values=nv,
        symbol=canonicalize(request.symbol),
    )


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
        # OTA-760: the engine owns verdict + score (Phase-7 band lookup). Claude
        # narrates an already-decided verdict — it must NOT set or infer a verdict
        # or a band. The prior "Set verdict from score (>=70/50)" instruction is
        # removed: no band literal lives in the prompt.
        "Populate the narrative and trade-structure fields for each strategy.",
        "Do NOT set or change the verdict or the score — those are decided upstream.",
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
    trade_key: Optional[str] = None    # OTA-624: reference to trade_candidates row


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
    Structured multi-strategy evaluation — engine-precedence (OTA-760).

    LLM precedence (insight_engine.md §2.6): the engine produces the verdict and
    score; Claude only narrates survivors. Flow:
      1. Retained EarningsInWindowGate runs PRE-ENGINE (the engine's earnings gate
         is inert until an adapter earnings producer lands); a BLOCK/DEFER halt
         short-circuits with no engine/Claude call.
      2. For every requested strategy, build a Candidate from the request's trade
         and run engine.evaluate (via the shared evaluate_screening path, with the
         runtime bronze sink). Verdict + score come ONLY from the ResultRecord's
         Phase-7 band lookup against the per-strategy verdict_band_set.
      3. Claude is called once for SURVIVORS only, for narrative prose; it never
         sets or alters verdict/score. Halted candidates get a templated read.
      4. Writes the full input/output to agent_run_log; bronze persistence is
         handled inside engine.evaluate via the injected sink.
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

    # ─── OTA-676: Compute EV for naked single-leg long options ────────────────
    # NakedOptionEngine does not emit total_ev. Compute it server-side so
    # NegativeEVGate can evaluate instead of receiving None (fail-soft pass).
    if request.trade:
        _opt_type = request.trade.get("option_type")
        _has_spread = (
            request.trade.get("long_strike") is not None
            and request.trade.get("short_strike") is not None
        )
        if _opt_type and not _has_spread and request.trade.get("total_ev") is None:
            _strike = request.trade.get("strike")
            _entry = request.trade.get("mid_price") or request.trade.get("entry_price")
            if _strike is not None and _entry is not None:
                try:
                    _computed_ev = _compute_naked_long_option_ev(
                        option_type=_opt_type,
                        strike=float(_strike),
                        underlying_price=request.current_price,
                        iv=request.iv,
                        days_to_exp=dte,
                        entry_price=float(_entry),
                    )
                    request.trade["total_ev"] = _computed_ev
                    logger.info(
                        f"OTA-676: computed naked option EV={_computed_ev:.2f} "
                        f"for {request.symbol} {_opt_type} {_strike}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"OTA-676: failed to compute naked option EV for "
                        f"{request.symbol}: {exc}"
                    )

    # ─── OTA-760: engine runtime + fail-closed guards ────────────────────────
    runtime = get_engine_runtime()
    if request.trade is None:
        raise HTTPException(
            status_code=422,
            detail="trade data is required: the engine evaluates a concrete candidate.",
        )
    _unknown_keys = [k for k in request.strategy_keys if k not in runtime.config.rule_sets]
    if _unknown_keys:
        # MANDATORY GUARD: never fall back to a hardcoded band for an unknown
        # strategy — fail closed (§3.8 / OTA-760).
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown strategy_key(s) not present in the engine config: "
                f"{_unknown_keys}. Fail-closed — no hardcoded verdict fallback."
            ),
        )

    # ─── Earnings Gate (retained app-layer §2 residual — OTA-760) ────────────
    # The engine reproduces dte / credit-debit / negative-EV gating, so those
    # gates were removed from this route. EarningsInWindowGate is RETAINED
    # unchanged as a PRE-ENGINE short-circuit (the engine's earnings gate is
    # inert — no next_earnings_date producer wired into the adapter yet). It
    # fires before engine.evaluate; on a BLOCK/DEFER halt no engine or Claude
    # call is made. Its WAIT_FOR_EARNINGS metadata is preserved natively.
    auto_pass_reason = None

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

    # OTA-775: generic Candidate with named values for the earnings gate
    _gate_candidate = Candidate(
        candidate_id=str(run_id),
        candidate_type="options_trade",
        named_values={
            "expiry_date": _expiry_date,
            "dte": dte,
            "expected_value": _gate_ev,
        },
        symbol=canonicalize(request.symbol),
    )
    _gate_ctx = GateTradeContext(
        symbol=canonicalize(request.symbol),
        entry_date=date.today(),
        candidate=_gate_candidate,
        trade=request.trade,
        db=db,
    )
    earnings_result = await _get_earnings_gate().evaluate(_gate_ctx)
    _wait_for_earnings = False  # OTA-515: set when action is DEFER

    # OTA-776: domain mapping — action codes → OTA verdict strings (earnings only)
    _ACTION_TO_VERDICT = {
        ACTION_BLOCK: "PASS",
        ACTION_DEFER: "WAIT_FOR_EARNINGS",
    }

    if earnings_result and earnings_result.triggered:
        if earnings_result.action == ACTION_DEFER:
            # OTA-515: Route 2 or 3 — short-circuit with WAIT_FOR_EARNINGS cards
            _wait_for_earnings = True
            auto_pass_reason = earnings_result.reason
        else:
            # Hard block (BLOCK) — feed the auto-pass short-circuit below
            auto_pass_reason = earnings_result.reason
    elif earnings_result and not earnings_result.triggered:
        # Route 4 (pre-earnings momentum play): apply effective_dte as a
        # PRE-ENGINE input so the engine scores with the adjusted DTE.
        if earnings_result.effective_dte_override is not None:
            dte = earnings_result.effective_dte_override
        # DOCUMENTED RESIDUAL (OTA-760): the Route-4 15-point penalty is NOT
        # applied. The engine owns the score; a post-engine subtraction would
        # desync the score from the engine band-lookup verdict (forbidden —
        # verdict must come only from the ResultRecord). Restore as a
        # junction-bound earnings adjustment when the earnings input producer
        # lands and the retained EarningsInWindowGate is removed.

    # ─── Auto-PASS / WAIT_FOR_EARNINGS: return immediately, NO engine/Claude ──
    # Only the retained earnings gate can short-circuit here (OTA-760).
    if auto_pass_reason:
        _verdict = _ACTION_TO_VERDICT.get(earnings_result.action, "PASS") if earnings_result else "PASS"
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

        # Credit/debit % reproduced app-side (CreditDebitQualityGate removed; the
        # engine never runs on an earnings short-circuit). Display-only.
        _ap_credit_pct, _ap_debit_pct = _credit_debit_pct(request.trade)
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
                credit_pct_of_width=_ap_credit_pct,
                debit_pct_of_width=_ap_debit_pct,
                dte_after_earnings=earnings_result.metadata.get("dte_after_earnings") if _wait_for_earnings and earnings_result else None,
                reevaluate_on=earnings_result.metadata.get("reevaluate_on") if _wait_for_earnings and earnings_result else None,
            ))

        db.add(AgentRunLog(
            run_id=run_id,
            agent_name="claude-trade-agent",
            stage="auto_pass",
            symbol=canonicalize(request.symbol),
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
        # OTA-624: Update trade candidate with auto-pass evaluation
        # Use user.get("sub") directly — user_id may be None (skip_auth AgentRunLog FK safety)
        # but TradeCandidate was created with the real sub from analysis_routes.
        await _update_trade_candidate_evaluation(db, request.trade_key, user.get("sub", ""), auto_pass_cards)
        await db.commit()

        return StructuredEvaluationResponse(
            evaluations=auto_pass_cards,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            agent_run_id=run_id,
        )

    logger.info(f"Evaluation request payload: symbol={request.symbol}, price={request.current_price}, "
                f"iv={request.iv}, strategies={request.strategy_keys}, dte={dte}, "
                f"trade_keys={list(request.trade.keys()) if request.trade else None}")

    # Probability matrix once (same IV/price/DTE across all strategies) — display only.
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

    # ─── Engine evaluation (LLM-precedence, insight_engine.md §2.6) ───────────
    # The engine runs to completion (gates → scoring → adjustments → verdict)
    # for EVERY requested strategy BEFORE any Claude call. Verdict and score come
    # ONLY from the engine ResultRecord's Phase-7 band lookup against the
    # per-strategy verdict_band_set (§3.8); no app/route code assigns a verdict.
    # evaluate_screening is the single decision-C screening path; passing
    # runtime.sink lands bronze candidate snapshots + decisions (OTA-758).
    _chain_adapter = OptionsChainAdapter()
    _registry = get_screening_registry()

    engine_results: dict[str, Any] = {}
    for _key in request.strategy_keys:
        _cand = _build_engine_candidate(request, _key, dte, run_id)
        _screen = evaluate_screening(
            candidates=[_cand],
            strategy_key=_key,
            config=runtime.config,
            registry=_registry,
            adapter=_chain_adapter,
            sink=runtime.sink,
        )
        if not _screen:
            raise HTTPException(
                status_code=500,
                detail=f"Engine returned no result for strategy {_key!r}.",
            )
        _sr = _screen[0]
        if _sr.verdict is None:
            # Fail-closed: a gate halt with no terminal_verdict is a config gap —
            # never invent a verdict (MANDATORY GUARD).
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Engine produced no verdict for strategy {_key!r} "
                    f"(terminal_phase={_sr.terminal_phase}). Engine config issue — "
                    "not falling back to a hardcoded band."
                ),
            )
        engine_results[_key] = (_sr, _cand)

    # Survivors completed through the verdict phase; halted candidates exited at a
    # gate (terminal_phase = the gate phase value). Claude narrates survivors only.
    survivor_keys = [
        k for k, (sr, _c) in engine_results.items()
        if sr.terminal_phase == "verdict"
    ]

    # ─── Claude narrative — survivors only, prose only (§2.6) ─────────────────
    # Claude sits strictly downstream of the engine verdict. It never sets or
    # alters verdict/score; for halted candidates it is not called at all.
    system_prompt = skill.get("DEEP_DIVE_SYSTEM")
    _claude_by_key: dict[str, Any] = {}
    raw_text = ""
    user_message = ""
    _model_name = "none"
    _input_tokens = 0
    _output_tokens = 0
    _otel_trace_id = None

    if survivor_keys:
        # OTA-618: strategy_spec per surviving strategy
        from app.analysis.strategy_definitions import STRATEGIES as _STRATEGIES
        _strategy_specs = {}
        for _sk in survivor_keys:
            _sdef = _STRATEGIES.get(_sk)
            if _sdef:
                _credit_types = {"bull_put_credit", "bear_call_credit"}
                _is_credit = bool(_credit_types & set(_sdef.compatible_structures))
                _strategy_specs[_sk] = {
                    "preferred_dte_window": [_sdef.dte_min, _sdef.dte_max],
                    "preferred_structure": "credit" if _is_credit else "debit",
                    "compatible_structures": _sdef.compatible_structures,
                }

        user_message = _build_structured_user_message(
            symbol=request.symbol,
            current_price=request.current_price,
            iv=request.iv,
            sma_alignment=request.sma_alignment,
            strategy_keys=survivor_keys,
            scores=request.scores,
            trade=request.trade,
            current_date=current_date,
            dte=dte,
            strategy_specs=_strategy_specs,
        )

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
                    "strategy_keys": survivor_keys,
                    "trade_type": request.trade.get("option_type") or request.trade.get("spread_type") if request.trade else None,
                    "user_message_preview": user_message[:500],
                }
                if isinstance(e, httpx.HTTPStatusError):
                    err_details["status_code"] = e.response.status_code
                    err_details["response_body"] = e.response.text[:1000]
                logger.error(
                    f"AI narrative failed for {request.symbol} "
                    f"(strategies={survivor_keys}): {type(e).__name__}: {e}",
                    extra={"eval_error_details": err_details},
                )
                raise HTTPException(status_code=502, detail=f"AI narrative failed: {e}")

            span_ctx["input_tokens"] = result["input_tokens"]
            span_ctx["output_tokens"] = result["output_tokens"]
            _otel_trace_id = span_ctx.get("otel_trace_id")

        raw_text = result["text"]
        _input_tokens = result["input_tokens"]
        _output_tokens = result["output_tokens"]
        _model_name = result["model"]
        _parsed = _try_parse_cards(raw_text)

        # Retry once with correction context if initial parse failed
        if _parsed is None:
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
                _input_tokens += retry_result["input_tokens"]
                _output_tokens += retry_result["output_tokens"]
                _parsed = _try_parse_cards(raw_text)
            except Exception as retry_exc:
                logger.warning(
                    f"AI narrative retry failed for {request.symbol}: "
                    f"{type(retry_exc).__name__}: {retry_exc}"
                )

        if _parsed:
            for _c in _parsed:
                _claude_by_key[_c.strategy_key] = _c

        # ─── Narrative Grounding (OTA-504) — PROSE ONLY; never touches verdict/score ──
        _raw_ev = request.trade.get("total_ev") if request.trade else None
        _computed_fields = EvaluationFields(
            price=request.current_price,
            sma_8=_to_float_safe(request.sma_alignment.get("sma_8")),
            sma_21=_to_float_safe(request.sma_alignment.get("sma_21")),
            sma_50=_to_float_safe(request.sma_alignment.get("sma_50")),
            expected_value=_to_float_safe(_raw_ev),
        )
        _grounding_errors = []
        for _c in _claude_by_key.values():
            if _c.claude_read:
                _grounding_errors.extend(validate_narrative(_c.claude_read, _computed_fields))

        if _grounding_errors:
            logger.warning(
                f"Narrative grounding errors for {request.symbol} (run_id={run_id}): "
                f"{[e.code for e in _grounding_errors]}"
            )
            _retry_evals = None
            try:
                _retry_result = await adapter.chat(system_prompt, user_message, max_tokens=3000)
                _input_tokens += _retry_result["input_tokens"]
                _output_tokens += _retry_result["output_tokens"]
                _retry_evals = _try_parse_cards(_retry_result["text"])
            except Exception as _retry_exc:
                logger.warning(f"Narrative grounding retry call failed: {_retry_exc}")

            _retry_ok = False
            if _retry_evals is not None:
                _retry_map = {c.strategy_key: c for c in _retry_evals}
                _retry_errors = []
                for _c in _retry_map.values():
                    if _c.claude_read:
                        _retry_errors.extend(validate_narrative(_c.claude_read, _computed_fields))
                if not _retry_errors:
                    # Replace PROSE ONLY — engine verdict/score applied below.
                    for _k, _c in _retry_map.items():
                        if _k in _claude_by_key:
                            _claude_by_key[_k] = _c
                    _retry_ok = True
                    logger.info(f"Narrative grounding retry succeeded for {request.symbol} (run_id={run_id})")

            if not _retry_ok:
                for _c in _claude_by_key.values():
                    _c.claude_read = (
                        "Structured evaluation complete. See computed fields for details. "
                        "Narrative unavailable this cycle."
                    )

            # Fire-and-forget observability — never block emission
            asyncio.create_task(
                _log_validator_event(
                    run_id, request.symbol, user_id,
                    {
                        "validator": "narrative_grounding",
                        "errors": [
                            {"code": e.code, "field": e.field_context, "msg": e.message}
                            for e in _grounding_errors
                        ],
                        "retry_triggered": True,
                        "fallback_used": not _retry_ok,
                    },
                    skill.prompt_version,
                )
            )

    # ─── Assemble cards — engine owns verdict + score; Claude prose attached ──
    evaluations: List[TradeEvaluationCard] = []
    for _key in request.strategy_keys:
        _sr, _cand = engine_results[_key]
        _label = _key.replace("-", " ").title()
        _engine_score = int(round(_sr.score)) if _sr.score is not None else 0

        if _key in survivor_keys and _key in _claude_by_key:
            card = _claude_by_key[_key]
            card.score = _engine_score          # engine owns score
            card.verdict = _sr.verdict          # engine owns verdict (Phase-7 band)
        else:
            # Halted at a gate (or narrative missing) → templated card, no prose.
            _structure = (request.trade.get("spread_label") or "") if request.trade else ""
            card = TradeEvaluationCard(
                strategy_key=_key,
                strategy_label=_label,
                trade_structure=_structure,
                entry_price=0.0,
                max_profit=0.0,
                max_loss=0.0,
                exit_warning_price=0.0,
                exit_warning_pnl=0.0,
                exit_target_debit=0.0,
                exit_stop_debit=0.0,
                probability_matrix={},
                score=_engine_score,
                verdict=_sr.verdict,
                claude_read=_halt_claude_read(_sr),
                key_risks=[],
                thesis_invalidators=[],
            )

        # Reproduced display metadata (no effect on verdict/score):
        # - probability_matrix + effective_dte (echoed)
        # - credit/debit % (CreditDebitQualityGate display metric, app-side)
        # - dte_warning (DTEGate 8-13 banner; engine applies the score penalty)
        # - asymmetry_ratio (diagnostic from candidate COMPUTED values; the score
        #   impact is the engine's probability_asymmetry_penalty adjustment)
        card.probability_matrix = pm_dict
        card.effective_dte = dte
        _credit_pct, _debit_pct = _credit_debit_pct(request.trade)
        if _credit_pct is not None:
            card.credit_pct_of_width = _credit_pct
        if _debit_pct is not None:
            card.debit_pct_of_width = _debit_pct
        _dwarn = _dte_warning_message(dte)
        if _dwarn:
            card.dte_warning = _dwarn
        card.asymmetry_ratio = _asymmetry_ratio_from_candidate(_cand)
        evaluations.append(card)

    # ─── Strategy Classifier (OTA-506) — ranks by the engine score ───────────
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
    # OTA-636: resolve trade_structure for structural compatibility gating
    _trade_structure = normalize_to_structure(
        spread_type=(request.trade or {}).get("spread_type"),
        option_type=(request.trade or {}).get("option_type"),
    )
    _classification = classify_best_strategy(
        _clf_candidates, effective_dte=dte, trade_structure=_trade_structure,
    )
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
        symbol=canonicalize(request.symbol),
        user_id=user_id,
        prompt_system=system_prompt if survivor_keys else "ENGINE_ONLY",
        prompt_user=user_message if survivor_keys else "ENGINE_ONLY (all strategies halted at gates)",
        prompt_version=skill.prompt_version,
        market_snapshot={
            "symbol": canonicalize(request.symbol),
            "underlying_price": request.current_price,
            "iv": request.iv,
            **request.sma_alignment,
        },
        trade_snapshot={
            "strategy_keys": request.strategy_keys,
            "survivor_keys": survivor_keys,
            "trade": request.trade,
            "earnings_gate": {
                "gate_id": earnings_result.gate_id,
                "triggered": earnings_result.triggered,
                "effective_dte_override": earnings_result.effective_dte_override,
                "reason": earnings_result.reason,
            } if earnings_result else None,
        },
        model_response_raw=raw_text,
        verdict=None,
        verdict_summary=verdicts_summary,
        otel_trace_id=_otel_trace_id,
        input_tokens=_input_tokens,
        output_tokens=_output_tokens,
        model_name=_model_name,
        created_at=datetime.now(timezone.utc),
    ))
    # OTA-624: Update trade candidate with the evaluation
    # Use user.get("sub") directly — same reasoning as auto-pass path above.
    await _update_trade_candidate_evaluation(db, request.trade_key, user.get("sub", ""), evaluations)
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


# ─── OTA-676: _compute_naked_long_option_ev — moved to
# app.ota_adapters._shared.black_scholes (OTA-716). Imported at top of file.

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


# _pdf_prob — moved to app.ota_adapters._shared.black_scholes (OTA-716).
# Imported at top of file.


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
