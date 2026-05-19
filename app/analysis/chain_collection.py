"""
options_chain_snapshots daily collection.
Triggered by the scheduler or on-demand via POST /api/v1/market/collect-chains.
OTA-200
"""

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import OptionsChainSnapshot
from app.services.symbol_normalization import canonicalize
from app.services.symbol_cache import to_api_symbol_cached

log = logging.getLogger(__name__)


async def collect_chain_snapshot(symbol: str, db_session: AsyncSession, factory) -> dict:
    """
    Fetch current options chain for symbol via the configured provider and write
    one snapshot row. Skips if a snapshot already exists for today (idempotent).

    Returns: { symbol, snapshot_date, contract_count, status: "inserted"|"skipped"|"error" }
    """
    today = date.today()

    # Skip if already collected today
    existing = await db_session.execute(
        select(OptionsChainSnapshot)
        .where(OptionsChainSnapshot.symbol == symbol)
        .where(OptionsChainSnapshot.snapshot_date == today)
    )
    if existing.scalar_one_or_none():
        return {"symbol": symbol, "snapshot_date": str(today), "status": "skipped"}

    # Resolve provider (Schwab if connected, else configured default)
    from app.core.config import settings
    token_mgr = getattr(factory, "_schwab_token_manager", None)
    if token_mgr and token_mgr.get_status().get("connected"):
        provider = factory.get_market_data("schwab")
    else:
        provider = factory.get_market_data(settings.default_market_data_provider)

    try:
        api_sym = to_api_symbol_cached(symbol, "schwab")
        chain_data = await provider.get_chain(api_sym, min_dte=0, max_dte=70, strike_range_pct=20)
    except Exception as exc:
        log.error("chain_collection: provider error for %s: %s", symbol, exc)
        return {"symbol": symbol, "snapshot_date": str(today), "status": "error", "error": str(exc)}

    contracts = chain_data.get("contracts", [])
    underlying_price = chain_data.get("underlying_price", 0.0)
    dtes = [c.get("dte", 0) for c in contracts if c.get("dte") is not None]

    snapshot = OptionsChainSnapshot(
        symbol=canonicalize(symbol),
        snapshot_date=today,
        captured_at=datetime.now(timezone.utc),
        underlying_price=underlying_price,
        chain_json=json.dumps(chain_data, default=str),
        contract_count=len(contracts),
        dte_min=min(dtes) if dtes else None,
        dte_max=max(dtes) if dtes else None,
        provider=chain_data.get("provider", "schwab"),
    )
    db_session.add(snapshot)
    await db_session.commit()

    return {
        "symbol": symbol,
        "snapshot_date": str(today),
        "contract_count": len(contracts),
        "status": "inserted",
    }
