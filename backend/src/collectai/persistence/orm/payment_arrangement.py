"""PaymentArrangement ORM table (data-models.md PaymentArrangement).
Maps to `payment_arrangement`."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ
from collectai.persistence.orm.types import MoneyType
from collectai.types.money import Money


class PaymentArrangementOrm(Base):
    __tablename__ = "payment_arrangement"

    arrangement_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_via: Mapped[str] = mapped_column(Text)
    exception_case_id: Mapped[str | None] = mapped_column(Text, default=None)
    option_id: Mapped[str] = mapped_column(Text)
    installment_count: Mapped[int] = mapped_column()
    installment_amount: Mapped[Money] = mapped_column(MoneyType)
    final_installment_amount: Mapped[Money] = mapped_column(MoneyType)
    total_amount: Mapped[Money] = mapped_column(MoneyType)
    first_installment_date: Mapped[date] = mapped_column()
    frequency: Mapped[str] = mapped_column(Text, default="MONTHLY")
    schedule: Mapped[list[object]] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    version: Mapped[int] = mapped_column(default=1)
