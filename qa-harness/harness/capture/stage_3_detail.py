"""
Stage 3 — Trade detail extraction.

Per Phase 1 finding #2: detail is embedded inline in Stage 2 responses.
No separate API call needed. This module extracts and reshapes the detail
fields from each candidate for the capture contract.
"""

from typing import Dict, Any, List


def _extract_vertical_detail(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Extract detail fields from a vertical spread candidate."""
    return {
        "trade_key": candidate.get("trade_key"),
        "natural_key": candidate.get("natural_key"),
        "structure": candidate.get("structure"),
        "spread_type": candidate.get("spread_type"),
        "long_strike": candidate.get("long_strike"),
        "short_strike": candidate.get("short_strike"),
        "option_type": candidate.get("option_type"),
        "expiration": candidate.get("expiration"),
        "dte": candidate.get("dte"),
        "entry_price": candidate.get("net_debit"),
        "max_profit": candidate.get("max_profit"),
        "max_loss": candidate.get("max_loss"),
        "breakeven": candidate.get("breakeven"),
        "spread_width": candidate.get("spread_width"),
        "reward_risk_ratio": candidate.get("reward_risk_ratio"),
        "prob_of_profit": candidate.get("prob_of_profit"),
        "ev_raw": candidate.get("ev_raw"),
        "composite_score": candidate.get("composite_score"),
        "net_delta": candidate.get("net_delta"),
        "net_theta": candidate.get("net_theta"),
        "net_vega": candidate.get("net_vega"),
        "iv": candidate.get("iv"),
        "long_volume": candidate.get("long_volume"),
        "long_oi": candidate.get("long_oi"),
        "short_volume": candidate.get("short_volume"),
        "short_oi": candidate.get("short_oi"),
        "fitting_strategies": candidate.get("fitting_strategies"),
        "score_breakdown": candidate.get("score_breakdown"),
        "required_move_pct": candidate.get("required_move_pct"),
    }


def _extract_option_detail(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Extract detail fields from a long option candidate."""
    return {
        "trade_key": candidate.get("trade_key"),
        "natural_key": candidate.get("natural_key"),
        "structure": candidate.get("structure"),
        "option_type": candidate.get("option_type"),
        "strike": candidate.get("strike"),
        "expiration": candidate.get("expiration"),
        "dte": candidate.get("days_to_exp") or candidate.get("dte"),
        "bid": candidate.get("bid"),
        "ask": candidate.get("ask"),
        "mid_price": candidate.get("mid_price"),
        "delta": candidate.get("delta"),
        "theta_per_day_dollars": candidate.get("theta_per_day_dollars"),
        "iv": candidate.get("iv"),
        "volume": candidate.get("volume"),
        "open_interest": candidate.get("open_interest"),
        "breakeven": candidate.get("breakeven"),
        "composite_score": candidate.get("composite_score"),
        "delta_score": candidate.get("delta_score"),
        "theta_score": candidate.get("theta_score"),
        "iv_score": candidate.get("iv_score"),
        "rr_score": candidate.get("rr_score"),
        "liquidity_score": candidate.get("liquidity_score"),
        "fitting_strategies": candidate.get("fitting_strategies"),
    }


def capture(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract detail from Stage 2 candidates. No API call."""
    details = {}
    for c in candidates:
        nk = c.get("natural_key", c.get("trade_key", "unknown"))
        if c.get("candidate_type") == "vertical":
            details[nk] = _extract_vertical_detail(c)
        else:
            details[nk] = _extract_option_detail(c)

    return {
        "per_candidate": details,
        "count": len(details),
        "warnings": [],
        "errors": [],
    }
