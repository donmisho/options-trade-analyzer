"""
Schwab account activity adapter (OTA-855).

The Trader API side of Schwab: account numbers, transactions and orders, plus
the two Market Data calls the fill-context capture needs (multi-symbol quotes
and daily candles). It shares the SchwabTokenManager with SchwabMarketData, so
there is one OAuth login and one refresh loop for the whole app.

WHY a second adapter rather than more methods on SchwabMarketData: market data
and account activity are different capabilities with different lifecycles
(the Schwab developer app must have the "Accounts and Trading" product enabled
for the Trader API calls to work at all). Keeping them apart lets the registry
describe each one on its own and keeps the market-data adapter free of account
concerns.

API notes (schwab-py's reading of the Trader API, confirmed against the
developer portal where it is public):
  - GET /trader/v1/accounts/accountNumbers → [{accountNumber, hashValue}]
  - GET /trader/v1/accounts/{hash}/transactions?startDate&endDate&types
        dates are ISO-8601 UTC; startDate must be within 60 days of today
  - GET /trader/v1/accounts/{hash}/orders?fromEnteredTime&toEnteredTime&maxResults&status
  - GET /marketdata/v1/quotes?symbols=A,B&fields=quote
        option symbols use the OCC layout: root padded to 6, yymmdd, C|P, strike×1000 as 8 digits
  - GET /marketdata/v1/pricehistory?symbol&periodType=month&period&frequencyType=daily&frequency=1
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from app.providers.base import AccountActivityProvider

logger = logging.getLogger(__name__)

SCHWAB_API_URL = "https://api.schwabapi.com"

# The Trader API refuses a transactions startDate older than this many days.
TRANSACTIONS_LOOKBACK_DAYS = 60


def iso_utc(moment: datetime) -> str:
    """Format a datetime the way the Trader API wants its date parameters (UTC, millisecond Z)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def option_symbol(root: str, expiration: date, put_call: str, strike: float) -> str:
    """Build a Schwab/OCC option symbol: 'SPY   261024C00580000'."""
    letter = "C" if put_call.upper().startswith("C") else "P"
    return f"{root.upper():<6}{expiration.strftime('%y%m%d')}{letter}{int(round(float(strike) * 1000)):08d}"


class SchwabAccountActivity(AccountActivityProvider):
    """
    Trader API reads for the account activity poller.

    Every call asks the token manager for a valid access token first, exactly
    as SchwabMarketData does, so refresh and re-auth live in one place.
    """

    def __init__(self, token_manager):
        self._token_manager = token_manager
        self._client = httpx.AsyncClient(base_url=SCHWAB_API_URL, timeout=30.0)

    async def _headers(self) -> dict:
        token = await self._token_manager.get_access_token()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def _get(self, path: str, params: Optional[dict] = None):
        resp = await self._client.get(path, headers=await self._headers(), params=params)
        if resp.status_code in (401, 403):
            # The Trader API answers 401/403 when the developer app lacks the Accounts and
            # Trading product, even with a valid market-data token. Say so plainly.
            raise PermissionError(
                f"Schwab Trader API refused {path} ({resp.status_code}). The developer app needs "
                "the 'Accounts and Trading Production' product enabled and a fresh login."
            )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # AccountActivityProvider interface
    # ------------------------------------------------------------------

    async def get_account_numbers(self) -> list[dict]:
        """[{accountNumber, hashValue}] for every account the login can see."""
        data = await self._get("/trader/v1/accounts/accountNumbers")
        return data if isinstance(data, list) else []

    async def get_transactions(
        self,
        account_hash: str,
        start: datetime,
        end: datetime,
        types: str = "TRADE",
        symbol: Optional[str] = None,
    ) -> list[dict]:
        """Transactions of the given types in [start, end], as Schwab returns them."""
        floor = datetime.now(timezone.utc) - timedelta(days=TRANSACTIONS_LOOKBACK_DAYS - 1)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start < floor:
            start = floor
        params = {"startDate": iso_utc(start), "endDate": iso_utc(end), "types": types}
        if symbol:
            params["symbol"] = symbol
        data = await self._get(f"/trader/v1/accounts/{account_hash}/transactions", params)
        return data if isinstance(data, list) else []

    async def get_orders(
        self,
        account_hash: str,
        start: datetime,
        end: datetime,
        max_results: int = 3000,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Orders entered in [start, end] for one account, with their child strategies."""
        params = {"fromEnteredTime": iso_utc(start), "toEnteredTime": iso_utc(end), "maxResults": max_results}
        if status:
            params["status"] = status
        data = await self._get(f"/trader/v1/accounts/{account_hash}/orders", params)
        return data if isinstance(data, list) else []

    async def get_quotes(self, symbols: list[str]) -> dict:
        """{symbol: {quote: {...}, reference: {...}}} for underlyings and option symbols alike."""
        if not symbols:
            return {}
        out: dict = {}
        # Schwab accepts long symbol lists; keep requests comfortably sized anyway.
        for i in range(0, len(symbols), 50):
            chunk = symbols[i:i + 50]
            data = await self._get("/marketdata/v1/quotes", {"symbols": ",".join(chunk), "fields": "quote,reference"})
            if isinstance(data, dict):
                out.update(data)
        return out

    async def get_daily_candles(self, symbol: str, months: int = 3) -> list[dict]:
        """Daily OHLC candles, oldest first: [{open, high, low, close, volume, datetime}]."""
        data = await self._get("/marketdata/v1/pricehistory", {
            "symbol": symbol.upper(), "periodType": "month", "period": str(months),
            "frequencyType": "daily", "frequency": "1",
        })
        candles = data.get("candles", []) if isinstance(data, dict) else []
        return [c for c in candles if all(k in c for k in ("open", "high", "low", "close"))]

    async def health_check(self) -> bool:
        try:
            return bool(await self.get_account_numbers())
        except Exception as e:
            logger.warning(f"Schwab account activity health check failed: {e}")
            return False

    async def close(self):
        await self._client.aclose()
