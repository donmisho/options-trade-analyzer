"""
Account activity sync (OTA-855).

Every 15 minutes in market hours (APScheduler, wired in main.py) or on demand
(POST /api/v1/account-activity/run), pull the brokerage's record into the
broker_* tables:

  1. Account numbers → broker_accounts (hash, last four digits, label)
  2. TRADE transactions since the last stored one (3-day overlap; 59 days on
     the first run, the Trader API's lookback limit) → broker_transactions,
     new activityIds only
  3. Orders entered in the same window (7-day overlap, so a stop that fired
     or a target that was cancelled updates in place) → broker_orders, upsert
  4. Fill context for new option fills → broker_fill_context: quotes for the
     underlying and the option at this poll, ATR14 from the daily candles
     before the trade date. Fills older than the live window (a backfill) get
     a daily context from the day's own candle instead, marked kind="daily".

The provider is the AccountActivityProvider from the registry; nothing here
names Schwab. Every row carries the owning user's id (Data Isolation Invariant).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import (
    BrokerAccount, BrokerFillContext, BrokerOrder, BrokerSyncRun, BrokerTransaction, User,
)
from app.providers.base import AccountActivityProvider
from app.services.broker_activity import (
    daily_context_from_candles, fill_context_values, in_market_hours, normalize_order,
    normalize_transaction, quote_block, wilder_atr,
)
from app.services.symbol_cache import to_api_symbol_cached

logger = logging.getLogger(__name__)

FIRST_RUN_DAYS = 59          # the Trader API refuses a transactions start older than 60 days
TRANSACTION_OVERLAP = timedelta(days=3)
ORDER_OVERLAP = timedelta(days=7)
LIVE_CONTEXT_WINDOW = timedelta(hours=6)   # a fill older than this gets a daily context, not a live quote


@dataclass
class SyncResult:
    status: str                       # ok | skipped | error
    run_id: Optional[int] = None
    accounts: int = 0
    transactions_new: int = 0
    orders_upserted: int = 0
    contexts_captured: int = 0
    message: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None


def _naive_utc(moment: Optional[datetime]) -> Optional[datetime]:
    """The DateTime columns hold naive UTC, as the rest of the schema does."""
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _aware(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def account_labels() -> dict:
    """{last4: label} from settings.broker_account_labels ('7892=Options,1234=IRA')."""
    out = {}
    for part in (settings.broker_account_labels or "").split(","):
        if "=" in part:
            last4, label = part.split("=", 1)
            if last4.strip() and label.strip():
                out[last4.strip()[-4:]] = label.strip()
    return out


async def resolve_owner_user_id(db: AsyncSession) -> Optional[str]:
    """
    The user the pulled rows belong to. The Schwab login is app-wide (one token
    manager), so the owner is named in settings, or is the single active admin,
    or the single user, in that order. None means the poller stands down.
    """
    if settings.broker_activity_user_id:
        return settings.broker_activity_user_id
    admins = (await db.execute(select(User.id).where(User.role == "admin", User.is_active == True))).scalars().all()  # noqa: E712
    if len(admins) == 1:
        return admins[0]
    everyone = (await db.execute(select(User.id))).scalars().all()
    if len(everyone) == 1:
        return everyone[0]
    return None


class AccountActivitySync:
    """The poller. One instance per app, built in main.py's lifespan."""

    def __init__(self, provider: AccountActivityProvider, now=None):
        self._provider = provider
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._last_run: Optional[SyncResult] = None
        self._running = False

    @property
    def last_run(self) -> Optional[SyncResult]:
        return self._last_run

    async def run(self, db: AsyncSession, trigger: str = "schedule", force: bool = False) -> SyncResult:
        """Pull once. Outside market hours the scheduled run stands down unless force is set."""
        now = self._now()
        if not force and not in_market_hours(now):
            result = SyncResult(status="skipped", message="outside market hours", started_at=now, finished_at=now)
            self._last_run = result
            return result
        if self._running:
            result = SyncResult(status="skipped", message="a run is already in progress", started_at=now, finished_at=now)
            return result
        self._running = True
        try:
            return await self._run(db, trigger, now)
        finally:
            self._running = False

    async def _run(self, db: AsyncSession, trigger: str, now: datetime) -> SyncResult:
        user_id = await resolve_owner_user_id(db)
        run = BrokerSyncRun(user_id=user_id, started_at=_naive_utc(now), status="running", trigger=trigger)
        db.add(run)
        await db.commit()
        result = SyncResult(status="running", run_id=run.id, started_at=now)
        if not user_id:
            return await self._finish(db, run, result, "error",
                                      "no owner user: set BROKER_ACTIVITY_USER_ID or keep exactly one admin user")
        try:
            accounts = await self._sync_accounts(db, user_id)
            result.accounts = len(accounts)
            new_transactions: list[BrokerTransaction] = []
            window_start = None
            for account in accounts:
                start, added = await self._sync_transactions(db, user_id, account, now)
                window_start = start if window_start is None or start < window_start else window_start
                new_transactions.extend(added)
                result.transactions_new += len(added)
                result.orders_upserted += await self._sync_orders(db, user_id, account, start - ORDER_OVERLAP, now)
                account.last_synced_at = _naive_utc(now)
                await db.commit()
            run.window_start = _naive_utc(window_start)
            run.window_end = _naive_utc(now)
            result.contexts_captured = await self._capture_contexts(db, user_id, new_transactions, now)
            return await self._finish(db, run, result, "ok", None)
        except Exception as e:
            logger.error(f"AccountActivitySync: run failed: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            return await self._finish(db, run, result, "error", str(e)[:1000])

    async def _finish(self, db: AsyncSession, run: BrokerSyncRun, result: SyncResult, status: str, message: Optional[str]) -> SyncResult:
        finished = self._now()
        result.status, result.message, result.finished_at = status, message, finished
        try:
            run = await db.merge(run)
            run.status, run.message, run.finished_at = status, message, _naive_utc(finished)
            run.accounts, run.transactions_new = result.accounts, result.transactions_new
            run.orders_upserted, run.contexts_captured = result.orders_upserted, result.contexts_captured
            await db.commit()
        except Exception as e:
            logger.warning(f"AccountActivitySync: could not record the run: {e}")
        self._last_run = result
        logger.info(
            f"AccountActivitySync: {status} — accounts={result.accounts} transactions_new={result.transactions_new} "
            f"orders_upserted={result.orders_upserted} contexts={result.contexts_captured}"
            + (f" ({message})" if message else "")
        )
        return result

    # ------------------------------------------------------------------

    async def _sync_accounts(self, db: AsyncSession, user_id: str) -> list[BrokerAccount]:
        numbers = await self._provider.get_account_numbers()
        labels = account_labels()
        existing = {
            a.account_hash: a for a in (await db.execute(
                select(BrokerAccount).where(BrokerAccount.user_id == user_id, BrokerAccount.provider == "schwab")
            )).scalars().all()
        }
        out = []
        for entry in numbers:
            account_hash = entry.get("hashValue")
            number = str(entry.get("accountNumber") or "")
            if not account_hash:
                continue
            last4 = number[-4:] if number else "????"
            label = labels.get(last4, f"…{last4}")
            account = existing.get(account_hash)
            if account is None:
                account = BrokerAccount(user_id=user_id, provider="schwab", account_hash=account_hash,
                                        account_last4=last4, label=label, is_active=True)
                db.add(account)
            elif account.label != label and last4 in labels:
                account.label = label
            out.append(account)
        await db.commit()
        return [a for a in out if a.is_active]

    async def _sync_transactions(self, db: AsyncSession, user_id: str, account: BrokerAccount, now: datetime):
        latest = (await db.execute(
            select(BrokerTransaction.time).where(BrokerTransaction.account_id == account.id)
            .order_by(BrokerTransaction.time.desc()).limit(1)
        )).scalar_one_or_none()
        start = (_aware(latest) - TRANSACTION_OVERLAP) if latest else (now - timedelta(days=FIRST_RUN_DAYS))
        raw_rows = await self._provider.get_transactions(account.account_hash, start, now)
        known = set((await db.execute(
            select(BrokerTransaction.activity_id).where(
                BrokerTransaction.account_id == account.id, BrokerTransaction.time >= _naive_utc(start) - timedelta(days=1))
        )).scalars().all())
        added = []
        for raw in raw_rows:
            try:
                values = normalize_transaction(raw)
            except Exception as e:
                logger.warning(f"AccountActivitySync: unreadable transaction skipped: {e}")
                continue
            if values["activity_id"] is None or values["activity_id"] in known:
                continue
            values["time"] = _naive_utc(values["time"])
            txn = BrokerTransaction(user_id=user_id, account_id=account.id, provider="schwab",
                                    captured_at=_naive_utc(now), **values)
            db.add(txn)
            known.add(values["activity_id"])
            added.append(txn)
        await db.commit()
        return start, added

    async def _sync_orders(self, db: AsyncSession, user_id: str, account: BrokerAccount, start: datetime, now: datetime) -> int:
        raw_rows = await self._provider.get_orders(account.account_hash, start, now)
        flat = []
        for raw in raw_rows:
            try:
                flat.extend(normalize_order(raw))
            except Exception as e:
                logger.warning(f"AccountActivitySync: unreadable order skipped: {e}")
        if not flat:
            return 0
        ids = [r["order_id"] for r in flat if r["order_id"] is not None]
        existing = {
            o.order_id: o for o in (await db.execute(
                select(BrokerOrder).where(BrokerOrder.account_id == account.id, BrokerOrder.order_id.in_(ids))
            )).scalars().all()
        }
        count = 0
        for values in flat:
            if values["order_id"] is None:
                continue
            values["entered_time"] = _naive_utc(values["entered_time"])
            values["close_time"] = _naive_utc(values["close_time"])
            order = existing.get(values["order_id"])
            if order is None:
                order = BrokerOrder(user_id=user_id, account_id=account.id, provider="schwab", captured_at=_naive_utc(now), **values)
                db.add(order)
                existing[values["order_id"]] = order
                count += 1
            else:
                changed = False
                for key, value in values.items():
                    if key == "raw_json":
                        continue
                    if getattr(order, key) != value and not (key in ("price", "stop_price", "stop_price_offset", "quantity", "filled_quantity", "remaining_quantity", "strike_price") and _same_number(getattr(order, key), value)):
                        setattr(order, key, value)
                        changed = True
                if changed:
                    order.raw_json = values["raw_json"]
                    order.updated_at = _naive_utc(now)
                    count += 1
        await db.commit()
        return count

    async def _capture_contexts(self, db: AsyncSession, user_id: str, transactions: list[BrokerTransaction], now: datetime) -> int:
        """Quotes and ATR for every new option fill; daily candles stand in for fills older than the live window."""
        fills = [t for t in transactions if t.asset_type in ("OPTION", "MULTI") and t.underlying_symbol]
        if not fills:
            return 0
        live = [t for t in fills if now - _aware(t.time) <= LIVE_CONTEXT_WINDOW]
        daily = [t for t in fills if t not in live]
        candles: dict[str, list] = {}

        async def candles_for(underlying: str) -> list:
            api_symbol = to_api_symbol_cached(underlying, "schwab")
            if api_symbol not in candles:
                try:
                    candles[api_symbol] = await self._provider.get_daily_candles(api_symbol, months=3)
                except Exception as e:
                    logger.warning(f"AccountActivitySync: candles failed for {api_symbol}: {e}")
                    candles[api_symbol] = []
            return candles[api_symbol]

        count = 0
        if live:
            symbols = sorted({to_api_symbol_cached(t.underlying_symbol, "schwab") for t in live}
                             | {t.option_symbol for t in live if t.option_symbol})
            try:
                quotes = await self._provider.get_quotes(symbols)
            except Exception as e:
                logger.warning(f"AccountActivitySync: quotes failed, live contexts deferred: {e}")
                quotes = None
            if quotes is not None:
                for txn in live:
                    api_symbol = to_api_symbol_cached(txn.underlying_symbol, "schwab")
                    atr, as_of = wilder_atr(await candles_for(txn.underlying_symbol), before=txn.trade_date)
                    values = fill_context_values(
                        _aware(txn.time), now, txn.underlying_symbol, txn.option_symbol,
                        quote_block(quotes, api_symbol), quote_block(quotes, txn.option_symbol), atr, as_of, kind="live",
                    )
                    values["captured_at"] = _naive_utc(now)
                    db.add(BrokerFillContext(user_id=user_id, transaction_id=txn.id, **values))
                    count += 1
        for txn in daily:
            series = await candles_for(txn.underlying_symbol)
            if not series:
                continue
            quote, atr, as_of = daily_context_from_candles(series, txn.trade_date)
            values = fill_context_values(_aware(txn.time), now, txn.underlying_symbol, txn.option_symbol, quote, {}, atr, as_of, kind="daily")
            values["captured_at"] = _naive_utc(now)
            db.add(BrokerFillContext(user_id=user_id, transaction_id=txn.id, **values))
            count += 1
        await db.commit()
        return count


def _same_number(a, b) -> bool:
    try:
        if a is None or b is None:
            return a is None and b is None
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return False
