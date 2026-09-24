"""ReviewDecision ORM table (data-models.md ReviewDecision; migration 0005).
Maps to `review_decision` -- an insert-only table (deploy/db/init-roles.sql:
`collectai_app` holds INSERT+SELECT only, no UPDATE/DELETE), so every
decision against a case is a new row, never an edit of a prior one."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class ReviewDecisionOrm(Base):
    __tablename__ = "review_decision"

    decision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    case_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text, default=None)
    compliance_outcome: Mapped[str | None] = mapped_column(Text, default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    modification_option_id: Mapped[str | None] = mapped_column(Text, default=None)
    escalate_reason: Mapped[str | None] = mapped_column(Text, default=None)
    rerouted_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    release_suppression: Mapped[bool] = mapped_column(Boolean, default=False)
    overrode_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_persona: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    case_version_after: Mapped[int] = mapped_column()
    policy_version: Mapped[str] = mapped_column(Text)
