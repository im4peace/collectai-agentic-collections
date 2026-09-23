"""Shared ownership-check and pagination plumbing for `/api/me/*` handlers,
split out of `me.py` and `me_resources.py` (both of which use every name
here) once `me.py` alone crossed the code-gen skill's 300-line block
threshold (principle #1; mirrors `api/middleware/error_types.py` being
split out of `errors.py`).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Annotated, Final, TypeVar

from fastapi import Query, Request
from sqlalchemy.orm import InstrumentedAttribute

from collectai.api.deps import AuditServiceDep, DbSession
from collectai.api.middleware.errors import NotFoundError, resolve_correlation_id
from collectai.api.schemas.me import PageInfo
from collectai.audit.events import CROSS_CUSTOMER_ACCESS_DENIED_EVENT_TYPE, AuditEventDraft
from collectai.audit.service import AuditService, AuditUnavailable
from collectai.persistence.orm.base import Base
from collectai.persistence.repositories.customer_scoped import (
    exists_regardless_of_owner,
    find_owned_by_id,
)
from collectai.types.enums import ActorKind, AuditStage, Persona

logger = logging.getLogger(__name__)

SELF_READ: Final[dict[str, str]] = {"x-capability": "self:read"}
NOT_FOUND_MESSAGE: Final[str] = (
    "The requested resource does not exist or is not visible to this account."
)
_MAX_LIMIT: Final[int] = 50

OrmT = TypeVar("OrmT", bound=Base)

LimitQuery = Annotated[int, Query(ge=1, le=_MAX_LIMIT)]
OffsetQuery = Annotated[int, Query(ge=0)]


def paginate(rows: Sequence[OrmT], limit: int, offset: int) -> tuple[Sequence[OrmT], PageInfo]:
    return rows[offset : offset + limit], PageInfo(limit=limit, offset=offset, total=len(rows))


async def require_owned(
    db: DbSession,
    request: Request,
    audit_service: AuditServiceDep,
    customer_id: str,
    orm_class: type[OrmT],
    pk_column: InstrumentedAttribute[str],
    pk_value: str,
) -> OrmT:
    """Resolve one customer-owned row by id, or raise `NotFoundError` with
    an identical body whether the row belongs to someone else or does not
    exist at all (AC3). A cross-customer attempt is additionally audited
    (AC5); a genuinely nonexistent id is not."""
    row = await find_owned_by_id(db, orm_class, pk_column, pk_value, customer_id)
    if row is not None:
        return row
    if await exists_regardless_of_owner(db, orm_class, pk_column, pk_value):
        await _audit_cross_customer_denied(audit_service, request, customer_id)
    raise NotFoundError(message=NOT_FOUND_MESSAGE)


async def _audit_cross_customer_denied(
    audit_service: AuditService, request: Request, customer_id: str
) -> None:
    """AC5: persona, bound customer_id and endpoint, never the target
    resource's contents. Best-effort: the denial must still reach the
    caller as a 404 even if the audit write itself fails."""
    draft = AuditEventDraft(
        correlation_id=resolve_correlation_id(request),
        stage=AuditStage.INPUT,
        event_type=CROSS_CUSTOMER_ACCESS_DENIED_EVENT_TYPE,
        actor_kind=ActorKind.CUSTOMER,
        actor_persona=Persona.CUSTOMER,
        customer_id=customer_id,
        final_action=f"{request.method} {request.url.path}",
    )
    try:
        await audit_service.record(draft)
    except AuditUnavailable:
        logger.warning(
            "Cross-customer access denial audit write failed",
            extra={"correlation_id": draft.correlation_id, "final_action": draft.final_action},
        )
