"""DelinquencyRecord domain model (data-models.md DelinquencyRecord)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from collectai.types.enums import Bucket, CollectionStatus
from collectai.types.ids import EntityPrefix, id_validator
from collectai.types.money import Money

AccountId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]
CustomerId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CUSTOMER))]


class DelinquencyRecord(BaseModel):
    """Current snapshot of delinquency facts for one account."""

    model_config = ConfigDict(frozen=True)

    account_id: AccountId
    customer_id: CustomerId
    outstanding_balance: Money
    overdue_amount: Money
    dpd: int = Field(ge=0)
    bucket: Bucket
    collection_status: CollectionStatus
    as_of: datetime | None
    record_version: int = Field(ge=1)
    updated_at: datetime
