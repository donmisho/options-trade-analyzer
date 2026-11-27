"""
Entry signal monitor — the one-minute loop (entries only).

Not an AI agent: plain arithmetic on Schwab price bars. Each minute in the regular
session it reads today's 1-minute bars for every watched underlying, judges the
entry conditions with app/services/entry_signals.py, reads the option chain only
for the names whose underlying gates all pass, and rewrites one row per symbol in
entry_signals. The get_signals MCP tool serves those rows; the dashboard only
displays them.

Schwab calls per run: one /pricehistory per symbol, one more per symbol once a day
for the daily candles behind ATR and the prior close, and one /chains per symbol
that is ready. Nine symbols is about ten calls a minute against a working limit of
about 120.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.account_activity_sync import resolve_owner_user_id
from app.agents.schwab_expiry_alert import is_auth_error
from app.core.config import settings
from app.models.database import EntrySignal
from app.services.broker_activity import MARKET_TZ, simple_atr, candle_date, to_float, zone
from app.services.entry_signals import EntryRules, evaluate_underlying, pick_contract
from app.services.price_bars import bar_session, early_close_dates, session_close, symbol_list
from app.services.symbol_cache import to_api_symbol_cached
from app.services.symbol_normalization import canonicalize

logger = logging.getLogger(__name__)

# The first run is five minutes after the open, when the first 5-minute bar exists.
_FIRST_RUN = time(9, 35)
# A symbol whose newest 1-minute bar is older than this is not judged.
_STALE_BARS = timedelta(minutes=6)
_DAILY_LOOKBACK_DAYS = 45
_CHAIN_STRIKE_RANGE_PCT = 6.0

# Row fields copied straight from the rules' answer.
_UNDERLYING_FIELDS = (
    "direction", "message", "price", "vwap", "trend_15m", "push", "push_pct_atr", "push_strong",
    "volume_ratio", "atr", "prev_close", "net_change", "atr_used_pct", "range_used_pct",
    "gate_trend", "gate_push", "gate_volume", "gate_room",
)
_CONTRACT_FIELDS = ("gate_contract", "option_symbol", "put_call", "expiration", "dte", "strike", "delta",
                    "option_bid", "option_ask", "option_mid", "spread_pct")


@dataclass
class SignalRunResult:
    status: str = "ok"            # ok | skipped | auth_error | error
    message: Optional[str] = None
    symbols: int = 0
    signals: int = 0
    errors: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    failed: list = field(default_factory=list)


def _naive_utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def watched_symbols() -> list[str]:
    """The configured list, canonical and de-duplicated; price_bars_symbols when none is set."""
    out: list[str] = []
    for sym in symbol_list(settings.signal_monitor_symbols or settings.price_bars_symbols):
        sym = canonicalize(sym)
        if sym not in out:
            out.append(sym)
    return out


def in_signal_hours(now: datetime, early_closes: frozenset = frozenset()) -> bool:
    """Mon–Fri from 09:35 New York to the session close (13:00 on an early close)."""
    local = now.astimezone(zone(MARKET_TZ))
    if local.weekday() >= 5:
        return False
    clock = local.time().replace(tzinfo=None)
    return _FIRST_RUN <= clock < session_close(local.date(), early_closes)


class SignalMonitor:
    """The loop. One instance per app, built in main.py's lifespan."""

    def __init__(self, provider, now=None, rules: Optional[EntryRules] = None):
        self._provider = provider
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.rules = rules or EntryRules()
        self._last_run: Optional[SignalRunResult] = None
        self._running = False
        self._daily: dict = {}        # symbol -> (New York date, atr, prev_close)

    @property
    def last_run(self) -> Optional[SignalRunResult]:
        return self._last_run

    async def run(self, db: AsyncSession, trigger: str = "schedule", force: bool = False) -> SignalRunResult:
        """Judge every watched symbol once. Outside the session the run stands down unless force is set."""
        now = self._now()
        early = early_close_dates(settings.price_bars_early_closes)
        if not force and not in_signal_hours(now, early):
            self._last_run = SignalRunResult(status="skipped", message="outside the regular session",
                                             started_at=now, finished_at=now)
            return self._last_run
        if self._running:
            return SignalRunResult(status="skipped", message="a run is already in progress", started_at=now, finished_at=now)
        self._running = True
        try:
            result = await self._run(db, now, early)
        except Exception as e:  # noqa: BLE001 — the loop must survive any one bad minute
            logger.error(f"SignalMonitor: run failed: {e}")
            result = SignalRunResult(status="error", message=str(e)[:400], started_at=now)
        finally:
            self._running = False
        result.finished_at = self._now()
        self._last_run = result
        return result

    async def _run(self, db: AsyncSession, now: datetime, early: frozenset) -> SignalRunResult:
        result = SignalRunResult(started_at=now)
        user_id = await resolve_owner_user_id(db)
        if not user_id:
            result.status, result.message = "skipped", "no owner user resolved"
            return result
        symbols = watched_symbols()
        result.symbols = len(symbols)
        if not symbols:
            result.status, result.message = "skipped", "no symbols to watch"
            return result

        gate = asyncio.Semaphore(max(int(settings.signal_monitor_concurrency or 1), 1))

        async def judge(symbol: str) -> dict:
            async with gate:
                try:
                    return await self._judge(symbol, now, early)
                except Exception as e:  # noqa: BLE001 — recorded on the row
                    return {"status": "error", "message": str(e)[:400]}

        answers = await asyncio.gather(*(judge(s) for s in symbols))

        auth = next((a["message"] for a in answers if a["status"] == "error" and is_auth_error(a.get("message"))), None)
        existing = {row.symbol: row for row in (await db.execute(
            select(EntrySignal).where(EntrySignal.user_id == user_id))).scalars().all()}
        stamp = _naive_utc(now)
        for symbol, answer in zip(symbols, answers):
            row = existing.get(symbol)
            if row is None:
                row = EntrySignal(user_id=user_id, symbol=symbol, status_since=stamp)
                db.add(row)
            elif (row.status, row.direction) != (answer["status"], answer.get("direction")):
                row.status_since = stamp
            row.status, row.evaluated_at = answer["status"], stamp
            row.last_bar_at = _naive_utc(answer.get("last_bar_utc"))
            row.push_bar_at = _naive_utc(answer.get("push_bar_utc"))
            for name in _UNDERLYING_FIELDS + _CONTRACT_FIELDS:
                setattr(row, name, answer.get(name))
            if answer["status"] == "signal":
                result.signals += 1
            elif answer["status"] == "error":
                result.errors += 1
                result.failed.append(symbol)
        # A symbol taken off the list leaves no row behind.
        for symbol, row in existing.items():
            if symbol not in symbols:
                await db.delete(row)
        await db.commit()

        if auth:
            result.status, result.message = "auth_error", auth
        elif result.errors == len(symbols):
            result.status, result.message = "error", answers[0].get("message")
        elif result.errors:
            result.message = f"failed: {', '.join(result.failed)}"
        logger.info(f"SignalMonitor: {result.status} — {result.symbols} symbols, {result.signals} signals, {result.errors} errors")
        return result

    async def _judge(self, symbol: str, now: datetime, early: frozenset) -> dict:
        api_symbol = to_api_symbol_cached(symbol, "schwab")
        local = now.astimezone(zone(MARKET_TZ))
        today = local.date()
        atr, prev_close = await self._daily_levels(symbol, api_symbol, today, now)

        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        bars = await self._provider.get_bars(api_symbol, "1m", day_start, now, False)
        bars = [b for b in bars if bar_session(datetime.fromtimestamp(int(b["datetime"]) / 1000, tz=timezone.utc), early) == (today, "reg")]

        answer = evaluate_underlying(bars, atr, prev_close, now, self.rules)
        last_bar = answer.get("last_bar_utc")
        if last_bar is not None and now - last_bar > _STALE_BARS:
            answer.update({"status": "no_data", "message": f"newest 1-minute bar is {int((now - last_bar).total_seconds() // 60)} minutes old"})
            return answer
        if answer["status"] != "ready":
            return answer

        chain = await self._provider.get_chain(
            symbol=api_symbol, min_dte=self.rules.dte_min, max_dte=self.rules.dte_max,
            strike_range_pct=_CHAIN_STRIKE_RANGE_PCT, option_type=answer["direction"],
        )
        contract, why = pick_contract(chain.get("contracts", []), answer["direction"], self.rules)
        if contract is None:
            answer.update({"status": "no_contract", "gate_contract": False, "message": why})
            return answer
        answer.update({
            "status": "signal", "gate_contract": True,
            "option_symbol": contract.get("symbol"), "put_call": contract.get("option_type"),
            "expiration": contract.get("expiration"), "dte": contract.get("dte"), "strike": contract.get("strike"),
            "delta": contract.get("delta"), "option_bid": contract.get("bid"), "option_ask": contract.get("ask"),
            "option_mid": contract.get("mid"), "spread_pct": contract.get("spread_pct"),
        })
        return answer

    async def _daily_levels(self, symbol: str, api_symbol: str, today: date, now: datetime) -> tuple[Optional[float], Optional[float]]:
        """D ATR (simple, 14 completed sessions) and the prior close, read once per symbol per day."""
        cached = self._daily.get(symbol)
        if cached and cached[0] == today:
            return cached[1], cached[2]
        candles = await self._provider.get_bars(api_symbol, "1d", now - timedelta(days=_DAILY_LOOKBACK_DAYS), now)
        atr, _ = simple_atr(candles, before=today)
        prior = sorted((c for c in candles if (candle_date(c) or today) < today), key=lambda c: int(c["datetime"]))
        prev_close = to_float(prior[-1].get("close")) if prior else None
        if atr is not None and prev_close is not None:
            self._daily[symbol] = (today, atr, prev_close)
        return atr, prev_close
