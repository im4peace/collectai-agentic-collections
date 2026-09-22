"""Shared fixtures for `bt/db/` tests: one embedded PostgreSQL server per test
session, a migrated schema, and per-test isolation via table truncation.

Starting a fresh embedded-postgres cluster takes several seconds, so the
server itself is session-scoped (started once). Each test that needs a clean
slate depends on `clean_db`, which truncates every business table before the
test body runs, instead of re-running migrations or restarting the server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import embedded_postgres as ep
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "collectai" / "persistence" / "migrations"
)

# Tables truncated between tests, in an order that respects FK dependencies
# (children before parents). Kept in one place so a new ORM-mapped table only
# needs one edit.
_BUSINESS_TABLES: tuple[str, ...] = (
    "review_decision",
    "escalation_case",
    "dispute",
    "hardship_case",
    "payment_arrangement",
    "payment_event",
    "promise_to_pay",
    "proposal",
    "chat_turn",
    "chat_message",
    "conversation",
    "interaction",
    "delinquent_item",
    "delinquency_record",
    "account",
    "customer",
    "idempotency_record",
    "demo_session",
)


@pytest.fixture(scope="session")
def pg_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ep.PostgresServer]:
    """Start one embedded PostgreSQL server for the whole `bt/db/` session."""
    pgdata = tmp_path_factory.mktemp("collectai_pgdata", numbered=True)
    server = ep.get_server(str(pgdata), cleanup_mode="delete")
    server.ensure_pgdata_inited()
    server.ensure_postgres_running()
    yield server
    server.cleanup()


@pytest.fixture(scope="session")
def async_database_url(pg_server: ep.PostgresServer) -> str:
    """The asyncpg-scheme URL used by the application's async engine."""
    raw_uri = pg_server.get_uri()
    return raw_uri.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture(scope="session")
def migrated_schema(async_database_url: str) -> str:
    """Apply every migration once for the session; returns the URL used.

    Alembic's `env.py` runs migrations with a real `AsyncEngine` (matching
    the application's driver scheme), invoked here via `command.upgrade`
    from a synchronous, session-scoped fixture so `env.py`'s internal
    `asyncio.run(...)` never collides with pytest-asyncio's own event loop.
    """
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", async_database_url)
    command.upgrade(config, "head")
    return async_database_url


@pytest_asyncio.fixture
async def engine(migrated_schema: str, async_database_url: str) -> AsyncIterator[AsyncEngine]:
    """A function-scoped async engine bound to the migrated database.

    Function-scoped (not session-scoped) deliberately: pytest-asyncio's
    default "auto" mode gives each test function its own event loop, and
    asyncpg connections cannot be reused across event loops (it raises
    `InterfaceError: another operation is in progress` when they are). The
    migration itself still runs only once per session, via `migrated_schema`.
    """
    eng = create_async_engine(async_database_url, future=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A fresh `AsyncSession` per test."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def clean_db(engine: AsyncEngine) -> AsyncIterator[None]:
    """Truncate every business table before the test body runs."""
    async with engine.begin() as conn:
        table_list = ", ".join(_BUSINESS_TABLES)
        await conn.exec_driver_sql(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
    yield
