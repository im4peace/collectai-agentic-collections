"""Alembic environment.

Migrations are written as raw, explicit DDL (`op.execute`) rather than
generated from ORM metadata, so every CHECK constraint, partial unique index,
composite FK and trigger in data-models.md is expressed exactly as specified
(SQLAlchemy's autogenerate cannot express triggers or `CHECK ... ~` id
patterns). `target_metadata` is left `None` accordingly; `--autogenerate` is
not a supported workflow for this project.

Runs migrations with a real `AsyncEngine` (asyncpg), per the async-Alembic
pattern, so the same driver scheme is used here as in the running
application (`db.py`) — never a sync driver against an async-scheme URL.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database using an `AsyncEngine`."""
    connectable: AsyncEngine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
