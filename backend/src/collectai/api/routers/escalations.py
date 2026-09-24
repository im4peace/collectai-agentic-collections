"""Staff escalation list and reviewer decisions: `GET /api/escalations`
(E7-S1 AC7), `POST /api/escalations/{case_id}/decisions` (E7-S2). Case
detail and the summary endpoint belong to E7-S3/E7-S5 (not in Group H),
which extend this same router later, per this codebase's established "the
orchestrator wires every sibling router in once every group's stories land"
convention (see `api/routers/chat.py`'s own docstring for the precedent).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from collectai.api.deps import (
    AuditServiceDep,
    ClockDep,
    DbSession,
    PersonaContext,
    PolicyProviderDep,
    require_capability,
)
from collectai.api.middleware.errors import (
    AuditUnavailableError,
    ConflictError,
    NotFoundError,
    ObjectForbiddenError,
    QueueNotPermittedError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.routers.me_ownership import LimitQuery, OffsetQuery, paginate
from collectai.api.schemas.escalations import (
    EscalationListItem,
    EscalationPage,
    ReviewDecisionRequest,
    ReviewDecisionResult,
)
from collectai.audit.service import AuditUnavailable
from collectai.domain_services._escalation_queue_query import list_for_queue_view
from collectai.domain_services._review_exceptions import (
    ReviewCaseNotFoundError,
    ReviewConflictError,
    ReviewNotPermittedError,
    ReviewValidationError,
)
from collectai.domain_services.review_service import ReviewDecisionRequest as DecisionRequest
from collectai.domain_services.review_service import decide
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
from collectai.types.reason_codes import ReasonCode
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


_ESCALATION_REVIEW = {"x-capability": "escalation:review"}
_require_escalation_review = require_capability("escalation:review")


def _require_idempotency_key(idempotency_key: str) -> None:
    if not idempotency_key:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REQUIRED,
            message="Idempotency-Key is required for this endpoint.",
        )


@router.post(
    "/{case_id}/decisions",
    response_model=ReviewDecisionResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_ESCALATION_REVIEW,
)
async def decide_case_endpoint(
    case_id: str,
    body: ReviewDecisionRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_escalation_review)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> ReviewDecisionResult:
    """AC1-AC8: reviewer decisions (APPROVE/REJECT/MODIFY/
    REQUEST_MORE_INFORMATION/ESCALATE). `require_capability("escalation:
    review")` already restricts this to `COLLECTIONS_OFFICER` (AC5's
    persona-level half); `domain_services.review_service.decide` adds the
    object-level half (a case whose own `reviewer_role` is not
    `COLLECTIONS_OFFICER` is still rejected)."""
    _require_idempotency_key(idempotency_key)
    try:
        outcome = await decide(
            db,
            request=DecisionRequest(
                case_id=case_id,
                action=body.action,
                expected_version=body.expected_version,
                reason=body.reason,
                note=body.note,
                modification_option_id=body.modification_option_id,
                escalate_reason=body.escalate_reason,
            ),
            reviewer_persona=persona_context.persona,
            idempotency_key=idempotency_key,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except ReviewCaseNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except ReviewValidationError as exc:
        raise RequestValidationFailedError(
            reason_code=exc.reason_code, message=exc.message
        ) from exc
    except ReviewNotPermittedError as exc:
        raise ObjectForbiddenError(reason_code=exc.reason_code, message=exc.message) from exc
    except ReviewConflictError as exc:
        raise ConflictError(reason_code=exc.reason_code, message=exc.message) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc
    await db.commit()
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return ReviewDecisionResult.model_validate(
        {**outcome.response_body, "replayed": outcome.replayed}
    )
