"""AC2: Money columns are PostgreSQL NUMERIC and a Decimal('0.10') round-trip
is exact. This test exercises `orm/types.py::MoneyType` directly against a
real embedded PostgreSQL, ahead of and independent from the migrated schema,
to validate the whole DB test harness early (process step (a) of E1-S3).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.ext.asyncio import create_async_engine

from collectai.persistence.orm.types import MoneyType
from collectai.types.money import Money

pytestmark = pytest.mark.db


@pytest.mark.asyncio
async def test_money_round_trips_exactly_through_numeric_column(async_database_url: str) -> None:
    engine = create_async_engine(async_database_url, future=True)
    metadata = MetaData()
    probe_table = Table(
        "money_type_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", MoneyType),
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(probe_table.insert().values(id=1, amount=Money("0.10")))

        async with engine.connect() as conn:
            row = (await conn.execute(probe_table.select())).one()

        assert isinstance(row.amount, Money)
        assert row.amount.amount == Decimal("0.10")
        assert row.amount == Money("0.10")
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_money_column_is_numeric_14_2_in_information_schema(
    async_database_url: str,
) -> None:
    engine = create_async_engine(async_database_url, future=True)
    metadata = MetaData()
    Table(
        "money_type_probe_schema",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", MoneyType),
    )  # registers with `metadata` as a side effect; `create_all` below picks it up
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "SELECT data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns "
                "WHERE table_name = 'money_type_probe_schema' AND column_name = 'amount'"
            )
            data_type, precision, scale = result.one()

        assert data_type == "numeric"
        assert precision == 14
        assert scale == 2
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()
