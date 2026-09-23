"""Shared FastAPI dependencies. Kept separate from `app.py` so routers can
import `DbSession` without an import cycle back through `app.py`.

E3-S1 adds persona/session resolution and the `require_capability`
authorization dependency (AC1-AC5): every non-public route depends on
`require_capability(<capability>)`, which resolves the caller's persona,
checks it against `api/rbac.py`'s matrix, writes the AC2 `ACCESS_DENIED`
audit event on a denial, and raises a typed error for
`middleware/errors.py` to turn into the 401/403 envelope.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Final, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.middleware.errors import resolve_correlation_id
from collectai.api.rbac import (
    PUBLIC_CAPABILITY,
    ForbiddenError,
    UnauthenticatedError,
    is_capability_allowed,
)
from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService, AuditUnavailable
from collectai.config.policy.provider import PolicyProvider
from collectai.persistence.repositories.demo_session_repository import DemoSessionRepository
from collectai.types.clock import Clock
from collectai.types.enums import ActorKind, AuditStage, Persona

_DEMO_SESSION_HEADER = "X-Demo-Session"
_PERSONA_HEADER = "X-Persona"
_demo_session_repository = DemoSessionRepository()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Per-request session, built from the session factory `lifespan`
    stores on `app.state` (see `api/app.py`). Never construct a session
    manually per request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_clock(request: Request) -> Clock:
    """The `Clock` `api/app.py`'s `create_app` stores on `app.state`."""
    return cast(Clock, request.app.state.clock)


ClockDep = Annotated[Clock, Depends(get_clock)]


def get_audit_service(request: Request) -> AuditService:
    """The `AuditService` `api/app.py`'s `create_app` stores on
    `app.state`, sharing the same session factory and clock as `get_db`."""
    return cast(AuditService, request.app.state.audit_service)


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]

# No story before E6-S6 has needed the active PolicyRuleSet at the API layer
# (every route so far is `session`/`system`, neither of which touches
# `rules_engine`), so `api/app.py`'s `lifespan` does not yet set
# `app.state.policy_provider`. Since this story may not edit `app.py` (the
# parallel-batch orchestrator wires every sibling router and any new
# app.state attribute into it in one pass once every Group E story lands),
# `get_policy_provider` degrades to a fresh, never-activated `PolicyProvider`
# instead of raising `AttributeError` when the attribute is still missing.
# `PolicyProvider.get_active()` on that fallback instance always raises
# `PolicyUnavailable` (fail-closed, CLAUDE.md's core engineering principle),
# so a route depending on `PolicyProviderDep` degrades to a clean 503
# `POLICY_UNAVAILABLE` rather than an unhandled 500 until the orchestrator's
# integration pass adds `app.state.policy_provider = ...` to `lifespan`.
_FALLBACK_POLICY_PROVIDER: Final[PolicyProvider] = PolicyProvider()


def get_policy_provider(request: Request) -> PolicyProvider:
    """The active-policy registry `api/app.py`'s `lifespan` is expected to
    store on `app.state` (see module note above)."""
    existing = getattr(request.app.state, "policy_provider", None)
    return existing if isinstance(existing, PolicyProvider) else _FALLBACK_POLICY_PROVIDER


PolicyProviderDep = Annotated[PolicyProvider, Depends(get_policy_provider)]


def hash_session_token(raw_token: str) -> str:
    """sha256 of an opaque demo-session token (data-models.md DemoSession:
    "the raw token is returned once and never stored")."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PersonaContext:
    """The caller's resolved persona for this request (AC1)."""

    persona: Persona
    customer_id: str | None
    display_name: str
    session_token_hash: str | None


async def get_persona_context(request: Request, db: DbSession) -> PersonaContext:
    """Resolve `X-Persona` (and, for CUSTOMER, `X-Demo-Session`) into a
    `PersonaContext` (api-contracts.md 1.2). Raises `UnauthenticatedError`
    -- mapped to 401 by `middleware/errors.py` -- when the persona header is
    missing/invalid, or a CUSTOMER's session is missing, unknown to the
    server, or bound to a different persona."""
    persona = _read_persona_header(request)
    if persona is not Persona.CUSTOMER:
        return PersonaContext(
            persona=persona, customer_id=None, display_name=persona.value, session_token_hash=None
        )
    return await _resolve_customer_session(request, db)


def _read_persona_header(request: Request) -> Persona:
    raw = request.headers.get(_PERSONA_HEADER)
    if raw is None:
        raise UnauthenticatedError(reason=f"Missing required header {_PERSONA_HEADER!r}.")
    try:
        return Persona(raw)
    except ValueError as exc:
        raise UnauthenticatedError(reason=f"Unknown persona {raw!r}.") from exc


async def _resolve_customer_session(request: Request, db: AsyncSession) -> PersonaContext:
    raw_token = request.headers.get(_DEMO_SESSION_HEADER)
    if not raw_token:
        raise UnauthenticatedError(
            reason=f"CUSTOMER requires the {_DEMO_SESSION_HEADER!r} header."
        )
    demo_session = await _demo_session_repository.get_by_token_hash(
        db, hash_session_token(raw_token)
    )
    if demo_session is None or demo_session.persona != Persona.CUSTOMER.value:
        raise UnauthenticatedError(reason="Unknown or persona-mismatched demo session.")
    return PersonaContext(
        persona=Persona.CUSTOMER,
        customer_id=demo_session.customer_id,
        display_name=demo_session.display_name,
        session_token_hash=demo_session.session_token_hash,
    )


def require_capability(
    capability: str,
) -> Callable[..., Awaitable[PersonaContext | None]]:
    """Build a FastAPI dependency enforcing `capability` (AC1). Public
    routes (`PUBLIC_CAPABILITY`) resolve no persona at all, matching
    api-contracts.md 1.2's "Public endpoints are exempt". Every other route
    resolves the persona, denies with an audited 403 when the matrix says
    no (AC1, AC2), and otherwise returns the resolved `PersonaContext` so a
    route handler that needs it (e.g. `GET /api/session/me`) can depend on
    the same call."""
    if capability == PUBLIC_CAPABILITY:

        async def _public_dependency() -> None:
            return None

        return _public_dependency

    async def _dependency(
        request: Request,
        db: DbSession,
        audit_service: AuditServiceDep,
    ) -> PersonaContext:
        persona_context = await get_persona_context(request, db)
        if not is_capability_allowed(capability, persona_context.persona):
            await _audit_access_denied(
                audit_service=audit_service,
                request=request,
                persona=persona_context.persona,
                capability=capability,
            )
            raise ForbiddenError(capability=capability, persona=persona_context.persona)
        return persona_context

    return _dependency


def bound_customer_id(
    persona_context: Annotated[PersonaContext, Depends(require_capability("self:read"))],
) -> str:
    """The CUSTOMER persona's server-bound `customer_id` (E3-S5 AC1), for
    every `/api/me/*` handler to scope its lookups by. Safe to assert
    non-None: only CUSTOMER holds `self:read` (`api/rbac.py`'s
    `CAPABILITY_MATRIX`), and `_resolve_customer_session` above always sets
    `customer_id` on a CUSTOMER's `PersonaContext`. A client-supplied
    `customer_id` is never read here or anywhere in a `/api/me/*` request
    schema -- this is the only source of truth a handler may use."""
    assert persona_context.customer_id is not None  # noqa: S101 - guaranteed by self:read
    return persona_context.customer_id


BoundCustomerId = Annotated[str, Depends(bound_customer_id)]


async def _audit_access_denied(
    *,
    audit_service: AuditService,
    request: Request,
    persona: Persona,
    capability: str,
) -> None:
    """AC2: every 403 produces an audit event with persona, endpoint and
    correlation id. Best-effort: a denial must still be returned to the
    caller even if audit persistence itself fails, so `AuditUnavailable` is
    logged, not propagated -- denying access is already the safe outcome."""
    correlation_id = resolve_correlation_id(request)
    draft = AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.INPUT,
        event_type="ACCESS_DENIED",
        actor_kind=ActorKind.STAFF if persona is not Persona.CUSTOMER else ActorKind.CUSTOMER,
        actor_persona=persona,
        capability=capability,
        final_action=f"{request.method} {request.url.path}",
        reason_code="FORBIDDEN",
    )
    try:
        await audit_service.record(draft)
    except AuditUnavailable:
        pass
