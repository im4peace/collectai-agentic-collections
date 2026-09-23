"""IdempotencyRecord ORM table (data-models.md IdempotencyRecord). Maps to
`idempotency_record` (migration 0006). Stores the result of an idempotent
operation so replays return the original result (D-037) instead of
re-executing it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class IdempotencyRecordOrm(Base):
    __tablename__ = "idempotency_record"

    idempotency_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int] = mapped_column()
    response_body: Mapped[dict[str, object]] = mapped_column(JSONB)
    resource_type: Mapped[str | None] = mapped_column(Text, default=None)
    resource_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
