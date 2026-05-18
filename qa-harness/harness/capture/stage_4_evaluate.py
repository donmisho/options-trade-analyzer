"""
Stage 4 — Claude (Foundry) evaluation.

Endpoint: POST /api/v1/evaluate/structured
Samples top N candidates per strategy section, sends to Foundry.
Records both the request payload and response verbatim.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from harness.config import (
    DEV_API_BASE,
    EVALUATE_TOP_N_PER_STRATEGY,
    STRATEGY_KEYS,
    ENGINE_TO_STRUCTURE,
)
from harness.auth import get_auth_headers


def _group_by_strategy(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group candidates by their fitting strategies. A candidate may appear in multiple groups."""
    groups: Dict[str, List[Dict[str, Any]]] = {k: [] for k in STRATEGY_KEYS}
    for c in candidates:
        fitting = c.get("fitting_strategies") or []
        for strat in fitting:
            if strat in groups:
                groups[strat].append(c)
    return groups


def _top_n(candidates: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """Return top N candidates by composite_score."""
    scored = sorted(candidates, key=lambda c: c.get("composite_score") or 0, reverse=True)
    return scored[:n]


def _build_eval_payload(
    symbol: str,
    candidate: Dict[str, Any],
    strategy_key: str,
    stage1_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the structured evaluation request payload."""
    inputs = stage1_data.get("inputs", {})
    sma_alignment = {
        "sma_8": inputs.get("sma_8"),
        "sma_21": inputs.get("sma_21"),
        "sma_50": inputs.get("sma_50"),
        "alignment": inputs.get("sma_alignment"),
    }

    # Build trade dict from candidate
    trade = {}
    if candidate.get("candidate_type") == "vertical":
        trade = {
            "spread_type": candidate.get("spread_type"),
            "structure": candidate.get("structure"),
            "long_strike": candidate.get("long_strike"),
            "short_strike": candidate.get("short_strike"),
            "option_type": candidate.get("option_type"),
            "expiration": candidate.get("expiration"),
            "net_debit": candidate.get("net_debit"),
            "max_profit": candidate.get("max_profit"),
            "max_loss": candidate.get("max_loss"),
            "breakeven": candidate.get("breakeven"),
            "spread_width": candidate.get("spread_width"),
            "prob_of_profit": candidate.get("prob_of_profit"),
            "ev_raw": candidate.get("ev_raw"),
            "net_delta": candidate.get("net_delta"),
            "net_theta": candidate.get("net_theta"),
            "iv": candidate.get("iv"),
        }
    else:
        trade = {
            "option_type": candidate.get("option_type"),
            "structure": candidate.get("structure"),
            "strike": candidate.get("strike"),
            "expiration": candidate.get("expiration"),
            "bid": candidate.get("bid"),
            "ask": candidate.get("ask"),
            "mid_price": candidate.get("mid_price"),
            "delta": candidate.get("delta"),
            "iv": candidate.get("iv"),
        }

    # Score from candidate
    scores = {strategy_key: candidate.get("composite_score")}

    return {
        "symbol": symbol,
        "current_price": inputs.get("underlying_price"),
        "iv": candidate.get("iv") or 0.0,
        "sma_alignment": sma_alignment,
        "strategy_keys": [strategy_key],
        "scores": scores,
        "trade": trade,
        "trade_key": candidate.get("trade_key"),
    }


def _call_evaluate(payload: Dict[str, Any], headers: dict) -> Dict[str, Any]:
    """Call the structured evaluation endpoint."""
    url = f"{DEV_API_BASE}/api/v1/evaluate/structured"
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        if resp.status_code != 200:
            return {
                "success": False,
                "http_status": resp.status_code,
                "body": resp.text[:1000],
            }
        return {
            "success": True,
            "http_status": resp.status_code,
            "data": resp.json(),
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "exception": str(e),
        }


def capture(
    symbol: str,
    candidates: List[Dict[str, Any]],
    stage1_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate top N candidates per strategy. Return structured capture."""
    ts = datetime.now(timezone.utc).isoformat()
    headers = {"Content-Type": "application/json", **get_auth_headers()}
    warnings = []
    errors = []

    grouped = _group_by_strategy(candidates)
    evaluations = {}
    eval_count = 0
    error_count = 0

    for strat_key in STRATEGY_KEYS:
        strat_candidates = grouped.get(strat_key, [])
        top = _top_n(strat_candidates, EVALUATE_TOP_N_PER_STRATEGY)

        for candidate in top:
            nk = candidate.get("natural_key", candidate.get("trade_key", "unknown"))
            eval_key = f"{strat_key}|{nk}"

            payload = _build_eval_payload(symbol, candidate, strat_key, stage1_data)

            result = _call_evaluate(payload, headers)
            eval_count += 1

            if not result.get("success"):
                error_count += 1
                errors.append({
                    "stage": "stage_4_evaluate",
                    "eval_key": eval_key,
                    "strategy": strat_key,
                    "natural_key": nk,
                    **{k: v for k, v in result.items() if k != "success"},
                })
                evaluations[eval_key] = {
                    "strategy_key": strat_key,
                    "natural_key": nk,
                    "trade_key": candidate.get("trade_key"),
                    "request_payload": payload,
                    "response": None,
                    "error": result,
                }
            else:
                resp_data = result.get("data", {})
                evaluations[eval_key] = {
                    "strategy_key": strat_key,
                    "natural_key": nk,
                    "trade_key": candidate.get("trade_key"),
                    "request_payload": payload,
                    "response": resp_data,
                }

    return {
        "captured_at_utc": ts,
        "per_evaluation": evaluations,
        "counts": {
            "total_evaluated": eval_count,
            "errors": error_count,
            "by_strategy": {
                k: len(_top_n(grouped.get(k, []), EVALUATE_TOP_N_PER_STRATEGY))
                for k in STRATEGY_KEYS
            },
        },
        "warnings": warnings,
        "errors": errors,
    }
