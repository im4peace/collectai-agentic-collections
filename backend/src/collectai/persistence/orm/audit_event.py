"""AuditEvent ORM table (data-models.md AuditEvent). Maps to `audit_event`.

`sequence` is a database identity column (migration 0007, `GENERATED ALWAYS
AS IDENTITY`). Callers never set it when constructing this class; it is
populated by `AuditService` reading it back from the row after
`session.flush()` (`server_default=FetchedValue()` tells SQLAlchemy to fetch
the server-generated value on insert).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, FetchedValue, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class AuditEventOrm(Base):
    __tablename__ = "audit_event"

    audit_event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, server_default=FetchedValue())
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    correlation_id: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    actor_kind: Mapped[str] = mapped_column(Text)
    actor_persona: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[str | None] = mapped_column(Text)
    capability: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    provider_mode: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    policy_version: Mapped[str | None] = mapped_column(Text)
    input_ref: Mapped[str | None] = mapped_column(Text)
    ai_output: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    tool_calls: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    rule_results: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    human_override: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    final_action: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(Text)
    latency: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    token_usage: Mapped[dict[str, object] | None] = mapped_column(JSONB)
