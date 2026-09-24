"""E4-S3: the next-best-action generation flow (AC1-AC5) and the
recommendation read path, built entirely from the already-implemented AI
orchestration layer (E5-S1/E5-S2/E5-S3) and deterministic services -- this
module never talks to an LLM provider directly and never derives its own
schema-validation or retry logic.

Public entry points (called from `api.routers.recommendations`):

- `generate_recommendation` (AC1-AC5): builds a Customer 360 read model,
  short-circuits to a governance-hold recommendation when AC3 applies,
  otherwise calls `ai_orchestration.orchestrator.run_ai_interaction` with
  `domain_port=None` (advisory -- AC4's "no financial record changes during
  generation") and applies AC1/AC2's guardrails to whatever it returns.
- `get_latest_recommendation`: the read-only GET path.
- `decide_recommendation` (re-exported from `_recommendation_decision.py`,
  split out to keep this module under the code-gen skill's 300-line block
  threshold).

AC4's audit event (model id, prompt version, rule-set version, output) and
AC5's fail-closed persistence are both `_recommendation_persistence
.persist_recommendation`'s responsibility, not this module's -- see that
module's docstring for why a second, recommendation-specific audit event
exists alongside the orchestrator's own generic one.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.orchestrator import AiCallContext, run_ai_interaction
from collectai.ai_orchestration.prompts.nba_v1 import NBA_PROMPT_VERSION, build_nba_request
from collectai.ai_orchestration.schemas.nba import NbaRecommendationOutput
from collectai.api.middleware.errors import NotFoundError, PolicyUnavailableError
from collectai.api.schemas.customer360 import Customer360
from collectai.application._recommendation_context import (
    allowed_factor_ids,
    build_prompt_context,
    grounded_facts,
)
from collectai.application._recommendation_decision import decide_recommendation
from collectai.application._recommendation_governance import (
    GOVERNANCE_HOLD_RATIONALE,
    requires_human_review,
)
from collectai.application._recommendation_guardrails import (
    GuardedRecommendation,
    apply_guardrails,
    safe_fallback_recommendation,
)
from collectai.application._recommendation_persistence import persist_recommendation
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.customer360_service import build_customer360
from collectai.domain_services.recommendation_mapping import to_recommendation_schema
from collectai.llm_provider.base import LlmProvider
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.recommendation_repository import (
    RecommendationRepository,
)
from collectai.types.clock import Clock
from collectai.types.enums import (
    ContentSource,
    NbaAction,
    Persona,
    ProviderMode,
    RecommendationStatus,
)

__all__ = [
    "RecommendationGenerationResult",
    "decide_recommendation",
    "generate_recommendation",
    "get_latest_recommendation",
    "to_recommendation_schema",
]

_account_repository = AccountRepository()
_recommendation_repository = RecommendationRepository()


@dataclass(frozen=True, slots=True)
class RecommendationGenerationResult:
    status: RecommendationStatus
    recommendation: RecommendationOrm | None


async def generate_recommendation(
    session: AsyncSession,
    audit_service: AuditService,
    *,
    account_id: str,
    provider: LlmProvider,
    provider_name: str,
    provider_mode: ProviderMode,
    policy_provider: PolicyProvider,
    clock: Clock,
    correlation_id: str,
    retry_bound: int = 1,
) -> RecommendationGenerationResult:
    """AC1-AC5. Raises `NotFoundError` for an unknown account,
    `PolicyUnavailableError` when no active policy is usable, and lets
    `audit.service.AuditUnavailable` propagate uncaught (AC5 -- the router
    maps it to 503 `AUDIT_UNAVAILABLE`)."""
    customer360 = await build_customer360(
        session, account_id=account_id, policy_provider=policy_provider, clock=clock
    )
    if customer360.deterministic.status != "OK" or customer360.deterministic.priority is None:
        raise PolicyUnavailableError()

    if requires_human_review(customer360):
        return await _persist_and_wrap(
            session,
            audit_service,
            customer360=customer360,
            guarded=GuardedRecommendation(
                action=NbaAction.ESCALATE_TO_HUMAN_REVIEW,
                rationale=GOVERNANCE_HOLD_RATIONALE,
                referenced_factor_ids=[],
                content_source=ContentSource.TEMPLATE,
            ),
            status=RecommendationStatus.HUMAN_REVIEW_ONLY,
            model_id=None,
            prompt_version=None,
            correlation_id=correlation_id,
            clock=clock,
        )

    ai_result = await run_ai_interaction(
        provider,
        build_nba_request(build_prompt_context(customer360)),
        NbaRecommendationOutput,
        AiCallContext(
            correlation_id=correlation_id,
            capability="recommendation:generate",
            prompt_version=NBA_PROMPT_VERSION,
            provider_name=provider_name,
            provider_mode=provider_mode,
            policy_version=customer360.deterministic.policy_version,
            actor_persona=Persona.COLLECTIONS_OFFICER,
            customer_id=customer360.profile.customer_id,
            account_id=account_id,
        ),
        audit_service,
        domain_port=None,
        retry_bound=retry_bound,
    )

    if ai_result.unavailable_reason == "PROVIDER_TIMEOUT":
        # AC's "AI failure" path (api-contracts.md 3.5): a response-only
        # state, deliberately never stored (component-map.md).
        return RecommendationGenerationResult(
            status=RecommendationStatus.AI_UNAVAILABLE, recommendation=None
        )
    if ai_result.unavailable_reason == "SCHEMA_INVALID":
        return await _persist_and_wrap(
            session,
            audit_service,
            customer360=customer360,
            guarded=safe_fallback_recommendation(),
            status=RecommendationStatus.SAFE_FALLBACK,
            model_id=None,
            prompt_version=None,
            correlation_id=correlation_id,
            clock=clock,
        )

    assert ai_result.structured_output is not None  # noqa: S101 - guaranteed by the two branches above
    guarded = apply_guardrails(
        ai_result.structured_output,
        allowed_factor_ids=allowed_factor_ids(customer360),
        facts=grounded_facts(customer360),
    )
    is_model_sourced = guarded.content_source is ContentSource.MODEL
    return await _persist_and_wrap(
        session,
        audit_service,
        customer360=customer360,
        guarded=guarded,
        status=RecommendationStatus.GENERATED,
        model_id=ai_result.model_id if is_model_sourced else None,
        prompt_version=NBA_PROMPT_VERSION if is_model_sourced else None,
        correlation_id=correlation_id,
        clock=clock,
    )


async def _persist_and_wrap(
    session: AsyncSession,
    audit_service: AuditService,
    *,
    customer360: Customer360,
    guarded: GuardedRecommendation,
    status: RecommendationStatus,
    model_id: str | None,
    prompt_version: str | None,
    correlation_id: str,
    clock: Clock,
) -> RecommendationGenerationResult:
    assert customer360.deterministic.policy_version is not None  # noqa: S101 - status == "OK" already checked
    orm = await persist_recommendation(
        session,
        audit_service,
        account_id=customer360.account_id,
        customer_id=customer360.profile.customer_id,
        guarded=guarded,
        status=status,
        model_id=model_id,
        prompt_version=prompt_version,
        policy_version=customer360.deterministic.policy_version,
        record_version=customer360.snapshot.record_version,
        correlation_id=correlation_id,
        actor_persona=Persona.COLLECTIONS_OFFICER,
        now=clock.now(),
    )
    return RecommendationGenerationResult(status=status, recommendation=orm)


async def get_latest_recommendation(
    session: AsyncSession, *, account_id: str
) -> RecommendationOrm | None:
    """AC-adjacent read path (api-contracts.md 3.5 GET): status
    NOT_GENERATED with a null recommendation when none exists yet is the
    router's concern, not this function's -- it returns `None` either way a
    caller can only tell apart by re-checking the account."""
    account = await _account_repository.get_by_id(session, account_id)
    if account is None:
        raise NotFoundError(message=f"Account {account_id!r} was not found.")
    return await _recommendation_repository.get_latest_by_account(session, account_id)
