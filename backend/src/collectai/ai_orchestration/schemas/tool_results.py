"""Pydantic result schemas for the six-tool registry (E5-S4 AC5).

`EligibleOptionsResult.arrangement_options` is always empty in Slice 1
(payable amounts and the PTP date window only, per AC5); its item type
(`ArrangementOptionSummary`, shaped like `data-models.md`'s
`PaymentArrangement`/`ArrangementOption`) is defined now so a Slice-2 story
(E8-S1) can populate it later without changing this schema's shape.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    DisputeCategory,
    EscalationPriority,
    EscalationReason,
    HardshipIndicatorType,
    PayableOptionType,
    ReviewerRole,
    ReviewQueue,
)
from collectai.types.models.account import AccountId, CustomerId
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode


class AccountContextResult(StrictToolModel):
    """READ `get_account_context`'s account/customer/delinquency snapshot."""

    account_id: AccountId
    customer_id: CustomerId
    account_type: AccountType
    product_name: str
    opened_on: date
    outstanding_balance: Money
    overdue_amount: Money
    dpd: int
    bucket: Bucket
    collection_status: CollectionStatus
    as_of: datetime | None
    record_version: int


class PayableOptionResult(StrictToolModel):
    option_type: PayableOptionType
    amount: Money


class PtpDateWindowResult(StrictToolModel):
    earliest: date
    latest: date


class ArrangementOptionSummary(StrictToolModel):
    """Slice-2 shape; never populated in Slice 1 -- see this module's
    docstring."""

    option_id: str
    installment_count: int
    installment_amount: Money
    total_amount: Money
    first_installment_date: date


class EligibleOptionsResult(StrictToolModel):
    account_id: AccountId
    payable_options: list[PayableOptionResult]
    ptp_date_window: PtpDateWindowResult
    arrangement_options: list[ArrangementOptionSummary] = Field(default_factory=list)


class AmountRangeResult(StrictToolModel):
    min: Money
    max: Money


class DateRangeResult(StrictToolModel):
    earliest: date
    latest: date


class PtpAlternativesResult(StrictToolModel):
    valid_amount_range: AmountRangeResult | None = None
    valid_date_range: DateRangeResult | None = None


class ProposePtpResult(StrictToolModel):
    """Mirrors `rules_engine.ptp_rules.PtpValidationOutcome`, including
    `alternatives` on rejection."""

    account_id: AccountId
    promised_amount: str
    promised_date: date
    valid: bool
    reason_codes: list[ReasonCode]
    alternatives: PtpAlternativesResult | None = None


class FlagHardshipResult(StrictToolModel):
    """A validated echo (AC1 description): no `hardship_case` row is written
    by this story -- see E8-S2."""

    account_id: AccountId
    indicator_type: HardshipIndicatorType
    note: str


class FlagDisputeResult(StrictToolModel):
    """A validated echo: no `dispute` row is written by this story -- see
    E8-S3."""

    account_id: AccountId
    category: DisputeCategory
    customer_reason: str
    item_id: str | None = None


class EscalateToHumanResult(StrictToolModel):
    """Mirrors `rules_engine.routing.RoutingResult`; `rationale` is the
    model-proposed text, echoed for traceability -- routing itself never
    reads it."""

    reason: EscalationReason | None
    queue: ReviewQueue
    reviewer_role: ReviewerRole
    priority: EscalationPriority
    policy_version: str | None
    flags: list[str]
    rationale: str
