"""Staff escalation list and reviewer decisions: `GET /api/escalations`
(E7-S1 AC7), `POST /api/escalations/{case_id}/decisions` (E7-S2). Case
detail and the summary endpoint belong to E7-S3/E7-S5 (not in Group H),
which extend this same router later, per this codebase's established "the
orchestrator wires every sibling router in once every group's stories land"
convention (see `api/routers/chat.py`'s own docstring for the precedent).
"""

from __future__ import annotations

from datetime import datetime
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
from collectai.api.routers._chat_views import message_view
from collectai.api.routers.me_ownership import LimitQuery, OffsetQuery, paginate
from collectai.api.schemas.escalations import (
    ComplianceDecisionRequest,
    ComplianceDecisionResult,
    EscalationCaseDetail,
    EscalationListItem,
    EscalationPage,
    EscalationRuleResults,
    ReviewDecisionRequest,
    ReviewDecisionResult,
)
from collectai.application._chat_persistence import persist_message
from collectai.audit.service import AuditUnavailable
from collectai.domain_services._escalation_queue_query import list_for_queue_view
from collectai.domain_services._review_exceptions import (
    ReviewCaseNotFoundError,
    ReviewConflictError,
    ReviewNotPermittedError,
    ReviewValidationError,
)
from collectai.domain_services.compliance_service import (
    ComplianceDecisionRequest as ComplianceRequest,
)
from collectai.domain_services.compliance_service import record_compliance_review_decision
from collectai.domain_services.customer360_mapping import to_disputes
from collectai.domain_services.escalation_detail_service import get_case_detail
from collectai.domain_services.recommendation_mapping import to_recommendation_schema
from collectai.domain_services.review_service import ReviewDecisionRequest as DecisionRequest
from collectai.domain_services.review_service import decide
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.types.clock import Clock
from collectai.types.enums import (
    CaseSource,
    CaseStatus,
    ContentSource,
    EscalationPriority,
    EscalationReason,
    MessageRole,
    Persona,
    ReviewAction,
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

    policy_version, aging_warning_hours = await _resolve_policy_context(policy_provider)

    now = clock.now()
    items: list[EscalationListItem] = [
        await _list_item(db, row, now=now, aging_warning_hours=aging_warning_hours)
        for row in page_rows
    ]
    return EscalationPage(items=items, page=page_info, policy_version=policy_version)


async def _resolve_policy_context(
    policy_provider: PolicyProviderDep,
) -> tuple[str | None, dict[EscalationPriority, int]]:
    try:
        policy = policy_provider.get_active()
        return policy.policy_version, dict(policy.parameters.routing.aging_warning_hours)
    except PolicyUnavailable:
        return None, {}


async def _list_item(
    db: DbSession,
    row: EscalationCaseOrm,
    *,
    now: datetime,
    aging_warning_hours: dict[EscalationPriority, int],
) -> EscalationListItem:
    """Shared by `list_escalations` (AC1) and `get_case_detail_endpoint`
    (E7-S3 AC2), which embeds the same summary fields alongside its detail
    sections -- one place computes age/aging-warning/customer-name so the
    list and the detail view can never disagree about them."""
    customer = await _customer_repo.get_by_id(db, row.customer_id)
    age_hours = int((now - row.created_at).total_seconds() // 3600)
    threshold = aging_warning_hours.get(EscalationPriority(row.priority))
    return EscalationListItem(
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


@router.get(
    "/{case_id}", response_model=EscalationCaseDetail, openapi_extra=_ESCALATION_READ
)
async def get_case_detail_endpoint(
    case_id: str,
    db: DbSession,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_escalation_read)],
) -> EscalationCaseDetail:
    """E7-S3 AC2, AC3: case detail with the conversation, AI recommendation
    and deterministic rule results in three separately labelled sections,
    plus whether APPROVE is currently permitted. Object-level scoping
    matches the list endpoint (AC6): COMPLIANCE_RISK may only open a
    COMPLIANCE_REVIEW-queue case."""
    try:
        detail = await get_case_detail(
            db,
            case_id=case_id,
            viewer_persona=persona_context.persona,
            policy_provider=policy_provider,
        )
    except ReviewCaseNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except ReviewNotPermittedError as exc:
        raise ObjectForbiddenError(reason_code=exc.reason_code, message=exc.message) from exc

    _, aging_warning_hours = await _resolve_policy_context(policy_provider)
    summary = await _list_item(
        db, detail.case, now=clock.now(), aging_warning_hours=aging_warning_hours
    )
    return EscalationCaseDetail(
        **summary.model_dump(),
        conversation=[message_view(message) for message in detail.conversation],
        ai_recommendation=(
            to_recommendation_schema(detail.recommendation)
            if detail.recommendation is not None
            else None
        ),
        rule_results=EscalationRuleResults(
            summary=detail.case.summary,
            requested_terms=detail.case.requested_terms,
            exception_types=detail.case.exception_types,
            routing_flags=list(detail.case.routing_flags),
            routing_policy_version=detail.case.routing_policy_version,
        ),
        approve_permitted=detail.approve_permitted,
        dispute=to_disputes([detail.dispute])[0] if detail.dispute is not None else None,
    )


async def _inform_customer_of_rejected_exception(
    db: DbSession, *, case_id: str, clock: Clock
) -> None:
    """E7-S4 AC5: "a rejected exception ... informs the customer." Only
    applies to an EXCEPTIONAL_ARRANGEMENT case with a real conversation to
    post into -- a reviewer-raised case (no `conversation_id`) or any other
    case reason has no customer-facing message to send here. A fixed
    template (`content_source=TEMPLATE`), matching every other
    customer-facing string in this codebase -- never free-form reviewer
    text reaching the customer verbatim."""
    case = await db.get(EscalationCaseOrm, case_id)
    if (
        case is None
        or case.reason != EscalationReason.EXCEPTIONAL_ARRANGEMENT.value
        or case.conversation_id is None
    ):
        return
    await persist_message(
        db,
        conversation_id=case.conversation_id,
        customer_id=case.customer_id,
        role=MessageRole.ASSISTANT,
        content=(
            "A specialist has reviewed your payment plan request and was not able to "
            "approve it as requested. You can talk to a human at any time to discuss "
            "other options."
        ),
        content_source=ContentSource.TEMPLATE,
        labels=[],
        created_at=clock.now(),
    )


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

    if not outcome.replayed and body.action is ReviewAction.REJECT:
        await _inform_customer_of_rejected_exception(db, case_id=case_id, clock=clock)

    await db.commit()
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return ReviewDecisionResult.model_validate(
        {**outcome.response_body, "replayed": outcome.replayed}
    )


_COMPLIANCE_DECIDE = {"x-capability": "compliance:decide"}
_require_compliance_decide = require_capability("compliance:decide")


@router.post(
    "/{case_id}/compliance-decision",
    response_model=ComplianceDecisionResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_COMPLIANCE_DECIDE,
)
async def compliance_decision_endpoint(
    case_id: str,
    body: ComplianceDecisionRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_compliance_decide)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> ComplianceDecisionResult:
    """E7-S5 AC1-AC6: `require_capability("compliance:decide")` already
    restricts this to `COMPLIANCE_RISK` (AC6's persona-level half);
    `domain_services.compliance_service` adds the object-level half (only a
    case in COMPLIANCE_REVIEW, AC3) and is the only mutating endpoint
    COMPLIANCE_RISK may call -- it never touches a financial table (AC4)."""
    _require_idempotency_key(idempotency_key)
    try:
        outcome = await record_compliance_review_decision(
            db,
            request=ComplianceRequest(
                case_id=case_id,
                outcome=body.outcome,
                reason=body.reason,
                expected_version=body.expected_version,
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
    return ComplianceDecisionResult.model_validate(
        {**outcome.response_body, "replayed": outcome.replayed}
    )
