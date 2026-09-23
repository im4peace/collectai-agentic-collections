"""Promise-to-Pay endpoints this story owns (api-contracts.md 3.6):
`POST /api/ptps/validate`, `POST /api/ptps`, `GET /api/ptps/{ptp_id}`.
`POST /api/ptps/{ptp_id}/cancel` belongs to a later story (E6-S4/E6-S2/E8-S1)
and is not defined here.

This router is the HTTP-shaped translation layer only: it reads headers,
calls `domain_services.ptp_service`, and maps each domain exception (plus
`types.results.PolicyUnavailable` and `audit.service.AuditUnavailable`) to
the matching `api.middleware.errors` exception. All amount/date/conflict/
freshness/idempotency logic lives in the service, not here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response, status

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
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
    PolicyUnavailableError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.schemas.ptps import (
    PromiseToPayResponse,
    PtpCreateRequest,
    PtpValidateRequest,
    PtpValidationResult,
)
from collectai.audit.service import AuditUnavailable
from collectai.domain_services.ptp_service import (
    PtpAccountNotFoundError,
    PtpBusinessRuleViolation,
    PtpConflictError,
    PtpRecordRequest,
    dry_run_validate_ptp,
    get_ptp_by_id,
    ptp_wire_dict,
    record_officer_ptp,
)
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable

router = APIRouter(prefix="/api/ptps", tags=["Promise to Pay"])

_require_ptp_record = require_capability("ptp:record")
_require_ptp_read = require_capability("ptp:read")

_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


@router.post(
    "/validate",
    response_model=PtpValidationResult,
    openapi_extra={"x-capability": "ptp:record"},
)
async def validate_ptp_endpoint(
    body: PtpValidateRequest,
    db: DbSession,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    persona_context: PersonaContext = Depends(_require_ptp_record),  # noqa: B008
) -> PtpValidationResult:
    """Dry-run only: never mutates state, never needs `Idempotency-Key`."""
    del persona_context
    try:
        result = await dry_run_validate_ptp(
            db,
            account_id=body.account_id,
            promised_amount=body.promised_amount,
            promised_date=body.promised_date,
            policy_provider=policy_provider,
            clock=clock,
        )
    except PtpAccountNotFoundError as exc:
        raise NotFoundError(message=f"Unknown account {exc.account_id!r}.") from exc
    except PolicyUnavailable as exc:
        raise PolicyUnavailableError() from exc
    return PtpValidationResult(
        valid=result.valid,
        reason_codes=result.reason_codes,
        alternatives=result.alternatives,
        policy_version=result.policy_version,
    )


@router.post(
    "",
    response_model=PromiseToPayResponse,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"x-capability": "ptp:record"},
)
async def create_ptp_endpoint(
    body: PtpCreateRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    audit_service: AuditServiceDep,
    persona_context: PersonaContext = Depends(_require_ptp_record),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias=_IDEMPOTENCY_KEY_HEADER),
) -> PromiseToPayResponse:
    validated_key = _require_idempotency_key(idempotency_key)
    domain_request = PtpRecordRequest(
        account_id=body.account_id,
        promised_amount=body.promised_amount,
        promised_date=body.promised_date,
        interaction_reference=body.interaction_reference,
        item_id=body.item_id,
        record_version=body.record_version,
        snapshot_as_of=body.snapshot_as_of,
    )
    try:
        outcome = await record_officer_ptp(
            db,
            request=domain_request,
            idempotency_key=validated_key,
            persona=persona_context.persona,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except PtpAccountNotFoundError as exc:
        raise NotFoundError(message=f"Unknown account {exc.account_id!r}.") from exc
    except PolicyUnavailable as exc:
        raise PolicyUnavailableError() from exc
    except PtpBusinessRuleViolation as exc:
        raise BusinessRuleViolationError(
            reason_code=exc.reason_code, message=exc.message, alternatives=exc.alternatives
        ) from exc
    except PtpConflictError as exc:
        raise ConflictError(
            reason_code=exc.reason_code, message=exc.message, context=exc.context
        ) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc

    await db.commit()
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return PromiseToPayResponse.model_validate(outcome.response_body)


@router.get(
    "/{ptp_id}",
    response_model=PromiseToPayResponse,
    openapi_extra={"x-capability": "ptp:read"},
)
async def get_ptp_endpoint(
    ptp_id: str,
    db: DbSession,
    persona_context: PersonaContext = Depends(_require_ptp_read),  # noqa: B008
) -> PromiseToPayResponse:
    del persona_context
    row = await get_ptp_by_id(db, ptp_id)
    if row is None:
        raise NotFoundError(message=f"Unknown PTP {ptp_id!r}.")
    return PromiseToPayResponse.model_validate(ptp_wire_dict(row))


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REQUIRED,
            message=f"{_IDEMPOTENCY_KEY_HEADER!r} header is required (8-128 chars [A-Za-z0-9_-]).",
        )
    return idempotency_key
