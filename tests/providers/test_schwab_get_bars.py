"""SchwabMarketData.get_bars (OTA-859): query mapping, errors raise, empty is empty."""

from datetime import datetime, timezone

import httpx
import pytest

from app.providers.schwab import SCHWAB_MARKET_DATA_URL, SchwabMarketData

START = datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 25, 4, 59, 59, 999000, tzinfo=timezone.utc)


class FakeTokens:
    async def get_access_token(self):
        return "t"


def provider_with(handler):
    p = SchwabMarketData(FakeTokens())
    p._client = httpx.AsyncClient(base_url=SCHWAB_MARKET_DATA_URL, transport=httpx.MockTransport(handler))
    return p


def recorder(payload, status=200):
    seen = {}

    def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(status, json=payload)

    return handler, seen


@pytest.mark.asyncio
@pytest.mark.parametrize("frequency, minutes", [("1m", "1"), ("5m", "5")])
async def test_intraday_query(frequency, minutes):
    handler, seen = recorder({"candles": [], "empty": True})
    await provider_with(handler).get_bars("IWM", frequency, START, END, extended=False)
    assert seen["path"].endswith("/pricehistory") and seen["auth"] == "Bearer t"
    assert seen["params"] == {
        "symbol": "IWM", "periodType": "day", "frequencyType": "minute", "frequency": minutes,
        "startDate": str(int(START.timestamp() * 1000)), "endDate": str(int(END.timestamp() * 1000)),
        "needExtendedHoursData": "false",
    }


@pytest.mark.asyncio
async def test_daily_query_has_no_extended_flag_and_no_period():
    handler, seen = recorder({"candles": []})
    await provider_with(handler).get_bars("iwm", "1d", START, END)
    params = seen["params"]
    assert params["symbol"] == "IWM"
    assert (params["periodType"], params["frequencyType"], params["frequency"]) == ("year", "daily", "1")
    assert "needExtendedHoursData" not in params and "period" not in params


@pytest.mark.asyncio
async def test_extended_true_by_default():
    handler, seen = recorder({"candles": []})
    await provider_with(handler).get_bars("SPY", "1m", START, END)
    assert seen["params"]["needExtendedHoursData"] == "true"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 500])
async def test_http_errors_raise(status):
    handler, _ = recorder({"errors": ["x"]}, status=status)
    with pytest.raises(httpx.HTTPStatusError):
        await provider_with(handler).get_bars("IWM", "1m", START, END)


@pytest.mark.asyncio
async def test_empty_answer_is_an_empty_list():
    handler, _ = recorder({"candles": [], "symbol": "IWM", "empty": True})
    assert await provider_with(handler).get_bars("IWM", "5m", START, END) == []


@pytest.mark.asyncio
async def test_rows_cleaned_and_sorted():
    candles = [
        {"datetime": 3000, "open": 3, "high": 4, "low": 2, "close": 3.5, "volume": 30},
        {"datetime": 1000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"datetime": 1000, "open": 9, "high": 9, "low": 9, "close": 9, "volume": 99},   # duplicate time
        {"datetime": 2000, "open": 2, "high": None, "low": 1, "close": 2},              # missing price
        {"open": 5, "high": 6, "low": 4, "close": 5},                                   # missing time
        {"datetime": 4000, "open": 4, "high": 5, "low": 3, "close": 4.5},               # no volume
    ]
    handler, _ = recorder({"candles": candles})
    bars = await provider_with(handler).get_bars("IWM", "1m", START, END)
    assert [b["datetime"] for b in bars] == [1000, 3000, 4000]
    assert bars[0] == {"datetime": 1000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    assert bars[2]["volume"] == 0


@pytest.mark.asyncio
async def test_unknown_frequency_raises_before_any_request():
    def handler(request):
        raise AssertionError("no request expected")

    with pytest.raises(ValueError):
        await provider_with(handler).get_bars("IWM", "15m", START, END)
