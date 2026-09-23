"""Shared fixtures for `bt/api/` tests: one embedded PostgreSQL server per
test session, a migrated schema, a `TestClient` wired to `create_app` with a
`SimulatedClock`, and a seeded demo customer for CUSTOMER-persona tests.

Mirrors `bt/db/conftest.py`'s embedded-postgres pattern rather than
importing it, so `bt/api/` stays independently runnable and does not risk
perturbing `bt/db/`'s fixtures (a story unrelated to this one owns that
file).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import embedded_postgres as ep
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from collectai.api.app import create_app
from collectai.config.settings import Settings
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import LlmMode, Persona

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "collectai" / "persistence" / "migrations"
)
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
NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
SEEDED_CUSTOMER_ID = "cus_000101"


@pytest.fixture(scope="session")
def pg_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ep.PostgresServer]:
    pgdata = tmp_path_factory.mktemp("collectai_api_pgdata", numbered=True)
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
async def seeded_customer_id(engine: AsyncEngine, clean_db: None) -> str:
    """One seeded customer with one account, for CUSTOMER-persona session
    creation (api-contracts.md `POST /api/session`)."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        db_session.add(
            CustomerOrm(
                customer_id=SEEDED_CUSTOMER_ID,
                display_name="Jordan Rivera",
                email="jordan.rivera@example.com",
                phone="+1-555-0101",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        # Flushed (not just added) before the account insert: neither ORM
        # class declares a SQLAlchemy `ForeignKey` (data-models.md's FKs are
        # enforced purely by migration-level DDL, per persistence/orm's own
        # convention), so the unit of work has no dependency information to
        # order these two inserts on its own -- an unflushed customer row
        # can otherwise be sent to the database after the account row that
        # references it, violating `account_customer_id_fkey`.
        await db_session.flush()
        db_session.add(
            AccountOrm(
                account_id="acc_000101",
                customer_id=SEEDED_CUSTOMER_ID,
                account_type="CARD",
                product_name="Everyday Card",
                currency="USD",
                opened_on=NOW.date(),
                product_attributes={},
                created_at=NOW,
            )
        )
        await db_session.commit()
    return SEEDED_CUSTOMER_ID


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def api_client(migrated_schema: str, clock: SimulatedClock, clean_db: None) -> Iterator[TestClient]:
    settings = Settings(
        llm_mode=LlmMode.MOCK,
        anthropic_model=None,
        anthropic_api_key=None,
        tool_call_cap_per_turn=5,
        ai_retry_bound=1,
        max_clarification_turns=2,
        chat_rate_limit_per_minute=20,
        api_rate_limit_per_minute=300,
        provider_timeout_seconds=20,
        proposal_ttl_minutes=30,
        demo_controls_enabled=False,
        database_url=migrated_schema,
    )
    app = create_app(settings, clock=clock)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def customer_session_headers(
    api_client: TestClient, seeded_customer_id: str
) -> dict[str, str]:
    """A real `X-Persona`/`X-Demo-Session` header pair for `seeded_customer_id`,
    obtained through `POST /api/session` itself (not by hand-hashing a
    token), so tests exercise the same path a real client would."""
    response = api_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": seeded_customer_id}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}
