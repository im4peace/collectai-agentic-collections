"""DelinquencyRecord repository: 1:1 with Account, PK is `account_id`, and
every update increments `record_version` (AC7)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Table, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
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

    async def refresh_all_snapshots(self, session: AsyncSession, *, now: datetime) -> int:
        """E9-S3 AC2 `refresh_snapshots`: marks every delinquency record's
        snapshot as freshly reviewed at `now` -- `dpd`/`bucket`/`overdue_
        amount` are never recomputed here (no core-sync/DPD recomputation
        service exists, CLAUDE.md's documented known item), only `as_of`/
        `updated_at` are touched; migration 0001's own `BEFORE UPDATE`
        trigger bumps `record_version` for every row regardless of which
        columns changed, so `rules_engine.freshness.check_freshness`'s
        `snapshot_version == current_record.record_version` check still
        holds immediately afterward. Returns the number of rows touched."""
        stmt = update(DelinquencyRecordOrm).values(as_of=now, updated_at=now)
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0

    async def list_portfolio_candidates(
        self,
        session: AsyncSession,
        *,
        dpd_min: int | None,
        dpd_max: int | None,
        statuses: Sequence[str] | None,
    ) -> Sequence[tuple[DelinquencyRecordOrm, AccountOrm, CustomerOrm]]:
        """SQL-filterable slice of the portfolio query (E3-S2 AC1-AC2):
        joins `delinquency_record` to `account` and `customer`, filtering
        only what is directly stored -- `overdue_amount > 0` (api-contracts.md
        3.3: "Only accounts with overdue_amount > 0 are listed"), the `dpd`
        range and `collection_status`. `priority_band` has no column: it is
        a computed value (data-models.md), filtered in Python by
        `domain_services.portfolio_service` once each candidate has been
        scored by `rules_engine.priority`."""
        stmt = (
            select(DelinquencyRecordOrm, AccountOrm, CustomerOrm)
            .join(AccountOrm, AccountOrm.account_id == DelinquencyRecordOrm.account_id)
            .join(CustomerOrm, CustomerOrm.customer_id == DelinquencyRecordOrm.customer_id)
            .where(DelinquencyRecordOrm.overdue_amount > Money("0"))
        )
        if dpd_min is not None:
            stmt = stmt.where(DelinquencyRecordOrm.dpd >= dpd_min)
        if dpd_max is not None:
            stmt = stmt.where(DelinquencyRecordOrm.dpd <= dpd_max)
        if statuses:
            stmt = stmt.where(DelinquencyRecordOrm.collection_status.in_(statuses))
        result = await session.execute(stmt)
        return [(record, account, customer) for record, account, customer in result.all()]
