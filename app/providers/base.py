"""
Abstract provider interfaces.

WHY: These are the "contracts" that every data source must implement.
The analysis engine and API endpoints talk to these interfaces, never to
Schwab directly. Adding a new provider means writing one class
that implements these methods — zero changes anywhere else.

The Adapter Pattern in action:
  - MarketDataProvider defines what any chain data source must do
  - SchwabMarketData (in providers/schwab.py) implements it for Schwab
  - The API endpoint calls provider.get_chain() — doesn't know or care which
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class ContextSignal:
    """
    A single normalized signal from one source for one symbol.

    Produced by ContextSource.normalize() and written to symbol_context
    by ContextStore. The ttl_seconds field drives the expires_at timestamp.
    """
    source_id: str
    signal_type: str    # PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS
    symbol: str
    value: dict         # normalized signal data — shape defined by the source
    ttl_seconds: int    # how long this signal stays fresh before re-fetching


class ContextSource(ABC):
    """
    Plug-in interface for any signal source the Position Monitor Agent can use.

    WHY: The agent reads from this interface, not from Schwab or any specific
    provider. Adding social sentiment, fundamentals, or a second brokerage
    means writing one new ContextSource subclass — zero changes to the agent.

    Register new sources in ProviderRegistry so the agent picks them up
    automatically on the next run.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier, e.g. 'schwab_quotes', 'social_sentiment'."""
        ...

    @property
    @abstractmethod
    def signal_type(self) -> str:
        """One of: PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS"""
        ...

    @abstractmethod
    async def fetch(self, symbol: str) -> dict:
        """Fetch raw data for the symbol from this source."""
        ...

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """
        Normalize raw data into a stable signal_value JSON blob.

        The shape returned here must not change without a migration — downstream
        consumers (the Position Monitor prompt, health grade logic) depend on it.
        """
        ...

    @abstractmethod
    def ttl_seconds(self) -> int:
        """How long a cached signal from this source stays fresh."""
        ...

    async def fetch_and_normalize(self, symbol: str) -> ContextSignal:
        """Convenience: fetch + normalize in one call."""
        raw = await self.fetch(symbol)
        return ContextSignal(
            source_id=self.source_id,
            signal_type=self.signal_type,
            symbol=symbol,
            value=self.normalize(raw),
            ttl_seconds=self.ttl_seconds(),
        )


class MarketDataProvider(ABC):
    """
    Any source of options market data implements this interface.

    Today: Schwab
    Tomorrow: Interactive Brokers, CBOE, CSV import, whatever
    """

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict:
        """Get current price data for an underlying symbol."""
        ...

    @abstractmethod
    async def get_chain(
        self,
        symbol: str,
        min_dte: int = 0,
        max_dte: int = 90,
        strike_range_pct: float = 10.0,
        option_type: Optional[str] = None,  # "call", "put", or None for both
    ) -> dict:
        """
        Fetch and filter an options chain.

        Returns a dict with:
            underlying_price: float
            contracts: list of normalized contract dicts
            expirations_available: list of date strings
            fetched_at: datetime
            provider: str (e.g. "schwab")
        """
        ...

    @abstractmethod
    async def get_expirations(self, symbol: str) -> list[str]:
        """Get available expiration dates for a symbol."""
        ...

    @abstractmethod
    async def get_strikes(self, symbol: str, expiration: str) -> list[float]:
        """Get available strike prices for a specific expiration."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Test if the provider connection is working."""
        ...


