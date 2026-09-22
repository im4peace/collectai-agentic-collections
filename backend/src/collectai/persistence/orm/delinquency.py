"""DelinquencyRecord and DelinquentItem ORM tables (data-models.md), grouped
in one module since they are a tight 1:N pair maintained together."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ
from collectai.persistence.orm.types import MoneyType
from collectai.types.money import Money


class DelinquencyRecordOrm(Base):
    __tablename__ = "delinquency_record"

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    outstanding_balance: Mapped[Money] = mapped_column(MoneyType)
    overdue_amount: Mapped[Money] = mapped_column(MoneyType)
    dpd: Mapped[int] = mapped_column()
    bucket: Mapped[str] = mapped_column(Text)
    collection_status: Mapped[str] = mapped_column(Text)
    as_of: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    record_version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


class DelinquentItemOrm(Base):
    __tablename__ = "delinquent_item"

    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    amount_outstanding: Mapped[Money] = mapped_column(MoneyType)
    due_date: Mapped[date] = mapped_column()
    status: Mapped[str] = mapped_column(Text)
