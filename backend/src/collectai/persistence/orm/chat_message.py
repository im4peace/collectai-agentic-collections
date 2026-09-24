"""ChatMessage ORM table (data-models.md ChatMessage). Maps to `chat_message`
(migration `0002_conversation_chat`).

`turn_id` starts `None` and is set once the owning `ChatTurnOrm` row exists
-- `chat_message.turn_id`'s FK (added by that migration's
`_add_chat_message_turn_fk`, after `chat_turn` itself is created) cannot be
satisfied any earlier, since `chat_turn` itself references two
`chat_message` rows (`customer_message_id`, `assistant_message_id`). See
`application._chat_persistence` for the insert-order sequencing this
requires.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class ChatMessageOrm(Base):
    __tablename__ = "chat_message"

    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    turn_id: Mapped[str | None] = mapped_column(Text, default=None)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_source: Mapped[str] = mapped_column(Text)
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
