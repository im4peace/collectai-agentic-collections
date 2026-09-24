"""Chat-driven proposal creation (E6-S2, E6-S3), the "genuinely new" wiring
`chat_flow.py`'s own docstring reserved for this story: once
`ai_orchestration.safety_precedence.SafetyDecision.proposal_execution_permitted`
is true for a `PAY_NOW` or `PROMISE_TO_PAY` message, this module extracts
what the customer stated (advisory only), validates it deterministically
against the existing rules-engine services (E2-S2, E2-S4), and -- only on a
valid outcome -- persists a `Proposal` row via
`domain_services.proposal_service` for the customer to explicitly confirm
(D-041; CLAUDE.md's core engineering principle: the LLM never creates the
PTP or PaymentEvent itself, `application.confirmation_flow` does, later,
from an explicit customer action).

Split from `_chat_turn_processing.py`, its only caller: this module owns
policy/suppression/data lookups and the extraction call;
`_chat_proposal_builders.py` owns the two per-kind (PTP/PAYMENT) outcome
builders; customer-facing copy lives in `_chat_proposal_messages.py`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.orchestrator import AiCallContext, run_ai_interaction
from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.ai_orchestration.prompts.proposal_v1 import (
    PROMPT_VERSION,
    build_proposal_extraction_request,
)
from collectai.ai_orchestration.schemas.proposal_extraction import ProposalExtractionResult
from collectai.application._chat_proposal_builders import (
    ProposalFlowOutcome,
    build_arrangement_reply,
    build_payment_reply,
    build_ptp_reply,
)
from collectai.application._chat_proposal_messages import (
    ARRANGEMENT_RULES_UNAVAILABLE_MESSAGE,
    SUPPRESSED_MESSAGE,
)
from collectai.application._tool_backend_suppression import build_suppression_input
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.escalation_service import create_escalation
from collectai.llm_provider.base import LlmProvider
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.rules_engine.payable import get_payable_options
from collectai.rules_engine.suppression import evaluate_suppression
from collectai.types.clock import Clock
from collectai.types.enums import CaseSource, EscalationReason, Intent, Persona, ProviderMode
from collectai.types.results import PolicyUnavailable

__all__ = ["ProposalFlowOutcome", "build_proposal_reply"]

_PROPOSAL_CAPABILITY = "PROPOSAL_EXTRACTION"

_delinquency_repository = DelinquencyRecordRepository()


async def build_proposal_reply(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    content: str,
    intent_label: Intent,
    correlation_id: str,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
    ai_retry_bound: int,
    policy_provider: PolicyProvider,
    clock: Clock,
    proposal_ttl_minutes: int,
) -> ProposalFlowOutcome:
    """AC1 (E6-S2/E6-S3): only ever produces the *offer* (a `Proposal` row);
    the PTP/PaymentEvent itself is created later, only by an explicit
    confirm action (`application.confirmation_flow`)."""
    record = await _delinquency_repository.get_by_account(
        session, conversation.account_id, customer_id
    )
    if record is None:
        return _unavailable(policy_unavailable=False)

    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable:
        if intent_label is Intent.PAYMENT_PLAN:
            # E8-S1 AC4: unlike PTP/PAY_NOW's generic safe-fallback (no
            # escalation), an arrangement's own rules-engine failure --
            # `get_eligible_options` can only ever fail this same way, via
            # `PolicyUnavailable` -- escalates AMBIGUOUS_VALIDATION so a
            # specialist follows up, mirroring `confirmation_flow
            # ._revalidate_freshness`'s own ad hoc, inline escalation for
            # its analogous `Freshness.UNKNOWN` case.
            await create_escalation(
                session,
                reason=EscalationReason.AMBIGUOUS_VALIDATION,
                customer_id=customer_id,
                account_id=conversation.account_id,
                conversation_id=conversation.conversation_id,
                item_id=None,
                source=CaseSource.SYSTEM,
                policy_provider=policy_provider,
                clock=clock,
                audit_service=audit_service,
                correlation_id=correlation_id,
            )
            return ProposalFlowOutcome(
                ARRANGEMENT_RULES_UNAVAILABLE_MESSAGE, (), None, False, False
            )
        return _unavailable(policy_unavailable=True)

    suppression_input = await build_suppression_input(session, conversation.account_id, customer_id)
    treatment = evaluate_suppression(suppression_input, policy)
    if treatment.automated_treatment_suppressed:
        return ProposalFlowOutcome(SUPPRESSED_MESSAGE, (), None, False, False)

    payable_options = get_payable_options(
        record.overdue_amount, record.outstanding_balance, False, policy
    )

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
    if extraction is None:
        return _unavailable(policy_unavailable=False)

    if intent_label is Intent.PROMISE_TO_PAY:
        return await build_ptp_reply(
            session,
            conversation=conversation,
            customer_id=customer_id,
            extraction=extraction,
            overdue_amount=record.overdue_amount,
            record_version=record.record_version,
            policy_provider=policy_provider,
            policy_version=policy.policy_version,
            clock=clock,
            proposal_ttl_minutes=proposal_ttl_minutes,
        )
    if intent_label is Intent.PAYMENT_PLAN:
        return await build_arrangement_reply(
            session,
            conversation=conversation,
            customer_id=customer_id,
            extraction=extraction,
            record=record,
            policy_provider=policy_provider,
            policy_version=policy.policy_version,
            clock=clock,
            proposal_ttl_minutes=proposal_ttl_minutes,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
    return await build_payment_reply(
        session,
        conversation=conversation,
        customer_id=customer_id,
        extraction=extraction,
        payable_options=payable_options,
        record_version=record.record_version,
        policy_version=policy.policy_version,
        clock=clock,
        proposal_ttl_minutes=proposal_ttl_minutes,
    )


def _unavailable(*, policy_unavailable: bool) -> ProposalFlowOutcome:
    return ProposalFlowOutcome(
        content="",
        labels=(),
        proposal=None,
        ai_unavailable=not policy_unavailable,
        policy_unavailable=policy_unavailable,
    )


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
) -> ProposalExtractionResult | None:
    context = AllowedPromptContext(
        customer_display_name=customer_id, account_reference=conversation.account_id
    )
    request = build_proposal_extraction_request(context=context, message=content)
    call_context = AiCallContext(
        correlation_id=correlation_id,
        capability=_PROPOSAL_CAPABILITY,
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
        ProposalExtractionResult,
        call_context,
        audit_service,
        domain_port=None,
        retry_bound=ai_retry_bound,
    )
    return result.structured_output
