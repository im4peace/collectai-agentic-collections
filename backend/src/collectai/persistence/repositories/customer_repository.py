"""Customer repository. Customer is the ownership root, not itself
customer-owned, so it does not subclass `CustomerScopedRepository`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, Table, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm

_DEMO_CUSTOMER_LIMIT = 25


@dataclass(frozen=True, slots=True)
class DemoCustomerRow:
    """One row of `GET /api/session/options`'s `demo_customers` (E3-S1;
    api-contracts.md `DemoCustomer`)."""

    customer_id: str
    display_name: str
    account_count: int


class CustomerRepository:
    async def get_by_id(self, session: AsyncSession, customer_id: str) -> CustomerOrm | None:
        stmt = select(CustomerOrm).where(CustomerOrm.customer_id == customer_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_demo_customers(self, session: AsyncSession) -> list[DemoCustomerRow]:
        """First 25 seeded customers with at least one account, ordered by
        `customer_id` for a stable switcher list (api-contracts.md
        `SessionOptionsResponse.demo_customers`)."""
        stmt = (
            select(
                CustomerOrm.customer_id,
                CustomerOrm.display_name,
                func.count(AccountOrm.account_id).label("account_count"),
            )
            .join(AccountOrm, AccountOrm.customer_id == CustomerOrm.customer_id)
            .group_by(CustomerOrm.customer_id, CustomerOrm.display_name)
            .order_by(CustomerOrm.customer_id)
            .limit(_DEMO_CUSTOMER_LIMIT)
        )
        rows = (await session.execute(stmt)).all()
        return [
            DemoCustomerRow(
                customer_id=row.customer_id,
                display_name=row.display_name,
                account_count=row.account_count,
            )
            for row in rows
        ]

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
