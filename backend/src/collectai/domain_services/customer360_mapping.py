"""Pure ORM/domain -> `api.schemas.customer360` mapping helpers for E4-S1.

Split out of `customer360_service.py` once field-by-field mapping pushed
that module past the 300-line block threshold, mirroring
`api/middleware/error_types.py`'s split from `errors.py`. Every function is
pure (no session, no I/O, no rules-engine call): given already-fetched ORM
rows, it returns the wire-shape Pydantic model. `customer360_service.py`
owns fetching, fact-derivation and rules-engine orchestration.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from collectai.api.schemas.customer360 import (
    AccountBlock,
    DelinquentItem,
    Dispute,
    EscalationBlock,
    EscalationSummary,
    Factor,
    HardshipCase,
    HardshipIndicator,
    Interaction,
    PriorityResult,
    ProfileBlock,
    PromiseToPay,
    RecordCheck,
    SuppressionEntry,
    TreatmentBlock,
)
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquentItemOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.rules_engine.consistency import RecordCheck as RulesRecordCheck
from collectai.rules_engine.priority import PriorityResult as RulesPriorityResult
from collectai.rules_engine.suppression import TreatmentBlock as RulesTreatmentBlock
from collectai.types.enums import (
    AccountType,
    CaseStatus,
    ContactOutcome,
    DisputeCategory,
    DisputeOutcome,
    DisputeStatus,
    EscalationPriority,
    EscalationReason,
    HardshipIndicatorType,
    HardshipStatus,
    InteractionChannel,
    InteractionDirection,
    ItemKind,
    ItemStatus,
    Persona,
    PtpSource,
    PtpStatus,
    ReviewQueue,
    VulnerabilityCategory,
)
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money

_INTERACTIONS_LIMIT = 20
_ESCALATION_CASES_LIMIT = 10
_ZERO_MONEY = Money("0.00")
_OPEN_DISPUTE_STATUSES = frozenset({DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW})
_OPEN_ESCALATION_BADGE_STATUSES = frozenset(
    {CaseStatus.OPEN, CaseStatus.IN_REVIEW, CaseStatus.AWAITING_INFORMATION}
)


def disputed_item_refs(disputes: list[DisputeOrm]) -> tuple[set[str], bool]:
    """Disputed item ids, and whether a dispute covers the whole overdue amount."""
    active = [row for row in disputes if row.status in _OPEN_DISPUTE_STATUSES]
    item_ids = {row.item_id for row in active if row.item_id is not None}
    whole_overdue_disputed = any(row.item_id is None for row in active)
    return item_ids, whole_overdue_disputed


def undisputed_overdue_amount(
    record: DelinquencyRecord,
    items: list[DelinquentItemOrm],
    disputed_item_ids: set[str],
    whole_overdue_disputed: bool,
) -> Money:
    if whole_overdue_disputed:
        return _ZERO_MONEY
    disputed_amount = sum(
        (item.amount_outstanding for item in items if item.item_id in disputed_item_ids),
        start=_ZERO_MONEY,
    )
    return record.overdue_amount - disputed_amount


def to_profile_block(customer: CustomerOrm) -> ProfileBlock:
    category = customer.vulnerability_category
    return ProfileBlock(
        customer_id=customer.customer_id,
        display_name=customer.display_name,
        email=customer.email,
        phone=customer.phone,
        vulnerability_flag=customer.vulnerability_flag,
        vulnerability_category=VulnerabilityCategory(category) if category else None,
    )


def to_account_block(
    account: AccountOrm, record: DelinquencyRecord, undisputed_amount: Money
) -> AccountBlock:
    return AccountBlock(
        account_id=account.account_id,
        account_type=AccountType(account.account_type),
        product_name=account.product_name,
        currency=account.currency,
        opened_on=account.opened_on,
        outstanding_balance=record.outstanding_balance,
        overdue_amount=record.overdue_amount,
        undisputed_overdue_amount=undisputed_amount,
        dpd=record.dpd,
        bucket=record.bucket,
        collection_status=record.collection_status,
        product_attributes=account.product_attributes,
    )


def to_items(items: list[DelinquentItemOrm], disputed_item_ids: set[str]) -> list[DelinquentItem]:
    ordered = sorted(items, key=lambda row: (row.due_date, row.item_id))
    return [
        DelinquentItem(
            item_id=row.item_id,
            kind=ItemKind(row.kind),
            label=row.label,
            amount_outstanding=row.amount_outstanding,
            due_date=row.due_date,
            status=ItemStatus(row.status),
            disputed=row.item_id in disputed_item_ids,
        )
        for row in ordered
    ]


def to_priority_schema(result: RulesPriorityResult) -> PriorityResult:
    return PriorityResult(
        score=result.score,
        band=result.band,
        factors=[
            Factor(
                factor_id=factor.factor_id,
                attribute=factor.attribute,
                value=factor.value,
                normalized_value=factor.normalized_value,
                weight=factor.weight,
                contribution=factor.contribution,
            )
            for factor in result.factors
        ],
        policy_version=result.policy_version,
    )


def to_treatment_schema(block: RulesTreatmentBlock) -> TreatmentBlock:
    return TreatmentBlock(
        human_treatment=block.human_treatment,
        automated_treatment_suppressed=block.automated_treatment_suppressed,
        suppressions=[
            SuppressionEntry(
                source_type=entry.source_type,
                source_id=entry.source_id,
                scope=entry.scope,
                item_id=entry.item_id,
            )
            for entry in block.suppressions
        ],
    )


def to_record_check_schema(check: RulesRecordCheck) -> RecordCheck:
    return RecordCheck(consistent=check.consistent, reason_code=check.reason_code)


def to_interactions(interactions: list[InteractionOrm]) -> list[Interaction]:
    latest = sorted(interactions, key=lambda row: row.occurred_at, reverse=True)
    return [
        Interaction(
            interaction_id=row.interaction_id,
            channel=InteractionChannel(row.channel),
            direction=InteractionDirection(row.direction),
            outcome=ContactOutcome(row.outcome) if row.outcome else None,
            occurred_at=row.occurred_at,
            summary=row.summary,
            counts_as_attempt=row.counts_as_attempt,
            conversation_id=row.conversation_id,
        )
        for row in latest[:_INTERACTIONS_LIMIT]
    ]


def to_ptp_history(ptps: list[PromiseToPayOrm]) -> list[PromiseToPay]:
    ordered = sorted(ptps, key=lambda row: row.created_at, reverse=True)
    return [
        PromiseToPay(
            ptp_id=row.ptp_id,
            account_id=row.account_id,
            promised_amount=row.promised_amount,
            promised_date=row.promised_date,
            status=PtpStatus(row.status),
            cumulative_paid=row.cumulative_paid,
            remaining_amount=Money(
                max(row.promised_amount.amount - row.cumulative_paid.amount, Decimal("0.00"))
            ),
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
        for row in ordered
    ]


def _to_hardship_indicators(raw_indicators: list[Any]) -> list[HardshipIndicator]:
    return [
        HardshipIndicator(
            indicator_type=HardshipIndicatorType(entry["indicator_type"]),
            customer_statement=entry["customer_statement"],
        )
        for entry in raw_indicators
    ]


def to_hardship_cases(hardship_cases: list[HardshipCaseOrm]) -> list[HardshipCase]:
    ordered = sorted(hardship_cases, key=lambda row: row.created_at, reverse=True)
    return [
        HardshipCase(
            hardship_case_id=row.hardship_case_id,
            account_id=row.account_id,
            customer_id=row.customer_id,
            conversation_id=row.conversation_id,
            status=HardshipStatus(row.status),
            indicators=_to_hardship_indicators(row.indicators),
            escalation_case_id=row.escalation_case_id,
            created_at=row.created_at,
            decided_at=row.decided_at,
        )
        for row in ordered
    ]


def to_disputes(disputes: list[DisputeOrm]) -> list[Dispute]:
    ordered = sorted(disputes, key=lambda row: row.created_at, reverse=True)
    return [
        Dispute(
            dispute_id=row.dispute_id,
            account_id=row.account_id,
            customer_id=row.customer_id,
            item_id=row.item_id,
            category=DisputeCategory(row.category),
            customer_reason=row.customer_reason,
            status=DisputeStatus(row.status),
            outcome=DisputeOutcome(row.outcome) if row.outcome else None,
            resolution_reason=row.resolution_reason,
            conversation_id=row.conversation_id,
            escalation_case_id=row.escalation_case_id,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
            version=row.version,
        )
        for row in ordered
    ]


def to_escalation_block(escalations: list[EscalationCaseOrm]) -> EscalationBlock:
    ordered = sorted(escalations, key=lambda row: row.created_at, reverse=True)
    open_exists = any(row.status in _OPEN_ESCALATION_BADGE_STATUSES for row in ordered)
    return EscalationBlock(
        badge="Escalated - human review" if open_exists else None,
        has_open_case=open_exists,
        cases=[
            EscalationSummary(
                case_id=row.case_id,
                reason=EscalationReason(row.reason),
                status=CaseStatus(row.status),
                priority=EscalationPriority(row.priority),
                queue=ReviewQueue(row.queue),
                created_at=row.created_at,
            )
            for row in ordered[:_ESCALATION_CASES_LIMIT]
        ],
    )
