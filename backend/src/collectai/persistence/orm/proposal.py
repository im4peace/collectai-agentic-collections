"""Proposal ORM table (data-models.md Proposal, D-041). Maps to `proposal`.

A deterministic, customer-visible proposal awaiting explicit confirmation
(E6-S2, E6-S3). Created only by `domain_services.proposal_service` -- never
directly by the LLM (CLAUDE.md's core engineering principle) and never by a
router handler.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class ProposalOrm(Base):
    __tablename__ = "proposal"

    proposal_id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(Text, default=None)
    case_id: Mapped[str | None] = mapped_column(Text, default=None)
    customer_id: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    terms: Mapped[dict[str, object]] = mapped_column(JSONB)
    terms_hash: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    record_version: Mapped[int] = mapped_column()
    policy_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    resulting_resource_id: Mapped[str | None] = mapped_column(Text, default=None)
