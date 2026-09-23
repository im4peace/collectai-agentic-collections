"""ORM row -> `/api/me/*` response-schema mappers, split out of `me.py` to
keep that module focused on request handling and ownership checks (mirrors
`api/middleware/error_types.py` being split out of `errors.py`). Pure
functions only: no session, no I/O, so every mapper here is trivially unit
-testable without a database.
"""

from __future__ import annotations

from decimal import Decimal

from collectai.api.schemas.me import (
    SIMULATED_PAYMENT_LABEL,
    ArrangementOption,
    CustomerAccountSummary,
    DisputeCustomerView,
    EscalationCustomerView,
    HardshipCustomerView,
    PaymentArrangement,
    PaymentEvent,
    PromiseToPay,
    ScheduleEntry,
    customer_message_for,
)
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
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

_ZERO: Decimal = Decimal("0")


def account_summary(
    account: AccountOrm, delinquency: DelinquencyRecordOrm
) -> CustomerAccountSummary:
    return CustomerAccountSummary(
        account_id=account.account_id,
        account_type=AccountType(account.account_type),
        product_name=account.product_name,
        currency=account.currency,
        outstanding_balance=delinquency.outstanding_balance,
        overdue_amount=delinquency.overdue_amount,
        collection_status=CollectionStatus(delinquency.collection_status),
    )


def ptp_view(row: PromiseToPayOrm) -> PromiseToPay:
    remaining = max(row.promised_amount.amount - row.cumulative_paid.amount, _ZERO)
    return PromiseToPay(
        ptp_id=row.ptp_id,
        account_id=row.account_id,
        promised_amount=row.promised_amount,
        promised_date=row.promised_date,
        status=PtpStatus(row.status),
        cumulative_paid=row.cumulative_paid,
        remaining_amount=Money(remaining),
        interaction_reference=row.interaction_reference,
        source=PtpSource(row.source),
        created_by_persona=Persona(row.created_by_persona),
        created_at=row.created_at,
        updated_at=row.updated_at,
        kept_at=row.kept_at,
        broken_at=row.broken_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
        policy_version=row.policy_version,
        version=row.version,
    )


def payment_event_view(row: PaymentEventOrm) -> PaymentEvent:
    return PaymentEvent(
        payment_event_id=row.payment_event_id,
        account_id=row.account_id,
        amount=row.amount,
        outcome=PaymentOutcome(row.outcome),
        source=PaymentSource(row.source),
        simulated=row.simulated,
        simulated_label=SIMULATED_PAYMENT_LABEL,
        occurred_at=row.occurred_at,
        balance_after=row.balance_after,
        applied_to_ptp_id=row.applied_to_ptp_id,
    )


def _schedule_entries(schedule: list[object]) -> list[ScheduleEntry]:
    return [
        ScheduleEntry(
            sequence=entry["sequence"],  # type: ignore[index]
            due_date=entry["due_date"],  # type: ignore[index]
            amount=Money(entry["amount"]),  # type: ignore[index]
        )
        for entry in schedule
    ]


def arrangement_view(row: PaymentArrangementOrm) -> PaymentArrangement:
    option = ArrangementOption(
        option_id=row.option_id,
        installment_count=row.installment_count,
        installment_amount=row.installment_amount,
        final_installment_amount=row.final_installment_amount,
        total_amount=row.total_amount,
        first_installment_date=row.first_installment_date,
        frequency=row.frequency,
        schedule=_schedule_entries(row.schedule),
    )
    return PaymentArrangement(
        arrangement_id=row.arrangement_id,
        account_id=row.account_id,
        status=ArrangementStatus(row.status),
        option=option,
        created_via=ArrangementCreatedVia(row.created_via),
        exception_case_id=row.exception_case_id,
        policy_version=row.policy_version,
        created_at=row.created_at,
    )


def hardship_view(row: HardshipCaseOrm) -> HardshipCustomerView:
    indicator_types = [
        HardshipIndicatorType(indicator["indicator_type"])  # type: ignore[index]
        for indicator in row.indicators
    ]
    return HardshipCustomerView(
        hardship_case_id=row.hardship_case_id,
        status=HardshipStatus(row.status),
        indicator_types=indicator_types,
        created_at=row.created_at,
    )


def dispute_view(row: DisputeOrm) -> DisputeCustomerView:
    return DisputeCustomerView(
        dispute_id=row.dispute_id,
        item_id=row.item_id,
        category=DisputeCategory(row.category),
        status=DisputeStatus(row.status),
        outcome=DisputeOutcome(row.outcome) if row.outcome is not None else None,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def escalation_view(row: EscalationCaseOrm) -> EscalationCustomerView:
    return EscalationCustomerView(
        case_id=row.case_id,
        account_id=row.account_id,
        status=CaseStatus(row.status),
        customer_message=customer_message_for(EscalationReason(row.reason)),
        created_at=row.created_at,
        decided_at=row.decided_at,
    )
