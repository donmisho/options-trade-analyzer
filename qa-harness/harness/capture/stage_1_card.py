"""
Stage 1 — Security Strategies card scan.

Endpoint: POST /api/v1/analyze/scorecard
Captures: per-strategy scores, best_trade, SMA alignment, quote data.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, Any, List

from harness.config import DEV_API_BASE, STRATEGY_KEYS
from harness.auth import get_auth_headers


def capture(symbol: str) -> Dict[str, Any]:
    """Call scorecard endpoint and return structured Stage 1 capture."""
    url = f"{DEV_API_BASE}/api/v1/analyze/scorecard"
    payload = {"symbol": symbol}
    headers = {"Content-Type": "application/json", **get_auth_headers()}

    ts = datetime.now(timezone.utc).isoformat()
    warnings = []
    errors = []

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
    except requests.RequestException as e:
        return {
            "captured_at_utc": ts,
            "inputs": {"symbol": symbol},
            "outputs": {},
            "warnings": [],
            "errors": [{"stage": "stage_1_card", "error": str(e)}],
        }

    if resp.status_code != 200:
        return {
            "captured_at_utc": ts,
            "inputs": {"symbol": symbol},
            "outputs": {},
            "warnings": [],
            "errors": [{"stage": "stage_1_card", "http_status": resp.status_code, "body": resp.text[:500]}],
        }

    data = resp.json()

    # Extract inputs
    sma = data.get("sma_signal") or {}
    quote = data.get("quote") or {}
    inputs = {
        "symbol": symbol,
        "capture_timestamp_utc": ts,
        "underlying_price": data.get("underlying_price"),
        "sma_8": sma.get("sma_8"),
        "sma_21": sma.get("sma_21"),
        "sma_50": sma.get("sma_50"),
        "sma_alignment": sma.get("alignment"),
        "sma_summary": sma.get("summary"),
        "quote_price": quote.get("price"),
        "quote_change": quote.get("change"),
        "quote_change_pct": quote.get("change_pct"),
        "quote_volume": quote.get("volume"),
        "quote_rel_volume": quote.get("rel_volume"),
        "quote_description": quote.get("description"),
    }

    # Extract per-strategy outputs
    strategies_raw = data.get("strategies") or []
    strategy_outputs = {}
    for s in strategies_raw:
        key = s.get("strategy_key")
        strategy_outputs[key] = {
            "strategy_key": key,
            "label": s.get("label"),
            "score": s.get("score"),
            "reason": s.get("reason"),
            "signal_summary": s.get("signal_summary"),
            "metric_scores": s.get("metric_scores"),
            "best_trade": s.get("best_trade"),  # verbatim — full candidate object
        }

    # Derive "no compatible setups" list (strategies where score is null or 0 with reason)
    no_setups = [
        key for key, v in strategy_outputs.items()
        if v["score"] is None or (v["score"] == 0 and v.get("reason"))
    ]

    return {
        "captured_at_utc": ts,
        "inputs": inputs,
        "outputs": {
            "strategies": strategy_outputs,
            "no_compatible_setups": no_setups,
        },
        "raw_response": data,  # verbatim for debugging
        "warnings": warnings,
        "errors": errors,
    }
