"""
Context Store — Phase 3.5 Stream A4.

Reads and writes symbol_context rows. The Position Monitor Agent uses this
instead of calling data providers directly. Two benefits:

1. TTL caching — only re-fetches from Schwab (or any source) when the
   cached signal has expired. Multiple positions on the same symbol in one
   monitor run only trigger one Schwab call, not N.

2. Source abstraction — the agent asks "what do I know about QQQ?" and
   gets back all available signals, regardless of how many sources are
   registered. Adding a sentiment source requires zero changes to the agent.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import SymbolContext
from app.providers.base import ContextSignal, ContextSource
from app.services.symbol_normalization import canonicalize

logger = logging.getLogger(__name__)


class ContextStore:
    """
    TTL-aware cache for symbol context signals backed by Azure SQL.

    Pass an open AsyncSession from the caller (route or agent) — this class
    does not manage session lifecycle.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, symbol: str, source_id: str) -> Optional[dict]:
        """
        Return the signal_value for a non-expired entry, or None if missing/stale.

        The query filters expires_at > now so stale rows are never returned,
        even if they haven't been cleaned up yet.
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            select(SymbolContext)
            .where(
                and_(
                    SymbolContext.symbol == symbol.upper(),
                    SymbolContext.source_id == source_id,
                    SymbolContext.expires_at > now,
                )
            )
            .order_by(SymbolContext.captured_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        try:
            return json.loads(row.signal_value)
        except (ValueError, TypeError):
            logger.warning(f"ContextStore.get: invalid JSON for {symbol}/{source_id}")
            return None

    async def set(self, signal: ContextSignal) -> None:
        """Write a ContextSignal to symbol_context."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=signal.ttl_seconds)
        row = SymbolContext(
            symbol=canonicalize(signal.symbol),
            source_id=signal.source_id,
            signal_type=signal.signal_type,
            signal_value=json.dumps(signal.value),
            captured_at=now,
            expires_at=expires_at,
        )
        self._db.add(row)
        await self._db.flush()  # write within caller's transaction
        logger.debug(
            f"ContextStore.set: {signal.symbol}/{signal.source_id} "
            f"expires={expires_at.isoformat()}"
        )

    async def get_all_for_symbol(self, symbol: str) -> List[dict]:
        """
        Return all non-expired signals for a symbol, across all sources.

        Each element is:
            {"source_id": str, "signal_type": str, "value": dict, "captured_at": str}
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            select(SymbolContext)
            .where(
                and_(
                    SymbolContext.symbol == symbol.upper(),
                    SymbolContext.expires_at > now,
                )
            )
            .order_by(SymbolContext.source_id, SymbolContext.captured_at.desc())
        )
        rows = result.scalars().all()

        # De-duplicate: keep only the freshest row per source_id
        seen: set[str] = set()
        signals = []
        for row in rows:
            if row.source_id in seen:
                continue
            seen.add(row.source_id)
            try:
                value = json.loads(row.signal_value)
            except (ValueError, TypeError):
                continue
            signals.append({
                "source_id":   row.source_id,
                "signal_type": row.signal_type,
                "value":       value,
                "captured_at": row.captured_at.isoformat() if row.captured_at else None,
            })
        return signals

    async def refresh_if_stale(
        self,
        symbol: str,
        source: ContextSource,
    ) -> dict:
        """
        Return the current signal value for symbol/source.

        If a fresh (non-expired) entry exists in symbol_context, return it.
        Otherwise fetch from the source, store it, and return the new value.

        This is the primary entry point for the Position Monitor Agent —
        it ensures data is fresh without ever fetching more than once per
        TTL window per symbol per source.
        """
        cached = await self.get(symbol, source.source_id)
        if cached is not None:
            logger.debug(
                f"ContextStore.refresh_if_stale: cache hit {symbol}/{source.source_id}"
            )
            return cached

        logger.info(
            f"ContextStore.refresh_if_stale: cache miss — fetching "
            f"{symbol}/{source.source_id}"
        )
        try:
            signal = await source.fetch_and_normalize(symbol)
        except Exception as e:
            logger.error(
                f"ContextStore.refresh_if_stale: fetch failed for "
                f"{symbol}/{source.source_id}: {e}"
            )
            return {}

        await self.set(signal)
        return signal.value
