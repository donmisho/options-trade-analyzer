"""
Abstract provider interfaces.

WHY: These are the "contracts" that every data source must implement.
The analysis engine and API endpoints talk to these interfaces, never to
Tradier or Schwab directly. Adding a new provider means writing one class
that implements these methods — zero changes anywhere else.

The Adapter Pattern in action:
  - MarketDataProvider defines what any chain data source must do
  - TradierMarketData (in providers/tradier.py) implements it for Tradier
  - SchwabMarketData (in providers/schwab.py) implements it for Schwab
  - The API endpoint calls provider.get_chain() — doesn't know or care which
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime


class MarketDataProvider(ABC):
    """
    Any source of options market data implements this interface.
    
    Today: Tradier, Schwab
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
            provider: str (e.g. "tradier")
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


class AccountProvider(ABC):
    """
    Any source of brokerage account data implements this interface.
    
    Each user connects their own brokerage account. The provider reads
    their positions, balances, and history using their personal API tokens.
    """

    @abstractmethod
    async def get_positions(self, account_id: str) -> list[dict]:
        """Get current holdings with cost basis."""
        ...

    @abstractmethod
    async def get_balances(self, account_id: str) -> dict:
        """Get cash, buying power, margin info."""
        ...

    @abstractmethod
    async def get_orders(self, account_id: str) -> list[dict]:
        """Get open and recent orders."""
        ...

    @abstractmethod
    async def get_gain_loss(self, account_id: str) -> list[dict]:
        """Get realized P/L on closed positions."""
        ...

    @abstractmethod
    async def get_history(self, account_id: str) -> list[dict]:
        """Get account activity history."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Test if the provider connection is working."""
        ...


class TradingProvider(ABC):
    """
    Any broker that can execute trades implements this interface.
    
    Kept separate from AccountProvider because trading is high-risk.
    You enable it deliberately, and it always requires per-trade MFA.
    """

    @abstractmethod
    async def preview_order(self, account_id: str, order: dict) -> dict:
        """Dry-run: show estimated fills and commissions without executing."""
        ...

    @abstractmethod
    async def place_order(self, account_id: str, order: dict) -> dict:
        """Execute a trade. Returns order confirmation with broker order ID."""
        ...

    @abstractmethod
    async def cancel_order(self, account_id: str, order_id: str) -> bool:
        """Cancel a pending order."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Test if the provider connection is working."""
        ...
