"""
Unit tests for app.services.symbol_normalization — OTA-668 Phase 3b.2.

Uses in-memory SQLite with aiosqlite, matching the project's existing
test pattern (see tests/test_data_isolation_contract.py).
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.database import Base, SymbolReference
from app.services.symbol_normalization import canonicalize, to_api_symbol, from_api_symbol

# ── In-memory async SQLite engine ─────────────────────────────────────────────

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop after."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Yield an AsyncSession for test use."""
    async with _session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_with_fixtures(db: AsyncSession):
    """Seed symbol_reference with test rows."""
    db.add(SymbolReference(symbol="SPX", name="S&P 500 Index", api_symbol="$SPX"))
    db.add(SymbolReference(symbol="AAPL", name="Apple Inc.", api_symbol=None))
    db.add(SymbolReference(symbol="DJX", name="Dow Jones Index", api_symbol="$DJX"))
    await db.flush()
    return db


# ── canonicalize tests ────────────────────────────────────────────────────────


class TestCanonicalize:
    def test_strips_dollar_prefix(self):
        assert canonicalize("$SPX") == "SPX"

    def test_uppercases(self):
        assert canonicalize("spx") == "SPX"

    def test_strips_whitespace(self):
        assert canonicalize("  SPX  ") == "SPX"

    def test_idempotent(self):
        assert canonicalize("SPX") == "SPX"

    def test_dollar_only(self):
        assert canonicalize("$") == ""

    def test_empty_string(self):
        assert canonicalize("") == ""

    def test_combined(self):
        assert canonicalize("  $spx  ") == "SPX"

    def test_multiple_dollars(self):
        assert canonicalize("$$SPX") == "SPX"


# ── to_api_symbol tests ──────────────────────────────────────────────────────


class TestToApiSymbol:
    @pytest.mark.asyncio
    async def test_schwab_with_mapping(self, db_with_fixtures):
        result = await to_api_symbol(db_with_fixtures, "SPX", "schwab")
        assert result == "$SPX"

    @pytest.mark.asyncio
    async def test_schwab_no_mapping(self, db_with_fixtures):
        result = await to_api_symbol(db_with_fixtures, "AAPL", "schwab")
        assert result == "AAPL"

    @pytest.mark.asyncio
    async def test_non_schwab_provider_ignores_mapping(self, db_with_fixtures):
        result = await to_api_symbol(db_with_fixtures, "SPX", "finnhub")
        assert result == "SPX"

    @pytest.mark.asyncio
    async def test_unknown_symbol(self, db):
        result = await to_api_symbol(db, "ZZZZ", "schwab")
        assert result == "ZZZZ"

    @pytest.mark.asyncio
    async def test_canonicalizes_input(self, db_with_fixtures):
        result = await to_api_symbol(db_with_fixtures, "$spx", "schwab")
        assert result == "$SPX"


# ── from_api_symbol tests ────────────────────────────────────────────────────


class TestFromApiSymbol:
    @pytest.mark.asyncio
    async def test_reverse_lookup(self, db_with_fixtures):
        result = await from_api_symbol(db_with_fixtures, "$SPX")
        assert result == "SPX"

    @pytest.mark.asyncio
    async def test_no_matching_row(self, db):
        result = await from_api_symbol(db, "MSFT")
        assert result == "MSFT"

    @pytest.mark.asyncio
    async def test_no_matching_row_canonicalizes(self, db):
        result = await from_api_symbol(db, "$UNKNOWN")
        assert result == "UNKNOWN"


# ── Round-trip identity tests ────────────────────────────────────────────────


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_round_trip_with_mapping(self, db_with_fixtures):
        """from_api_symbol(to_api_symbol(s, "schwab")) == s for mapped symbol."""
        api_form = await to_api_symbol(db_with_fixtures, "SPX", "schwab")
        canonical = await from_api_symbol(db_with_fixtures, api_form)
        assert canonical == "SPX"

    @pytest.mark.asyncio
    async def test_round_trip_without_mapping(self, db_with_fixtures):
        """from_api_symbol(to_api_symbol(s, "schwab")) == s for unmapped symbol."""
        api_form = await to_api_symbol(db_with_fixtures, "AAPL", "schwab")
        canonical = await from_api_symbol(db_with_fixtures, api_form)
        assert canonical == "AAPL"

    @pytest.mark.asyncio
    async def test_round_trip_all_fixtures(self, db_with_fixtures):
        """Round-trip identity holds for every canonical symbol in test set."""
        for sym in ["SPX", "AAPL", "DJX"]:
            api_form = await to_api_symbol(db_with_fixtures, sym, "schwab")
            canonical = await from_api_symbol(db_with_fixtures, api_form)
            assert canonical == sym, f"Round-trip failed for {sym}"
