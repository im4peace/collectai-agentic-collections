"""Escalation case detail (E7-S3 AC2, AC3): conversation, AI recommendation
and deterministic rule results for one case, plus whether APPROVE is
currently permitted -- so the review screen can render three separately
labelled sections and hide APPROVE without re-deriving `review_service`'s
own policy gate (`review_service.approval_readiness` is the single source
of truth for that rule; this module only assembles the read).

Read-only: no write path, no idempotency, no audit event (mirrors
`api/routers/disputes.py`'s own `GET /{dispute_id}` -- a read never needs
either).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._review_exceptions import (
    ReviewCaseNotFoundError,
    ReviewNotPermittedError,
)
from collectai.domain_services.review_service import approval_readiness
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.persistence.repositories.chat_message_repository import ChatMessageRepository
from collectai.persistence.repositories.recommendation_repository import RecommendationRepository
from collectai.types.enums import Persona, ReviewQueue
from collectai.types.reason_codes import ReasonCode

_chat_message_repository = ChatMessageRepository()
_recommendation_repository = RecommendationRepository()


@dataclass(frozen=True, slots=True)
class CaseDetailResult:
    case: EscalationCaseOrm
    conversation: list[ChatMessageOrm]
    recommendation: RecommendationOrm | None
    approve_permitted: bool


async def get_case_detail(
    session: AsyncSession,
    *,
    case_id: str,
    viewer_persona: Persona,
    policy_provider: PolicyProvider,
) -> CaseDetailResult:
    """AC6's object-level half applied to the detail view too: a
    COMPLIANCE_RISK viewer may only open a COMPLIANCE_REVIEW-queue case,
    mirroring `api/routers/escalations.py`'s own `_effective_queues` scoping
    for the list. COLLECTIONS_OFFICER may open any case (read-only; the
    write path's own `reviewer_role` gate in `review_service.decide` still
    applies separately to any actual decision)."""
    case = await session.get(EscalationCaseOrm, case_id)
    if case is None:
        raise ReviewCaseNotFoundError(case_id)
    is_outside_compliance_queue = case.queue != ReviewQueue.COMPLIANCE_REVIEW.value
    if viewer_persona is Persona.COMPLIANCE_RISK and is_outside_compliance_queue:
        raise ReviewNotPermittedError(
            reason_code=ReasonCode.QUEUE_NOT_PERMITTED,
            message="This case is outside the COMPLIANCE_REVIEW queue.",
        )

    conversation: list[ChatMessageOrm] = []
    if case.conversation_id is not None:
        conversation = list(
            await _chat_message_repository.list_by_conversation_for_customer(
                session, case.conversation_id, case.customer_id
            )
        )

    recommendation: RecommendationOrm | None = None
    if case.recommendation_id is not None:
        recommendation = await _recommendation_repository.get_by_id(session, case.recommendation_id)

    approve_permitted = await approval_readiness(
        session, case, viewer_persona=viewer_persona, policy_provider=policy_provider
    )

    return CaseDetailResult(
        case=case,
        conversation=conversation,
        recommendation=recommendation,
        approve_permitted=approve_permitted,
    )


__all__ = ["CaseDetailResult", "get_case_detail"]
