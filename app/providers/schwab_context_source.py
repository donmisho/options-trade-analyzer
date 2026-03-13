"""
Schwab price context source — Phase 3.5 Stream A3.

Implements ContextSource for equity price + market data from Schwab.
Wraps the existing SchwabMarketData provider so no duplicate HTTP logic.

WHY this exists: The Position Monitor Agent needs current price data to
evaluate position health. Rather than calling Schwab directly from the
agent, it reads from ContextStore, which calls this source only when
the cached signal is stale (TTL = 5 minutes during market hours).

Signal shape (signal_value JSON):
    price           float   — last trade price
    change          float   — price change vs previous close
    change_pct      float   — change as percentage
    volume          int     — today's volume
    day_high        float
    day_low         float
    previous_close  float
    volume_ratio    float | null   — today vs 1-year average
    next_earnings_date  str | null — YYYY-MM-DD
"""

import logging
from typing import TYPE_CHECKING

from app.providers.base import ContextSource

if TYPE_CHECKING:
    from app.providers.schwab import SchwabMarketData

logger = logging.getLogger(__name__)


class SchwabPriceContextSource(ContextSource):
    """
    PRICE signal source backed by SchwabMarketData.get_quote().

    Inject the live SchwabMarketData instance at construction time so
    this source shares the same authenticated HTTP client as the rest
    of the app — no second OAuth flow, no second token.
    """

    def __init__(self, provider: "SchwabMarketData"):
        self._provider = provider

    @property
    def source_id(self) -> str:
        return "schwab_quotes"

    @property
    def signal_type(self) -> str:
        return "PRICE"

    def ttl_seconds(self) -> int:
        return 300  # 5 minutes — enough freshness for post-close monitoring

    async def fetch(self, symbol: str) -> dict:
        """Delegate to the existing Schwab adapter — returns normalized Quote dict."""
        return await self._provider.get_quote(symbol)

    def normalize(self, raw: dict) -> dict:
        """
        Map from SchwabMarketData.get_quote() output to a stable signal shape.

        The quote dict is already normalized by the Schwab adapter, so this is
        mostly a field selection + explicit null handling step.
        """
        return {
            "price":              raw.get("price", 0),
            "change":             raw.get("change", 0),
            "change_pct":         raw.get("change_pct", 0),
            "volume":             raw.get("volume", 0),
            "day_high":           raw.get("day_high", 0),
            "day_low":            raw.get("day_low", 0),
            "previous_close":     raw.get("previous_close", 0),
            "volume_ratio":       raw.get("volume_ratio"),
            "next_earnings_date": raw.get("next_earnings_date"),
        }
