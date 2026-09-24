"""Recommendation endpoints this story owns (api-contracts.md 3.5):
`GET /api/accounts/{account_id}/recommendation`,
`POST /api/accounts/{account_id}/recommendation`,
`POST /api/accounts/{account_id}/recommendation/{recommendation_id}/decision`.

NOTE -- not yet wired into `api/app.py`: E6-S1 lands a sibling router in the
same parallel batch and touches the same file; per every other Group E
router's own note (see `api/routers/portfolio.py`), the integration pass
adds `app.include_router(recommendations_router)` once both stories land.
This router is fully self-contained and independently testable via its own
`APIRouter` instance in the meantime (see `tests/api/test_e4_s3_*`, which
mount it on a locally-built `FastAPI` app rather than `create_app`).

NOTE -- LLM provider selection: `get_llm_provider` below mirrors
`portfolio.py`'s `get_policy_provider` fallback pattern exactly: read
`request.app.state.llm_provider` when the integration pass has added it,
otherwise fall back to a process-wide `MockProvider` (this demo's default
`LLM_MODE`), so this router has a real, working provider either way.

Rate limiting (api-contracts.md: recommendation generation capped at
10/min, "per session token, persona for staff" since staff personas hold
no individual session token in this demo): added in the Group F
integration pass, once E6-S1's `api/middleware/rate_limit.py` existed for
this router to reuse without an ownership conflict during parallel
authoring.
"""

from __future__ import annotations

from typing import Annotated, Final, cast

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field

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
    RateLimitedError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.middleware.rate_limit import SlidingWindowRateLimiter
from collectai.api.schemas.customer360 import Recommendation
from collectai.application._recommendation_idempotency import (
    RecommendationDecisionIdempotencyConflict,
)
from collectai.application.recommendation_flow import (
    decide_recommendation,
    generate_recommendation,
    get_latest_recommendation,
    to_recommendation_schema,
)
from collectai.audit.service import AuditUnavailable
from collectai.llm_provider.base import LlmProvider
from collectai.llm_provider.mock import MockProvider
from collectai.types.enums import (
    NbaAction,
    ProviderMode,
    RecommendationDecision,
    RecommendationStatus,
)
from collectai.types.reason_codes import ReasonCode

router = APIRouter(prefix="/api/accounts", tags=["Recommendations"])

_require_recommendation_read = require_capability("recommendation:read")
_require_recommendation_generate = require_capability("recommendation:generate")
_require_recommendation_decide = require_capability("recommendation:decide")
_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_RECOMMENDATION_GENERATE_RATE_LIMIT_PER_MINUTE: Final[int] = 10

_fallback_llm_provider: LlmProvider | None = None


class RecommendationResult(BaseModel):
    """api-contracts.md `RecommendationResult`: the GET/POST envelope."""

    model_config = ConfigDict(frozen=True)

    status: RecommendationStatus
    recommendation: Recommendation | None


class RecommendationDecisionRequest(BaseModel):
    """api-contracts.md `RecommendationDecisionRequest`. Unknown fields are
    rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: RecommendationDecision
    reason: str | None = Field(default=None, min_length=1, max_length=1000)
    chosen_action: NbaAction | None = None


def get_llm_provider(request: Request) -> LlmProvider:
    configured = getattr(request.app.state, "llm_provider", None)
    if configured is not None:
        return cast(LlmProvider, configured)
    global _fallback_llm_provider
    if _fallback_llm_provider is None:
        _fallback_llm_provider = MockProvider()
    return _fallback_llm_provider


def get_provider_mode(request: Request) -> ProviderMode:
    configured = getattr(request.app.state, "llm_provider_mode", None)
    return configured if isinstance(configured, ProviderMode) else ProviderMode.MOCK


LlmProviderDep = Annotated[LlmProvider, Depends(get_llm_provider)]
ProviderModeDep = Annotated[ProviderMode, Depends(get_provider_mode)]


def _get_generate_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    """One `SlidingWindowRateLimiter` per `FastAPI` app instance, lazily
    created and cached on `app.state` -- never a bare module-level
    singleton. This process serves exactly one real app, so that
    distinction is invisible in production, but a bare singleton would
    otherwise leak rate-limit state between the independent `app` instances
    each test in `tests/api/test_e4_s3_recommendations_api.py` builds via
    its own `app`/`client` fixtures, causing later tests to see hits an
    earlier, unrelated test already made."""
    limiter = getattr(request.app.state, "recommendation_rate_limiter", None)
    if limiter is None:
        limiter = SlidingWindowRateLimiter()
        request.app.state.recommendation_rate_limiter = limiter
    return cast(SlidingWindowRateLimiter, limiter)


async def _rate_limited_generate(
    request: Request,
    clock: ClockDep,
    persona_context: Annotated[PersonaContext, Depends(_require_recommendation_generate)],
) -> PersonaContext:
    """api-contracts.md 1.2: 10/min "per session token (persona for staff)"
    -- COLLECTIONS_OFFICER holds no individual session token in this demo
    (only CUSTOMER does), so every officer shares one persona-keyed
    sliding window, mirroring `chat.py`'s `_rate_limited_customer_id`."""
    key = persona_context.session_token_hash or persona_context.persona.value
    limiter = _get_generate_rate_limiter(request)
    decision = limiter.check(key, clock.now(), _RECOMMENDATION_GENERATE_RATE_LIMIT_PER_MINUTE)
    if not decision.allowed:
        raise RateLimitedError(retry_after_seconds=decision.retry_after_seconds)
    return persona_context


RateLimitedGenerate = Annotated[PersonaContext, Depends(_rate_limited_generate)]


@router.get(
    "/{account_id}/recommendation",
    response_model=RecommendationResult,
    openapi_extra={"x-capability": "recommendation:read"},
)
async def get_recommendation_endpoint(
    account_id: str,
    db: DbSession,
    persona_context: PersonaContext = Depends(_require_recommendation_read),  # noqa: B008
) -> RecommendationResult:
    del persona_context
    row = await get_latest_recommendation(db, account_id=account_id)
    if row is None:
        return RecommendationResult(status=RecommendationStatus.NOT_GENERATED, recommendation=None)
    return RecommendationResult(
        status=RecommendationStatus(row.status), recommendation=to_recommendation_schema(row)
    )


@router.post(
    "/{account_id}/recommendation",
    response_model=RecommendationResult,
    openapi_extra={"x-capability": "recommendation:generate"},
)
async def generate_recommendation_endpoint(
    account_id: str,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    provider: LlmProviderDep,
    provider_mode: ProviderModeDep,
    persona_context: RateLimitedGenerate,
) -> RecommendationResult:
    del persona_context
    provider_name = "mock" if provider_mode is ProviderMode.MOCK else "anthropic"
    try:
        outcome = await generate_recommendation(
            db,
            audit_service,
            account_id=account_id,
            provider=provider,
            provider_name=provider_name,
            provider_mode=provider_mode,
            policy_provider=policy_provider,
            clock=clock,
            correlation_id=resolve_correlation_id(request),
        )
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc

    await db.commit()
    recommendation = (
        to_recommendation_schema(outcome.recommendation)
        if outcome.recommendation is not None
        else None
    )
    return RecommendationResult(status=outcome.status, recommendation=recommendation)


@router.post(
    "/{account_id}/recommendation/{recommendation_id}/decision",
    response_model=Recommendation,
    openapi_extra={"x-capability": "recommendation:decide"},
)
async def decide_recommendation_endpoint(
    account_id: str,
    recommendation_id: str,
    body: RecommendationDecisionRequest,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    persona_context: PersonaContext = Depends(_require_recommendation_decide),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias=_IDEMPOTENCY_KEY_HEADER),
) -> Recommendation:
    validated_key = _require_idempotency_key(idempotency_key)
    try:
        outcome = await decide_recommendation(
            db,
            audit_service,
            account_id=account_id,
            recommendation_id=recommendation_id,
            decision=body.decision,
            reason=body.reason,
            chosen_action=body.chosen_action,
            persona=persona_context.persona,
            idempotency_key=validated_key,
            clock=clock,
            correlation_id=resolve_correlation_id(request),
        )
    except RecommendationDecisionIdempotencyConflict as exc:
        raise ConflictError(reason_code=exc.reason_code, message=str(exc)) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc

    await db.commit()
    return outcome.recommendation


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REQUIRED,
            message=f"{_IDEMPOTENCY_KEY_HEADER!r} header is required (8-128 chars [A-Za-z0-9_-]).",
        )
    return idempotency_key


__all__ = ["router"]
