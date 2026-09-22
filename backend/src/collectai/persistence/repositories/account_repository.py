"""Account repository (customer-owned, AC6)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class AccountRepository(CustomerScopedRepository[AccountOrm]):
    def __init__(self) -> None:
        super().__init__(AccountOrm)

    async def get_by_id_for_customer(
        self, session: AsyncSession, account_id: str, customer_id: str
    ) -> AccountOrm | None:
        """Scoped read: an account that belongs to a different customer is
        indistinguishable from a missing one (AC6)."""
        stmt = select(AccountOrm).where(
            AccountOrm.account_id == account_id, AccountOrm.customer_id == customer_id
        )
        return (await session.execute(stmt)).scalar_one_or_none()
