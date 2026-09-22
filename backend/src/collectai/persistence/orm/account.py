"""Account ORM table (data-models.md Account). Maps to `account`."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class AccountOrm(Base):
    __tablename__ = "account"

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    account_type: Mapped[str] = mapped_column(Text)
    product_name: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text)
    opened_on: Mapped[date] = mapped_column()
    product_attributes: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
