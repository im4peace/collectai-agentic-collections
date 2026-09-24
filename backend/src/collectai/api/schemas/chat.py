"""Customer chat (`/api/chat/*`) wire schemas (api-contracts.md 3.8,
section 4: `ConversationCreateRequest`, `ChatMessage`, `IntentSummary`,
`MessageCreateRequest`, `ChatTurnResponse`, `Conversation`,
`ConversationDetail`, `ConversationCreateResult`, `ConversationPage`).

`ChatTurnResponse.proposal` and `ConversationDetail.pending_proposal` are
widened, as of E6-S2/E6-S3, from the always-`None` placeholder E6-S1 shipped
to the real `chat_proposals.Proposal` shape -- this is the "a later story
widens `proposal`'s type without otherwise changing this schema" the
original docstring anticipated. `handoff` is similarly widened, as of E7-S1,
to be populated whenever a real `escalation_case` exists for the
conversation. `escalation_reported`/`escalation_reason` are E6-S1's own
addition: `SafeState` has no member meaning "a sensitive/UNKNOWN outcome was
reported to escalation, but no case exists yet" (see
`application.chat_flow`'s module docstring for the full design note), so
these two fields carry that signal explicitly instead of overloading
`safe_state`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from collectai.api.schemas._chat_message import ChatMessage
from collectai.api.schemas.chat_proposals import Proposal
from collectai.api.schemas.me import EscalationCustomerView, PageInfo
from collectai.types.enums import (
    ConversationStatus,
    EscalationReason,
    Intent,
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
    pending_proposal: Proposal | None = None
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
    proposal: Proposal | None = None
    handoff: EscalationCustomerView | None = None
    safe_state: SafeState
    talk_to_human_available: bool
    correlation_id: str
    escalation_reported: bool
    escalation_reason: EscalationReason | None
