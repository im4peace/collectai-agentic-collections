"""Dev and demo controls (E9-S3; api-contracts.md 3.14): `GET /api/demo-
controls/state`, `POST /api/demo-controls/clock/advance`, `POST /api/demo-
controls/ptp-lifecycle/run`, `POST /api/demo-controls/payments/simulate`,
`POST /api/demo-controls/reseed`.

AC1: every route under this router answers 404 `NOT_FOUND` when
`DEMO_CONTROLS_ENABLED=false`, *before* any persona/capability check -- the
flag-check dependency is a router-level dependency
(`APIRouter(dependencies=[...])`), which FastAPI always resolves before a
route's own per-endpoint dependencies, so this ordering is structural, not
a convention a future endpoint could accidentally get wrong.
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
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.routers.chat import SettingsDep
from collectai.api.schemas.demo_controls import (
    ClockAdvanceRequest,
    ClockAdvanceResult,
    DemoState,
    LifecycleRunResult,
    ReseedRequest,
    ReseedResult,
    SimulatePaymentRequest,
    SimulatePaymentResult,
)
from collectai.audit.service import AuditUnavailable
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import demo_service
from collectai.domain_services._demo_exceptions import DemoAccountNotFoundError, DemoValidationError
from collectai.types.reason_codes import ReasonCode

_require_demo_controls_use = require_capability("demo_controls:use")


def _get_policy_provider(request: Request) -> PolicyProvider:
    provider = getattr(request.app.state, "policy_provider", None)
    return provider if isinstance(provider, PolicyProvider) else PolicyProvider()


PolicyProviderDep = Annotated[PolicyProvider, Depends(_get_policy_provider)]


async def _require_demo_controls_enabled(settings: SettingsDep) -> None:
    """AC1: `settings.demo_controls_enabled=false` -> 404 for every route
    under this router, before any persona/capability dependency runs."""
    if not settings.demo_controls_enabled:
        raise NotFoundError(message="Demo controls are not enabled.")


router = APIRouter(
    prefix="/api/demo-controls",
    tags=["Demo Controls"],
    dependencies=[Depends(_require_demo_controls_enabled)],
)


def _require_idempotency_key(idempotency_key: str) -> None:
    if not idempotency_key:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REQUIRED,
            message="Idempotency-Key is required for this endpoint.",
        )


@router.get(
    "/state", response_model=DemoState, openapi_extra={"x-capability": "demo_controls:use"}
)
async def get_state_endpoint(
    settings: SettingsDep,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_demo_controls_use)],
) -> DemoState:
    del persona_context
    body = demo_service.build_demo_state(
        clock=clock,
        llm_mode=settings.llm_mode,
        demo_controls_enabled=settings.demo_controls_enabled,
        policy_provider=policy_provider,
    )
    return DemoState.model_validate(body)


@router.post(
    "/clock/advance",
    response_model=ClockAdvanceResult,
    openapi_extra={"x-capability": "demo_controls:use"},
)
async def advance_clock_endpoint(
    body: ClockAdvanceRequest,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    persona_context: Annotated[PersonaContext, Depends(_require_demo_controls_use)],
) -> ClockAdvanceResult:
    """AC2: `body.refresh_snapshots` is accepted (schema-required by
    api-contracts.md) but is a documented no-op -- see `demo_service
    .advance_clock`'s own docstring."""
    try:
        result = await demo_service.advance_clock(
            db,
            clock=clock,
            days=body.days,
            reviewer_persona=persona_context.persona,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc
    await db.commit()
    return ClockAdvanceResult.model_validate(result)


@router.post(
    "/ptp-lifecycle/run",
    response_model=LifecycleRunResult,
    openapi_extra={"x-capability": "demo_controls:use"},
)
async def run_ptp_lifecycle_endpoint(
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_demo_controls_use)],
) -> LifecycleRunResult:
    try:
        result = await demo_service.run_ptp_lifecycle(
            db,
            policy_provider=policy_provider,
            clock=clock,
            reviewer_persona=persona_context.persona,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc
    await db.commit()
    return LifecycleRunResult.model_validate(result)


@router.post(
    "/payments/simulate",
    response_model=SimulatePaymentResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"x-capability": "demo_controls:use"},
)
async def simulate_payment_endpoint(
    body: SimulatePaymentRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_demo_controls_use)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> SimulatePaymentResult:
    """AC3: creates a `PaymentEvent` with `source=DEMO_CONTROL`,
    `simulated=True`."""
    _require_idempotency_key(idempotency_key)
    try:
        response_body, replayed = await demo_service.simulate_payment(
            db,
            account_id=body.account_id,
            amount_input=body.amount,
            outcome=body.outcome,
            reviewer_persona=persona_context.persona,
            idempotency_key=idempotency_key,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except DemoAccountNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except DemoValidationError as exc:
        if exc.reason_code is ReasonCode.IDEMPOTENCY_KEY_REUSED:
            raise ConflictError(reason_code=exc.reason_code, message=exc.message) from exc
        raise BusinessRuleViolationError(reason_code=exc.reason_code, message=exc.message) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc

    await db.commit()
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return SimulatePaymentResult.model_validate({**response_body, "replayed": replayed})


@router.post(
    "/reseed", response_model=ReseedResult, openapi_extra={"x-capability": "demo_controls:use"}
)
async def reseed_endpoint(
    body: ReseedRequest,
    request: Request,
    db: DbSession,
    audit_service: AuditServiceDep,
    persona_context: Annotated[PersonaContext, Depends(_require_demo_controls_use)],
) -> ReseedResult:
    """AC4: restores the seeded dataset's core tables and writes DEMO_RESEED."""
    if not body.confirm:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.FIELD_INVALID, message="confirm must be true."
        )
    try:
        result = await demo_service.reseed(
            db,
            reviewer_persona=persona_context.persona,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
        )
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc
    await db.commit()
    return ReseedResult(
        customers=result.customers,
        accounts=result.accounts,
        delinquency_records=result.delinquency_records,
        delinquent_items=result.delinquent_items,
        interactions=result.interactions,
        promise_to_pays=result.promise_to_pays,
    )
