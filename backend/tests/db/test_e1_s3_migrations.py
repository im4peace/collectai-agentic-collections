"""AC5: the schema is created by versioned migrations that apply cleanly to
an empty database and can be re-run without error."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.db

_ALL_23_TABLES: tuple[str, ...] = (
    "customer",
    "account",
    "delinquency_record",
    "delinquent_item",
    "interaction",
    "conversation",
    "chat_message",
    "chat_turn",
    "promise_to_pay",
    "payment_event",
    "payment_arrangement",
    "hardship_case",
    "dispute",
    "escalation_case",
    "review_decision",
    "proposal",
    "recommendation",
    "policy_rule_set",
    "demo_session",
    "idempotency_record",
    "clock_state",
    "eval_run",
    "eval_case_result",
)


@pytest.mark.asyncio
async def test_migrations_create_all_23_business_tables(
    migrated_schema: str, async_database_url: str
) -> None:
    engine = create_async_engine(async_database_url, future=True)
    try:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            table_names = {row[0] for row in result}
        missing = set(_ALL_23_TABLES) - table_names
        assert not missing, f"migrations did not create: {sorted(missing)}"
        assert "audit_event" not in table_names, "audit_event is E1-S4's table, not E1-S3's"
    finally:
        await engine.dispose()


def test_migrations_reapply_without_error(migrated_schema: str) -> None:
    """Running `alembic upgrade head` a second time against an
    already-migrated database must be a no-op, not an error."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    migrations_dir = (
        Path(__file__).resolve().parents[2] / "src" / "collectai" / "persistence" / "migrations"
    )
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", migrated_schema)

    command.upgrade(config, "head")  # must not raise
