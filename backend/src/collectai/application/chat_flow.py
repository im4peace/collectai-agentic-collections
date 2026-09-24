"""Chat turn orchestration (E6-S1): disclose -> classify -> apply safety
precedence -> persist -> report escalation. `api/routers/chat.py` stays a
thin HTTP-shaped translation layer that calls this module, mirroring
`ptps.py`'s split from `domain_services.ptp_service`.

CLAUDE.md's core engineering principle, concretely: `IntentResult`
(`ai_orchestration.schemas.intent`) is the LLM's *advisory* classification
only, produced through `ai_orchestration.orchestrator.run_ai_interaction`
with `domain_port=None` -- the same "advisory, no domain write" path E5-S2's
`finish_advisory` already implements for other non-state-changing AI
outputs. `ai_orchestration.safety_precedence.apply_safety_precedence` is the
one deterministic, non-LLM function that decides whether a transactional
template may be shown at all (AC4); `_chat_reply_planning.plan_reply`
branches on its result and every branch either takes its
`proposal_execution_permitted` gate or reports one of AC5's two escalation
paths. No PTP/payment/proposal execution ever happens here --
`ai_orchestration.tools` and `application.tool_backend` are deliberately
never imported. E6-S2/E6-S3 wire real proposal creation in through this same
gate in a later story.

Split across four modules to stay under the code-gen skill's 300-line block
threshold, each with one job: this module (the two public entry points a
router calls), `_chat_types.py` (shared result dataclasses),
`_chat_turn_processing.py` (the classify-then-respond orchestration for one
turn), `_chat_reply_planning.py` (the pure AC4/AC5 dispatch), plus
`_chat_persistence.py` (ORM row construction) and
`_chat_escalation_reporting.py` (the AC5 audit write) that both of those
already depended on.

Every assistant message this module (and the ones it composes) writes is
`content_source=TEMPLATE` -- see `_chat_templates.py`'s docstring for why
E5-S3's grounding check does not apply here: the one LLM call this story
makes classifies, it never generates customer-facing prose.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.application._chat_persistence import persist_message
from collectai.application._chat_templates import GREETING_TEXT
from collectai.application._chat_turn_processing import classify_and_respond, respond_handed_off
from collectai.application._chat_types import ConversationCreateOutcome, TurnOutcome
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.llm_provider.base import LlmProvider
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.clock import Clock
from collectai.types.enums import (
    ContentSource,
    ConversationStatus,
    MessageLabel,
    MessageRole,
    ProviderMode,
)
from collectai.types.ids import EntityPrefix, generate_id

__all__ = [
    "ConversationCreateOutcome",
    "TurnOutcome",
    "create_conversation",
    "process_customer_message",
]


async def create_conversation(
    session: AsyncSession, *, customer_id: str, account_id: str, clock: Clock
) -> ConversationCreateOutcome:
    """AC1: the first assistant message states it is an AI assistant
    (`GREETING_TEXT`) and carries the `AI_DISCLOSURE` label. No AI provider
    call: the greeting is a template (api-contracts.md 3.8)."""
    now = clock.now()
    conversation = ConversationOrm(
        conversation_id=generate_id(EntityPrefix.CONVERSATION),
        customer_id=customer_id,
        account_id=account_id,
        status=ConversationStatus.ACTIVE.value,
        clarification_count=0,
        created_at=now,
        last_message_at=now,
    )
    session.add(conversation)
    await session.flush()
    greeting = await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content=GREETING_TEXT,
        content_source=ContentSource.TEMPLATE,
        labels=[MessageLabel.AI_DISCLOSURE],
        created_at=now,
    )
    return ConversationCreateOutcome(conversation=conversation, greeting=greeting)


async def process_customer_message(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    content: str,
    clock: Clock,
    correlation_id: str,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
    ai_retry_bound: int,
    max_clarification_turns: int,
    policy_provider: PolicyProvider,
    proposal_ttl_minutes: int,
) -> TurnOutcome:
    """One `POST /messages` call's full business logic (AC2-AC5, AC7).
    `conversation` must already be ownership-checked by the caller (the
    router, via `me_ownership.require_owned`) -- this function trusts it."""
    now = clock.now()
    # Generated up front so `customer_message` can carry it at INSERT time --
    # see `_chat_persistence`'s module docstring for why (the deferred
    # `fk_chat_message_turn` constraint this relies on).
    turn_id = generate_id(EntityPrefix.CHAT_TURN)
    customer_message = await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.CUSTOMER,
        content=content,
        content_source=ContentSource.CUSTOMER_INPUT,
        labels=[],
        created_at=now,
        turn_id=turn_id,
    )

    if conversation.status == ConversationStatus.HANDED_OFF.value:
        outcome = await respond_handed_off(
            session,
            conversation=conversation,
            customer_id=customer_id,
            customer_message=customer_message,
            correlation_id=correlation_id,
            now=now,
            turn_id=turn_id,
        )
    else:
        outcome = await classify_and_respond(
            session,
            conversation=conversation,
            customer_id=customer_id,
            customer_message=customer_message,
            content=content,
            now=now,
            correlation_id=correlation_id,
            provider=provider,
            provider_mode=provider_mode,
            audit_service=audit_service,
            ai_retry_bound=ai_retry_bound,
            max_clarification_turns=max_clarification_turns,
            policy_provider=policy_provider,
            clock=clock,
            proposal_ttl_minutes=proposal_ttl_minutes,
            turn_id=turn_id,
        )

    conversation.last_message_at = now
    return outcome
