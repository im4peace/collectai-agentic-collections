"""One turn's classify-and-respond orchestration (E6-S1), split out of
`chat_flow.py` to keep that module under the code-gen skill's 300-line
block threshold. `chat_flow.process_customer_message` is the only caller;
both functions here take an already-persisted customer `ChatMessageOrm` and
return a `TurnOutcome`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.orchestrator import (
    AiCallContext,
    AiInteractionResult,
    run_ai_interaction,
)
from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.ai_orchestration.prompts.intent_v1 import PROMPT_VERSION, build_intent_request
from collectai.ai_orchestration.safety_precedence import apply_safety_precedence
from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.application._chat_escalation_reporting import report_escalation
from collectai.application._chat_persistence import persist_message, persist_turn
from collectai.application._chat_reply_planning import plan_reply
from collectai.application._chat_templates import HANDED_OFF_HOLDING_MESSAGE, SAFE_FALLBACK_MESSAGE
from collectai.application._chat_types import TurnOutcome
from collectai.audit.service import AuditService
from collectai.llm_provider.base import LlmProvider
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.enums import ContentSource, MessageLabel, MessageRole, Persona, ProviderMode
from collectai.types.enums import SafeState as _SafeState

_CHAT_CAPABILITY = "INTENT_CLASSIFICATION"


async def respond_handed_off(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    customer_message: ChatMessageOrm,
    correlation_id: str,
    now: datetime,
) -> TurnOutcome:
    """api-contracts.md 3.8: "In a HANDED_OFF conversation replies are
    templated holding messages without a provider call for that topic." No
    classification, no clarification-count change, no new escalation report
    (one was already reported the turn this conversation became
    HANDED_OFF)."""
    assistant_message = await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content=HANDED_OFF_HOLDING_MESSAGE,
        content_source=ContentSource.TEMPLATE,
        labels=[MessageLabel.HUMAN_HANDOFF],
        created_at=now,
    )
    turn = await persist_turn(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        customer_message=customer_message,
        assistant_message=assistant_message,
        intent=None,
        safe_state=_SafeState.NONE.value,
        correlation_id=correlation_id,
        created_at=now,
    )
    return TurnOutcome(
        turn=turn,
        customer_message=customer_message,
        assistant_message=assistant_message,
        intent=None,
        safe_state=_SafeState.NONE,
        escalation_reported=False,
        escalation_reason=None,
    )


async def classify_and_respond(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    customer_message: ChatMessageOrm,
    content: str,
    now: datetime,
    correlation_id: str,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
    ai_retry_bound: int,
    max_clarification_turns: int,
) -> TurnOutcome:
    result = await _classify(
        conversation=conversation,
        content=content,
        correlation_id=correlation_id,
        provider=provider,
        provider_mode=provider_mode,
        audit_service=audit_service,
        ai_retry_bound=ai_retry_bound,
        customer_id=customer_id,
    )

    if result.structured_output is None or not result.governed:
        return await _respond_unclassifiable(
            session,
            conversation=conversation,
            customer_id=customer_id,
            customer_message=customer_message,
            correlation_id=correlation_id,
            safe_state=result.safe_state,
            now=now,
        )

    intent_result = result.structured_output
    decision = apply_safety_precedence(intent_result)
    plan = plan_reply(
        intent_result, decision, conversation.clarification_count, max_clarification_turns
    )

    conversation.clarification_count = plan.clarification_count
    conversation.status = plan.conversation_status.value

    if plan.escalation_reason is not None:
        await report_escalation(
            session=session,
            audit_service=audit_service,
            correlation_id=correlation_id,
            customer_id=customer_id,
            account_id=conversation.account_id,
            reason=plan.escalation_reason,
        )

    assistant_message = await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content=plan.content,
        content_source=ContentSource.TEMPLATE,
        labels=list(plan.labels),
        created_at=now,
    )
    turn = await persist_turn(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        customer_message=customer_message,
        assistant_message=assistant_message,
        intent=intent_result.model_dump(mode="json"),
        safe_state=_SafeState.NONE.value,
        correlation_id=correlation_id,
        created_at=now,
    )
    return TurnOutcome(
        turn=turn,
        customer_message=customer_message,
        assistant_message=assistant_message,
        intent=intent_result,
        safe_state=_SafeState.NONE,
        escalation_reported=plan.escalation_reason is not None,
        escalation_reason=plan.escalation_reason,
    )


async def _classify(
    *,
    conversation: ConversationOrm,
    content: str,
    correlation_id: str,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
    ai_retry_bound: int,
    customer_id: str,
) -> AiInteractionResult[IntentResult]:
    context = AllowedPromptContext(
        customer_display_name=customer_id, account_reference=conversation.account_id
    )
    request = build_intent_request(context=context, message=content)
    call_context = AiCallContext(
        correlation_id=correlation_id,
        capability=_CHAT_CAPABILITY,
        prompt_version=PROMPT_VERSION,
        provider_name="anthropic" if provider_mode is ProviderMode.LIVE else "mock",
        provider_mode=provider_mode,
        actor_persona=Persona.CUSTOMER,
        customer_id=customer_id,
        account_id=conversation.account_id,
    )
    return await run_ai_interaction(
        provider,
        request,
        IntentResult,
        call_context,
        audit_service,
        domain_port=None,
        retry_bound=ai_retry_bound,
    )


async def _respond_unclassifiable(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    customer_message: ChatMessageOrm,
    correlation_id: str,
    safe_state: _SafeState,
    now: datetime,
) -> TurnOutcome:
    """AC1/api-contracts.md 3.8: a provider failure or an audit write
    failure for the classification itself both fail closed to the same safe
    fallback -- `talk_to_human_available` stays true either way (that flag
    is constant across every response this router returns, not conditional
    on this branch)."""
    assistant_message = await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content=SAFE_FALLBACK_MESSAGE,
        content_source=ContentSource.TEMPLATE,
        labels=[MessageLabel.SAFE_FALLBACK],
        created_at=now,
    )
    turn = await persist_turn(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        customer_message=customer_message,
        assistant_message=assistant_message,
        intent=None,
        safe_state=safe_state.value,
        correlation_id=correlation_id,
        created_at=now,
    )
    return TurnOutcome(
        turn=turn,
        customer_message=customer_message,
        assistant_message=assistant_message,
        intent=None,
        safe_state=safe_state,
        escalation_reported=False,
        escalation_reason=None,
    )
