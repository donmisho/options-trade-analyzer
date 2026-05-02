import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context

# Alembic Config object — access to values in alembic.ini.
config = context.config

# Set up logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the app's shared engine and Base metadata.
#
# WHY reuse the engine from session.py rather than calling async_engine_from_config:
# The session.py engine has the Azure SQL Entra ID token-injection event registered
# on it (do_connect handler that calls DefaultAzureCredential and packs the token
# into SQL_COPT_SS_ACCESS_TOKEN). A second engine built from alembic.ini would have
# no token injection, so every connection attempt would fail with an auth error.
# Reusing the same engine means Alembic inherits the full auth setup automatically.
#
# sqlalchemy.url in alembic.ini is intentionally left blank — the URL is determined
# by app/core/config.py (from .env or environment variables), not hardcoded here.
from app.models.database import Base
from app.models.session import engine as _app_engine
from app.core.config import settings

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation, no DB connection).

    Uses the app's database URL from settings rather than alembic.ini, which is
    intentionally blank.  Offline mode is useful for generating migration SQL to
    review before applying — it does not connect to the database.
    """
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations online using the app's shared async engine.

    The shared engine already has the Azure SQL Entra ID token-injection event
    registered (do_connect in session.py), so every new physical connection from
    the pool automatically receives a fresh AAD token — no extra auth setup needed.
    """
    async with _app_engine.connect() as connection:
        await connection.run_sync(do_run_migrations)


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
