"""HardshipCase ORM table (data-models.md HardshipCase). Maps to `hardship_case`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class HardshipCaseOrm(Base):
    __tablename__ = "hardship_case"

    hardship_case_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text)
    indicators: Mapped[list[object]] = mapped_column(JSONB)
    escalation_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    version: Mapped[int] = mapped_column(default=1)
