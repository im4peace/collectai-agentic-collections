"""PromiseToPay ORM table (data-models.md PromiseToPay). Maps to `promise_to_pay`."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ
from collectai.persistence.orm.types import MoneyType
from collectai.types.money import Money


class PromiseToPayOrm(Base):
    __tablename__ = "promise_to_pay"

    ptp_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    item_id: Mapped[str | None] = mapped_column(Text, default=None)
    promised_amount: Mapped[Money] = mapped_column(MoneyType)
    promised_date: Mapped[date] = mapped_column()
    status: Mapped[str] = mapped_column(Text)
    cumulative_paid: Mapped[Money] = mapped_column(MoneyType)
    interaction_reference: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(Text)
    created_by_persona: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    kept_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    broken_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(Text, default=None)
    policy_version: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
