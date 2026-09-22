"""DelinquencyRecord repository: 1:1 with Account, PK is `account_id`, and
every update increments `record_version` (AC7)."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.repositories.base import CustomerScopedRepository
from collectai.persistence.repositories.concurrency import optimistic_update
from collectai.types.money import Money


class DelinquencyRecordRepository(CustomerScopedRepository[DelinquencyRecordOrm]):
    def __init__(self) -> None:
        super().__init__(DelinquencyRecordOrm)

    async def get_by_account(
        self, session: AsyncSession, account_id: str, customer_id: str
    ) -> DelinquencyRecordOrm | None:
        stmt = select(DelinquencyRecordOrm).where(
            DelinquencyRecordOrm.account_id == account_id,
            DelinquencyRecordOrm.customer_id == customer_id,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def update_snapshot(
        self,
        session: AsyncSession,
        *,
        account_id: str,
        customer_id: str,
        expected_version: int,
        outstanding_balance: Money,
        overdue_amount: Money,
        dpd: int,
        bucket: str,
        collection_status: str,
        as_of: datetime | None,
        updated_at: datetime,
    ) -> bool:
        """AC7: every update increments `record_version`. Uses the shared
        optimistic-concurrency helper; the `delinquency_record` BEFORE UPDATE
        trigger (migration 0001) also enforces monotonicity as defence in
        depth, independent of the value this method passes."""
        return await optimistic_update(
            session,
            cast(Table, DelinquencyRecordOrm.__table__),
            pk_conditions={"account_id": account_id, "customer_id": customer_id},
            version_column="record_version",
            expected_version=expected_version,
            values={
                "outstanding_balance": outstanding_balance,
                "overdue_amount": overdue_amount,
                "dpd": dpd,
                "bucket": bucket,
                "collection_status": collection_status,
                "as_of": as_of,
                "updated_at": updated_at,
                "record_version": expected_version + 1,
            },
        )
