"""E4-S3 AC4: single owner of the `recommendation` row insert, paired with
the recommendation-specific audit event a governed recommendation always
gets.

`ai_orchestration.orchestrator.run_ai_interaction` already writes a generic
`AI_RESPONSE_RECORDED`/`AI_OUTPUT_INVALID`/`PROVIDER_UNAVAILABLE` audit event
for the AI *interaction* itself (E5-S2), best-effort. The event this module
writes describes a different thing -- the recommendation's own governance
record (model id, prompt version, rule-set version and final output, AC4) --
so both exist; this is not a double-write of the same logical event, the
same way a domain write's own audit event is distinct from the interaction
audit `run_ai_interaction` already wrote for it.

Unlike the orchestrator's best-effort write, this one is never swallowed:
`AuditService.record` raises `AuditUnavailable` on failure and this module
lets it propagate *before* the recommendation row is ever added to the
session (AC5 -- "no recommendation body", never a partially-persisted one).
`generate_recommendation` (`recommendation_flow.py`) does not catch it
either; only the router does, mapping it to 503 `AUDIT_UNAVAILABLE`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.application._recommendation_guardrails import GuardedRecommendation
from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.persistence.repositories.recommendation_repository import (
    RecommendationRepository,
)
from collectai.types.enums import ActorKind, AuditStage, Persona, RecommendationStatus
from collectai.types.ids import EntityPrefix, generate_id

RECOMMENDATION_GENERATED_EVENT_TYPE = "RECOMMENDATION_GENERATED"

_repository = RecommendationRepository()


async def persist_recommendation(
    session: AsyncSession,
    audit_service: AuditService,
    *,
    account_id: str,
    customer_id: str,
    guarded: GuardedRecommendation,
    status: RecommendationStatus,
    model_id: str | None,
    prompt_version: str | None,
    policy_version: str,
    record_version: int,
    correlation_id: str,
    actor_persona: Persona,
    now: datetime,
) -> RecommendationOrm:
    """Write this recommendation's own audit event, then (only once that
    succeeds) insert its row -- the only INSERT call site for
    `recommendation` (code-gen skill's "single owner for state mutations")."""
    recommendation_id = generate_id(EntityPrefix.RECOMMENDATION)
    audit_event_id = await audit_service.record(
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.AI_INTERPRETATION,
            event_type=RECOMMENDATION_GENERATED_EVENT_TYPE,
            actor_kind=ActorKind.AI,
            actor_persona=actor_persona,
            customer_id=customer_id,
            account_id=account_id,
            capability="recommendation:generate",
            model_id=model_id,
            prompt_version=prompt_version,
            policy_version=policy_version,
            ai_output={
                "recommendation_id": recommendation_id,
                "action": guarded.action.value,
                "rationale": guarded.rationale,
                "referenced_factor_ids": guarded.referenced_factor_ids,
                "content_source": guarded.content_source.value,
                "status": status.value,
            },
            final_action=guarded.action.value,
            resource_type="recommendation",
            resource_id=recommendation_id,
        )
    )
    orm = RecommendationOrm(
        recommendation_id=recommendation_id,
        account_id=account_id,
        customer_id=customer_id,
        action=guarded.action.value,
        rationale=guarded.rationale,
        referenced_factor_ids=guarded.referenced_factor_ids,
        status=status.value,
        content_source=guarded.content_source.value,
        model_id=model_id,
        prompt_version=prompt_version,
        policy_version=policy_version,
        record_version=record_version,
        correlation_id=correlation_id,
        created_at=now,
        audit_event_id=audit_event_id,
    )
    return await _repository.create(session, orm)


__all__ = ["RECOMMENDATION_GENERATED_EVENT_TYPE", "persist_recommendation"]
