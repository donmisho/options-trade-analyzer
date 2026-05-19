"""
Unit tests for app.services.symbol_cache — OTA-672.

Tests the sync cached helper and the cache refresh mechanism.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.database import Base, SymbolReference
from app.services.symbol_cache import (
    _api_symbol_cache,
    _refresh_api_symbol_cache,
    _set_session_factory,
    to_api_symbol_cached,
)

# ── In-memory async SQLite engine ─────────────────────────────────────────────

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop after. Clear cache."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _api_symbol_cache.clear()
    _set_session_factory(_test_session_factory)
    yield
    _api_symbol_cache.clear()
    _set_session_factory(None)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_with_fixtures(db: AsyncSession):
    db.add(SymbolReference(symbol="SPX", name="S&P 500 Index", api_symbol="$SPX"))
    db.add(SymbolReference(symbol="AAPL", name="Apple Inc.", api_symbol=None))
    db.add(SymbolReference(symbol="DJX", name="Dow Jones Index", api_symbol="$DJX"))
    await db.flush()
    await db.commit()
    return db


# ── to_api_symbol_cached tests (sync, pure cache lookup) ───────────────────


class TestToApiSymbolCached:
    def test_returns_canonical_when_cache_empty(self):
        assert to_api_symbol_cached("SPX", "schwab") == "SPX"

    def test_returns_canonical_for_non_schwab(self):
        _api_symbol_cache["SPX"] = "$SPX"
        assert to_api_symbol_cached("SPX", "finnhub") == "SPX"

    def test_returns_api_symbol_when_cached(self):
        _api_symbol_cache["SPX"] = "$SPX"
        assert to_api_symbol_cached("SPX", "schwab") == "$SPX"

    def test_canonicalizes_input(self):
        _api_symbol_cache["SPX"] = "$SPX"
        assert to_api_symbol_cached("$spx", "schwab") == "$SPX"

    def test_unmapped_symbol_returns_canonical(self):
        _api_symbol_cache["SPX"] = "$SPX"
        assert to_api_symbol_cached("AAPL", "schwab") == "AAPL"

    def test_multiple_mappings(self):
        _api_symbol_cache["SPX"] = "$SPX"
        _api_symbol_cache["DJX"] = "$DJX"
        assert to_api_symbol_cached("SPX", "schwab") == "$SPX"
        assert to_api_symbol_cached("DJX", "schwab") == "$DJX"
        assert to_api_symbol_cached("AAPL", "schwab") == "AAPL"


# ── _refresh_api_symbol_cache tests ─────────────────────────────────────────


class TestRefreshCache:
    @pytest.mark.asyncio
    async def test_loads_mappings(self, db_with_fixtures):
        count = await _refresh_api_symbol_cache()

        assert count == 2  # SPX and DJX have api_symbol; AAPL has None
        assert _api_symbol_cache["SPX"] == "$SPX"
        assert _api_symbol_cache["DJX"] == "$DJX"
        assert "AAPL" not in _api_symbol_cache

    @pytest.mark.asyncio
    async def test_clears_stale_entries(self, db_with_fixtures):
        _api_symbol_cache["OLD"] = "$OLD"
        count = await _refresh_api_symbol_cache()

        assert "OLD" not in _api_symbol_cache
        assert count == 2

    @pytest.mark.asyncio
    async def test_empty_table(self, db):
        count = await _refresh_api_symbol_cache()

        assert count == 0
        assert len(_api_symbol_cache) == 0


# ── Integration: refresh then cached lookup ─────────────────────────────────


class TestCacheIntegration:
    @pytest.mark.asyncio
    async def test_refresh_then_lookup(self, db_with_fixtures):
        await _refresh_api_symbol_cache()

        assert to_api_symbol_cached("SPX", "schwab") == "$SPX"
        assert to_api_symbol_cached("AAPL", "schwab") == "AAPL"
        assert to_api_symbol_cached("DJX", "schwab") == "$DJX"
        assert to_api_symbol_cached("SPX", "finnhub") == "SPX"
