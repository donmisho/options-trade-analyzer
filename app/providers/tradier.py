"""
Tradier API adapter for market data.

This is where the Adapter Pattern does its work. Tradier returns data in
Tradier's format. This class translates it into the standard format that
the analysis engine expects. If Tradier changes their API, only this file
needs to change.

API docs: https://documentation.tradier.com/brokerage-api
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)

# Tradier base URLs by environment
TRADIER_URLS = {
    "sandbox": "https://sandbox.tradier.com",
    "production": "https://api.tradier.com",
}


class TradierMarketData(MarketDataProvider):
    """
    Fetches quotes and option chains from Tradier's API.
    
    Translates Tradier's response format into the standard OptionContract
    format that the analysis engine uses.
    """

    def __init__(self, token: str, environment: str = "sandbox"):
        self.token = token
        self.environment = environment
        self.base_url = TRADIER_URLS.get(environment, TRADIER_URLS["sandbox"])
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def get_quote(self, symbol: str) -> dict:
        """
        GET /v1/markets/quotes?symbols={symbol}
        
        Returns normalized Quote dict.
        """
        resp = await self._client.get(
            "/v1/markets/quotes",
            params={"symbols": symbol, "greeks": "false"},
        )
        resp.raise_for_status()
        data = resp.json()

        # Tradier wraps single quotes differently than multiple
        quotes = data.get("quotes", {})
        quote = quotes.get("quote", {})
        if isinstance(quote, list):
            quote = quote[0]

        return {
            "symbol": quote.get("symbol", symbol),
            "price": quote.get("last", 0),
            "change": quote.get("change", 0),
            "change_pct": quote.get("change_percentage", 0),
            "volume": quote.get("volume", 0),
            "day_high": quote.get("high", 0),
            "day_low": quote.get("low", 0),
            "previous_close": quote.get("prevclose", 0),
            "week_52_high": quote.get("week_52_high"),
            "week_52_low": quote.get("week_52_low"),
            "avg_volume": quote.get("average_volume"),
            "volume_ratio": (
                round(quote.get("volume", 0) / quote.get("average_volume", 1), 2)
                if quote.get("average_volume", 0) > 0 else None
            ),
            "timestamp": datetime.now(timezone.utc),
        }

    async def get_chain(
        self,
        symbol: str,
        min_dte: int = 0,
        max_dte: int = 90,
        strike_range_pct: float = 10.0,
        option_type: Optional[str] = None,
    ) -> dict:
        """
        GET /v1/markets/options/chains
        
        Fetches the full chain, then filters by DTE and strike range.
        Returns normalized contracts in the standard format.
        
        WHY filter client-side: Tradier's API filters by single expiration
        only. To get multiple expirations within a DTE range, we fetch all
        and filter. Chain data is small enough that this is fast.
        """
        # Get current price first (needed for strike range filtering)
        quote = await self.get_quote(symbol)
        current_price = quote["price"]

        # Get available expirations
        expirations = await self.get_expirations(symbol)

        # Filter expirations by DTE range
        today = datetime.now().date()
        valid_expirations = []
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if min_dte <= dte <= max_dte:
                valid_expirations.append(exp_str)

        if not valid_expirations:
            return {
                "underlying": symbol,
                "underlying_price": current_price,
                "contracts": [],
                "expirations_available": expirations,
                "fetched_at": datetime.now(timezone.utc),
                "provider": "tradier",
            }

        # Fetch chain for each valid expiration
        all_contracts = []
        for expiration in valid_expirations:
            params = {
                "symbol": symbol,
                "expiration": expiration,
                "greeks": "true",
            }
            if option_type:
                params["optionType"] = option_type

            resp = await self._client.get(
                "/v1/markets/options/chains", params=params
            )
            resp.raise_for_status()
            data = resp.json()

            options = data.get("options", {})
            if options is None:
                continue
            raw_contracts = options.get("option", [])
            if isinstance(raw_contracts, dict):
                raw_contracts = [raw_contracts]

            # Normalize each contract and filter by strike range
            strike_low = current_price * (1 - strike_range_pct / 100)
            strike_high = current_price * (1 + strike_range_pct / 100)

            for raw in raw_contracts:
                strike = raw.get("strike", 0)
                if not (strike_low <= strike <= strike_high):
                    continue

                # Apply liquidity filters
                volume = raw.get("volume", 0) or 0
                oi = raw.get("open_interest", 0) or 0

                contract = self._normalize_contract(raw, symbol, current_price)
                all_contracts.append(contract)

        return {
            "underlying": symbol,
            "underlying_price": current_price,
            "contracts": all_contracts,
            "expirations_available": expirations,
            "fetched_at": datetime.now(timezone.utc),
            "provider": "tradier",
        }

    async def get_expirations(self, symbol: str) -> list[str]:
        """
        GET /v1/markets/options/expirations
        
        Returns list of date strings: ["2026-03-20", "2026-03-27", ...]
        """
        resp = await self._client.get(
            "/v1/markets/options/expirations",
            params={"symbol": symbol, "includeAllRoots": "true"},
        )
        resp.raise_for_status()
        data = resp.json()

        expirations = data.get("expirations", {})
        if expirations is None:
            return []
        dates = expirations.get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        return dates

    async def get_strikes(self, symbol: str, expiration: str) -> list[float]:
        """
        GET /v1/markets/options/strikes
        
        Returns list of available strike prices for a specific expiration.
        """
        resp = await self._client.get(
            "/v1/markets/options/strikes",
            params={"symbol": symbol, "expiration": expiration},
        )
        resp.raise_for_status()
        data = resp.json()

        strikes = data.get("strikes", {})
        if strikes is None:
            return []
        strike_list = strikes.get("strike", [])
        if isinstance(strike_list, (int, float)):
            strike_list = [strike_list]
        return [float(s) for s in strike_list]

    async def health_check(self) -> bool:
        """Test connection by fetching market clock."""
        try:
            resp = await self._client.get("/v1/markets/clock")
            return resp.status_code == 200
        except Exception:
            return False

    async def get_daily_close(self, symbol: str, date: str) -> Optional[float]:
        """
        GET /v1/markets/history — returns the closing price on a specific date.

        Used for YTD return calculations. `date` is YYYY-MM-DD.
        Returns None if the market was closed or data is unavailable.
        """
        resp = await self._client.get(
            "/v1/markets/history",
            params={"symbol": symbol, "interval": "daily", "start": date, "end": date},
        )
        resp.raise_for_status()
        data = resp.json()

        history = data.get("history")
        if not history or history == "null":
            return None
        day = history.get("day")
        if isinstance(day, list):
            day = day[0] if day else None
        if not day:
            return None
        return day.get("close")

    # ------------------------------------------------------------------
    # Private: normalization
    # ------------------------------------------------------------------

    def _normalize_contract(
        self, raw: dict, underlying: str, underlying_price: float
    ) -> dict:
        """
        Translate Tradier's contract format → standard OptionContract format.
        
        This is where the adapter pattern earns its keep. Tradier calls it
        "open_interest", Schwab might call it "openInterest", IBKR might
        call it "oi". This method normalizes them all to the same shape.
        """
        exp_str = raw.get("expiration_date", "")
        today = datetime.now().date()
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
        except (ValueError, TypeError):
            dte = 0

        bid = raw.get("bid", 0) or 0
        ask = raw.get("ask", 0) or 0
        mid = round((bid + ask) / 2, 2) if (bid + ask) > 0 else 0

        # Greeks come nested in Tradier's response
        greeks = raw.get("greeks", {}) or {}

        return {
            "symbol": raw.get("symbol", ""),
            "underlying": underlying,
            "expiration": exp_str,
            "dte": dte,
            "strike": raw.get("strike", 0),
            "option_type": raw.get("option_type", "").lower(),  # "call" or "put"
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "last": raw.get("last", None),
            "volume": raw.get("volume", 0) or 0,
            "open_interest": raw.get("open_interest", 0) or 0,
            "implied_volatility": greeks.get("mid_iv", None),
            "delta": greeks.get("delta", None),
            "gamma": greeks.get("gamma", None),
            "theta": greeks.get("theta", None),
            "vega": greeks.get("vega", None),
            "rho": greeks.get("rho", None),
        }

    async def close(self):
        """Clean up the HTTP client."""
        await self._client.aclose()
