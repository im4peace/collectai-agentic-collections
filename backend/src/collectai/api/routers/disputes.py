"""Officer dispute read, review and resolution (E8-S4; api-contracts.md
3.11): `GET /api/disputes/{dispute_id}`, `POST /api/disputes/{dispute_id}
/start-review`, `POST /api/disputes/{dispute_id}/resolve`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from collectai.api.deps import (
    AuditServiceDep,
    ClockDep,
    DbSession,
    PersonaContext,
    require_capability,
)
from collectai.api.middleware.errors import (
    AuditUnavailableError,
    ConflictError,
    NotFoundError,
    ObjectForbiddenError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.schemas.customer360 import Dispute
from collectai.api.schemas.disputes import (
    DisputeResolveRequest,
    DisputeStartReviewRequest,
    DisputeTransitionResult,
)
from collectai.audit.service import AuditUnavailable
from collectai.domain_services._dispute_review_exceptions import (
    DisputeConflictError,
    DisputeNotFoundError,
    DisputeNotPermittedError,
    DisputeValidationError,
)
from collectai.domain_services.dispute_review_service import resolve_dispute, start_review
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.types.enums import DisputeCategory, DisputeOutcome, DisputeStatus
from collectai.types.reason_codes import ReasonCode

router = APIRouter(prefix="/api/disputes", tags=["Disputes"])

_require_dispute_read = require_capability("dispute:read")
_require_dispute_resolve = require_capability("dispute:resolve")


def _dispute_view(row: DisputeOrm) -> Dispute:
    return Dispute(
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


def _require_idempotency_key(idempotency_key: str) -> None:
    if not idempotency_key:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REQUIRED,
            message="Idempotency-Key is required for this endpoint.",
        )


@router.get(
    "/{dispute_id}", response_model=Dispute, openapi_extra={"x-capability": "dispute:read"}
)
async def get_dispute_endpoint(
    dispute_id: str,
    db: DbSession,
    persona_context: Annotated[PersonaContext, Depends(_require_dispute_read)],
) -> Dispute:
    del persona_context
    dispute = await db.get(DisputeOrm, dispute_id)
    if dispute is None:
        raise NotFoundError(message=f"No dispute found for id {dispute_id!r}.")
    return _dispute_view(dispute)


@router.post(
    "/{dispute_id}/start-review",
    response_model=DisputeTransitionResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"x-capability": "dispute:resolve"},
)
async def start_review_endpoint(
    dispute_id: str,
    body: DisputeStartReviewRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    persona_context: Annotated[PersonaContext, Depends(_require_dispute_resolve)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> DisputeTransitionResult:
    """AC2, AC4: OPEN to UNDER_REVIEW."""
    _require_idempotency_key(idempotency_key)
    try:
        outcome = await start_review(
            db,
            dispute_id=dispute_id,
            expected_version=body.expected_version,
            reviewer_persona=persona_context.persona,
            idempotency_key=idempotency_key,
            clock=clock,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except DisputeNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except DisputeValidationError as exc:
        raise RequestValidationFailedError(
            reason_code=exc.reason_code, message=exc.message
        ) from exc
    except DisputeNotPermittedError as exc:
        raise ObjectForbiddenError(reason_code=exc.reason_code, message=exc.message) from exc
    except DisputeConflictError as exc:
        raise ConflictError(reason_code=exc.reason_code, message=exc.message) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc

    await db.commit()
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return DisputeTransitionResult(
        dispute=Dispute.model_validate(outcome.response_body), replayed=outcome.replayed
    )


@router.post(
    "/{dispute_id}/resolve",
    response_model=DisputeTransitionResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"x-capability": "dispute:resolve"},
)
async def resolve_dispute_endpoint(
    dispute_id: str,
    body: DisputeResolveRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    persona_context: Annotated[PersonaContext, Depends(_require_dispute_resolve)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> DisputeTransitionResult:
    """AC1, AC2, AC3, AC4: UNDER_REVIEW to RESOLVED with outcome and reason;
    item suppression lifts only once RESOLVED (derived, see
    `dispute_review_service`'s own module docstring)."""
    _require_idempotency_key(idempotency_key)
    try:
        outcome = await resolve_dispute(
            db,
            dispute_id=dispute_id,
            outcome=body.outcome,
            reason=body.reason,
            expected_version=body.expected_version,
            reviewer_persona=persona_context.persona,
            idempotency_key=idempotency_key,
            clock=clock,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except DisputeNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except DisputeValidationError as exc:
        raise RequestValidationFailedError(
            reason_code=exc.reason_code, message=exc.message
        ) from exc
    except DisputeNotPermittedError as exc:
        raise ObjectForbiddenError(reason_code=exc.reason_code, message=exc.message) from exc
    except DisputeConflictError as exc:
        raise ConflictError(reason_code=exc.reason_code, message=exc.message) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc

    await db.commit()
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return DisputeTransitionResult(
        dispute=Dispute.model_validate(outcome.response_body), replayed=outcome.replayed
    )
