"""
Strategy Scorer Engine (Phase 2.9)

Scores all four strategies for a given symbol using a SINGLE options chain fetch.
This is critical for quota management — never fetches the chain more than once per call.

Each strategy is scored 0-100 based on its own weighted metrics from strategy_definitions.py.
Candidates are normalized with min-max scaling independently per strategy.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Optional

from app.analysis.strategy_definitions import STRATEGIES
from app.analysis.vertical_engine import VerticalSpreadEngine, SpreadFilters
from app.analysis.long_call_engine import LongCallEngine, LongCallFilters

log = logging.getLogger(__name__)


@dataclass
class StrategyScore:
    strategy_key: str
    label: str
    score: int                    # 0-100
    best_trade: Optional[dict]    # top-scoring candidate for this strategy
    signal_summary: str           # brief human-readable summary
    metric_scores: dict           # individual metric values for transparency


# ─── Utilities ──────────────────────────────────────────────────────────────

def _normalize(values: list, higher_is_better: bool = True) -> list:
    """Min-max normalize a list of floats to 0-1."""
    if not values:
        return []
    mn, mx = min(values), max(values)
    rng = mx - mn
    if rng == 0:
        return [0.5] * len(values)
    if higher_is_better:
        return [(v - mn) / rng for v in values]
    return [(mx - v) / rng for v in values]


def _dte_from_expiration(expiration: str) -> int:
    """Calculate DTE from YYYY-MM-DD string."""
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        return max(0, (exp_date - date.today()).days)
    except (ValueError, TypeError):
        return 0


def _get_atm_iv(contracts: list, underlying_price: float) -> float:
    """
    Estimate ATM IV from the closest call options.
    Returns annualized IV as a decimal (0.25 = 25%). Defaults to 0.30 if unavailable.
    """
    if not contracts or underlying_price <= 0:
        return 0.30

    calls = [c for c in contracts if c.get("option_type") == "call"]
    if not calls:
        return 0.30

    calls_sorted = sorted(calls, key=lambda c: abs(c.get("strike", 0) - underlying_price))
    ivs = []
    for c in calls_sorted[:5]:
        iv = c.get("implied_volatility", 0) or 0
        if iv > 0:
            ivs.append(iv)
    return sum(ivs) / len(ivs) if ivs else 0.30


# ─── Cushion Penalty ──────────────────────────────────────────────────────────

def cushion_penalty(trade: dict, current_price: float) -> tuple:
    """
    Deterministic scoring penalty for thin short strike cushion.

    cushion_pct = |current_price - short_strike| / current_price * 100

    Penalties:
    - cushion_pct < 1.0%: -20 points
    - cushion_pct < 2.0%: -10 points
    - cushion_pct >= 2.0%: 0 (no penalty)

    Only applies to trades with a short strike (credit spreads).
    Returns (penalty: int, cushion_pct: float).

    # TODO: Phase 2.4.x — when ATR(14) is available, add flag:
    # "Insufficient buffer — one average daily move breaches short strike"
    # when cushion < 1.0 × ATR(14). This is a flag, not a gate.
    """
    short_strike = trade.get("short_strike") or trade.get("sell_strike")
    if short_strike is None or current_price is None or current_price == 0:
        return 0, 0.0

    pct = abs(current_price - short_strike) / current_price * 100

    if pct < 1.0:
        return -20, pct
    elif pct < 2.0:
        return -10, pct
    return 0, pct


# ─── Credit Spread Scorer ─────────────────────────────────────────────────────

def _score_credit_spread_strategy(
    strategy_key: str,
    contracts: list,
    underlying_price: float,
    user_config: dict,
    atm_iv: float,
) -> StrategyScore:
    """
    Score a credit spread strategy (steady-paycheck or weekly-grind).

    Uses VerticalSpreadEngine with bull_put + bear_call spread types.
    Filters candidates by strategy DTE range, then re-scores using the
    strategy's own scoring_weights from strategy_definitions.py.

    NOTE: theta_gamma_ratio (weekly-grind) uses net_theta/max_loss as a proxy
    since gamma is not exposed per-spread in VerticalSpreadEngine.
    """
    strategy = STRATEGIES[strategy_key]
    cfg = user_config or {}
    weights = strategy.scoring_weights

    dte_min = int(cfg.get("dte_min", strategy.dte_min))
    dte_max = int(cfg.get("dte_max", strategy.dte_max))
    delta_max = float(cfg.get("delta_max", 0.30))

    # Relaxed liquidity filters — we want candidates even in low-volume symbols
    filters = SpreadFilters(
        spread_types=["bull_put", "bear_call"],
        min_short_delta=0.05,
        max_short_delta=delta_max,
        min_volume=1,
        min_open_interest=10,
        min_reward_risk=0.10,
        min_ev_threshold=-999.0,  # allow all EV to avoid filtering out valid spreads
    )
    engine = VerticalSpreadEngine(filters=filters)
    result = engine.analyze(contracts, underlying_price)
    spreads = result.get("spreads", [])

    # Filter to strategy DTE window
    spreads = [
        s for s in spreads
        if dte_min <= _dte_from_expiration(s.get("expiration", "")) <= dte_max
    ]

    if not spreads:
        return StrategyScore(
            strategy_key=strategy_key,
            label=strategy.label,
            score=0,
            best_trade=None,
            signal_summary=f"No credit spreads found in {dte_min}-{dte_max} DTE range",
            metric_scores={},
        )

    # ── Metric extractors — keyed to match scoring_weights ────────────────
    def theta_margin_ratio(s):
        """Net theta collected per dollar of max loss."""
        ml = s.get("max_loss", 0)
        return abs(s.get("net_theta", 0)) / ml if ml > 0 else 0

    def theta_gamma_ratio(s):
        """
        Proxy: theta efficiency per dollar at risk.
        True theta/gamma ratio requires per-contract gamma which is not in ScoredSpread.
        This proxy correctly differentiates spreads by theta collection efficiency.
        """
        ml = s.get("max_loss", 0)
        return abs(s.get("net_theta", 0)) / ml if ml > 0 else 0

    def credit_width_pct(s):
        """Credit received as % of spread width — measures premium quality."""
        credit = abs(s.get("net_debit", 0))  # net_debit is stored negative for credits
        width = s.get("spread_width", 1)
        return (credit / width * 100) if width > 0 else 0

    def liquidity_metric(s):
        """Combined volume + OI across both legs."""
        return (
            s.get("long_volume", 0) + s.get("short_volume", 0) +
            s.get("long_oi", 0) + s.get("short_oi", 0)
        )

    metric_fns = {
        "theta_margin_ratio":    theta_margin_ratio,
        "theta_gamma_ratio":     theta_gamma_ratio,
        "probability_of_profit": lambda s: s.get("prob_of_profit", 0),
        "expected_value":        lambda s: s.get("ev_raw", 0),
        "reward_risk":           lambda s: s.get("reward_risk_ratio", 0),
        "credit_width_pct":      credit_width_pct,
        "liquidity":             liquidity_metric,
    }

    # Compute raw values for all relevant metrics
    raw = {k: [metric_fns[k](s) for s in spreads] for k in weights if k in metric_fns}

    # iv_rank is externally supplied — use ATM IV as proxy, normalized 0-1
    iv_rank_norm = min(1.0, max(0.0, atm_iv / 0.60)) if atm_iv > 0 else 0.5

    # Normalize each metric across candidates
    norm = {k: _normalize(raw[k], higher_is_better=True) for k in raw}

    # Composite score per candidate
    composite_scores = []
    for i in range(len(spreads)):
        cs = 0.0
        for k, w in weights.items():
            if k == "iv_rank":
                cs += iv_rank_norm * w
            elif k in norm:
                cs += norm[k][i] * w
            # else: unknown metric, skip (weight effectively 0)
        composite_scores.append(cs)

    best_idx = composite_scores.index(max(composite_scores))
    best = spreads[best_idx]
    best_score = composite_scores[best_idx]
    score = min(100, max(0, round(best_score * 100)))

    # Apply cushion penalty (post-scoring adjustment)
    _cushion_penalty, _cushion_pct = cushion_penalty(best, underlying_price)
    if _cushion_penalty != 0:
        score = max(0, score + _cushion_penalty)

    best_metrics = {k: round(float(metric_fns[k](best)), 4) for k in weights if k in metric_fns}
    if "iv_rank" in weights:
        best_metrics["iv_rank"] = round(iv_rank_norm, 4)

    # Always include cushion metrics for transparency
    best_metrics["cushion_pct"] = round(_cushion_pct, 2)
    if _cushion_penalty != 0:
        best_metrics["cushion_penalty"] = _cushion_penalty

    signal_summary = (
        f"{len(spreads)} credit spreads in range. "
        f"Best: {best.get('spread_type', '').replace('_', ' ').title()} "
        f"short {best.get('short_strike', '')} | "
        f"exp {best.get('expiration', '')[:7]} | "
        f"PoP {best.get('prob_of_profit', 0):.0%} | "
        f"R:R {best.get('reward_risk_ratio', 0):.2f}"
    )

    return StrategyScore(
        strategy_key=strategy_key,
        label=strategy.label,
        score=score,
        best_trade=best,
        signal_summary=signal_summary,
        metric_scores=best_metrics,
    )


# ─── Long Option Scorer ───────────────────────────────────────────────────────

def _score_long_option_strategy(
    strategy_key: str,
    contracts: list,
    underlying_price: float,
    user_config: dict,
    atm_iv: float,
) -> StrategyScore:
    """
    Score a long option strategy (trend-rider or lottery-ticket).

    Uses LongCallEngine (NakedOptionEngine) with strategy-specific DTE/delta filters.
    Re-scores candidates using the strategy's own scoring_weights.
    """
    strategy = STRATEGIES[strategy_key]
    cfg = user_config or {}
    weights = strategy.scoring_weights

    dte_min = int(cfg.get("dte_min", strategy.dte_min))
    dte_max = int(cfg.get("dte_max", strategy.dte_max))
    delta_min = float(cfg.get("delta_min", 0.05))
    delta_max = float(cfg.get("delta_max", 0.85))

    filters = LongCallFilters(
        min_delta=delta_min,
        max_delta=delta_max,
        min_days_to_exp=dte_min,
        max_days_to_exp=dte_max,
        max_premium=cfg.get("max_cost_per_contract", 10000.0),
        min_volume=1,
        min_open_interest=10,
        max_bid_ask_spread_pct=0.50,
        option_types=["call"],
    )
    engine = LongCallEngine(filters=filters)
    result = engine.analyze(contracts, underlying_price)
    options = result.get("options", [])

    if not options:
        return StrategyScore(
            strategy_key=strategy_key,
            label=strategy.label,
            score=0,
            best_trade=None,
            signal_summary=f"No long call candidates in {dte_min}-{dte_max} DTE range",
            metric_scores={},
        )

    # SMA alignment: client-supplied in user_config; defaults to neutral 0.5
    sma_score = float(cfg.get("sma_alignment_score", 0.5))

    # Delta sweet-spot targets per strategy
    if strategy_key == "trend-rider":
        delta_center = (float(cfg.get("delta_min", 0.50)) + float(cfg.get("delta_max", 0.70))) / 2
        delta_half_range = max(0.10, (float(cfg.get("delta_max", 0.70)) - float(cfg.get("delta_min", 0.50))) / 2)
    else:
        delta_center = 0.10
        delta_half_range = 0.10

    def delta_quality(o):
        """How well delta hits the strategy's target range."""
        d = o.get("delta", 0)
        return max(0.0, 1.0 - abs(d - delta_center) / (delta_half_range + 0.05))

    def delta_otm_score(o):
        """Lottery ticket: lower delta = more OTM = higher score."""
        d = o.get("delta", 0)
        return max(0.0, 1.0 - d / 0.25)

    def payout_ratio(o):
        """
        Estimated payout multiple on a 10% underlying move.
        payout = (delta × underlying_price × 0.10 × 100) / premium_dollars
        """
        cost = o.get("premium_dollars", 0)
        if cost <= 0:
            return 0.0
        return (o.get("delta", 0) * underlying_price * 0.10 * 100) / cost

    def bid_ask_tightness(o):
        """Lower bid-ask spread % = better fill quality."""
        ba_pct = o.get("bid_ask_spread_pct", 100)
        return max(0.0, 1.0 - ba_pct / 100.0)

    def iv_percentile_cost(o):
        """Lower IV = cheaper options for buyers. IV stored as % in engine output."""
        iv_pct = o.get("iv", 100)
        iv_decimal = iv_pct / 100 if iv_pct > 1 else iv_pct
        return max(0.0, 1.0 - iv_decimal / 1.0)

    def runway_score(o):
        """More theta runway days = more time for thesis to play out."""
        return float(o.get("theta_runway_days", 0))

    def expected_value(o):
        """
        Simple EV proxy: expected gain on a 5% move minus cost.
        EV = delta × underlying × 0.05 - mid_price
        """
        mid = o.get("mid_price", 0)
        return o.get("delta", 0) * underlying_price * 0.05 - mid

    def open_interest_metric(o):
        return float(o.get("open_interest", 0))

    metric_fns = {
        "sma_alignment_score": lambda o: sma_score,
        "delta_quality":        delta_quality,
        "expected_value":       expected_value,
        "iv_percentile_cost":   iv_percentile_cost,
        "runway_score":         runway_score,
        "payout_ratio":         payout_ratio,
        "delta_otm_score":      delta_otm_score,
        "bid_ask_tightness":    bid_ask_tightness,
        "open_interest":        open_interest_metric,
    }

    raw = {k: [metric_fns[k](o) for o in options] for k in weights if k in metric_fns}
    norm = {k: _normalize(raw[k], higher_is_better=True) for k in raw}

    composite_scores = []
    for i in range(len(options)):
        cs = sum(norm[k][i] * weights[k] for k in norm)
        composite_scores.append(cs)

    best_idx = composite_scores.index(max(composite_scores))
    best = options[best_idx]
    best_score = composite_scores[best_idx]
    score = min(100, max(0, round(best_score * 100)))

    best_metrics = {k: round(float(metric_fns[k](best)), 4) for k in weights if k in metric_fns}

    signal_summary = (
        f"{len(options)} call candidates found. "
        f"Best: {best.get('option_type', 'call').title()} {best.get('strike', '')} @ "
        f"exp {best.get('expiration', '')[:7]} | "
        f"Δ {best.get('delta', 0):.2f} | "
        f"Premium {best.get('premium_dollars', 0):.0f}"
    )

    return StrategyScore(
        strategy_key=strategy_key,
        label=strategy.label,
        score=score,
        best_trade=best,
        signal_summary=signal_summary,
        metric_scores=best_metrics,
    )


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def score_all_strategies(
    symbol: str,
    provider,
    user_config: dict = None,
) -> List[StrategyScore]:
    """
    Fetch options chain ONCE, run all four strategy scoring functions,
    return normalized 0-100 scores for each strategy.

    CRITICAL: exactly one provider.get_chain() call regardless of strategy count.
    This is enforced by design — chain is fetched here and passed down.

    user_config keys (all optional):
        dte_min, dte_max, delta_min, delta_max — override strategy defaults
        sma_alignment_score — float 0-1, for trend-rider (from frontend SMA data)
        iv_rank_proxy — float 0-100, explicit IV rank if available
    """
    cfg = user_config or {}

    # Single chain fetch — wide range to cover all strategies (lottery 1d to trend-rider 65d)
    try:
        chain_data = await provider.get_chain(
            symbol=symbol.upper(),
            min_dte=0,
            max_dte=70,
            strike_range_pct=20.0,
        )
    except Exception as e:
        log.warning(f"Chain fetch failed for {symbol}: {e}")
        return [
            StrategyScore(
                strategy_key=k,
                label=s.label,
                score=0,
                best_trade=None,
                signal_summary="Chain fetch failed",
                metric_scores={},
            )
            for k, s in STRATEGIES.items()
        ], 0.0

    contracts = chain_data.get("contracts", [])
    underlying_price = chain_data.get("underlying_price", 0)

    if not contracts or underlying_price <= 0:
        return [
            StrategyScore(
                strategy_key=k,
                label=s.label,
                score=0,
                best_trade=None,
                signal_summary="No chain data available",
                metric_scores={},
            )
            for k, s in STRATEGIES.items()
        ], 0.0

    # ATM IV estimate from chain — used as iv_rank proxy for credit strategies
    atm_iv = _get_atm_iv(contracts, underlying_price)

    # Run all four scorers against the same contracts list
    scores = [
        _score_credit_spread_strategy(
            "steady-paycheck", contracts, underlying_price, cfg, atm_iv
        ),
        _score_credit_spread_strategy(
            "weekly-grind", contracts, underlying_price, cfg, atm_iv
        ),
        _score_long_option_strategy(
            "trend-rider", contracts, underlying_price, cfg, atm_iv
        ),
        _score_long_option_strategy(
            "lottery-ticket", contracts, underlying_price, cfg, atm_iv
        ),
    ]

    return scores, underlying_price
