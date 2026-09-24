"""Recommendation repository (E4-S3).

Recommendations are customer-owned data (`customer_id` column, like every
other table `CustomerScopedRepository` backs), but every reader of this
repository is a COLLECTIONS_OFFICER, not the owning customer -- officer
endpoints operate on any account, unlike a CUSTOMER's own `/api/me/*`
lookups (api-contracts.md 1.5's object-level check does not apply here).
Mirrors `AccountRepository`'s pattern exactly: subclass
`CustomerScopedRepository` for the inherited `create`/`list_by_customer`
methods, and add the officer-facing unscoped reads this story actually needs
on top.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class RecommendationRepository(CustomerScopedRepository[RecommendationOrm]):
    def __init__(self) -> None:
        super().__init__(RecommendationOrm)

    async def get_latest_by_account(
        self, session: AsyncSession, account_id: str
    ) -> RecommendationOrm | None:
        """The most recently created recommendation for `account_id`,
        unscoped by customer (officer read path)."""
        stmt = (
            select(RecommendationOrm)
            .where(RecommendationOrm.account_id == account_id)
            .order_by(RecommendationOrm.created_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(
        self, session: AsyncSession, recommendation_id: str
    ) -> RecommendationOrm | None:
        """Unscoped read by id, for the decision endpoint (which already
        authorizes via `recommendation:decide`, not object ownership)."""
        stmt = select(RecommendationOrm).where(
            RecommendationOrm.recommendation_id == recommendation_id
        )
        return (await session.execute(stmt)).scalar_one_or_none()
