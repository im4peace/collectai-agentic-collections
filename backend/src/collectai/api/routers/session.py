"""Session endpoints (api-contracts.md 3.2): `GET /api/session/options`,
`POST /api/session`, `GET /api/session/me`. Demo persona selection, not
authentication (D-019, E3-S1)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, status

from collectai.api.deps import (
    ClockDep,
    DbSession,
    PersonaContext,
    hash_session_token,
    require_capability,
)
from collectai.api.middleware.errors import NotFoundError, RequestValidationFailedError
from collectai.api.rbac import capabilities_for_persona
from collectai.api.schemas.session import (
    DemoCustomer,
    SessionCreateRequest,
    SessionInfo,
    SessionOptionsResponse,
    display_name_for,
    persona_options,
)
from collectai.persistence.orm.demo_session import DemoSessionOrm
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.persistence.repositories.demo_session_repository import DemoSessionRepository
from collectai.types.enums import Persona
from collectai.types.reason_codes import ReasonCode

router = APIRouter(prefix="/api/session", tags=["Session"])

_customer_repository = CustomerRepository()
_demo_session_repository = DemoSessionRepository()


@router.get(
    "/options",
    response_model=SessionOptionsResponse,
    openapi_extra={"x-capability": "public"},
)
async def get_session_options(db: DbSession) -> SessionOptionsResponse:
    """Public: list personas and seeded demo customers for the switcher."""
    demo_customers = await _customer_repository.list_demo_customers(db)
    return SessionOptionsResponse(
        personas=persona_options(),
        demo_customers=[
            DemoCustomer(
                customer_id=row.customer_id,
                display_name=row.display_name,
                account_count=row.account_count,
            )
            for row in demo_customers
        ],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionInfo,
    openapi_extra={"x-capability": "public"},
)
async def create_session(
    body: SessionCreateRequest, db: DbSession, clock: ClockDep
) -> SessionInfo:
    """Public: select a persona; for CUSTOMER, bind one seeded `customer_id`
    server-side and return an opaque session token (never the persona's raw
    identity -- the client never sends a `customer_id` back, it sends this
    token as `X-Demo-Session`)."""
    display_name = await _resolve_display_name(db, body)
    raw_token = secrets.token_urlsafe(32)
    now = clock.now()
    await _demo_session_repository.create(
        db,
        DemoSessionOrm(
            session_token_hash=hash_session_token(raw_token),
            persona=body.persona.value,
            customer_id=body.customer_id,
            display_name=display_name,
            issued_at=now,
            last_seen_at=now,
        ),
    )
    # `get_db` only flushes/closes; the write is this handler's, so this
    # handler owns committing it (mirrors `UnitOfWork`'s "whoever performs
    # the write controls its transaction boundary" convention elsewhere in
    # this codebase). Without this, `get_db`'s `async with` closes the
    # session on an uncommitted transaction, which rolls it back silently.
    await db.commit()
    return SessionInfo(
        persona=body.persona,
        customer_id=body.customer_id,
        display_name=display_name,
        capabilities=capabilities_for_persona(body.persona),
        session_token=raw_token,
        issued_at=now.isoformat().replace("+00:00", "Z"),
    )


_require_session_read = require_capability("session:read")


@router.get(
    "/me",
    response_model=SessionInfo,
    openapi_extra={"x-capability": "session:read"},
)
async def get_session_me(
    clock: ClockDep,
    persona_context: PersonaContext = Depends(_require_session_read),  # noqa: B008
) -> SessionInfo:
    """Current persona, bound customer and capability list (AC1: requires a
    valid, allowed persona -- unauthenticated or disallowed callers never
    reach this handler)."""
    return SessionInfo(
        persona=persona_context.persona,
        customer_id=persona_context.customer_id,
        display_name=persona_context.display_name,
        capabilities=capabilities_for_persona(persona_context.persona),
        session_token=None,
        issued_at=clock.now().isoformat().replace("+00:00", "Z"),
    )


async def _resolve_display_name(db: DbSession, body: SessionCreateRequest) -> str:
    if body.persona is Persona.CUSTOMER:
        if not body.customer_id:
            raise RequestValidationFailedError(
                reason_code=ReasonCode.CUSTOMER_ID_REQUIRED_OR_FORBIDDEN,
                message="customer_id is required when persona is CUSTOMER.",
            )
        customer = await _customer_repository.get_by_id(db, body.customer_id)
        if customer is None:
            raise NotFoundError(
                message=f"Customer {body.customer_id!r} is not a seeded customer."
            )
        return customer.display_name
    if body.customer_id is not None:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.CUSTOMER_ID_REQUIRED_OR_FORBIDDEN,
            message="customer_id is only accepted when persona is CUSTOMER.",
        )
    return display_name_for(body.persona)
