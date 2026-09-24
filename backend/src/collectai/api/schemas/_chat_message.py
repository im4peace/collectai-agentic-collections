"""`ChatMessage`, split into its own module so both `chat.py` and
`chat_proposals.py` can depend on it without an import cycle (`chat.py`'s
`ChatTurnResponse`/`ConversationDetail` need `chat_proposals.Proposal`;
`chat_proposals.py`'s `ConfirmResult`/`CancelProposalResult`/`HandoffResult`
need `ChatMessage`)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from collectai.types.enums import ContentSource as MessageContentSource
from collectai.types.enums import MessageLabel, MessageRole


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
