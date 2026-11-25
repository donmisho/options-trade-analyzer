"""
Underlying price bars — pull route (OTA-859, slice 1 of the price bars spec).

GET /api/v1/market/bars/pull streams 1-minute, 5-minute or daily bars straight
from Schwab /pricehistory as CSV. Nothing is stored: slice 2 adds the table and
the daily top-up. Tier 2, because one call can make hundreds of Schwab requests.

The file is complete only if its last line is "#done". Lines starting with "#"
are metadata: one trailer per symbol, then "#done", or "#error" on an auth failure.
"""

import asyncio
import csv
import io
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.market_routes import _get_provider, _get_registry
from app.auth.dependencies import require_write
from app.core.config import settings
from app.models.database import BrokerTransaction
from app.models.session import get_db
from app.services.price_bars import (
    FREQUENCIES, bar_session, bar_windows, complete, early_close_dates, iso_utc,
    ny_date, symbol_list, to_utc,
)
from app.services.symbol_cache import to_api_symbol_cached
from app.services.symbol_normalization import canonicalize

router = APIRouter(prefix="/market/bars", tags=["Market Data"])
log = logging.getLogger(__name__)

CSV_HEADER = ["symbol", "frequency", "bar_start_utc", "session_date", "session",
              "open", "high", "low", "close", "volume"]

_AUTH_MARKERS = ("re-authenticate", "reconnect your schwab", "no schwab tokens", "refresh token expired")
_RATE_LIMIT_PAUSE_SECONDS = 30


def _is_auth_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        if exc.response.status_code in (401, 403):
            return True
    text = str(exc).lower()
    return any(marker in text for marker in _AUTH_MARKERS)


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and exc.response.status_code == 429


def _csv_line(values: list) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(values)
    return buf.getvalue()


def _today_ny() -> date:
    return ny_date(datetime.now(timezone.utc))


async def _default_symbols(db: AsyncSession, user_id: Optional[str]) -> list[str]:
    """The configured list, then the caller's traded underlyings (Data Isolation Invariant)."""
    symbols = symbol_list(settings.price_bars_symbols)
    if user_id:
        rows = await db.execute(
            select(distinct(BrokerTransaction.underlying_symbol)).where(
                BrokerTransaction.user_id == user_id,
                BrokerTransaction.underlying_symbol.isnot(None),
            )
        )
        traded = sorted({canonicalize(s) for s in rows.scalars().all() if s and s.strip()})
        for sym in traded:
            if sym not in symbols:
                symbols.append(sym)
    return symbols


class _Pacer:
    """Successive Schwab calls start at least 60 / calls_per_minute seconds apart."""

    def __init__(self, calls_per_minute: int):
        self.interval = 60.0 / max(int(calls_per_minute or 1), 1)
        self.last: Optional[float] = None
        self.calls = 0

    async def wait(self):
        if self.last is not None:
            gap = self.interval - (time.monotonic() - self.last)
            if gap > 0:
                await asyncio.sleep(gap)
        self.last = time.monotonic()
        self.calls += 1


async def stream_bars(provider, symbols: list[str], frequency: str, start: date, end: date,
                      extended: bool, early: frozenset, calls_per_minute: int, now_fn=None):
    """Yields CSV text: the header, rows window by window, trailers, then #done (or #error)."""
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    pacer = _Pacer(calls_per_minute)
    windows = bar_windows(frequency, start, end)
    started = time.monotonic()
    trailers: list[str] = []
    total = 0

    yield _csv_line(CSV_HEADER)

    for sym in symbols:
        canonical = canonicalize(sym)
        api_symbol = to_api_symbol_cached(canonical, "schwab")
        seen: set = set()
        ok = failed = count = 0
        first_bar = last_bar = ""

        for w_start, w_end in windows:
            bars = None
            for attempt in (1, 2):
                await pacer.wait()
                try:
                    bars = await provider.get_bars(api_symbol, frequency, w_start, w_end, extended)
                    break
                except Exception as e:  # noqa: BLE001 — classified below
                    if _is_auth_error(e):
                        message = str(e).replace(",", ";").replace("\n", " ")
                        log.warning(f"bars pull: auth failure on {canonical}: {message}")
                        for line in trailers:
                            yield line
                        yield f"#error,{canonical},{message}\n"
                        return
                    if _is_rate_limited(e) and attempt == 1:
                        log.warning(f"bars pull: 429 on {canonical}, pausing {_RATE_LIMIT_PAUSE_SECONDS}s")
                        await asyncio.sleep(_RATE_LIMIT_PAUSE_SECONDS)
                        continue
                    log.warning(f"bars pull: {canonical} {frequency} window {iso_utc(w_start)} failed: {e}")
                    bars = None
                    break
            if bars is None:
                failed += 1
                continue
            ok += 1

            now = now_fn()
            chunk = []
            for bar in sorted(bars, key=lambda b: int(b["datetime"])):
                stamp = int(bar["datetime"])
                if stamp in seen:
                    continue
                bar_start = to_utc(stamp)
                if frequency == "1d":
                    session_date, session = ny_date(bar_start), "reg"
                else:
                    session_date, session = bar_session(bar_start, early)
                if session_date < start or session_date > end:
                    continue
                if not complete(bar_start, frequency, now, early):
                    continue
                seen.add(stamp)
                stamp_iso = iso_utc(bar_start)
                first_bar = min(first_bar, stamp_iso) if first_bar else stamp_iso   # ISO UTC sorts as text
                last_bar = max(last_bar, stamp_iso) if last_bar else stamp_iso
                count += 1
                chunk.append(_csv_line([
                    canonical, frequency, stamp_iso, session_date.isoformat(), session,
                    bar["open"], bar["high"], bar["low"], bar["close"], int(bar.get("volume") or 0),
                ]))
            if chunk:
                yield "".join(chunk)

        if ok == 0:
            status = "error"        # every window failed
        elif failed:
            status = "partial"      # some windows failed
        else:
            status = "ok" if count else "empty"
        trailers.append(f"#{canonical},{status},{first_bar},{last_bar},{count}\n")
        total += count

    for line in trailers:
        yield line
    yield "#done\n"
    log.info(
        f"bars pull: {frequency} {start}..{end}, {len(symbols)} symbols, "
        f"{pacer.calls} calls, {total} bars, {time.monotonic() - started:.0f}s"
    )


@router.get("/pull")
async def pull_bars(
    frequency: str = Query(..., description="1m, 5m or 1d"),
    start: date = Query(..., description="First New York date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="Last New York date, default today"),
    symbols: Optional[str] = Query(None, description="Comma list. Default: price_bars_symbols plus your traded underlyings"),
    extended: bool = Query(True, description="Include pre- and post-market bars (1m and 5m)"),
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream Schwab price bars as CSV:
    `symbol,frequency,bar_start_utc,session_date,session,open,high,low,close,volume`.
    The bar still forming is never included. Ends with one
    `#symbol,status,first_bar,last_bar,bars` line per symbol and `#done`; a file
    without `#done` is incomplete. An auth failure ends the file with `#error`.
    """
    if frequency not in FREQUENCIES:
        raise HTTPException(status_code=422, detail=f"frequency must be one of {list(FREQUENCIES)}")
    end = end or _today_ny()
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")

    provider = _get_provider(_get_registry(), user.get("sub"))
    if not hasattr(provider, "get_bars"):
        raise HTTPException(status_code=501, detail="Price bars not supported by this provider")

    # Read everything from the database before streaming: the session is not used
    # once the response has started.
    wanted = symbol_list(symbols) if symbols else await _default_symbols(db, user.get("sub"))
    if not wanted:
        raise HTTPException(status_code=422, detail="no symbols to pull")

    early = early_close_dates(settings.price_bars_early_closes)
    body = stream_bars(provider, wanted, frequency, start, end, extended, early,
                       settings.price_bars_calls_per_minute)
    filename = f"bars_{frequency}_{start.isoformat()}_{end.isoformat()}.csv"
    return StreamingResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
