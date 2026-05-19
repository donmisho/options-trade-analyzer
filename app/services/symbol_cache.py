"""
Startup-loaded, sync-accessible symbol cache — OTA-672.

Caches the symbol_reference.api_symbol column in a plain dict so that
outbound Schwab callers can translate canonical → api_symbol without
needing an AsyncSession.  The cache is populated once at startup and
refreshed on a configurable interval (default: 6 hours).

Public API:
  - to_api_symbol_cached(symbol, provider) -> str   [sync, no db]
  - start_symbol_cache_refresh_task() -> asyncio.Task
"""

import asyncio
import logging

from sqlalchemy import select

from app.services.symbol_normalization import canonicalize

logger = logging.getLogger(__name__)

# ── In-memory cache ─────────────────────────────────────────────────────────
# Key: canonical symbol (uppercase, no $)  →  Value: api_symbol string
_api_symbol_cache: dict[str, str] = {}

REFRESH_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours

# Session factory — set at module level by _get_session_factory() on first use.
# Tests can override via _set_session_factory().
_session_factory = None


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        from app.models.session import async_session
        _session_factory = async_session
    return _session_factory


def _set_session_factory(factory):
    """Test hook: override the session factory."""
    global _session_factory
    _session_factory = factory


async def _refresh_api_symbol_cache() -> int:
    """
    Query symbol_reference and repopulate _api_symbol_cache.

    Returns the number of mappings loaded.
    """
    from app.models.database import SymbolReference

    factory = _get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(SymbolReference.symbol, SymbolReference.api_symbol).where(
                SymbolReference.api_symbol.isnot(None)
            )
        )
        rows = result.all()

    new_cache: dict[str, str] = {}
    for canonical, api_sym in rows:
        new_cache[canonical] = api_sym

    _api_symbol_cache.clear()
    _api_symbol_cache.update(new_cache)

    logger.info("symbol_cache: loaded %d api_symbol mappings", len(new_cache))
    return len(new_cache)


async def start_symbol_cache_refresh_task() -> asyncio.Task:
    """
    Populate the cache immediately, then schedule periodic refreshes.

    Call this from the lifespan startup, after init_db().
    Returns the background Task (caller should cancel it on shutdown).
    """
    try:
        await _refresh_api_symbol_cache()
    except Exception as exc:
        logger.warning("symbol_cache: initial load failed (cache empty, passthrough mode): %s", exc)

    async def _loop():
        while True:
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            try:
                await _refresh_api_symbol_cache()
            except Exception as exc:
                logger.warning("symbol_cache: refresh failed: %s", exc)

    return asyncio.create_task(_loop())


def to_api_symbol_cached(symbol: str, provider: str) -> str:
    """
    Sync helper: canonical → provider api_symbol using the in-memory cache.

    For Schwab, looks up the cached api_symbol mapping.
    For any other provider, returns the canonical form unchanged.

    Safe to call from any context — no db, no await.
    """
    canonical = canonicalize(symbol)
    if provider == "schwab":
        api_sym = _api_symbol_cache.get(canonical)
        if api_sym is not None:
            return api_sym
    return canonical
