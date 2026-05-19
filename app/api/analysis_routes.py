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

import asyncio
import json
import logging
import uuid
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.core.config import settings
from app.providers.factory import ProviderRegistry
from app.models.session import get_db
from app.models.database import OptionChainSnapshot, AnalysisRun, AnalyzedTrade, TradeCandidate
from app.analysis.vertical_engine import (
    VerticalSpreadEngine, ScoringWeights, SpreadFilters
)
from app.analysis.long_call_engine import (
    LongCallEngine, LongCallWeights, LongCallFilters
)
from app.analysis.directional_engine import DirectionalEngine, Thesis
from app.analysis.strategy_scorer import score_all_strategies, compute_sma_signal
from app.services.symbol_normalization import canonicalize
from app.analysis.strategy_definitions import STRATEGIES
from app.analysis.black_scholes import compute_probability_matrix
from app.models.schemas import (
    ScorecardRequest, ScorecardResponse, StrategyScoreItem,
    ProbabilityMatrixRequest, ProbabilityMatrixResponse,
)

log = logging.getLogger(__name__)

# OTA-649: Human-readable labels for compatible_structures values.
_STRUCTURE_LABELS = {
    "bull_put_credit":   "Bull Put Credit",
    "bear_call_credit":  "Bear Call Credit",
    "bull_call_debit":   "Bull Call Debit",
    "bear_put_debit":    "Bear Put Debit",
    "long_call":         "Long Call",
    "long_put":          "Long Put",
}


def _structure_human_label(structure: str) -> str:
    return _STRUCTURE_LABELS.get(structure, structure.replace("_", " ").title())


router = APIRouter(prefix="/analyze", tags=["Analysis"])

# Initialized in main.py at startup
_provider_registry: Optional[ProviderRegistry] = None


def init_analysis_routes(registry: ProviderRegistry):
    global _provider_registry
    _provider_registry = registry


def _get_registry() -> ProviderRegistry:
    if _provider_registry is None:
        raise RuntimeError("Provider registry not initialized")
    return _provider_registry


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
    min_spread_width: float = Field(default=1.0, ge=0.5)
    max_spread_width: float = Field(default=10.0, ge=1)
    # Greek filters
    min_short_delta: float = Field(default=0.15, ge=0.0, le=1.0)
    max_short_delta: float = Field(default=0.45, ge=0.0, le=1.0)
    min_net_delta: float = Field(default=0.0, ge=0.0, le=1.0)
    max_net_theta: float = Field(default=0.0, ge=0.0)
    # Liquidity filters
    min_open_interest: int = Field(default=50, ge=0)
    min_volume: int = Field(default=5, ge=0)
    # Scoring filters (surfaced from frontend system vars)
    min_reward_risk: float = Field(default=0.5, ge=0.0)
    min_ev_threshold: float = Field(default=0.0)
    # OTA-559: strategy-aware DTE filtering
    enabled_strategies: Optional[list[str]] = Field(
        default=None,
        description="Strategy keys to filter by (e.g. ['steady-paycheck','weekly-grind']). None=all."
    )
    user_config: Optional[dict] = Field(
        default=None,
        description="Per-strategy DTE overrides: {'weekly-grind': {'dte_min': 10, 'dte_max': 25}}"
    )


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
) -> tuple[list[dict], float, dict]:
    """
    Fetch options chain and underlying price from the provider.
    Returns (contracts, underlying_price, raw_chain_dict).

    WHY this is a shared helper: All three endpoints need chain data.
    Extracting it avoids duplicating the provider lookup + error handling.
    The raw chain dict is returned so callers can persist it.
    """
    registry = _get_registry()
    provider = registry.get_market_data(settings.default_market_data_provider, user_id=user.get("sub"))

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

    return contracts, underlying_price, chain_data


async def _persist_chain_snapshot(
    db: AsyncSession,
    user_id: str,
    symbol: str,
    underlying_price: float,
    chain_data: dict,
    provider: str = "unknown",
) -> Optional[int]:
    """
    Persist an option chain snapshot and return its id.
    Returns None if persistence fails (never blocks the response).
    """
    try:
        contracts = chain_data.get("contracts", [])
        snapshot = OptionChainSnapshot(
            user_id=user_id,
            symbol=symbol,
            underlying_price=underlying_price,
            provider=provider,
            contract_count=len(contracts),
            chain_data=contracts,
        )
        db.add(snapshot)
        await db.flush()  # gets the id without committing
        return snapshot.id
    except Exception as e:
        log.warning(f"Failed to persist chain snapshot for {symbol}: {e}")
        return None


# ─── OTA-559: Strategy-aware DTE helpers ─────────────────────────────


def _resolve_strategy_bands(
    enabled_strategies: list[str] | None,
    user_config: dict | None,
) -> dict[str, tuple[int, int]]:
    """
    Build {strategy_key: (dte_min, dte_max)} for the enabled strategies,
    applying user_config overrides if provided. Returns empty dict when
    no strategy filtering should be applied.
    """
    if enabled_strategies is not None:
        keys = [k for k in enabled_strategies if k in STRATEGIES]
    else:
        keys = list(STRATEGIES.keys())

    if not keys:
        return {}

    uc = user_config or {}
    bands = {}
    for k in keys:
        s = STRATEGIES[k]
        overrides = uc.get(k, {})
        lo = overrides.get("dte_min", s.dte_min)
        hi = overrides.get("dte_max", s.dte_max)
        bands[k] = (int(lo), int(hi))
    return bands


def _spread_dte(spread: dict) -> int:
    """Compute DTE from a spread dict's expiration field."""
    exp = spread.get("expiration")
    if not exp:
        return 0
    try:
        exp_date = date.fromisoformat(exp[:10])
        return max(0, (exp_date - date.today()).days)
    except (ValueError, TypeError):
        return 0


# ─── OTA-624: Trade candidate persistence helpers ────────────────

def _build_vertical_candidate(
    spread: dict, user_id: str, symbol: str, underlying_price: float,
) -> TradeCandidate:
    """Build a TradeCandidate from a vertical spread result dict."""
    trade_key = str(uuid.uuid4())
    spread["trade_key"] = trade_key

    legs = []
    # Build leg detail from spread fields
    if spread.get("long_strike") is not None:
        legs.append({
            "side": "long",
            "option_type": spread.get("option_type", "call"),
            "strike": spread.get("long_strike"),
            "expiration": spread.get("expiration"),
            "qty": 1,
            "bid": spread.get("long_bid"),
            "ask": spread.get("long_ask"),
            "delta": spread.get("long_delta"),
            "iv": spread.get("long_iv"),
            "symbol": spread.get("long_symbol"),
        })
    if spread.get("short_strike") is not None:
        legs.append({
            "side": "short",
            "option_type": spread.get("option_type", "call"),
            "strike": spread.get("short_strike"),
            "expiration": spread.get("expiration"),
            "qty": 1,
            "bid": spread.get("short_bid"),
            "ask": spread.get("short_ask"),
            "delta": spread.get("short_delta"),
            "iv": spread.get("short_iv"),
            "symbol": spread.get("short_symbol"),
        })

    net_metrics = {
        "entry_price": spread.get("net_debit"),
        "max_profit": spread.get("max_profit"),
        "max_loss": spread.get("net_debit"),
        "breakeven": spread.get("breakeven"),
        "net_bid_ask": spread.get("net_bid_ask"),
        "dte": spread.get("dte"),
        "iv_rank": spread.get("iv_rank"),
        "scenario_weighted_ev": spread.get("ev_raw"),
        "prob_of_profit": spread.get("prob_of_profit"),
    }

    # Per-component scores from the engine (raw 0-100 values)
    engine_scores = {
        "ev_score": spread.get("ev_score"),
        "rr_score": spread.get("rr_score"),
        "prob_score": spread.get("prob_score"),
        "liquidity_score": spread.get("liquidity_score"),
        "theta_score": spread.get("theta_score"),
    }

    # OTA-643 precursor: structured component breakdown for score table rendering.
    # Maps engine score keys to display labels and captures weight + contribution.
    _VERTICAL_COMPONENT_MAP = [
        ("ev_score",        "Expected value (EV)",            0.35),
        ("rr_score",        "Structure fit (vs profile)",     0.25),
        ("prob_score",      "Cushion / strike placement",     0.20),
        ("liquidity_score", "Liquidity (bid-ask, volume)",    0.15),
        ("theta_score",     "IV environment",                 0.05),
    ]
    component_breakdown = []
    raw_total = 0.0
    for key, label, default_weight in _VERTICAL_COMPONENT_MAP:
        score_val = engine_scores.get(key) or 0
        score_int = min(100, max(0, round(float(score_val))))
        contribution = round(float(score_val) * default_weight, 1)
        raw_total += contribution
        component_breakdown.append({
            "key": key, "label": label,
            "score": score_int, "weight": default_weight,
            "contribution": contribution,
        })
    raw_total = round(raw_total, 1)

    pipeline_components = {
        **engine_scores,
        "component_breakdown": component_breakdown,
        "raw_total": raw_total,
        "adjusted_total": spread.get("composite_score"),
    }

    structure = spread.get("spread_type", "vertical")
    strategies = spread.get("fitting_strategies", [])

    return TradeCandidate(
        trade_key=trade_key,
        user_id=user_id,
        symbol=symbol,
        structure=structure,
        leg_count=len(legs),
        legs=json.dumps(legs),
        net_metrics=json.dumps(net_metrics),
        underlying_spot=underlying_price,
        pipeline_score=spread.get("composite_score"),
        pipeline_components=json.dumps(pipeline_components),
        scan_source="/analyze/verticals",
        scan_strategy_key=strategies[0] if strategies else None,
        scanned_at=datetime.now(timezone.utc),
    )


def _build_long_option_candidate(
    option: dict, user_id: str, symbol: str, underlying_price: float,
) -> TradeCandidate:
    """Build a TradeCandidate from a long option result dict."""
    trade_key = str(uuid.uuid4())
    option["trade_key"] = trade_key

    opt_type = option.get("option_type", "call")
    legs = [{
        "side": "long",
        "option_type": opt_type,
        "strike": option.get("strike"),
        "expiration": option.get("expiration"),
        "qty": 1,
        "bid": option.get("bid"),
        "ask": option.get("ask"),
        "delta": option.get("delta"),
        "iv": option.get("iv"),
        "symbol": option.get("occ_symbol"),
    }]

    net_metrics = {
        "entry_price": option.get("mid_price") or option.get("premium_dollars"),
        "max_profit": None,  # unlimited for long options
        "max_loss": option.get("mid_price") or option.get("premium_dollars"),
        "breakeven": option.get("breakeven"),
        "dte": option.get("days_to_exp"),
        "iv_rank": option.get("iv_rank"),
    }

    engine_scores = {
        "delta_score": option.get("delta_score"),
        "theta_score": option.get("theta_score"),
        "iv_score": option.get("iv_score"),
        "rr_score": option.get("rr_score"),
        "liquidity_score": option.get("liquidity_score"),
    }

    # OTA-643 precursor: structured component breakdown for long options.
    _LONG_COMPONENT_MAP = [
        ("delta_score",     "Technical alignment (SMAs)",     0.30),
        ("rr_score",        "Expected value (EV)",            0.25),
        ("iv_score",        "IV environment",                 0.20),
        ("theta_score",     "DTE fit",                        0.15),
        ("liquidity_score", "Liquidity (bid-ask, volume)",    0.10),
    ]
    component_breakdown = []
    raw_total = 0.0
    for key, label, default_weight in _LONG_COMPONENT_MAP:
        score_val = engine_scores.get(key) or 0
        score_int = min(100, max(0, round(float(score_val))))
        contribution = round(float(score_val) * default_weight, 1)
        raw_total += contribution
        component_breakdown.append({
            "key": key, "label": label,
            "score": score_int, "weight": default_weight,
            "contribution": contribution,
        })
    raw_total = round(raw_total, 1)

    pipeline_components = {
        **engine_scores,
        "component_breakdown": component_breakdown,
        "raw_total": raw_total,
        "adjusted_total": option.get("composite_score"),
    }

    return TradeCandidate(
        trade_key=trade_key,
        user_id=user_id,
        symbol=symbol,
        structure=f"long_{opt_type}",
        leg_count=1,
        legs=json.dumps(legs),
        net_metrics=json.dumps(net_metrics),
        underlying_spot=underlying_price,
        pipeline_score=option.get("composite_score"),
        pipeline_components=json.dumps(pipeline_components),
        scan_source="/analyze/long-calls",
        scan_strategy_key=None,
        scanned_at=datetime.now(timezone.utc),
    )


async def _persist_trade_candidates(
    db: AsyncSession, candidates: list[TradeCandidate],
) -> None:
    """Bulk insert trade candidates. Fire-and-forget — never blocks the response."""
    try:
        for c in candidates:
            db.add(c)
        await db.flush()
    except Exception as e:
        log.warning(f"Failed to persist trade candidates: {e}")


# ─── Endpoints ────────────────────────────────────────────────────

@router.post("/verticals")
async def analyze_verticals(
    req: VerticalRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Score and rank all valid vertical spreads for a symbol.

    Replaces the "Vertical Spreads" sheet from the Excel tool.
    Returns spreads ranked by composite score (weighted combination
    of EV, reward:risk, probability, liquidity, and theta efficiency).
    Every run persists the chain snapshot, run parameters, and all scored trades.
    """
    user_id = user.get("sub")
    sym = canonicalize(req.symbol)

    # OTA-559: Compute DTE envelope from enabled strategies
    _strategy_bands = _resolve_strategy_bands(
        req.enabled_strategies, req.user_config
    )
    if _strategy_bands:
        _env_min = min(b[0] for b in _strategy_bands.values())
        _env_max = max(b[1] for b in _strategy_bands.values())
    else:
        _env_min, _env_max = req.min_dte, req.max_dte

    contracts, price, chain_data = await _fetch_chain(
        req.symbol, user,
        min_dte=_env_min,
        max_dte=_env_max,
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

    filters = SpreadFilters(
        spread_types=req.spread_types,
        min_short_delta=req.min_short_delta,
        max_short_delta=req.max_short_delta,
        max_spread_width=req.max_spread_width,
        min_net_delta=req.min_net_delta,
        max_net_theta=req.max_net_theta,
        min_open_interest=req.min_open_interest,
        min_volume=req.min_volume,
        min_reward_risk=req.min_reward_risk,
        min_ev_threshold=req.min_ev_threshold,
    )
    engine = VerticalSpreadEngine(weights=weights, filters=filters)

    result = engine.analyze(
        contracts=contracts,
        underlying_price=price,
        max_results=None,  # don't truncate before strategy filter
    )

    # OTA-559: Tag each spread with fitting strategies and filter
    if _strategy_bands:
        tagged = []
        for s in result.get("spreads", []):
            dte = _spread_dte(s)
            fits = [k for k, (lo, hi) in _strategy_bands.items() if lo <= dte <= hi]
            if fits:
                s["fitting_strategies"] = fits
                tagged.append(s)
        result["spreads"] = tagged[:req.max_results] if req.max_results else tagged
        result["total_valid"] = len(tagged)

    result["symbol"] = sym

    # ── Persist analysis data (never block the response on failure) ──
    try:
        now = datetime.now(timezone.utc)
        weights_dict = {
            "expected_value": weights.expected_value,
            "reward_risk": weights.reward_risk,
            "probability": weights.probability,
            "liquidity": weights.liquidity,
            "theta_efficiency": weights.theta_efficiency,
        }
        filter_dict = {
            "spread_types": req.spread_types,
            "min_dte": req.min_dte,
            "max_dte": req.max_dte,
            "strike_range_pct": req.strike_range_pct,
            "min_spread_width": req.min_spread_width,
            "max_spread_width": req.max_spread_width,
            "min_reward_risk": req.min_reward_risk,
            "min_ev_threshold": req.min_ev_threshold,
        }

        chain_id = await _persist_chain_snapshot(db, user_id, sym, price, chain_data)

        spreads = result.get("spreads", [])
        run = AnalysisRun(
            user_id=user_id,
            symbol=sym,
            analysis_type="verticals",
            underlying_price=price,
            chain_snapshot_id=chain_id,
            scoring_weights=weights_dict,
            filter_params=filter_dict,
            result_count=len(spreads),
            total_valid=result.get("total_valid", len(spreads)),
            ran_at=now,
        )
        db.add(run)
        await db.flush()

        for s in spreads:
            db.add(AnalyzedTrade(
                run_id=run.id,
                user_id=user_id,
                symbol=sym,
                analysis_type="vertical",
                spread_type=s.get("spread_type"),
                long_strike=s.get("long_strike"),
                short_strike=s.get("short_strike"),
                option_type=s.get("option_type"),
                expiration=s.get("expiration"),
                dte=s.get("dte"),
                underlying_price=price,
                net_debit=s.get("net_debit"),
                max_profit=s.get("max_profit"),
                max_loss=s.get("net_debit"),
                breakeven=s.get("breakeven"),
                rr_ratio=s.get("reward_risk_ratio"),
                prob_of_profit=s.get("prob_of_profit"),
                ev_raw=s.get("ev_raw"),
                long_volume=s.get("long_volume"),
                short_volume=s.get("short_volume"),
                long_oi=s.get("long_oi"),
                short_oi=s.get("short_oi"),
                composite_score=s.get("composite_score", 0),
                score_breakdown={
                    "ev_score": s.get("ev_score"),
                    "rr_score": s.get("rr_score"),
                    "prob_score": s.get("prob_score"),
                    "liquidity_score": s.get("liquidity_score"),
                    "theta_score": s.get("theta_score"),
                },
                scoring_weights=weights_dict,
                captured_at=now,
            ))

        # OTA-624: Persist trade candidates for atomic Follow
        trade_candidates = [
            _build_vertical_candidate(s, user_id, sym, price)
            for s in spreads
        ]
        await _persist_trade_candidates(db, trade_candidates)

        await db.commit()
    except Exception as e:
        log.warning(f"Failed to persist vertical analysis run for {sym}: {e}")
        await db.rollback()

    return result


@router.post("/long-calls")
async def analyze_long_calls(
    req: LongCallRequest,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Score and rank long call candidates for a symbol.

    Replaces the "Naked Calls" sheet from the Excel tool.
    Returns calls ranked by composite score (weighted combination
    of delta alignment, theta efficiency, IV value, R:R, liquidity).
    Every run persists the chain snapshot, run parameters, and all scored trades.
    """
    user_id = user.get("sub")
    sym = canonicalize(req.symbol)

    chain_type = None
    if len(req.option_types) == 1:
        chain_type = req.option_types[0]

    contracts, price, chain_data = await _fetch_chain(
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
    result["symbol"] = sym

    # ── Persist analysis data (never block the response on failure) ──
    try:
        now = datetime.now(timezone.utc)
        # LongCallEngine uses default weights internally — capture them
        default_lc_weights = {
            "delta": 0.30,
            "theta_efficiency": 0.25,
            "iv_value": 0.20,
            "reward_risk": 0.15,
            "liquidity": 0.10,
        }
        filter_dict = {
            "option_types": req.option_types,
            "min_dte": req.min_dte,
            "max_dte": req.max_dte,
            "strike_range_pct": req.strike_range_pct,
            "max_premium": req.max_premium,
        }

        chain_id = await _persist_chain_snapshot(db, user_id, sym, price, chain_data)

        options = result.get("calls") or result.get("options", [])
        run = AnalysisRun(
            user_id=user_id,
            symbol=sym,
            analysis_type="naked",
            underlying_price=price,
            chain_snapshot_id=chain_id,
            scoring_weights=default_lc_weights,
            filter_params=filter_dict,
            result_count=len(options),
            total_valid=result.get("total_valid", len(options)),
            ran_at=now,
        )
        db.add(run)
        await db.flush()

        for o in options:
            opt_type = o.get("option_type", chain_type or "call")
            db.add(AnalyzedTrade(
                run_id=run.id,
                user_id=user_id,
                symbol=sym,
                analysis_type="naked",
                spread_type=f"long_{opt_type}",
                long_strike=o.get("strike"),
                option_type=opt_type,
                expiration=o.get("expiration"),
                dte=o.get("days_to_exp"),
                underlying_price=price,
                premium_dollars=o.get("premium_dollars"),
                delta=o.get("delta"),
                theta_per_day=o.get("theta_per_day_dollars"),
                iv=o.get("iv"),
                breakeven=o.get("breakeven"),
                long_volume=o.get("volume"),
                long_oi=o.get("open_interest"),
                composite_score=o.get("composite_score", 0),
                score_breakdown={
                    "delta_score": o.get("delta_score"),
                    "theta_score": o.get("theta_score"),
                    "iv_score": o.get("iv_score"),
                    "rr_score": o.get("rr_score"),
                    "liquidity_score": o.get("liquidity_score"),
                },
                scoring_weights=default_lc_weights,
                captured_at=now,
            ))

        # OTA-624: Persist trade candidates for atomic Follow
        trade_candidates = [
            _build_long_option_candidate(o, user_id, sym, price)
            for o in options
        ]
        await _persist_trade_candidates(db, trade_candidates)

        await db.commit()
    except Exception as e:
        log.warning(f"Failed to persist naked analysis run for {sym}: {e}")
        await db.rollback()

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
        symbol=canonicalize(req.symbol),
        direction=req.direction,
        target_price=req.target_price,
        timeframe_days=req.timeframe_days,
        risk_budget=req.risk_budget,
        current_price=price,
    )

    engine = DirectionalEngine()
    result = engine.compare(thesis=thesis, contracts=contracts)

    return result


@router.post("/scorecard", response_model=ScorecardResponse)
async def get_strategy_scorecard(
    req: ScorecardRequest,
    user: dict = Depends(require_read),
):
    """
    Score all four strategies for a symbol using a single chain fetch.

    Returns a 0-100 score per strategy plus the best candidate trade and
    a signal summary. Scores are normalized within each strategy independently
    using min-max scaling across candidates.

    Accepts optional user_config overrides (dte_min, delta_max, sma_alignment_score, etc.).
    Pass sma_alignment_score (0-1) from the frontend SMA indicator to influence trend-rider.

    IMPORTANT: exactly one chain fetch happens regardless of how many strategies are scored.
    """
    sym = canonicalize(req.symbol)
    registry = _get_registry()
    provider = registry.get_market_data(settings.default_market_data_provider, user_id=user.get("sub"))

    # Fetch strategy scores, quote, and price history in parallel
    scores_task = score_all_strategies(symbol=sym, provider=provider, user_config=req.user_config)

    has_price_history = hasattr(provider, "get_price_history")
    if has_price_history:
        results = await asyncio.gather(
            scores_task,
            provider.get_quote(sym),
            provider.get_price_history(sym),
            return_exceptions=True,
        )
        scores_result, quote_result, history_result = results
    else:
        results = await asyncio.gather(
            scores_task,
            provider.get_quote(sym),
            return_exceptions=True,
        )
        scores_result, quote_result = results
        history_result = []

    scores, underlying_price = scores_result if not isinstance(scores_result, Exception) else ([], 0.0)

    quote_data = None
    if not isinstance(quote_result, Exception):
        q = quote_result
        quote_data = {
            "price":       q.get("price"),
            "change":      q.get("change"),
            "change_pct":  q.get("change_pct"),
            "volume":      q.get("volume"),
            "rel_volume":  q.get("volume_ratio"),
            "description": q.get("description", ""),
        }

    sma_signal = None
    candles = history_result if isinstance(history_result, list) else []
    price_for_sma = (quote_data or {}).get("price") or underlying_price
    if candles and price_for_sma:
        sma_signal = compute_sma_signal(candles, price_for_sma)

    # OTA-649: Return all four strategies in canonical order (SP, WG, TR, LT).
    # None entries from score_all_strategies become score=null + reason for N/A display.
    strategy_items = []
    for i, (strategy_key, strategy_def) in enumerate(STRATEGIES.items()):
        s = scores[i] if i < len(scores) else None
        if s is not None:
            strategy_items.append(StrategyScoreItem(
                strategy_key=s.strategy_key,
                label=s.label,
                score=s.score,
                best_trade=s.best_trade,
                signal_summary=s.signal_summary,
                metric_scores=s.metric_scores,
            ))
        else:
            structures = ", ".join(
                _structure_human_label(st)
                for st in strategy_def.compatible_structures
            )
            strategy_items.append(StrategyScoreItem(
                strategy_key=strategy_key,
                label=strategy_def.label,
                score=None,
                reason=f"No eligible {strategy_def.label} candidates — strategy requires {structures}",
            ))

    return ScorecardResponse(
        symbol=sym,
        underlying_price=underlying_price,
        quote=quote_data,
        sma_signal=sma_signal,
        strategies=strategy_items,
    )


@router.post("/probability-matrix", response_model=ProbabilityMatrixResponse)
async def get_probability_matrix(
    req: ProbabilityMatrixRequest,
    user: dict = Depends(require_read),
):
    """
    Compute a Black-Scholes probability matrix for a trade.

    Returns the probability of the underlying being at each price level
    on four snapshot dates: expiry-9, expiry-6, expiry-3, and expiry.
    Price levels cover ±price_range_pct around current_price in price_step increments.

    This is a deterministic math computation — Claude is NOT involved.
    The matrix is used as context when Claude evaluates a trade.
    """
    try:
        result = compute_probability_matrix(
            current_price=req.current_price,
            iv=req.iv,
            dte=req.dte,
            risk_free_rate=req.risk_free_rate,
            price_range_pct=req.price_range_pct,
            price_step=req.price_step,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Matrix computation failed: {e}")

    return ProbabilityMatrixResponse(
        symbol=canonicalize(req.symbol),
        current_price=req.current_price,
        iv=req.iv,
        dte=req.dte,
        price_levels=result.price_levels,
        dates=[d.isoformat() for d in result.dates],
        matrix=result.matrix,
    )
