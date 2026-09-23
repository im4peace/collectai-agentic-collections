"""Customer 360 read-model assembly (E4-S1; api-contracts.md 3.4).

Fetches through existing repositories (`AccountRepository.get_by_id` (new,
unscoped), `CustomerRepository.get_by_id`, `DelinquencyRecordRepository
.get_by_account`, every customer-scoped repository's inherited
`list_by_account_for_customer`) and existing rules-engine services
(`priority.compute_priority`, `suppression.evaluate_suppression`,
`consistency.check_consistency`, `freshness.check_freshness`). Read-only:
never writes, never calls AI. `ai` is always NOT_GENERATED (E4-S3 does not
exist yet); `payment_events`/`arrangements` stay at their schema-level
empty default (E6-S3/E8-S1, also out of scope).

Pure ORM-to-wire mapping lives in `customer360_mapping.py` (split out past
the 300-line block threshold, mirroring `error_types.py`/`errors.py`).
`_TreatmentFacts` is derived once from the same rows the response body
renders, so the deterministic flags and displayed history never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.middleware.errors import NotFoundError
from collectai.api.schemas.customer360 import (
    AiBlock,
    Customer360,
    DeterministicBlock,
    SnapshotInfo,
    TreatmentBlock,
)
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import customer360_mapping as mapping
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.base import CustomerScopedRepository, OrmT
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.delinquent_item_repository import DelinquentItemRepository
from collectai.persistence.repositories.dispute_repository import DisputeRepository
from collectai.persistence.repositories.escalation_case_repository import EscalationCaseRepository
from collectai.persistence.repositories.hardship_case_repository import HardshipCaseRepository
from collectai.persistence.repositories.interaction_repository import InteractionRepository
from collectai.persistence.repositories.promise_to_pay_repository import PromiseToPayRepository
from collectai.rules_engine.consistency import check_consistency
from collectai.rules_engine.freshness import check_freshness
from collectai.rules_engine.priority import PriorityInput, compute_priority
from collectai.rules_engine.suppression import SuppressionInput, evaluate_suppression
from collectai.types.clock import Clock
from collectai.types.enums import (
    Bucket,
    CaseStatus,
    CollectionStatus,
    ContactOutcome,
    DisputeStatus,
    Freshness,
    HardshipStatus,
    PtpStatus,
    RecommendationStatus,
)
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable

_OPEN_HARDSHIP_STATUSES = frozenset({HardshipStatus.OPEN, HardshipStatus.UNDER_REVIEW})
_OPEN_DISPUTE_STATUSES = frozenset({DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW})

_account_repository = AccountRepository()
_customer_repository = CustomerRepository()
_delinquency_repository = DelinquencyRecordRepository()
_item_repository = DelinquentItemRepository()
_interaction_repository = InteractionRepository()
_ptp_repository = PromiseToPayRepository()
_hardship_repository = HardshipCaseRepository()
_dispute_repository = DisputeRepository()
_escalation_repository = EscalationCaseRepository()


@dataclass(frozen=True, slots=True)
class _TreatmentFacts:
    """Already-fetched facts `PriorityInput`/`SuppressionInput` both need."""

    broken_ptp_count: int
    recent_contact_outcome: str | None
    active_hardship_case_id: str | None
    active_escalation_case_id: str | None
    open_dispute_refs: list[tuple[str, str | None]]


async def _list_for_account(
    repository: CustomerScopedRepository[OrmT], session: AsyncSession, account_id: str, cid: str
) -> list[OrmT]:
    return list(await repository.list_by_account_for_customer(session, account_id, cid))


async def build_customer360(
    session: AsyncSession, *, account_id: str, policy_provider: PolicyProvider, clock: Clock
) -> Customer360:
    """Assemble the Customer 360 read model (AC1, AC2, AC5); raises
    `NotFoundError` for an unknown `account_id` (AC3). A degraded/inactive
    policy never raises here -- see `_build_deterministic_block`."""
    account = await _fetch_account(session, account_id)
    customer = await _fetch_customer(session, account.customer_id)
    record_orm = await _fetch_delinquency_record(session, account_id, customer.customer_id)
    record = _to_domain_record(record_orm)

    cid = customer.customer_id
    items = await _list_for_account(_item_repository, session, account_id, cid)
    interactions = await _list_for_account(_interaction_repository, session, account_id, cid)
    ptps = await _list_for_account(_ptp_repository, session, account_id, cid)
    hardship_cases = await _list_for_account(_hardship_repository, session, account_id, cid)
    disputes = await _list_for_account(_dispute_repository, session, account_id, cid)
    escalations = await _list_for_account(_escalation_repository, session, account_id, cid)

    facts = _derive_treatment_facts(ptps, interactions, hardship_cases, disputes, escalations)
    disputed_item_ids, whole_overdue_disputed = mapping.disputed_item_refs(disputes)
    undisputed_amount = mapping.undisputed_overdue_amount(
        record, items, disputed_item_ids, whole_overdue_disputed
    )

    return Customer360(
        account_id=account_id,
        generated_at=clock.now(),
        snapshot=_build_snapshot_info(record, policy_provider, clock),
        profile=mapping.to_profile_block(customer),
        account=mapping.to_account_block(account, record, undisputed_amount),
        items=mapping.to_items(items, disputed_item_ids),
        deterministic=_build_deterministic_block(record, customer, facts, policy_provider),
        ai=AiBlock(status=RecommendationStatus.NOT_GENERATED, recommendation=None),
        interactions=mapping.to_interactions(interactions),
        ptp_history=mapping.to_ptp_history(ptps),
        hardship_cases=mapping.to_hardship_cases(hardship_cases),
        disputes=mapping.to_disputes(disputes),
        escalation=mapping.to_escalation_block(escalations),
    )


async def _fetch_account(session: AsyncSession, account_id: str) -> AccountOrm:
    account = await _account_repository.get_by_id(session, account_id)
    if account is None:
        raise NotFoundError(message=f"Account {account_id!r} was not found.")
    return account


async def _fetch_customer(session: AsyncSession, customer_id: str) -> CustomerOrm:
    customer = await _customer_repository.get_by_id(session, customer_id)
    if customer is None:
        # Unreachable via the account.customer_id FK (migration 0001); kept as defence in depth.
        raise NotFoundError(message=f"Customer {customer_id!r} was not found.")
    return customer


async def _fetch_delinquency_record(
    session: AsyncSession, account_id: str, customer_id: str
) -> DelinquencyRecordOrm:
    record = await _delinquency_repository.get_by_account(session, account_id, customer_id)
    if record is None:
        raise NotFoundError(message=f"No delinquency record found for account {account_id!r}.")
    return record


def _to_domain_record(orm_record: DelinquencyRecordOrm) -> DelinquencyRecord:
    return DelinquencyRecord(
        account_id=orm_record.account_id,
        customer_id=orm_record.customer_id,
        outstanding_balance=orm_record.outstanding_balance,
        overdue_amount=orm_record.overdue_amount,
        dpd=orm_record.dpd,
        bucket=Bucket(orm_record.bucket),
        collection_status=CollectionStatus(orm_record.collection_status),
        as_of=orm_record.as_of,
        record_version=orm_record.record_version,
        updated_at=orm_record.updated_at,
    )


def _derive_treatment_facts(
    ptps: list[PromiseToPayOrm],
    interactions: list[InteractionOrm],
    hardship_cases: list[HardshipCaseOrm],
    disputes: list[DisputeOrm],
    escalations: list[EscalationCaseOrm],
) -> _TreatmentFacts:
    broken_ptp_count = sum(1 for row in ptps if row.status == PtpStatus.BROKEN)
    latest_interaction = max(interactions, key=lambda row: row.occurred_at, default=None)
    open_hardship = [row for row in hardship_cases if row.status in _OPEN_HARDSHIP_STATUSES]
    active_hardship = max(open_hardship, key=lambda row: row.created_at, default=None)
    open_escalations = [row for row in escalations if row.status != CaseStatus.DECIDED]
    active_escalation = max(open_escalations, key=lambda row: row.created_at, default=None)
    open_dispute_refs = [
        (row.dispute_id, row.item_id) for row in disputes if row.status in _OPEN_DISPUTE_STATUSES
    ]
    return _TreatmentFacts(
        broken_ptp_count=broken_ptp_count,
        recent_contact_outcome=latest_interaction.outcome if latest_interaction else None,
        active_hardship_case_id=active_hardship.hardship_case_id if active_hardship else None,
        active_escalation_case_id=active_escalation.case_id if active_escalation else None,
        open_dispute_refs=open_dispute_refs,
    )


def _build_deterministic_block(
    record: DelinquencyRecord,
    customer: CustomerOrm,
    facts: _TreatmentFacts,
    policy_provider: PolicyProvider,
) -> DeterministicBlock:
    record_check = mapping.to_record_check_schema(check_consistency(record))
    priority_result = compute_priority(_to_priority_input(record, facts), policy_provider)
    if not priority_result.ok or priority_result.value is None:
        # AC2: a degraded/inactive policy still returns 200, degraded here.
        return DeterministicBlock(
            policy_version=None,
            status="POLICY_UNAVAILABLE",
            priority=None,
            treatment=TreatmentBlock(
                human_treatment=False, automated_treatment_suppressed=False, suppressions=[]
            ),
            contact_policy=None,
            payable_options=[],
            record_check=record_check,
        )

    policy = policy_provider.get_active()
    treatment = evaluate_suppression(_to_suppression_input(customer, facts), policy)
    return DeterministicBlock(
        policy_version=policy.policy_version,
        status="OK",
        priority=mapping.to_priority_schema(priority_result.value),
        treatment=mapping.to_treatment_schema(treatment),
        contact_policy=None,
        payable_options=[],
        record_check=record_check,
    )


def _to_priority_input(record: DelinquencyRecord, facts: _TreatmentFacts) -> PriorityInput:
    raw_outcome = facts.recent_contact_outcome
    outcome = ContactOutcome(raw_outcome) if raw_outcome else None
    return PriorityInput(
        dpd=record.dpd,
        overdue_amount=record.overdue_amount,
        broken_ptp_count=facts.broken_ptp_count,
        recent_contact_outcome=outcome,
        has_active_dispute=bool(facts.open_dispute_refs),
        has_active_hardship=facts.active_hardship_case_id is not None,
        has_open_escalation=facts.active_escalation_case_id is not None,
    )


def _to_suppression_input(customer: CustomerOrm, facts: _TreatmentFacts) -> SuppressionInput:
    return SuppressionInput(
        has_open_escalation=facts.active_escalation_case_id is not None,
        escalation_case_id=facts.active_escalation_case_id,
        has_active_hardship=facts.active_hardship_case_id is not None,
        hardship_case_id=facts.active_hardship_case_id,
        is_vulnerable_customer=customer.vulnerability_flag,
        customer_id=customer.customer_id,
        open_disputes=facts.open_dispute_refs,
    )


def _build_snapshot_info(
    record: DelinquencyRecord, policy_provider: PolicyProvider, clock: Clock
) -> SnapshotInfo:
    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable:
        # No active policy: max_snapshot_age_minutes is unknown -> UNKNOWN.
        return SnapshotInfo(
            as_of=record.as_of,
            record_version=record.record_version,
            freshness=Freshness.UNKNOWN,
            freshness_reason_code=ReasonCode.POLICY_UNAVAILABLE.value,
            max_age_minutes=0,
        )

    result = check_freshness(
        snapshot_as_of=record.as_of,
        snapshot_version=record.record_version,
        current_record=record,
        policy=policy,
        clock=clock,
    )
    return SnapshotInfo(
        as_of=record.as_of,
        record_version=record.record_version,
        freshness=result.status,
        freshness_reason_code=result.reason_code.value if result.reason_code else None,
        max_age_minutes=policy.parameters.freshness.max_snapshot_age_minutes,
    )
