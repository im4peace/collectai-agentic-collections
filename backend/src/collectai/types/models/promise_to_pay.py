"""PromiseToPay domain model (data-models.md PromiseToPay)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from collectai.types.enums import Persona, PtpSource, PtpStatus
from collectai.types.ids import EntityPrefix, id_validator
from collectai.types.money import Money

PtpId = Annotated[str, AfterValidator(id_validator(EntityPrefix.PROMISE_TO_PAY))]
AccountId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]
CustomerId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CUSTOMER))]
ItemId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ITEM))]

_ZERO: Decimal = Decimal("0")


class PromiseToPay(BaseModel):
    """A customer payment commitment. Lifecycle PENDING to KEPT/BROKEN/CANCELLED."""

    model_config = ConfigDict(frozen=True)

    ptp_id: PtpId
    account_id: AccountId
    customer_id: CustomerId
    item_id: ItemId | None
    promised_amount: Money
    promised_date: date
    status: PtpStatus
    cumulative_paid: Money
    interaction_reference: str | None
    source: PtpSource
    created_by_persona: Persona
    created_at: datetime
    updated_at: datetime
    kept_at: datetime | None
    broken_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None = Field(default=None, max_length=500)
    policy_version: str = Field(max_length=40)
    version: int

    @field_validator("promised_amount")
    @classmethod
    def _promised_amount_must_be_positive(cls, value: Money) -> Money:
        if value.amount <= _ZERO:
            raise ValueError("promised_amount must be greater than zero.")
        return value

    @model_validator(mode="after")
    def _check_status_matches_timestamps(self) -> Self:
        if self.status is PtpStatus.KEPT and self.kept_at is None:
            raise ValueError("kept_at must be set when status is KEPT.")
        if self.status is PtpStatus.BROKEN and self.broken_at is None:
            raise ValueError("broken_at must be set when status is BROKEN.")
        if self.status is PtpStatus.CANCELLED and (
            self.cancelled_at is None or self.cancel_reason is None
        ):
            raise ValueError("cancelled_at and cancel_reason must be set when status is CANCELLED.")
        return self

    @property
    def remaining_amount(self) -> Money:
        """Derived, not stored: max(promised_amount - cumulative_paid, 0)."""
        difference = self.promised_amount.amount - self.cumulative_paid.amount
        return Money(max(difference, _ZERO))
