"""Recommendation ORM table (data-models.md Recommendation). Maps to
`recommendation` (migration 0002's `_create_recommendation_table`; this
module was the missing SQLAlchemy layer -- E4-S3).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class RecommendationOrm(Base):
    __tablename__ = "recommendation"

    recommendation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    referenced_factor_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    status: Mapped[str] = mapped_column(Text)
    content_source: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_version: Mapped[str | None] = mapped_column(Text, default=None)
    policy_version: Mapped[str] = mapped_column(Text)
    record_version: Mapped[int] = mapped_column()
    correlation_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    audit_event_id: Mapped[str] = mapped_column(Text)
    officer_decision: Mapped[str | None] = mapped_column(Text, default=None)
    officer_decision_reason: Mapped[str | None] = mapped_column(Text, default=None)
    officer_chosen_action: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by_persona: Mapped[str | None] = mapped_column(Text, default=None)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
