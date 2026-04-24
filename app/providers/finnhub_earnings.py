"""
Finnhub EarningsCalendarProvider — Phase 3.5 / OTA-508.

Implements ContextSource for earnings calendar data from Finnhub.io.
This is the interim adapter until Polygon.io replaces it in Phase 3.3.

WHY Finnhub: Schwab's fundamentals endpoint does not reliably return
nextEarningsDate (inherited stripped TDA shape). OTA-502 (earnings-in-window
hard gate) requires a dependable earnings source. Finnhub's free tier covers
the 90-day forward window we need.

signal_value payload shape:
    {
        "next_earnings_date": "YYYY-MM-DD" | None,   # soonest event in window
        "time_of_day":        "bmo" | "amc" | "dmh" | None,
        "eps_estimate":       float | None,
        "quarter":            int | None,
        "fetched_at":         "YYYY-MM-DDTHH:MM:SSZ",
        "meta": {
            "notes": None | "finnhub_no_data" | "finnhub_rate_limited"
                           | "finnhub_5xx" | "finnhub_timeout"
        }
    }

Consumers (OTA-502): call ContextStore.refresh_if_stale(symbol, source)
where source is FinnhubEarningsSource(). next_earnings_date=None means
"unknown — do not gate on earnings."
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from app.providers.base import ContextSource, ContextSignal

logger = logging.getLogger(__name__)

# Finnhub API base URL
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Key Vault secret name (note: vault has one-'n' typo — "finhub-api-key")
# Do not rename the vault secret without updating this constant.
FINNHUB_SECRET_NAME = "finhub-api-key"

# How many days forward to search for an earnings event
FINNHUB_WINDOW_DAYS = 90


class FinnhubEarningsSource(ContextSource):
    """
    FUNDAMENTAL signal source backed by Finnhub's earnings calendar API.

    Fetches the next scheduled earnings event for a symbol within a 90-day
    forward window. Returns a normalized ContextSignal with next_earnings_date
    and supporting metadata.

    Fail-soft: on any API error, returns next_earnings_date=None with a
    meta.notes reason code so OTA-502 can treat it as "unknown" rather than
    crashing the scoring pipeline.

    signal_value payload shape — see module docstring above.
    """

    def __init__(self):
        self._api_key: Optional[str] = None  # cached after first Key Vault fetch

    @property
    def source_id(self) -> str:
        return "finnhub_earnings"

    @property
    def signal_type(self) -> str:
        return "FUNDAMENTAL"

    def ttl_seconds(self) -> int:
        return 86400  # 24 hours — earnings dates don't change intraday

    async def _get_api_key(self) -> str:
        """
        Async load of the Finnhub API key from Azure Key Vault.

        Uses azure.identity.aio and azure.keyvault.secrets.aio exclusively —
        never the sync variants. Caches key in-instance after first fetch.
        WHY: sync Azure identity in async handlers caused the BFF identity
        production outage; we are not repeating that failure mode.
        """
        if self._api_key is not None:
            return self._api_key

        from azure.identity.aio import DefaultAzureCredential
        from azure.keyvault.secrets.aio import SecretClient

        vault_url = "https://options-analyzer.vault.azure.net"
        async with DefaultAzureCredential() as credential:
            async with SecretClient(vault_url=vault_url, credential=credential) as client:
                secret = await client.get_secret(FINNHUB_SECRET_NAME)
                self._api_key = secret.value

        return self._api_key

    async def fetch(self, symbol: str) -> dict:
        """
        Fetch raw earnings calendar from Finnhub for a 90-day forward window.

        Returns the raw Finnhub response dict, or a synthetic error dict
        with an "_error" key if the request fails. normalize() handles both.

        Emits a structured log record in the finally block with provider,
        symbol, cache_status, and latency_ms attributes. Azure Monitor
        auto-instrumentation picks these up without any explicit OTel calls.
        Attribute names match the eventual OTel span — future swap is
        mechanical.
        """
        start = time.monotonic()
        result: dict = {}
        try:
            try:
                api_key = await self._get_api_key()
            except Exception as e:
                logger.error(f"FinnhubEarningsSource: Key Vault fetch failed: {e}")
                result = {"_error": "finnhub_no_data"}
                return result

            today = date.today()
            to_date = today + timedelta(days=FINNHUB_WINDOW_DAYS)

            url = f"{FINNHUB_BASE_URL}/calendar/earnings"
            params = {
                "from":   today.isoformat(),
                "to":     to_date.isoformat(),
                "symbol": symbol.upper(),
                "token":  api_key,
            }

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, params=params)

                    if resp.status_code == 429:
                        logger.warning(f"FinnhubEarningsSource: rate limited for {symbol}, retrying once")
                        await asyncio.sleep(2)
                        resp = await client.get(url, params=params)
                        if resp.status_code == 429:
                            result = {"_error": "finnhub_rate_limited"}
                            return result

                    if resp.status_code >= 500:
                        logger.error(f"FinnhubEarningsSource: Finnhub 5xx for {symbol}: {resp.status_code}")
                        result = {"_error": "finnhub_5xx"}
                        return result

                    if resp.status_code >= 400:
                        logger.error(f"FinnhubEarningsSource: Finnhub 4xx for {symbol}: {resp.status_code}")
                        result = {"_error": "finnhub_no_data"}
                        return result

                    result = resp.json()
                    return result

            except httpx.TimeoutException:
                logger.warning(f"FinnhubEarningsSource: timeout for {symbol}")
                result = {"_error": "finnhub_timeout"}
                return result
            except Exception as e:
                logger.error(f"FinnhubEarningsSource: unexpected error for {symbol}: {e}")
                result = {"_error": "finnhub_no_data"}
                return result
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "provider_fetch",
                extra={
                    "provider":     "finnhub_earnings",
                    "symbol":       symbol,
                    "cache_status": "miss",  # fetch() is only called on cache miss by ContextStore
                    "latency_ms":   latency_ms,
                    "error":        result.get("_error"),
                },
            )

    def normalize(self, raw: dict) -> dict:
        """
        Map Finnhub response to stable signal_value shape.

        Picks the soonest upcoming event from earningsCalendar array.
        Returns next_earnings_date=None on error or empty calendar.
        """
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        error_code = raw.get("_error")
        if error_code:
            return {
                "next_earnings_date": None,
                "time_of_day":        None,
                "eps_estimate":       None,
                "quarter":            None,
                "fetched_at":         fetched_at,
                "meta":               {"notes": error_code},
            }

        events = raw.get("earningsCalendar", [])
        if not events:
            return {
                "next_earnings_date": None,
                "time_of_day":        None,
                "eps_estimate":       None,
                "quarter":            None,
                "fetched_at":         fetched_at,
                "meta":               {"notes": "finnhub_no_data"},
            }

        # Sort by date ascending, take the soonest
        sorted_events = sorted(events, key=lambda e: e.get("date", ""))
        event = sorted_events[0]

        eps_raw = event.get("epsEstimate")
        eps = float(eps_raw) if eps_raw is not None else None

        quarter_raw = event.get("quarter")
        quarter = int(quarter_raw) if quarter_raw is not None else None

        return {
            "next_earnings_date": event.get("date"),        # "YYYY-MM-DD"
            "time_of_day":        event.get("hour"),         # "bmo"|"amc"|"dmh"|None
            "eps_estimate":       eps,
            "quarter":            quarter,
            "fetched_at":         fetched_at,
            "meta":               {"notes": None},
        }
