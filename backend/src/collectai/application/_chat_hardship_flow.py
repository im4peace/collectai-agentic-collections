"""Chat-driven hardship-case creation (E8-S2), the "genuinely new" wiring
`_chat_escalation_reporting.py`'s own docstring reserved for this story:
once a message is classified `Intent.FINANCIAL_HARDSHIP`, this module
extracts which `HardshipIndicatorType`(s) the customer's own words best
match (advisory only, AC2 -- it never promises or implies relief), then
creates the real `HardshipCase` and `EscalationCase` rows via
`domain_services.hardship_service`. Mirrors `_chat_dispute_flow.py` exactly:
no separate confirm step, since recording a customer-reported hardship is
not itself a financial action, and the customer-facing reply is always a
fixed template chosen upstream by `_plan_sensitive` -- never free-form prose
reaching the customer, so no post-generation grounding check applies here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.orchestrator import AiCallContext, run_ai_interaction
from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.ai_orchestration.prompts.hardship_v1 import (
    PROMPT_VERSION,
    build_hardship_extraction_request,
)
from collectai.ai_orchestration.schemas.hardship_extraction import HardshipExtractionResult
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.hardship_service import (
    HardshipCreationResult,
    create_hardship_from_chat,
)
from collectai.llm_provider.base import LlmProvider
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.clock import Clock
from collectai.types.enums import Persona, ProviderMode

_HARDSHIP_CAPABILITY = "HARDSHIP_CLASSIFICATION"


@dataclass(frozen=True, slots=True)
class HardshipFlowOutcome:
    result: HardshipCreationResult


async def build_hardship_reply(
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
) -> HardshipFlowOutcome:
    """AC1: `content` (the customer's raw message) becomes every indicator's
    `customer_statement` verbatim; `indicator_types` is the LLM's advisory
    classification, defaulting to `[OTHER]` in `hardship_service.py` if the
    call is unavailable or returns none -- a hardship report is always
    recorded, never blocked on a classification the customer's own report
    does not actually need."""
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
    result = await create_hardship_from_chat(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        account_id=conversation.account_id,
        indicator_types=extraction.indicator_types if extraction is not None else [],
        customer_statement=content,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    return HardshipFlowOutcome(result=result)


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
) -> HardshipExtractionResult | None:
    context = AllowedPromptContext(
        customer_display_name=customer_id, account_reference=conversation.account_id
    )
    request = build_hardship_extraction_request(context=context, message=content)
    call_context = AiCallContext(
        correlation_id=correlation_id,
        capability=_HARDSHIP_CAPABILITY,
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
        HardshipExtractionResult,
        call_context,
        audit_service,
        domain_port=None,
        retry_bound=ai_retry_bound,
    )
    return result.structured_output
