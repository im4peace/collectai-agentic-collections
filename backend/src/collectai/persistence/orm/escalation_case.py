"""EscalationCase ORM table (data-models.md EscalationCase). Maps to `escalation_case`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class EscalationCaseOrm(Base):
    __tablename__ = "escalation_case"

    case_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text, default=None)
    item_id: Mapped[str | None] = mapped_column(Text, default=None)
    reason: Mapped[str] = mapped_column(Text)
    queue: Mapped[str] = mapped_column(Text)
    reviewer_role: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    requested_terms: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    exception_types: Mapped[list[str] | None] = mapped_column(ARRAY(Text), default=None)
    hardship_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    dispute_id: Mapped[str | None] = mapped_column(Text, default=None)
    recommendation_id: Mapped[str | None] = mapped_column(Text, default=None)
    parent_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    rerouted_to_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    routing_policy_version: Mapped[str] = mapped_column(Text)
    routing_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    first_reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    version: Mapped[int] = mapped_column(default=1)
