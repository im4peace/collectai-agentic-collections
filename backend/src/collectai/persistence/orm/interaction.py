"""Interaction ORM table (data-models.md Interaction). Maps to `interaction`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class InteractionOrm(Base):
    __tablename__ = "interaction"

    interaction_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    summary: Mapped[str] = mapped_column(Text)
    counts_as_attempt: Mapped[bool] = mapped_column(Boolean)
    conversation_id: Mapped[str | None] = mapped_column(Text, default=None)
