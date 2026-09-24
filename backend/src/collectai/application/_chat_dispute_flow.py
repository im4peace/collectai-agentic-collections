"""Chat-driven dispute creation (E8-S3), the "genuinely new" wiring
`_chat_escalation_reporting.py`'s own docstring reserved for this story:
once a message is classified `Intent.DISPUTE`, this module extracts which
`DisputeCategory` the customer's own words best match (advisory only, AC2 --
it never judges validity), then creates the real `Dispute` and
`EscalationCase` rows via `domain_services.dispute_service`. Unlike the
transactional (PTP/PAYMENT/ARRANGEMENT) proposal flow, there is no separate
confirm step: recording a customer-reported dispute is not a financial
action requiring explicit confirmation, and every model output involved is
either structured (the category) or a fixed template (the reply) -- never
free-form prose reaching the customer, so no post-generation grounding
check applies (mirrors `_chat_templates.py`'s own rule).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.orchestrator import AiCallContext, run_ai_interaction
from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.ai_orchestration.prompts.dispute_v1 import (
    PROMPT_VERSION,
    build_dispute_extraction_request,
)
from collectai.ai_orchestration.schemas.dispute_extraction import DisputeExtractionResult
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.dispute_service import (
    DisputeCreationResult,
    create_dispute_from_chat,
)
from collectai.llm_provider.base import LlmProvider
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.clock import Clock
from collectai.types.enums import Persona, ProviderMode

_DISPUTE_CAPABILITY = "DISPUTE_CLASSIFICATION"


@dataclass(frozen=True, slots=True)
class DisputeFlowOutcome:
    result: DisputeCreationResult


async def build_dispute_reply(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    content: str,
    correlation_id: str,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
    ai_retry_bound: int,
    policy_provider: PolicyProvider,
    clock: Clock,
) -> DisputeFlowOutcome:
    """AC1: `content` (the customer's raw message) becomes `Dispute
    .customer_reason` verbatim; `category` is the LLM's advisory
    classification, defaulting to `OTHER` in `dispute_service.py` if the
    call is unavailable or leaves it null -- a dispute is always recorded
    (AC3's suppression only helps the customer if it fires), never blocked
    on a classification the customer's own report does not actually need."""
    extraction = await _extract(
        conversation=conversation,
        content=content,
        correlation_id=correlation_id,
        provider=provider,
        provider_mode=provider_mode,
        audit_service=audit_service,
        ai_retry_bound=ai_retry_bound,
        customer_id=customer_id,
    )
    result = await create_dispute_from_chat(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        account_id=conversation.account_id,
        item_id=None,
        category=extraction.category if extraction is not None else None,
        customer_reason=content,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    return DisputeFlowOutcome(result=result)


async def _extract(
    *,
    conversation: ConversationOrm,
    content: str,
    correlation_id: str,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
    ai_retry_bound: int,
    customer_id: str,
) -> DisputeExtractionResult | None:
    context = AllowedPromptContext(
        customer_display_name=customer_id, account_reference=conversation.account_id
    )
    request = build_dispute_extraction_request(context=context, message=content)
    call_context = AiCallContext(
        correlation_id=correlation_id,
        capability=_DISPUTE_CAPABILITY,
        prompt_version=PROMPT_VERSION,
        provider_name="anthropic" if provider_mode is ProviderMode.LIVE else "mock",
        provider_mode=provider_mode,
        actor_persona=Persona.CUSTOMER,
        customer_id=customer_id,
        account_id=conversation.account_id,
    )
    result = await run_ai_interaction(
        provider,
        request,
        DisputeExtractionResult,
        call_context,
        audit_service,
        domain_port=None,
        retry_bound=ai_retry_bound,
    )
    return result.structured_output
