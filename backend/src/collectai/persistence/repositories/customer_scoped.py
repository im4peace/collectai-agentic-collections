"""Generic object-level authorization primitives (api-contracts.md 1.5.2,
E3-S5 AC2/AC3). Module-level functions, not a class: every `/api/me/*`
single-resource handler in `api/routers/me.py` composes the same two
lookups regardless of which table it targets, so there is nothing here
worth attaching per-entity state to.

`orm_class` and `pk_column` are always passed together (e.g. `PromiseToPayOrm`,
`PromiseToPayOrm.ptp_id`) rather than the primary key being looked up by
string name, so a typo in a column name is a type error, not a silent
always-empty query.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from collectai.persistence.orm.base import Base

OrmT = TypeVar("OrmT", bound=Base)


async def find_owned_by_id(
    session: AsyncSession,
    orm_class: type[OrmT],
    pk_column: InstrumentedAttribute[str],
    pk_value: str,
    customer_id: str,
) -> OrmT | None:
    """Scoped lookup: `SELECT ... WHERE pk = :pk AND customer_id = :bound`.
    A row owned by a different customer is indistinguishable from a missing
    row -- this is the only read path a `/api/me/*` handler may use to
    return resource data to the caller (AC2, AC3)."""
    stmt = select(orm_class).where(
        pk_column == pk_value,
        orm_class.customer_id == customer_id,  # type: ignore[attr-defined]
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def exists_regardless_of_owner(
    session: AsyncSession,
    orm_class: type[OrmT],
    pk_column: InstrumentedAttribute[str],
    pk_value: str,
) -> bool:
    """Unscoped existence check, used ONLY to decide whether a denied
    lookup was a cross-customer attempt (so the caller can write the AC5
    audit event) or a genuinely nonexistent id (no audit event) -- never to
    return row data to a caller."""
    stmt = select(pk_column).where(pk_column == pk_value)
    result = await session.execute(stmt)
    return result.first() is not None
