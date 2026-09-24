"""Customer 360's `AiBlock` assembly (E4-S3): the latest stored
recommendation for an account, or NOT_GENERATED when none exists yet.

Split out of `customer360_service.py` (code-gen skill's 300-line block
threshold -- that module and `customer360_mapping.py` were both already at
the limit before this story's addition) rather than growing either of them.
Private to this package: only `customer360_service.py` calls it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.schemas.customer360 import AiBlock
from collectai.domain_services.recommendation_mapping import to_recommendation_schema
from collectai.persistence.repositories.recommendation_repository import (
    RecommendationRepository,
)
from collectai.types.enums import RecommendationStatus

_recommendation_repository = RecommendationRepository()


async def build_ai_block(session: AsyncSession, account_id: str) -> AiBlock:
    row = await _recommendation_repository.get_latest_by_account(session, account_id)
    if row is None:
        return AiBlock(status=RecommendationStatus.NOT_GENERATED, recommendation=None)
    return AiBlock(
        status=RecommendationStatus(row.status), recommendation=to_recommendation_schema(row)
    )


__all__ = ["build_ai_block"]
