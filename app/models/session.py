"""
Database engine and session management.

WHY async: FastAPI is an async framework. Using async SQLAlchemy means database
queries don't block other requests. With SQLite this doesn't matter much, but
when we upgrade to PostgreSQL for multi-user, it becomes essential.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.database import Base

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL queries in debug mode
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables. Called once at app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """
    Dependency that provides a database session per request.
    
    Usage in endpoints:
        @router.get("/something")
        async def get_something(db: AsyncSession = Depends(get_db)):
            ...
    
    WHY Depends: FastAPI's dependency injection ensures each request gets its
    own session, and the session is properly closed when the request finishes,
    even if there's an error.
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
