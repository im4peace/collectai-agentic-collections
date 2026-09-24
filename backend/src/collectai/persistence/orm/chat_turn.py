"""ChatTurn ORM table (data-models.md ChatTurn). Maps to `chat_turn`
(migration `0002_conversation_chat`).

`intent` is the full validated `ai_orchestration.schemas.intent.IntentResult`
dump (or `NULL` when the AI provider/audit path failed for this turn --
`ChatTurnResponse.intent` is likewise `null` in that case). `proposal_id`
stays `NULL`/unused by this story (E6-S1): proposal persistence belongs to
E6-S2, which this story deliberately does not implement (AC4).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class ChatTurnOrm(Base):
    __tablename__ = "chat_turn"

    turn_id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    customer_message_id: Mapped[str] = mapped_column(Text)
    assistant_message_id: Mapped[str] = mapped_column(Text)
    intent: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    proposal_id: Mapped[str | None] = mapped_column(Text, default=None)
    safe_state: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(Text)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
