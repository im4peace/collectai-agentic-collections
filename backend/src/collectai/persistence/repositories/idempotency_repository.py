"""IdempotencyRecord repository (E5-S4). Not customer-scoped -- the table
has no `customer_id` column (data-models.md IdempotencyRecord) -- so this is
a small standalone repository rather than a `CustomerScopedRepository`
subclass.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.idempotency_record import IdempotencyRecordOrm


class IdempotencyRepository:
    async def get_by_scope_and_key(
        self, session: AsyncSession, scope: str, idempotency_key: str
    ) -> IdempotencyRecordOrm | None:
        stmt = select(IdempotencyRecordOrm).where(
            IdempotencyRecordOrm.scope == scope,
            IdempotencyRecordOrm.idempotency_key == idempotency_key,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def create(
        self, session: AsyncSession, entity: IdempotencyRecordOrm
    ) -> IdempotencyRecordOrm:
        session.add(entity)
        await session.flush()
        return entity
