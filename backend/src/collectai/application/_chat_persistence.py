"""Low-level ORM row construction for one chat turn (E6-S1).

Insert order follows migration `0002_conversation_chat`'s own note:
`chat_message` rows are written with `turn_id=NULL` first, then `chat_turn`
(which references both message ids by FK), then each `chat_message.turn_id`
is set once the `chat_turn` row exists -- otherwise `turn_id`'s FK (added by
that migration's `_add_chat_message_turn_fk`, after `chat_turn` itself is
created) can never be satisfied.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.chat_turn import ChatTurnOrm
from collectai.types.enums import ContentSource, MessageLabel, MessageRole
from collectai.types.ids import EntityPrefix, generate_id


async def persist_message(
    session: AsyncSession,
    *,
    conversation_id: str,
    customer_id: str,
    role: MessageRole,
    content: str,
    content_source: ContentSource,
    labels: list[MessageLabel],
    created_at: datetime,
) -> ChatMessageOrm:
    row = ChatMessageOrm(
        message_id=generate_id(EntityPrefix.MESSAGE),
        conversation_id=conversation_id,
        customer_id=customer_id,
        turn_id=None,
        role=role.value,
        content=content,
        content_source=content_source.value,
        labels=[label.value for label in labels],
        created_at=created_at,
    )
    session.add(row)
    await session.flush()
    return row


async def persist_turn(
    session: AsyncSession,
    *,
    conversation_id: str,
    customer_id: str,
    customer_message: ChatMessageOrm,
    assistant_message: ChatMessageOrm,
    intent: dict[str, object] | None,
    safe_state: str,
    correlation_id: str,
    created_at: datetime,
) -> ChatTurnOrm:
    """Insert `chat_turn`, then back-fill both messages' `turn_id` -- see
    this module's docstring for why that order is required."""
    turn = ChatTurnOrm(
        turn_id=generate_id(EntityPrefix.CHAT_TURN),
        conversation_id=conversation_id,
        customer_id=customer_id,
        customer_message_id=customer_message.message_id,
        assistant_message_id=assistant_message.message_id,
        intent=intent,
        proposal_id=None,
        safe_state=safe_state,
        correlation_id=correlation_id,
        tool_call_count=0,
        created_at=created_at,
    )
    session.add(turn)
    await session.flush()
    customer_message.turn_id = turn.turn_id
    assistant_message.turn_id = turn.turn_id
    await session.flush()
    return turn
