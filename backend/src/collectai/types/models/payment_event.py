"""PaymentEvent domain model (data-models.md PaymentEvent). Always SIMULATED (D-021)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator

from collectai.types.enums import PaymentOutcome, PaymentSource, Persona
from collectai.types.ids import EntityPrefix, id_validator
from collectai.types.money import Money

PaymentEventId = Annotated[str, AfterValidator(id_validator(EntityPrefix.PAYMENT_EVENT))]
AccountId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]
CustomerId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CUSTOMER))]
PtpId = Annotated[str, AfterValidator(id_validator(EntityPrefix.PROMISE_TO_PAY))]
ProposalId = Annotated[str, AfterValidator(id_validator(EntityPrefix.PROPOSAL))]

_ZERO: Decimal = Decimal("0")


class PaymentEvent(BaseModel):
    """A SIMULATED payment outcome. No real payment ever occurs (D-021)."""

    model_config = ConfigDict(frozen=True)

    payment_event_id: PaymentEventId
    account_id: AccountId
    customer_id: CustomerId
    amount: Money
    outcome: PaymentOutcome
    source: PaymentSource
    simulated: Literal[True]
    occurred_at: datetime
    balance_after: Money
    applied_to_ptp_id: PtpId | None
    proposal_id: ProposalId | None
    created_by_persona: Persona

    @field_validator("amount")
    @classmethod
    def _amount_must_be_positive(cls, value: Money) -> Money:
        if value.amount <= _ZERO:
            raise ValueError("amount must be greater than zero.")
        return value
