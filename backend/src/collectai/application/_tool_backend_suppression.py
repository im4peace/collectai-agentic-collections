"""Builds `rules_engine.suppression.SuppressionInput` from real persistence
reads (E5-S4's `get_eligible_options`, AC5). Split out of `tool_backend.py`
to keep that module under the code-gen skill's 300-line block threshold; the
only caller is `ToolBackend.get_eligible_options`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.persistence.repositories.dispute_repository import DisputeRepository
from collectai.persistence.repositories.escalation_case_repository import EscalationCaseRepository
from collectai.persistence.repositories.hardship_case_repository import HardshipCaseRepository
from collectai.rules_engine.suppression import SuppressionInput
from collectai.types.enums import CaseStatus, DisputeStatus, HardshipStatus

_OPEN_CASE_STATUSES = frozenset(
    {CaseStatus.OPEN, CaseStatus.IN_REVIEW, CaseStatus.AWAITING_INFORMATION}
)


async def build_suppression_input(
    session: AsyncSession, account_id: str, customer_id: str
) -> SuppressionInput:
    """Real reads, not mocks: every open escalation, active hardship case,
    unresolved dispute and the customer's vulnerability flag, exactly as
    `rules_engine.suppression.evaluate_suppression` (data-models.md section
    4.4) expects them."""
    escalations = await EscalationCaseRepository().list_by_account_for_customer(
        session, account_id, customer_id
    )
    open_escalation = next(
        (case for case in escalations if CaseStatus(case.status) in _OPEN_CASE_STATUSES), None
    )

    hardship_cases = await HardshipCaseRepository().list_by_account_for_customer(
        session, account_id, customer_id
    )
    active_hardship = next(
        (
            case
            for case in hardship_cases
            if HardshipStatus(case.status) is not HardshipStatus.DECIDED
        ),
        None,
    )

    customer = await CustomerRepository().get_by_id(session, customer_id)
    is_vulnerable = customer is not None and customer.vulnerability_flag

    disputes = await DisputeRepository().list_by_account_for_customer(
        session, account_id, customer_id
    )
    open_disputes = [
        (dispute.dispute_id, dispute.item_id)
        for dispute in disputes
        if DisputeStatus(dispute.status) is not DisputeStatus.RESOLVED
    ]

    return SuppressionInput(
        has_open_escalation=open_escalation is not None,
        escalation_case_id=open_escalation.case_id if open_escalation is not None else None,
        has_active_hardship=active_hardship is not None,
        hardship_case_id=(
            active_hardship.hardship_case_id if active_hardship is not None else None
        ),
        is_vulnerable_customer=is_vulnerable,
        customer_id=customer_id,
        open_disputes=open_disputes,
    )
