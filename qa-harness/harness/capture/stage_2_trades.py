"""
Stage 2 — Trades page candidate list.

Calls BOTH /analyze/verticals AND /analyze/long-calls, merges results.
Applies candidate bounds before capture.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, Any, List

from harness.config import DEV_API_BASE, ENGINE_TO_STRUCTURE
from harness.auth import get_auth_headers
from harness.filters.candidate_bounds import filter_verticals, filter_long_options


def _natural_key_vertical(spread: Dict[str, Any], symbol: str) -> str:
    """Deterministic key for cross-run matching of vertical spreads."""
    strikes = sorted([spread.get("long_strike", 0), spread.get("short_strike", 0)])
    return f"{symbol}|{spread.get('spread_type', 'UNK')}|{strikes[0]}|{strikes[1]}|{spread.get('expiration', '')}"


def _natural_key_option(opt: Dict[str, Any], symbol: str) -> str:
    """Deterministic key for cross-run matching of single options."""
    return f"{symbol}|{opt.get('option_type', 'UNK')}|{opt.get('strike', 0)}|{opt.get('expiration', '')}"


def _fetch_verticals(symbol: str, headers: dict) -> Dict[str, Any]:
    """Fetch vertical spread candidates."""
    url = f"{DEV_API_BASE}/api/v1/analyze/verticals"
    payload = {
        "symbol": symbol,
        "spread_types": ["bull_call", "bear_put", "bull_put", "bear_call"],
        "max_results": 50,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        if resp.status_code != 200:
            return {"spreads": [], "error": {"http_status": resp.status_code, "body": resp.text[:500]}}
        data = resp.json()
        return {"spreads": data.get("spreads") or [], "total_valid": data.get("total_valid"), "raw": data}
    except requests.RequestException as e:
        return {"spreads": [], "error": {"exception": str(e)}}


def _fetch_long_options(symbol: str, headers: dict) -> Dict[str, Any]:
    """Fetch long call/put candidates."""
    url = f"{DEV_API_BASE}/api/v1/analyze/long-calls"
    payload = {
        "symbol": symbol,
        "option_types": ["call", "put"],
        "max_results": 30,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        if resp.status_code != 200:
            return {"options": [], "error": {"http_status": resp.status_code, "body": resp.text[:500]}}
        data = resp.json()
        # Response may use "calls", "puts", or "options" key
        options = data.get("options") or data.get("calls") or data.get("puts") or []
        return {"options": options, "total_valid": data.get("total_valid"), "raw": data}
    except requests.RequestException as e:
        return {"options": [], "error": {"exception": str(e)}}


def capture(symbol: str, underlying_price: float) -> Dict[str, Any]:
    """Call both scan endpoints, apply bounds, return structured Stage 2 capture."""
    ts = datetime.now(timezone.utc).isoformat()
    headers = {"Content-Type": "application/json", **get_auth_headers()}
    warnings = []
    errors = []

    # Fetch verticals
    vert_result = _fetch_verticals(symbol, headers)
    if "error" in vert_result:
        errors.append({"stage": "stage_2_verticals", **vert_result["error"]})
    raw_verticals = vert_result["spreads"]

    # Fetch long options
    long_result = _fetch_long_options(symbol, headers)
    if "error" in long_result:
        errors.append({"stage": "stage_2_long_options", **long_result["error"]})
    raw_options = long_result["options"]

    # Apply bounds
    filtered_verticals = filter_verticals(raw_verticals, underlying_price)
    filtered_options = filter_long_options(raw_options, underlying_price)

    # Annotate each candidate with natural_key and normalized structure
    vertical_rows = []
    for s in filtered_verticals:
        nk = _natural_key_vertical(s, symbol)
        structure = ENGINE_TO_STRUCTURE.get(s.get("spread_type"), s.get("spread_type"))
        vertical_rows.append({
            **s,
            "natural_key": nk,
            "structure": structure,
            "candidate_type": "vertical",
        })

    option_rows = []
    for o in filtered_options:
        nk = _natural_key_option(o, symbol)
        structure = ENGINE_TO_STRUCTURE.get(o.get("option_type"), o.get("option_type"))
        option_rows.append({
            **o,
            "natural_key": nk,
            "structure": structure,
            "candidate_type": "long_option",
        })

    all_candidates = vertical_rows + option_rows

    return {
        "captured_at_utc": ts,
        "candidates": all_candidates,
        "counts": {
            "raw_verticals": len(raw_verticals),
            "filtered_verticals": len(filtered_verticals),
            "raw_long_options": len(raw_options),
            "filtered_long_options": len(filtered_options),
            "total_after_bounds": len(all_candidates),
        },
        "raw_verticals_response": vert_result.get("raw"),
        "raw_long_options_response": long_result.get("raw"),
        "warnings": warnings,
        "errors": errors,
    }
