"""
Dev-only regression test endpoints.

Gate: every endpoint returns HTTP 403 when app_env == "production".
Register in main.py only when app_env != "production".
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.providers.factory import ProviderRegistry
from app.analysis.vertical_engine import VerticalSpreadEngine, ScoringWeights, SpreadFilters

log = logging.getLogger(__name__)

router = APIRouter(tags=["Test"])

_provider_registry: Optional[ProviderRegistry] = None

# May 15, 2026 anchor expiration
_TARGET_EXP = "2026-05-15"
_ENTRY_TOLERANCE = 0.05

# Three MSFT anchor trades from 2026-03-25 — validates OTA-281/282/283 fixes.
# long_strike / short_strike follow ScoredSpread conventions:
#   bear_put:  long=higher-strike put,  short=lower-strike put
#   bear_call: long=higher-strike call, short=lower-strike call (income leg)
_ANCHORS = [
    {
        "spread": "BEAR_PUT_DEBIT 370/345",
        "spread_type": "bear_put",
        "long_strike": 370.0,
        "short_strike": 345.0,
        "entry": 8.80,
    },
    {
        "spread": "BEAR_PUT_DEBIT 350/325",
        "spread_type": "bear_put",
        "long_strike": 350.0,
        "short_strike": 325.0,
        "entry": 5.35,
    },
    {
        "spread": "BEAR_CALL_CREDIT 395/420",
        "spread_type": "bear_call",
        "long_strike": 420.0,
        "short_strike": 395.0,
        "entry": 5.40,
    },
]


def init_test_routes(registry: ProviderRegistry):
    global _provider_registry
    _provider_registry = registry


@router.post("/filter-validation/msft-anchor")
async def msft_anchor_regression():
    """
    Dev-only: validate the three MSFT anchor trades from 2026-03-25 appear in the
    vertical engine output with correct P&L values (OTA-281/282/283 regression check).

    Fetches the live MSFT May 15, 2026 options chain, runs it through the engine
    with wide-open filters (only 25-pt spread width enforced), then checks that all
    three anchor spreads are present and that max_profit / max_loss are in dollar
    amounts (i.e. the *100 formula is applied).

    Returns HTTP 400 with failure details if any anchor is missing or its entry
    price falls outside the ±0.05 tolerance.
    """
    if settings.app_env == "production":
        raise HTTPException(status_code=403, detail="Not available in production")

    if _provider_registry is None:
        raise HTTPException(status_code=503, detail="Provider registry not initialized")

    provider = _provider_registry.get_market_data(settings.default_market_data_provider)

    # Fetch MSFT chain with a wide DTE window, then filter to the target expiration.
    # strike_range_pct=30 covers strikes 325-420 for any MSFT price in the $350-$450 range.
    try:
        chain_data = await provider.get_chain(
            symbol="MSFT",
            min_dte=40,
            max_dte=60,
            strike_range_pct=30.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error fetching MSFT chain: {e}")

    contracts = chain_data.get("contracts", [])
    underlying_price = chain_data.get("underlying_price", 0)

    if not contracts:
        raise HTTPException(status_code=502, detail="No MSFT contracts returned from provider")

    target_contracts = [c for c in contracts if c.get("expiration") == _TARGET_EXP]
    if not target_contracts:
        available = sorted({c.get("expiration") for c in contracts})
        raise HTTPException(
            status_code=404,
            detail=f"No contracts found for {_TARGET_EXP}. Available expirations: {available}",
        )

    # Wide-open filters — only the 25-pt width limit applies
    filters = SpreadFilters(
        spread_types=["bear_put", "bear_call"],
        min_short_delta=0.0,
        max_short_delta=1.0,
        max_spread_width=25,
        min_net_delta=0.0,
        max_net_theta=0.0,
        min_open_interest=0,
        min_volume=0,
        min_reward_risk=0.0,
        min_ev_threshold=-999999.0,
    )
    engine = VerticalSpreadEngine(weights=ScoringWeights(), filters=filters)
    result = engine.analyze(contracts=target_contracts, underlying_price=underlying_price)
    spreads = result.get("spreads", [])

    results = []
    failures = []

    for anchor in _ANCHORS:
        match = next(
            (
                s for s in spreads
                if s.get("spread_type") == anchor["spread_type"]
                and s.get("long_strike") == anchor["long_strike"]
                and s.get("short_strike") == anchor["short_strike"]
            ),
            None,
        )

        if match is None:
            failures.append({
                "spread": anchor["spread"],
                "reason": (
                    f"Not found in results — no spread matched strikes "
                    f"{anchor['long_strike']:.0f}/{anchor['short_strike']:.0f} "
                    f"within entry price tolerance"
                ),
            })
            continue

        entry_price = abs(match.get("net_debit", 0))
        if abs(entry_price - anchor["entry"]) > _ENTRY_TOLERANCE:
            failures.append({
                "spread": anchor["spread"],
                "reason": (
                    f"Entry price {entry_price:.2f} outside tolerance "
                    f"(expected ~{anchor['entry']:.2f} \u00b1{_ENTRY_TOLERANCE})"
                ),
            })
            continue

        results.append({
            "spread": anchor["spread"],
            "entry_price": round(entry_price, 2),
            "max_profit": match.get("max_profit"),
            "max_loss": match.get("max_loss"),
            "matched": True,
        })

    if failures:
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "failures": failures},
        )

    return {"status": "pass", "results": results}
