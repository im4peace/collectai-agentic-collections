"""Dispute ORM table (data-models.md Dispute). Maps to `dispute`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class DisputeOrm(Base):
    __tablename__ = "dispute"

    dispute_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    item_id: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(Text)
    customer_reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    resolution_reason: Mapped[str | None] = mapped_column(Text, default=None)
    conversation_id: Mapped[str | None] = mapped_column(Text, default=None)
    escalation_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    version: Mapped[int] = mapped_column(default=1)
