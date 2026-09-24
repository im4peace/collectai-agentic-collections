"""Customer chat (`/api/chat/*`) wire schemas (api-contracts.md 3.8,
section 4: `ConversationCreateRequest`, `ChatMessage`, `IntentSummary`,
`MessageCreateRequest`, `ChatTurnResponse`, `Conversation`,
`ConversationDetail`, `ConversationCreateResult`, `ConversationPage`).

`ChatTurnResponse.proposal` and `.handoff` are always `None` in this story
(E6-S1): proposal persistence is E6-S2/E6-S3, and a populated `handoff`
needs a real `escalation_case` row, which only E6-S5/E7-S1 create. Both
fields are still declared here (typed as the always-`None` shape for now)
so this response matches api-contracts.md's `ChatTurnResponse` field set --
a later story widens `proposal`'s type without otherwise changing this
schema. `escalation_reported`/`escalation_reason` are this story's own
addition: `SafeState` has no member meaning "a sensitive/UNKNOWN outcome was
reported to escalation, but no case exists yet" (see
`application.chat_flow`'s module docstring for the full design note), so
these two fields carry that signal explicitly instead of overloading
`safe_state`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from collectai.api.schemas.me import EscalationCustomerView, PageInfo
from collectai.types.enums import ContentSource as MessageContentSource
from collectai.types.enums import (
    ConversationStatus,
    EscalationReason,
    Intent,
    MessageLabel,
    MessageRole,
    SafeState,
    SpecialRequest,
)

__all__ = [
    "ChatMessage",
    "ChatTurnResponse",
    "Conversation",
    "ConversationCreateRequest",
    "ConversationCreateResult",
    "ConversationDetail",
    "ConversationPage",
    "IntentSummary",
    "MessageCreateRequest",
]


class ConversationCreateRequest(BaseModel):
    """Start a conversation on one of the customer's own accounts. Unknown
    fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str


class MessageCreateRequest(BaseModel):
    """Customer message. Unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1, max_length=2000)


class ChatMessage(BaseModel):
    """One message (api-contracts.md `ChatMessage`)."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    conversation_id: str
    role: MessageRole
    content: str
    content_source: MessageContentSource
    labels: list[MessageLabel]
    created_at: datetime


class IntentSummary(BaseModel):
    """Advisory interpretation summary (never authoritative)."""

    model_config = ConfigDict(frozen=True)

    label: Intent
    confidence: float
    vulnerability_detected: bool
    special_request: SpecialRequest


class Conversation(BaseModel):
    """Conversation header."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    account_id: str
    status: ConversationStatus
    created_at: datetime
    last_message_at: datetime | None


class ConversationDetail(BaseModel):
    """Conversation with messages."""

    model_config = ConfigDict(frozen=True)

    conversation: Conversation
    messages: list[ChatMessage]
    pending_proposal: None = None
    handoff: EscalationCustomerView | None = None


class ConversationCreateResult(BaseModel):
    """New conversation with AI disclosure greeting (AC1)."""

    model_config = ConfigDict(frozen=True)

    conversation: Conversation
    greeting: ChatMessage
    talk_to_human_available: bool


class ConversationPage(BaseModel):
    """Own conversations."""

    model_config = ConfigDict(frozen=True)

    items: list[Conversation]
    page: PageInfo


class ChatTurnResponse(BaseModel):
    """Whole-message response for one turn (no streaming)."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    turn_id: str
    customer_message: ChatMessage
    assistant_message: ChatMessage
    intent: IntentSummary | None
    proposal: None = None
    handoff: EscalationCustomerView | None = None
    safe_state: SafeState
    talk_to_human_available: bool
    correlation_id: str
    escalation_reported: bool
    escalation_reason: EscalationReason | None
