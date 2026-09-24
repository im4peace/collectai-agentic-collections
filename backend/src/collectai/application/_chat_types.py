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
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.proposal import ProposalOrm
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
    proposal: ProposalOrm | None = None
    """E6-S2/E6-S3: the `Proposal` this turn created, if any (never set by
    `respond_handed_off`/`_respond_unclassifiable`, which default it via
    this field's own default)."""
    escalation_case: EscalationCaseOrm | None = None
    """E7-S1: the real `EscalationCase` this turn created (or the existing
    one AC6's idempotent dedup returned), when `escalation_reported` is
    true."""
