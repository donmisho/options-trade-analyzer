"""
Data Isolation Contract Test — OTA-542

Verifies that every CRUD endpoint with a resource ID filters by user_id.
Cross-user attempts must return 404 (not 403) and must not leak any resource data.

Pattern:
  1. As user A, create a resource.
  2. As user B, attempt GET / PUT / PATCH / DELETE on user A's resource ID.
  3. Assert response status == 404.
  4. Assert response body does NOT contain any field from the resource (no leak).

Uses an in-memory SQLite DB with transactional rollback. No dev DB is touched.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.database import Base, TradeRecommendation, NamedWatchlist, WatchlistEntry, \
    UserWatchlist, UserFavorite, Position

USER_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# ── Test DB engine (in-memory SQLite) ────────────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def _get_test_db():
    async with _test_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


def _make_user_dep(user_id: str):
    """Return a FastAPI dependency that simulates a logged-in user."""
    async def _dep():
        return {"sub": user_id, "username": "test", "role": "admin", "mfa": True}
    return _dep


def _build_app(user_id: str) -> FastAPI:
    """Build a minimal FastAPI app with auth overridden to the given user_id."""
    from app.auth.dependencies import require_read, require_write, get_current_user
    from app.models.session import get_db

    from app.api.agent_routes import router as agent_router
    from app.api.named_watchlist_routes import router as named_watchlist_router
    from app.api.watchlist_routes import router as watchlist_router
    from app.api.user_routes import router as user_router
    from app.api.position_routes import router as position_router
    from app.api.dashboard_routes import router as dashboard_router
    from app.api.config_routes import router as config_router
    from app.api.insight_routes import router as insight_router

    app = FastAPI()
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(named_watchlist_router, prefix="/api/v1")
    app.include_router(watchlist_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(position_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(insight_router, prefix="/api/v1")

    user_dep = _make_user_dep(user_id)
    app.dependency_overrides[require_read] = user_dep
    app.dependency_overrides[require_write] = user_dep
    app.dependency_overrides[get_current_user] = user_dep
    app.dependency_overrides[get_db] = _get_test_db

    return app


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client_a():
    app = _build_app(USER_A_ID)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_b():
    app = _build_app(USER_B_ID)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _assert_no_leak(response, *forbidden_strings):
    """Assert that the response body does not contain any of the forbidden strings."""
    body = response.text
    for s in forbidden_strings:
        assert s not in body, f"Response leaked data: found '{s}' in body"


# ── Recommendations (agent_routes) ───────────────────────────────────────────

class TestRecommendationIsolation:
    """DELETE /recommendations/{trade_key} was the known bug (OTA-542)."""

    TRADE_KEY = "AAPL|bull_call|100|110|2026-06-20"

    async def _seed_recommendation(self):
        """Insert a recommendation for USER_A directly in DB."""
        async with _test_session_factory() as db:
            rec = TradeRecommendation(
                user_id=USER_A_ID,
                trade_key=self.TRADE_KEY,
                symbol="AAPL",
                spread_label="Bull Call 100/110",
                expiration="2026-06-20",
                verdict="STRONG",
                verdict_summary="Looks great",
                rank="A",
                market_snapshot={"price": 200},
                trade_snapshot={"legs": []},
            )
            db.add(rec)
            await db.commit()

    @pytest.mark.asyncio
    async def test_get_recommendation_cross_user_returns_404(self, client_a, client_b):
        await self._seed_recommendation()
        # User A can see it
        resp = await client_a.get(f"/api/v1/agent/recommendations/{self.TRADE_KEY}")
        assert resp.status_code == 200

        # User B cannot
        resp = await client_b.get(f"/api/v1/agent/recommendations/{self.TRADE_KEY}")
        assert resp.status_code == 404
        _assert_no_leak(resp, "STRONG BUY", "Looks great", "Bull Call")

    @pytest.mark.asyncio
    async def test_put_recommendation_cross_user_returns_404(self, client_a, client_b):
        await self._seed_recommendation()
        resp = await client_b.put(
            f"/api/v1/agent/recommendations/{self.TRADE_KEY}",
            json={"verdict": "SELL", "verdict_summary": "Changed my mind"},
        )
        assert resp.status_code == 404
        _assert_no_leak(resp, "STRONG BUY", "Looks great")

    @pytest.mark.asyncio
    async def test_delete_recommendation_cross_user_returns_404(self, client_a, client_b):
        await self._seed_recommendation()
        # User B tries to delete user A's recommendation
        resp = await client_b.delete(f"/api/v1/agent/recommendations/{self.TRADE_KEY}")
        assert resp.status_code == 404
        _assert_no_leak(resp, "STRONG BUY", "Looks great")

        # User A can still see it (was not deleted)
        resp = await client_a.get(f"/api/v1/agent/recommendations/{self.TRADE_KEY}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_recommendation_own_user_succeeds(self, client_a, client_b):
        await self._seed_recommendation()
        resp = await client_a.delete(f"/api/v1/agent/recommendations/{self.TRADE_KEY}")
        assert resp.status_code == 204


# ── Named Watchlists ─────────────────────────────────────────────────────────

class TestNamedWatchlistIsolation:

    async def _seed_watchlist(self) -> str:
        """Insert a named watchlist for USER_A, return its ID."""
        wl_id = str(uuid.uuid4())
        async with _test_session_factory() as db:
            wl = NamedWatchlist(
                id=wl_id,
                user_id=USER_A_ID,
                name="My Secret Watchlist",
                is_default=False,
            )
            db.add(wl)
            # Also add a symbol
            db.add(WatchlistEntry(watchlist_id=wl_id, symbol="TSLA"))
            await db.commit()
        return wl_id

    @pytest.mark.asyncio
    async def test_rename_watchlist_cross_user_returns_404(self, client_a, client_b):
        wl_id = await self._seed_watchlist()
        resp = await client_b.put(
            f"/api/v1/watchlists/{wl_id}",
            json={"name": "Hacked Name"},
        )
        assert resp.status_code == 404
        _assert_no_leak(resp, "My Secret Watchlist")

    @pytest.mark.asyncio
    async def test_delete_watchlist_cross_user_returns_404(self, client_a, client_b):
        wl_id = await self._seed_watchlist()
        resp = await client_b.delete(f"/api/v1/watchlists/{wl_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_symbols_cross_user_returns_404(self, client_a, client_b):
        wl_id = await self._seed_watchlist()
        resp = await client_b.get(f"/api/v1/watchlists/{wl_id}/symbols")
        assert resp.status_code == 404
        _assert_no_leak(resp, "TSLA")

    @pytest.mark.asyncio
    async def test_add_symbol_cross_user_returns_404(self, client_a, client_b):
        wl_id = await self._seed_watchlist()
        resp = await client_b.post(
            f"/api/v1/watchlists/{wl_id}/symbols",
            json={"symbol": "NVDA"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_symbol_cross_user_returns_404(self, client_a, client_b):
        wl_id = await self._seed_watchlist()
        resp = await client_b.delete(f"/api/v1/watchlists/{wl_id}/symbols/TSLA")
        assert resp.status_code == 404


# ── Legacy Watchlist (watchlist_routes) ──────────────────────────────────────

class TestLegacyWatchlistIsolation:

    async def _seed_watchlist(self):
        async with _test_session_factory() as db:
            db.add(UserWatchlist(user_id=USER_A_ID, symbol="MSFT", position=0))
            await db.commit()

    @pytest.mark.asyncio
    async def test_delete_symbol_cross_user_returns_404(self, client_a, client_b):
        await self._seed_watchlist()
        resp = await client_b.delete("/api/v1/watchlist/MSFT")
        assert resp.status_code == 404

        # User A's symbol is still there
        resp = await client_a.get("/api/v1/watchlist")
        assert resp.status_code == 200
        assert "MSFT" in resp.text


# ── Favorites (user_routes) ─────────────────────────────────────────────────

class TestFavoritesIsolation:

    TRADE_ID = "GOOG|bear_put|150|140|2026-07-18"

    async def _seed_favorite(self):
        async with _test_session_factory() as db:
            db.add(UserFavorite(
                user_id=USER_A_ID,
                trade_id=self.TRADE_ID,
                symbol="GOOG",
                label="Bear Put 150/140",
                strategy="bear_put",
                trade_data={"legs": []},
            ))
            await db.commit()

    @pytest.mark.asyncio
    async def test_delete_favorite_cross_user_returns_404(self, client_a, client_b):
        await self._seed_favorite()
        resp = await client_b.delete(f"/api/v1/user/favorites/{self.TRADE_ID}")
        assert resp.status_code == 404
        _assert_no_leak(resp, "GOOG", "Bear Put")

        # User A's favorite still exists
        resp = await client_a.get("/api/v1/user/favorites")
        assert resp.status_code == 200
        assert "GOOG" in resp.text


# ── Positions ────────────────────────────────────────────────────────────────

class TestPositionIsolation:

    async def _seed_position(self) -> str:
        pos_id = str(uuid.uuid4())
        async with _test_session_factory() as db:
            db.add(Position(
                position_id=pos_id,
                user_id=USER_A_ID,
                symbol="AMZN",
                strategy_key="steady-paycheck",
                trade_structure=json.dumps({"legs": [{"strike": 200, "option_type": "put", "side": "short"}]}),
                source="PAPER",
                status="FOLLOWING",
                entry_price=3.50,
                entry_date=datetime.now(timezone.utc),
            ))
            await db.commit()
        return pos_id

    @pytest.mark.asyncio
    async def test_get_position_cross_user_returns_404(self, client_a, client_b):
        pos_id = await self._seed_position()
        # User A can see it
        resp = await client_a.get(f"/api/v1/positions/{pos_id}")
        assert resp.status_code == 200

        # User B cannot
        resp = await client_b.get(f"/api/v1/positions/{pos_id}")
        assert resp.status_code == 404
        _assert_no_leak(resp, "AMZN", "steady-paycheck", "3.50")

    @pytest.mark.asyncio
    async def test_close_position_cross_user_returns_404(self, client_a, client_b):
        pos_id = await self._seed_position()
        resp = await client_b.patch(
            f"/api/v1/positions/{pos_id}/close",
            json={"exit_price": 1.00, "exit_reason": "MANUAL"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_position_cross_user_returns_404(self, client_a, client_b):
        pos_id = await self._seed_position()
        resp = await client_b.patch(f"/api/v1/positions/{pos_id}/archive")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_assessments_cross_user_returns_404(self, client_a, client_b):
        pos_id = await self._seed_position()
        resp = await client_b.get(f"/api/v1/positions/{pos_id}/assessments")
        assert resp.status_code == 404
