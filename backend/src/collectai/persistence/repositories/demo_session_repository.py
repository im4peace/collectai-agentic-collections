"""DemoSession repository (E3-S1). A demo session is NOT authentication: it
only maps an opaque, hashed token to the persona (and, for CUSTOMER, the
bound `customer_id`) `POST /api/session` selected."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.demo_session import DemoSessionOrm


class DemoSessionRepository:
    async def create(self, session: AsyncSession, entity: DemoSessionOrm) -> DemoSessionOrm:
        session.add(entity)
        await session.flush()
        return entity

    async def get_by_token_hash(
        self, session: AsyncSession, session_token_hash: str
    ) -> DemoSessionOrm | None:
        stmt = select(DemoSessionOrm).where(
            DemoSessionOrm.session_token_hash == session_token_hash
        )
        return (await session.execute(stmt)).scalar_one_or_none()
