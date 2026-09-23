"""DemoSession ORM table (data-models.md DemoSession). Maps to the
`demo_session` table created by migration 0006. NOT authentication: a row
here only records which persona a caller last selected, and (for CUSTOMER)
which seeded customer that session is bound to server-side (E3-S1 AC1-AC5,
E3-S5 object-level authorization).

`session_token_hash` is the primary key and the only thing ever looked up by
a caller-supplied `X-Demo-Session` value: the raw opaque token is returned
once by `POST /api/session` and never stored (data-models.md DemoSession).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class DemoSessionOrm(Base):
    __tablename__ = "demo_session"

    session_token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    persona: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
