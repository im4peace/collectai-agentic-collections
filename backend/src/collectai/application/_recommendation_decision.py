"""`POST /api/accounts/{account_id}/recommendation/{recommendation_id}/decision`
business logic (E4-S3; api-contracts.md 3.5's third endpoint).

An officer accepting or overriding a stored recommendation is itself an
explicit, already-capability-gated (`recommendation:decide`) human action --
CLAUDE.md's human-in-the-loop requirement is about the *decisions* this
endpoint records (settlements, restructuring, ...), not about adding further
machinery around the act of recording one. What this module does add:
mandatory Idempotency-Key replay/conflict handling and a fail-closed audit
write, both because api-contracts.md 3.5 requires them for this endpoint
specifically (an Idempotency-Key header, and 503 AUDIT_UNAVAILABLE with the
transition rolled back on an audit failure).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.middleware.errors import NotFoundError, RequestValidationFailedError
from collectai.api.schemas.customer360 import Recommendation
from collectai.application._recommendation_idempotency import (
    hash_decision_request,
    insert_or_replay,
    replay_if_present,
)
from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.domain_services.recommendation_mapping import to_recommendation_schema
from collectai.persistence.repositories.recommendation_repository import (
    RecommendationRepository,
)
from collectai.types.clock import Clock
from collectai.types.enums import ActorKind, AuditStage, NbaAction, Persona, RecommendationDecision
from collectai.types.reason_codes import ReasonCode

RECOMMENDATION_DECIDED_EVENT_TYPE = "RECOMMENDATION_DECIDED"

_repository = RecommendationRepository()


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    recommendation: Recommendation
    replayed: bool


async def decide_recommendation(
    session: AsyncSession,
    audit_service: AuditService,
    *,
    account_id: str,
    recommendation_id: str,
    decision: RecommendationDecision,
    reason: str | None,
    chosen_action: NbaAction | None,
    persona: Persona,
    idempotency_key: str,
    clock: Clock,
    correlation_id: str,
) -> DecisionOutcome:
    request_hash = hash_decision_request(
        recommendation_id=recommendation_id,
        decision=decision.value,
        reason=reason,
        chosen_action=chosen_action.value if chosen_action is not None else None,
    )
    replay = await replay_if_present(session, idempotency_key, request_hash)
    if replay is not None:
        return DecisionOutcome(recommendation=Recommendation.model_validate(replay), replayed=True)

    row = await _repository.get_by_id(session, recommendation_id)
    if row is None or row.account_id != account_id:
        raise NotFoundError(message=f"Recommendation {recommendation_id!r} was not found.")
    if decision is RecommendationDecision.OVERRIDDEN and not reason:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.REASON_REQUIRED,
            message="`reason` is required when decision is OVERRIDDEN.",
        )

    now = clock.now()
    await audit_service.record(
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=RECOMMENDATION_DECIDED_EVENT_TYPE,
            actor_kind=ActorKind.STAFF,
            actor_persona=persona,
            customer_id=row.customer_id,
            account_id=row.account_id,
            capability="recommendation:decide",
            policy_version=row.policy_version,
            final_action=decision.value,
            resource_type="recommendation",
            resource_id=row.recommendation_id,
            human_override=(
                {"reason": reason, "chosen_action": chosen_action.value if chosen_action else None}
                if decision is RecommendationDecision.OVERRIDDEN
                else None
            ),
        )
    )

    row.officer_decision = decision.value
    row.officer_decision_reason = reason
    row.officer_chosen_action = chosen_action.value if chosen_action is not None else None
    row.decided_by_persona = persona.value
    row.decided_at = now
    await session.flush()

    schema = to_recommendation_schema(row)
    winner = await insert_or_replay(
        session,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_body=schema.model_dump(mode="json"),
        resource_id=row.recommendation_id,
        created_at=now,
    )
    if winner is not None:
        return DecisionOutcome(recommendation=Recommendation.model_validate(winner), replayed=True)
    return DecisionOutcome(recommendation=schema, replayed=False)


__all__ = ["DecisionOutcome", "RECOMMENDATION_DECIDED_EVENT_TYPE", "decide_recommendation"]
