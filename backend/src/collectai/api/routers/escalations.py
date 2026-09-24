"""Staff escalation list (E7-S1 AC7): `GET /api/escalations`. The minimal
Slice-1 read this story owns -- case detail, reviewer actions, and the
summary endpoint all belong to E7-S2/E7-S3/E7-S5 (Group H), which extend
this same router later, per this codebase's established "the orchestrator
wires every sibling router in once every group's stories land" convention
(see `api/routers/chat.py`'s own docstring for the precedent).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from collectai.api.deps import (
    ClockDep,
    DbSession,
    PersonaContext,
    PolicyProviderDep,
    require_capability,
)
from collectai.api.middleware.error_types import QueueNotPermittedError
from collectai.api.routers.me_ownership import LimitQuery, OffsetQuery, paginate
from collectai.api.schemas.escalations import EscalationListItem, EscalationPage
from collectai.domain_services._escalation_queue_query import list_for_queue_view
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.types.enums import (
    CaseSource,
    CaseStatus,
    EscalationPriority,
    EscalationReason,
    Persona,
    ReviewerRole,
    ReviewQueue,
)
from collectai.types.results import PolicyUnavailable

router = APIRouter(prefix="/api/escalations", tags=["Escalations"])

_ESCALATION_READ = {"x-capability": "escalation:read"}
_require_escalation_read = require_capability("escalation:read")
_customer_repo = CustomerRepository()

_DEFAULT_STATUSES: tuple[CaseStatus, ...] = (
    CaseStatus.OPEN,
    CaseStatus.IN_REVIEW,
    CaseStatus.AWAITING_INFORMATION,
)
_PRIORITY_ORDER: dict[EscalationPriority, int] = {
    EscalationPriority.URGENT: 0,
    EscalationPriority.ELEVATED: 1,
    EscalationPriority.NORMAL: 2,
}


@router.get("", response_model=EscalationPage, openapi_extra=_ESCALATION_READ)
async def list_escalations(
    request: Request,
    db: DbSession,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_escalation_read)],
    queue: Annotated[list[ReviewQueue] | None, Query()] = None,
    status: Annotated[list[CaseStatus] | None, Query()] = None,
    priority: Annotated[list[EscalationPriority] | None, Query()] = None,
    reason: Annotated[list[EscalationReason] | None, Query()] = None,
    account_id: str | None = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> EscalationPage:
    del request
    effective_queues = _effective_queues(persona_context.persona, queue)
    rows = await list_for_queue_view(
        db,
        queues=effective_queues,
        statuses=status or list(_DEFAULT_STATUSES),
        priorities=priority,
        reasons=reason,
        account_id=account_id,
    )
    rows = sorted(
        rows,
        key=lambda row: (_PRIORITY_ORDER[EscalationPriority(row.priority)], row.created_at),
    )
    page_rows, page_info = paginate(rows, limit, offset)

    policy_version: str | None
    aging_warning_hours: dict[EscalationPriority, int] = {}
    try:
        policy = policy_provider.get_active()
        policy_version = policy.policy_version
        aging_warning_hours = dict(policy.parameters.routing.aging_warning_hours)
    except PolicyUnavailable:
        policy_version = None

    now = clock.now()
    items: list[EscalationListItem] = []
    for row in page_rows:
        customer = await _customer_repo.get_by_id(db, row.customer_id)
        age_hours = int((now - row.created_at).total_seconds() // 3600)
        threshold = aging_warning_hours.get(EscalationPriority(row.priority))
        items.append(
            EscalationListItem(
                case_id=row.case_id,
                reason=EscalationReason(row.reason),
                queue=ReviewQueue(row.queue),
                reviewer_role=ReviewerRole(row.reviewer_role),
                priority=EscalationPriority(row.priority),
                status=CaseStatus(row.status),
                source=CaseSource(row.source),
                created_at=row.created_at,
                age_hours=age_hours,
                aging_warning=threshold is not None and age_hours >= threshold,
                customer_id=row.customer_id,
                customer_name=customer.display_name if customer is not None else "Unknown",
                account_id=row.account_id,
                customer_360_path=f"/customers/{row.account_id}",
                version=row.version,
            )
        )
    return EscalationPage(items=items, page=page_info, policy_version=policy_version)


def _effective_queues(
    persona: Persona, requested: list[ReviewQueue] | None
) -> list[ReviewQueue] | None:
    """AC7/api-contracts.md 3.9: COMPLIANCE_RISK is automatically scoped to
    COMPLIANCE_REVIEW; requesting any other queue is a 403
    `QUEUE_NOT_PERMITTED`. COLLECTIONS_OFFICER sees every queue (or the
    caller's own filter, unrestricted)."""
    if persona is not Persona.COMPLIANCE_RISK:
        return requested
    if requested and any(q is not ReviewQueue.COMPLIANCE_REVIEW for q in requested):
        raise QueueNotPermittedError()
    return [ReviewQueue.COMPLIANCE_REVIEW]
