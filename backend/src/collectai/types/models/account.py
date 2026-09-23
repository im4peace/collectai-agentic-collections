"""Account domain model (data-models.md Account)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from collectai.types.enums import AccountType
from collectai.types.ids import EntityPrefix, id_validator
from collectai.types.money import Money

AccountId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]
CustomerId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CUSTOMER))]


class CardProductAttributes(BaseModel):
    """product_attributes shape when Account.account_type is CARD."""

    model_config = ConfigDict(frozen=True)

    credit_limit: Money
    minimum_payment_due: Money


class PersonalLoanProductAttributes(BaseModel):
    """product_attributes shape when Account.account_type is PERSONAL_LOAN."""

    model_config = ConfigDict(frozen=True)

    original_principal: Money
    term_months: int = Field(ge=1)
    monthly_installment: Money


class Account(BaseModel):
    """A CARD or PERSONAL_LOAN account (data-models.md Account)."""

    model_config = ConfigDict(frozen=True)

    account_id: AccountId
    customer_id: CustomerId
    account_type: AccountType
    product_name: str = Field(max_length=120)
    currency: Literal["AED"]
    opened_on: date
    product_attributes: CardProductAttributes | PersonalLoanProductAttributes
    created_at: datetime

    @model_validator(mode="after")
    def _check_product_attributes_match_account_type(self) -> Self:
        if self.account_type is AccountType.CARD and not isinstance(
            self.product_attributes, CardProductAttributes
        ):
            raise ValueError("CARD accounts require CardProductAttributes.")
        if self.account_type is AccountType.PERSONAL_LOAN and not isinstance(
            self.product_attributes, PersonalLoanProductAttributes
        ):
            raise ValueError("PERSONAL_LOAN accounts require PersonalLoanProductAttributes.")
        return self
