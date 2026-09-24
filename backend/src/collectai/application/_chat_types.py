"""Shared result dataclasses for the chat flow (E6-S1), split into their own
module so `chat_flow.py` and `_chat_turn_processing.py` can both depend on
them without an import cycle (`chat_flow.py` composes
`_chat_turn_processing.py`'s functions; those functions return these
types)."""

from __future__ import annotations

from dataclasses import dataclass

from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.chat_turn import ChatTurnOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.enums import EscalationReason, SafeState


@dataclass(frozen=True, slots=True)
class ConversationCreateOutcome:
    conversation: ConversationOrm
    greeting: ChatMessageOrm


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    turn: ChatTurnOrm
    customer_message: ChatMessageOrm
    assistant_message: ChatMessageOrm
    intent: IntentResult | None
    safe_state: SafeState
    escalation_reported: bool
    escalation_reason: EscalationReason | None
