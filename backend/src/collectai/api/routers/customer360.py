"""Customer 360 endpoint (E4-S1; api-contracts.md 3.4 `GET
/api/customers/{account_id}/360`). Read-only: never mutates, never calls AI.

`POST /api/customers/{account_id}/refresh` is a different, not-yet-scheduled
story and is intentionally absent from this router.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from collectai.api.deps import ClockDep, DbSession, PersonaContext, require_capability
from collectai.api.schemas.customer360 import Customer360
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.customer360_service import build_customer360

router = APIRouter(prefix="/api/customers", tags=["Customer360"])

_require_customer360_read = require_capability("customer360:read")


def _get_policy_provider(request: Request) -> PolicyProvider:
    """The shared `PolicyProvider` `api/app.py`'s lifespan is expected to
    store on `app.state` (mirrors `api/deps.py`'s `get_clock`/
    `get_audit_service`). Falls back to a fresh, inactive `PolicyProvider`
    when the app has not wired one yet: that degrades to exactly the same
    `POLICY_UNAVAILABLE`, still-200 behaviour `build_customer360` already
    handles for a genuinely inactive policy, rather than a hard 500."""
    provider = getattr(request.app.state, "policy_provider", None)
    return cast(PolicyProvider, provider) if provider is not None else PolicyProvider()


PolicyProviderDep = Annotated[PolicyProvider, Depends(_get_policy_provider)]


@router.get(
    "/{account_id}/360",
    response_model=Customer360,
    openapi_extra={"x-capability": "customer360:read"},
)
async def get_customer_360(
    account_id: str,
    db: DbSession,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    persona_context: PersonaContext = Depends(_require_customer360_read),  # noqa: B008
) -> Customer360:
    """Consolidated Customer 360 read model (AC1-AC5). Read-only, strictly
    composed from existing repositories: no mutation, no AI call. An unknown
    `account_id` raises `NotFoundError` -> 404 (AC3); a degraded/inactive
    policy still returns 200 with `deterministic.status="POLICY_UNAVAILABLE"`
    (the spec's documented exception to fail-closed, since officers still
    need read access to keep working manually)."""
    del persona_context  # only used to enforce the capability gate (AC4)
    return await build_customer360(
        db, account_id=account_id, policy_provider=policy_provider, clock=clock
    )
