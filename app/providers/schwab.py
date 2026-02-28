"""
Schwab API adapter for market data.

This is the Schwab equivalent of providers/tradier.py. It implements the
same MarketDataProvider interface, so the analysis engines don't know
(or care) which provider supplied the data.

KEY DIFFERENCES FROM TRADIER:
  1. Authentication: OAuth tokens (managed by SchwabTokenManager) vs API key
  2. Chain structure: Nested callExpDateMap/putExpDateMap keyed by "expDate:DTE"
     then by strike, vs Tradier's flat list
  3. Greeks: Top-level on each contract (not nested in a "greeks" sub-object)
  4. IV format: Schwab returns volatility as percentage (29.24),
     engines expect decimal (0.2924) — we divide by 100
  5. Quote endpoint: GET /marketdata/v1/{symbol}/quotes vs Tradier's format

API docs: https://developer.schwab.com
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)

# Schwab API base URL for market data
SCHWAB_MARKET_DATA_URL = "https://api.schwabapi.com/marketdata/v1"


class SchwabMarketData(MarketDataProvider):
    """
    Fetches quotes and option chains from Schwab's API.

    Translates Schwab's response format into the standard OptionContract
    format that the analysis engines use.

    WHY token_manager (not a raw token): Unlike Tradier where the API key
    never changes, Schwab's access tokens expire every 30 minutes. The
    token_manager handles all the refresh logic, so this adapter just
    calls `await self._token_manager.get_access_token()` before each request
    and always gets a valid token.
    """

    def __init__(self, token_manager):
        """
        Args:
            token_manager: SchwabTokenManager instance that provides
                          valid access tokens with auto-refresh.
        """
        self._token_manager = token_manager
        self._client = httpx.AsyncClient(
            base_url=SCHWAB_MARKET_DATA_URL,
            timeout=30.0,
        )

    async def _get_headers(self) -> dict:
        """
        Build request headers with a valid Bearer token.

        Called before every API request. The token manager handles
        refresh automatically — we just ask for a token and it
        returns a valid one (or raises if re-auth needed).
        """
        token = await self._token_manager.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # MarketDataProvider interface methods
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> dict:
        """
        GET /marketdata/v1/{symbol}/quotes?fields=quote,reference

        Returns normalized Quote dict matching the same shape as Tradier's.

        WHY fields=quote,reference: Schwab's quote endpoint can return
        different "root nodes" of data. We only need the quote data
        (prices, volume) and reference data (description). Requesting
        fewer fields = faster response.
        """
        headers = await self._get_headers()

        resp = await self._client.get(
            f"/{symbol}/quotes",
            headers=headers,
            params={"fields": "quote,fundamental"},
        )
        resp.raise_for_status()
        data = resp.json()

        # Schwab wraps the response with the symbol as key
        # e.g., {"TSLA": {"assetMainType": "EQUITY", "quote": {...}}}
        symbol_data = data.get(symbol.upper(), {})
        quote = symbol_data.get("quote", {})

        fundamental = symbol_data.get("fundamental", {})
        total_volume = quote.get("totalVolume", 0) or 0
        avg_volume = fundamental.get("avg1YearVolume", 0) or 0
        volume_ratio = round(total_volume / avg_volume, 2) if avg_volume > 0 else None

        return {
            "symbol": symbol_data.get("symbol", symbol.upper()),
            "price": quote.get("lastPrice", 0),
            "change": quote.get("netChange", 0),
            "change_pct": quote.get("netPercentChange", 0),
            "volume": total_volume,
            "day_high": quote.get("highPrice", 0),
            "day_low": quote.get("lowPrice", 0),
            "previous_close": quote.get("closePrice", 0),
            "week_52_high": quote.get("52WeekHigh"),
            "week_52_low": quote.get("52WeekLow"),
            "avg_volume": avg_volume if avg_volume > 0 else None,
            "volume_ratio": volume_ratio,
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
        GET /marketdata/v1/chains

        Fetches the option chain and normalizes Schwab's nested structure
        into the flat list of contracts that the analysis engines expect.

        SCHWAB'S RESPONSE STRUCTURE:
          {
            "symbol": "MSFT",
            "underlyingPrice": 420.50,
            "callExpDateMap": {
              "2026-03-20:21": {    ← "expDate:DTE" as the key
                "415.0": [          ← strike price as string key
                  { contract data } ← array (usually 1 element)
                ],
                "420.0": [{ ... }],
              },
              "2026-04-17:49": { ... }
            },
            "putExpDateMap": { same structure }
          }

        OUR NORMALIZED OUTPUT:
          A flat list of contract dicts, each in the standard format
          that vertical_engine, long_call_engine, etc. expect.

        WHY strategy=SINGLE: Schwab supports strategy=VERTICAL which returns
        pre-paired spreads, but our engines pair spreads themselves (they need
        individual contracts to evaluate all possible combinations). SINGLE
        gives us the raw building blocks.
        """
        headers = await self._get_headers()

        # Get current price first
        quote = await self.get_quote(symbol)
        current_price = quote["price"]

        # Map our option_type to Schwab's contractType parameter
        contract_type = "ALL"
        if option_type == "call":
            contract_type = "CALL"
        elif option_type == "put":
            contract_type = "PUT"

        params = {
            "symbol": symbol.upper(),
            "contractType": contract_type,
            "strategy": "SINGLE",
            "range": "ALL",
            "includeUnderlyingQuote": "true",
        }

        # Add date range filters if specified
        # WHY fromDate/toDate: Schwab can filter expirations server-side,
        # which is more efficient than fetching everything and filtering.
        if min_dte > 0 or max_dte < 365:
            today = datetime.now().date()
            from_date = today + timedelta(days=min_dte)
            to_date = today + timedelta(days=max_dte)
            params["fromDate"] = from_date.isoformat()
            params["toDate"] = to_date.isoformat()

        resp = await self._client.get(
            "/chains",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        # Use Schwab's underlying price if available (more accurate than quote)
        underlying_price = data.get("underlyingPrice", current_price)

        # Calculate strike range for filtering
        strike_low = underlying_price * (1 - strike_range_pct / 100)
        strike_high = underlying_price * (1 + strike_range_pct / 100)

        # Normalize all contracts from the nested structure
        all_contracts = []
        expirations_seen = set()

        # Process calls
        call_map = data.get("callExpDateMap", {})
        self._process_exp_date_map(
            exp_date_map=call_map,
            underlying=symbol.upper(),
            underlying_price=underlying_price,
            option_type_str="call",
            strike_low=strike_low,
            strike_high=strike_high,
            min_dte=min_dte,
            max_dte=max_dte,
            out_contracts=all_contracts,
            out_expirations=expirations_seen,
        )

        # Process puts
        put_map = data.get("putExpDateMap", {})
        self._process_exp_date_map(
            exp_date_map=put_map,
            underlying=symbol.upper(),
            underlying_price=underlying_price,
            option_type_str="put",
            strike_low=strike_low,
            strike_high=strike_high,
            min_dte=min_dte,
            max_dte=max_dte,
            out_contracts=all_contracts,
            out_expirations=expirations_seen,
        )

        # Get ALL available expirations (not just the filtered ones)
        # for the expirations_available field
        all_expirations = set()
        for exp_key in list(call_map.keys()) + list(put_map.keys()):
            exp_date = exp_key.split(":")[0]  # "2026-03-20:21" → "2026-03-20"
            all_expirations.add(exp_date)

        logger.info(
            f"Schwab chain for {symbol}: {len(all_contracts)} contracts, "
            f"{len(expirations_seen)} filtered expirations"
        )

        return {
            "underlying": symbol.upper(),
            "underlying_price": underlying_price,
            "contracts": all_contracts,
            "expirations_available": sorted(all_expirations),
            "fetched_at": datetime.now(timezone.utc),
            "provider": "schwab",
        }

    async def get_expirations(self, symbol: str) -> list[str]:
        """
        Get available expiration dates for a symbol.

        WHY a separate call: Sometimes the UI just needs the list of
        available dates (e.g., for a dropdown) without fetching the
        entire chain. Schwab's chain endpoint with a narrow strike
        range gives us the expiration keys efficiently.
        """
        headers = await self._get_headers()

        params = {
            "symbol": symbol.upper(),
            "contractType": "CALL",
            "strategy": "SINGLE",
            "strikeCount": 1,  # Minimize data — we only want dates
        }

        resp = await self._client.get(
            "/chains",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        expirations = set()
        for exp_key in data.get("callExpDateMap", {}).keys():
            # Keys are "2026-03-20:21" — extract the date part
            exp_date = exp_key.split(":")[0]
            expirations.add(exp_date)

        return sorted(expirations)

    async def get_strikes(self, symbol: str, expiration: str) -> list[float]:
        """
        Get available strike prices for a specific expiration.

        WHY: The UI might need strike options for a dropdown after
        the user picks an expiration date.
        """
        headers = await self._get_headers()

        params = {
            "symbol": symbol.upper(),
            "contractType": "ALL",
            "strategy": "SINGLE",
            "fromDate": expiration,
            "toDate": expiration,
        }

        resp = await self._client.get(
            "/chains",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        strikes = set()
        for exp_key, strike_map in data.get("callExpDateMap", {}).items():
            for strike_str in strike_map.keys():
                try:
                    strikes.add(float(strike_str))
                except ValueError:
                    pass

        return sorted(strikes)

    async def health_check(self) -> bool:
        """
        Test if the Schwab connection is working.

        Tries to fetch a quote for SPY (highly liquid, always available).
        If it works, the connection is healthy.
        """
        try:
            quote = await self.get_quote("SPY")
            return quote.get("price", 0) > 0
        except Exception as e:
            logger.warning(f"Schwab health check failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_exp_date_map(
        self,
        exp_date_map: dict,
        underlying: str,
        underlying_price: float,
        option_type_str: str,
        strike_low: float,
        strike_high: float,
        min_dte: int,
        max_dte: int,
        out_contracts: list,
        out_expirations: set,
    ):
        """
        Walk Schwab's nested expiration→strike→contract structure and
        normalize each contract into our standard format.

        SCHWAB NESTING:
          callExpDateMap (or putExpDateMap)
            └── "2026-03-20:21"          ← expiration date : DTE
                └── "420.0"              ← strike price (string)
                    └── [ {contract} ]   ← array of contracts (usually 1)

        WHY this structure: Schwab groups contracts by expiration date,
        then by strike. This is efficient for their API but different from
        Tradier's flat list. We flatten it all into a single list because
        our engines iterate over all contracts to find the best combinations.
        """
        for exp_dte_key, strikes_map in exp_date_map.items():
            # Parse "2026-03-20:21" → date and DTE
            parts = exp_dte_key.split(":")
            exp_date_str = parts[0]

            # Calculate DTE ourselves (more reliable than parsing Schwab's)
            try:
                exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                dte = (exp_date - datetime.now().date()).days
            except (ValueError, TypeError):
                continue

            # Filter by DTE range
            if dte < min_dte or dte > max_dte:
                continue

            out_expirations.add(exp_date_str)

            # Iterate strikes
            for strike_str, contract_list in strikes_map.items():
                try:
                    strike = float(strike_str)
                except ValueError:
                    continue

                # Filter by strike range
                if strike < strike_low or strike > strike_high:
                    continue

                # Each strike has an array of contracts (usually just 1)
                for raw in contract_list:
                    contract = self._normalize_contract(
                        raw, underlying, underlying_price,
                        exp_date_str, dte, option_type_str,
                    )
                    out_contracts.append(contract)

    def _normalize_contract(
        self,
        raw: dict,
        underlying: str,
        underlying_price: float,
        expiration: str,
        dte: int,
        option_type: str,
    ) -> dict:
        """
        Convert a single Schwab contract into our normalized format.

        This is where the adapter pattern earns its keep. Schwab calls it
        "totalVolume", Tradier calls it "volume". Schwab puts greeks at
        the top level, Tradier nests them. This method handles all of that.

        CRITICAL CONVERSIONS:
          - volatility: Schwab gives 29.24 (percentage), we store 0.2924 (decimal)
          - mid: Schwab calls it "mark", but we calculate (bid+ask)/2 to be consistent
          - option_type: Schwab gives "CALL"/"PUT", we store "call"/"put"
        """
        bid = raw.get("bid", 0) or 0
        ask = raw.get("ask", 0) or 0
        mid = round((bid + ask) / 2, 4) if (bid + ask) > 0 else 0

        # IMPORTANT: Schwab returns volatility as percentage (29.24)
        # Our engines expect implied_volatility as decimal (0.2924)
        raw_vol = raw.get("volatility")
        implied_volatility = None
        if raw_vol is not None and raw_vol != -999.0:
            # Schwab uses -999.0 as a sentinel for "not available"
            implied_volatility = round(raw_vol / 100, 6)

        # Greeks are top-level in Schwab (not nested like Tradier)
        # Schwab uses -999.0 for unavailable greeks
        def safe_greek(value):
            if value is None or value == -999.0:
                return None
            return value

        return {
            "symbol": raw.get("symbol", ""),
            "underlying": underlying,
            "expiration": expiration,
            "dte": dte,
            "strike": raw.get("strikePrice", 0),
            "option_type": option_type,  # Already lowercase from caller
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "last": raw.get("last", None),
            "volume": raw.get("totalVolume", 0) or 0,
            "open_interest": raw.get("openInterest", 0) or 0,
            "implied_volatility": implied_volatility,
            "delta": safe_greek(raw.get("delta")),
            "gamma": safe_greek(raw.get("gamma")),
            "theta": safe_greek(raw.get("theta")),
            "vega": safe_greek(raw.get("vega")),
            "rho": safe_greek(raw.get("rho")),
        }

    async def close(self):
        """Clean up the HTTP client."""
        await self._client.aclose()
