"""Customer repository. Customer is the ownership root, not itself
customer-owned, so it does not subclass `CustomerScopedRepository`."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.customer import CustomerOrm


class CustomerRepository:
    async def get_by_id(self, session: AsyncSession, customer_id: str) -> CustomerOrm | None:
        stmt = select(CustomerOrm).where(CustomerOrm.customer_id == customer_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def create(self, session: AsyncSession, entity: CustomerOrm) -> CustomerOrm:
        session.add(entity)
        await session.flush()
        return entity

    async def bulk_upsert_ignore_conflicts(
        self, session: AsyncSession, rows: list[dict[str, Any]]
    ) -> int:
        """Idempotent bulk insert for seed data (AC1)."""
        if not rows:
            return 0
        stmt = (
            pg_insert(cast(Table, CustomerOrm.__table__))
            .values(rows)
            .on_conflict_do_nothing(index_elements=["customer_id"])
        )
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0
