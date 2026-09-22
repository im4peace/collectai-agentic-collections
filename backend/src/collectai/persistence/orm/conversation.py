"""Conversation ORM table (data-models.md Conversation). Maps to `conversation`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class ConversationOrm(Base):
    __tablename__ = "conversation"

    conversation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    clarification_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
