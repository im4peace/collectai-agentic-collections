"""Low-level ORM row construction for one chat turn (E6-S1).

`chat_message.turn_id` and `chat_turn` reference each other. Migration
`0008_defer_chat_message_turn_fk` makes `fk_chat_message_turn` DEFERRABLE
INITIALLY DEFERRED so the caller can generate a turn id up front, insert
both `chat_message` rows with that `turn_id` already set (pointing at a
`chat_turn` row that does not exist yet), then insert the `chat_turn` row
itself -- the FK is only checked at COMMIT, by which point it holds. This
never issues an UPDATE against `chat_message`: `collectai_app` is granted
only INSERT+SELECT on that table (deploy/db/init-roles.sql), so an
insert-then-back-fill order can never work against the real runtime role,
only against an unrestricted superuser/owner connection -- see 0008's own
docstring for how this was found.
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
    turn_id: str | None = None,
) -> ChatMessageOrm:
    """`turn_id` is `None` for a message that is never part of a `chat_turn`
    (the conversation-opening greeting, and standalone confirmation/handoff
    replies), or a turn id the caller already generated -- see this module's
    docstring for why the row can carry that id before `chat_turn` itself
    exists."""
    row = ChatMessageOrm(
        message_id=generate_id(EntityPrefix.MESSAGE),
        conversation_id=conversation_id,
        customer_id=customer_id,
        turn_id=turn_id,
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
    turn_id: str,
    conversation_id: str,
    customer_id: str,
    customer_message: ChatMessageOrm,
    assistant_message: ChatMessageOrm,
    intent: dict[str, object] | None,
    safe_state: str,
    correlation_id: str,
    created_at: datetime,
    proposal_id: str | None = None,
) -> ChatTurnOrm:
    """Insert `chat_turn` under the `turn_id` the caller already generated
    and already set on both `customer_message`/`assistant_message` when it
    persisted them -- see this module's docstring. `proposal_id` (E6-S2/
    E6-S3) is the `Proposal` this turn created, if any -- `None` for every
    turn before this group and for any turn that did not result in a
    proposal."""
    turn = ChatTurnOrm(
        turn_id=turn_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        customer_message_id=customer_message.message_id,
        assistant_message_id=assistant_message.message_id,
        intent=intent,
        proposal_id=proposal_id,
        safe_state=safe_state,
        correlation_id=correlation_id,
        tool_call_count=0,
        created_at=created_at,
    )
    session.add(turn)
    await session.flush()
    return turn
