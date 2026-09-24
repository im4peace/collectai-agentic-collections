"""Shared fixtures for `bt/evaluation/` tests: one embedded PostgreSQL
server per test session and a migrated schema. Mirrors `bt/api/conftest.py`
's embedded-postgres pattern rather than importing it, matching `bt/redteam
/conftest.py`'s and `bt/security/conftest.py`'s own copies of the same
convention.
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
_BUSINESS_TABLES: tuple[str, ...] = (
    "eval_case_result",
    "eval_run",
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
    pgdata = tmp_path_factory.mktemp("collectai_evaluation_pgdata", numbered=True)
    server = ep.get_server(str(pgdata), cleanup_mode="delete")
    server.ensure_pgdata_inited()
    server.ensure_postgres_running()
    yield server
    server.cleanup()


@pytest.fixture(scope="session")
def async_database_url(pg_server: ep.PostgresServer) -> str:
    return pg_server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture(scope="session")
def migrated_schema(async_database_url: str) -> str:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", async_database_url)
    command.upgrade(config, "head")
    return async_database_url


@pytest_asyncio.fixture
async def engine(migrated_schema: str, async_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(async_database_url, future=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def clean_db(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        table_list = ", ".join(_BUSINESS_TABLES)
        await conn.exec_driver_sql(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
    yield


@pytest_asyncio.fixture
async def policy_rule_set_row(session: AsyncSession, clean_db: None) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES ('policy-v1', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) "
            "ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"created_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC)},
    )
    await session.commit()
