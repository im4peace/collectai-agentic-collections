"""Customer ORM table (data-models.md Customer). Maps to the `customer` table
created by migration 0001. No native FK objects are declared here: the
database-level constraints (CHECKs, FKs, partial indexes) are the single
source of truth, created explicitly by the migrations in
`persistence/migrations/versions/`; this class only describes column shapes
for the ORM session to read and write.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class CustomerOrm(Base):
    __tablename__ = "customer"

    customer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    vulnerability_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    vulnerability_category: Mapped[str | None] = mapped_column(Text, default=None)
    vulnerability_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
