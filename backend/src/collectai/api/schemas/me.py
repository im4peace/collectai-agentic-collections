"""Customer-facing (`/api/me/*`) wire schemas (api-contracts.md 3.7, section
4: `CustomerAccountSummary`, `CustomerAccountPage`, `PromiseToPay`, `PtpPage`,
`PaymentEvent`, `PaymentEventPage`, `ScheduleEntry`, `ArrangementOption`,
`PaymentArrangement`, `ArrangementPage`, `HardshipCustomerView`,
`DisputeCustomerView`, `EscalationCustomerView`, `EscalationCustomerPage`,
`PageInfo`).

These are wire shapes, distinct from `types.models`'s persisted domain
models: `remaining_amount` is derived (not a stored column), the `*Page`
envelopes are list-shaped, and every model here is deliberately
customer-safe -- fields a customer should not see (e.g.
`EscalationCase.reviewer_role`, `Dispute.customer_reason`,
`HardshipCase.escalation_case_id`) are simply not declared, so leaking one
is a naming error a reviewer can see at a glance rather than a runtime
redaction rule that can be forgotten.

Over 200 lines because it declares 14 response models for 12 endpoints
plus their shared building blocks (`ScheduleEntry`, `ArrangementOption`,
`PageInfo`) in one place, as `api/schemas/session.py` does for the session
endpoints; still comfortably under the 300-line hard block.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from collectai.types.enums import (
    AccountType,
    ArrangementCreatedVia,
    ArrangementStatus,
    CaseStatus,
    CollectionStatus,
    DisputeCategory,
    DisputeOutcome,
    DisputeStatus,
    EscalationReason,
    HardshipIndicatorType,
    HardshipStatus,
    PaymentOutcome,
    PaymentSource,
    Persona,
    PtpSource,
    PtpStatus,
)
from collectai.types.money import Money

SIMULATED_PAYMENT_LABEL = "Simulated payment"

_CUSTOMER_MESSAGE_TEMPLATES: dict[EscalationReason, str] = {
    EscalationReason.REQUEST_HUMAN: (
        "You asked to speak with a team member. A specialist will review your case."
    ),
    EscalationReason.UNRESOLVED_UNKNOWN: (
        "We could not fully resolve your request automatically. "
        "A specialist will review your case."
    ),
    EscalationReason.AI_FAILURE_FALLBACK: (
        "We were unable to complete this automatically. A specialist will review your case."
    ),
    EscalationReason.EXCEPTIONAL_ARRANGEMENT: (
        "Your requested arrangement needs additional review. A specialist will follow up."
    ),
    EscalationReason.FINANCIAL_HARDSHIP: (
        "We have noted the financial difficulty you shared. "
        "A specialist will review your case and follow up."
    ),
    EscalationReason.DISPUTE: "We have recorded your dispute for review by a specialist.",
    EscalationReason.SETTLEMENT_REQUEST: (
        "Your settlement request has been passed to a specialist for review."
    ),
    EscalationReason.AMBIGUOUS_VALIDATION: (
        "We need a specialist to confirm some details on your request."
    ),
    EscalationReason.VULNERABLE_CUSTOMER: (
        "Your case has been passed to a specialist for extra support."
    ),
    EscalationReason.POLICY_EXCEPTION: (
        "Your request needs a policy exception review by a specialist."
    ),
    EscalationReason.HIGH_RISK_COMPLIANCE: (
        "Your case has been passed to our compliance team for review."
    ),
}


def customer_message_for(reason: EscalationReason) -> str:
    """The templated, respectful customer-facing message for an escalation
    reason (`EscalationCustomerView.customer_message`). Never the internal
    `reason` value or reviewer-facing `summary` verbatim."""
    return _CUSTOMER_MESSAGE_TEMPLATES[reason]


class PageInfo(BaseModel):
    """Offset pagination block."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int
    total: int


class CustomerAccountSummary(BaseModel):
    """Customer-safe account summary."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    account_type: AccountType
    product_name: str
    currency: str
    outstanding_balance: Money
    overdue_amount: Money
    collection_status: CollectionStatus


class CustomerAccountPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[CustomerAccountSummary]
    page: PageInfo


class PromiseToPay(BaseModel):
    """Promise-to-Pay record (own -- full shape, api-contracts.md
    `PromiseToPay`)."""

    model_config = ConfigDict(frozen=True)

    ptp_id: str
    account_id: str
    promised_amount: Money
    promised_date: date
    status: PtpStatus
    cumulative_paid: Money
    remaining_amount: Money
    interaction_reference: str | None
    source: PtpSource
    created_by_persona: Persona
    created_at: datetime
    updated_at: datetime
    kept_at: datetime | None
    broken_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    policy_version: str
    version: int


class PtpPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PromiseToPay]
    page: PageInfo


class PaymentEvent(BaseModel):
    """Simulated payment outcome. No real payment ever occurs."""

    model_config = ConfigDict(frozen=True)

    payment_event_id: str
    account_id: str
    amount: Money
    outcome: PaymentOutcome
    source: PaymentSource
    simulated: bool
    simulated_label: str
    occurred_at: datetime
    balance_after: Money
    applied_to_ptp_id: str | None


class PaymentEventPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PaymentEvent]
    page: PageInfo


class ScheduleEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int
    due_date: date
    amount: Money


class ArrangementOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    option_id: str
    installment_count: int
    installment_amount: Money
    final_installment_amount: Money
    total_amount: Money
    first_installment_date: date
    frequency: str
    schedule: list[ScheduleEntry]


class PaymentArrangement(BaseModel):
    model_config = ConfigDict(frozen=True)

    arrangement_id: str
    account_id: str
    status: ArrangementStatus
    option: ArrangementOption
    created_via: ArrangementCreatedVia
    exception_case_id: str | None
    policy_version: str
    created_at: datetime


class ArrangementPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PaymentArrangement]
    page: PageInfo


class HardshipCustomerView(BaseModel):
    """Customer-safe hardship record."""

    model_config = ConfigDict(frozen=True)

    hardship_case_id: str
    status: HardshipStatus
    indicator_types: list[HardshipIndicatorType]
    created_at: datetime


class DisputeCustomerView(BaseModel):
    """Customer-safe dispute record."""

    model_config = ConfigDict(frozen=True)

    dispute_id: str
    item_id: str | None
    category: DisputeCategory
    status: DisputeStatus
    outcome: DisputeOutcome | None
    created_at: datetime
    resolved_at: datetime | None


class EscalationCustomerView(BaseModel):
    """Customer-safe escalation view."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    account_id: str
    status: CaseStatus
    customer_message: str
    created_at: datetime
    decided_at: datetime | None


class EscalationCustomerPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[EscalationCustomerView]
    page: PageInfo
