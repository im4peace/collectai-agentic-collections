"""PaymentEvent ORM table (data-models.md PaymentEvent). Maps to `payment_event`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ
from collectai.persistence.orm.types import MoneyType
from collectai.types.money import Money


class PaymentEventOrm(Base):
    __tablename__ = "payment_event"

    payment_event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text)
    amount: Mapped[Money] = mapped_column(MoneyType)
    outcome: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    balance_after: Mapped[Money] = mapped_column(MoneyType)
    applied_to_ptp_id: Mapped[str | None] = mapped_column(Text, default=None)
    proposal_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_persona: Mapped[str] = mapped_column(Text)
