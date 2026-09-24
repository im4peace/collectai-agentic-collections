"""ORM row -> `/api/chat/*` response-schema mappers, split out of `chat.py`
to keep that module focused on request handling and dependency wiring
(mirrors `api/routers/me_views.py` being split out of `me.py`). Pure
functions only: no session, no I/O, so every mapper here is trivially
unit-testable without a database.
"""

from __future__ import annotations

from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.api.schemas.chat import ChatMessage, Conversation, IntentSummary
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.enums import ContentSource, ConversationStatus, MessageLabel, MessageRole


def conversation_view(row: ConversationOrm) -> Conversation:
    return Conversation(
        conversation_id=row.conversation_id,
        account_id=row.account_id,
        status=ConversationStatus(row.status),
        created_at=row.created_at,
        last_message_at=row.last_message_at,
    )


def message_view(row: ChatMessageOrm) -> ChatMessage:
    return ChatMessage(
        message_id=row.message_id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        content_source=ContentSource(row.content_source),
        labels=[MessageLabel(label) for label in row.labels],
        created_at=row.created_at,
    )


def intent_summary(intent: IntentResult | None) -> IntentSummary | None:
    if intent is None:
        return None
    return IntentSummary(
        label=intent.label,
        confidence=intent.confidence,
        vulnerability_detected=intent.vulnerability_detected,
        special_request=intent.special_request,
    )
