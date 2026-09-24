"""ReviewDecision repository (E7-S2). Insert-only, staff-facing (not
customer-scoped, like `escalation_case_repository.py`'s own pattern for
officer-facing tables -- see `_ptp_helpers.get_delinquency_record`'s note on
why officer routes never subclass `CustomerScopedRepository`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.review_decision import ReviewDecisionOrm


class ReviewDecisionRepository:
    async def create(self, session: AsyncSession, entity: ReviewDecisionOrm) -> ReviewDecisionOrm:
        session.add(entity)
        await session.flush()
        return entity

    async def list_by_case(
        self, session: AsyncSession, case_id: str
    ) -> list[ReviewDecisionOrm]:
        stmt = (
            select(ReviewDecisionOrm)
            .where(ReviewDecisionOrm.case_id == case_id)
            .order_by(ReviewDecisionOrm.decided_at)
        )
        return list((await session.execute(stmt)).scalars().all())
