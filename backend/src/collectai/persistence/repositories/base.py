"""Generic base for a customer-owned table's repository.

Per data-models.md section 1 ("Ownership"): customer-facing repositories
expose only methods that take the session-bound `customer_id` as a mandatory
argument and always add `WHERE customer_id = :bound`, so a row that is not
the customer's is indistinguishable from a missing row (AC6). Every
per-entity repository in this package subclasses this instead of
re-implementing the same list/create/bulk-upsert logic 11 times.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import CursorResult, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.base import Base

OrmT = TypeVar("OrmT", bound=Base)


class CustomerScopedRepository(Generic[OrmT]):
    """Base repository for a table that carries a `customer_id` column."""

    def __init__(self, orm_class: type[OrmT]) -> None:
        self._orm_class = orm_class

    async def list_by_customer(self, session: AsyncSession, customer_id: str) -> Sequence[OrmT]:
        """Every row for `customer_id`, scoped by the mandatory bound id
        (AC6): a differently-owned row is never returned, ever."""
        stmt = select(self._orm_class).where(self._orm_class.customer_id == customer_id)  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return result.scalars().all()

    async def list_by_account_for_customer(
        self, session: AsyncSession, account_id: str, customer_id: str
    ) -> Sequence[OrmT]:
        """Every row for `account_id`, additionally scoped by `customer_id`
        (AC6): a row on someone else's account is never returned even if the
        caller somehow guessed a valid `account_id`."""
        stmt = select(self._orm_class).where(
            self._orm_class.account_id == account_id,  # type: ignore[attr-defined]
            self._orm_class.customer_id == customer_id,  # type: ignore[attr-defined]
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def create(self, session: AsyncSession, entity: OrmT) -> OrmT:
        session.add(entity)
        await session.flush()
        return entity

    async def bulk_upsert_ignore_conflicts(
        self,
        session: AsyncSession,
        rows: list[dict[str, Any]],
        *,
        pk_columns: list[str],
    ) -> int:
        """Idempotent bulk insert for seed data: `INSERT ... ON CONFLICT DO
        NOTHING` on the deterministic seed ids (AC1). Returns the number of
        rows actually inserted (0 on a fully-conflicting replay)."""
        if not rows:
            return 0
        table = cast(Table, self._orm_class.__table__)
        stmt = pg_insert(table).values(rows).on_conflict_do_nothing(index_elements=pk_columns)
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0

    async def bulk_upsert_update_on_conflict(
        self,
        session: AsyncSession,
        rows: list[dict[str, Any]],
        *,
        pk_columns: list[str],
    ) -> int:
        """E9-S3's `reseed` demo control: `INSERT ... ON CONFLICT DO UPDATE`
        on the deterministic seed ids, overwriting every non-pk column back
        to its seeded value. Deliberately UPDATE, never `DELETE` +
        re-`INSERT`: `collectai_app` holds no `DELETE` grant on any table
        (`deploy/db/init-roles.sql`'s own least-privilege design,
        CLAUDE.md), so a real "restore the seeded dataset" for this
        deployment can only ever be an UPDATE-based reset of the rows it is
        allowed to touch -- never a literal delete-and-reload."""
        if not rows:
            return 0
        table = cast(Table, self._orm_class.__table__)
        update_columns = [col for col in rows[0] if col not in pk_columns]
        stmt = pg_insert(table).values(rows)
        if update_columns:
            stmt = stmt.on_conflict_do_update(
                index_elements=pk_columns,
                set_={col: stmt.excluded[col] for col in update_columns},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0
