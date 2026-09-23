"""Audit trail read API (api-contracts.md 3.12; E9-S1). Restricted to
COMPLIANCE_RISK (capability `audit:read`, enforced entirely by
`api/rbac.py`'s `CAPABILITY_MATRIX` through `require_capability`). Only GET
routes are declared here, satisfying AC3's "exposes no write route" without
any further work. Reads are not themselves audited (api-contracts.md 3.12
behaviour note), so this router never depends on `AuditServiceDep`.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from collectai.api.deps import DbSession, PersonaContext, require_capability
from collectai.api.middleware.errors import RequestValidationFailedError
from collectai.api.schemas.audit import (
    AuditChainPage,
    AuditChainSummary,
    AuditPage,
    PageInfo,
    audit_event_to_response,
)
from collectai.audit import queries
from collectai.audit.queries import ChainSummaryRow
from collectai.types.enums import AuditStage
from collectai.types.reason_codes import ReasonCode

router = APIRouter(prefix="/api/audit", tags=["Audit"])

_require_audit_read = require_capability("audit:read")

_FILTER_REQUIRED_MESSAGE = (
    "At least one of correlation_id, account_id, from or to is required."
)


@router.get("", response_model=AuditPage, openapi_extra={"x-capability": "audit:read"})
async def search_audit_events(
    db: DbSession,
    correlation_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to_ts: datetime | None = Query(default=None, alias="to"),  # noqa: B008
    stage: list[AuditStage] | None = Query(default=None),  # noqa: B008
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _persona_context: PersonaContext = Depends(_require_audit_read),  # noqa: B008
) -> AuditPage:
    """AC1, AC2: the decision chain for `correlation_id`, or events matching
    `account_id`/`from`/`to`/`stage`/`event_type`, ordered by
    `(timestamp, sequence)` ascending."""
    _require_at_least_one_filter(correlation_id, account_id, from_ts, to_ts)
    events, total = await queries.search(
        db,
        correlation_id=correlation_id,
        account_id=account_id,
        from_ts=from_ts,
        to_ts=to_ts,
        stages=stage,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return AuditPage(
        items=[audit_event_to_response(event) for event in events],
        page=PageInfo(limit=limit, offset=offset, total=total),
    )


@router.get(
    "/chains", response_model=AuditChainPage, openapi_extra={"x-capability": "audit:read"}
)
async def list_audit_chains(
    db: DbSession,
    account_id: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to_ts: datetime | None = Query(default=None, alias="to"),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _persona_context: PersonaContext = Depends(_require_audit_read),  # noqa: B008
) -> AuditChainPage:
    """One summary row per distinct `correlation_id` for the compliance
    viewer's search, newest chain first."""
    _require_at_least_one_filter(None, account_id, from_ts, to_ts)
    chains, total = await queries.list_chains(
        db, account_id=account_id, from_ts=from_ts, to_ts=to_ts, limit=limit, offset=offset
    )
    return AuditChainPage(
        items=[_chain_to_response(row) for row in chains],
        page=PageInfo(limit=limit, offset=offset, total=total),
    )


def _require_at_least_one_filter(
    correlation_id: str | None,
    account_id: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> None:
    """422 `FILTER_REQUIRED` unless at least one of `correlation_id`,
    `account_id`, `from` or `to` is supplied -- `stage`/`event_type`/
    `limit`/`offset` alone never satisfy this (api-contracts.md 3.12)."""
    if correlation_id is None and account_id is None and from_ts is None and to_ts is None:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.FILTER_REQUIRED, message=_FILTER_REQUIRED_MESSAGE
        )


def _chain_to_response(row: ChainSummaryRow) -> AuditChainSummary:
    return AuditChainSummary(
        correlation_id=row.correlation_id,
        account_id=row.account_id,
        started_at=row.started_at,
        last_event_at=row.last_event_at,
        event_count=row.event_count,
        stages_present=row.stages_present,
        final_action=row.final_action,
        policy_version=row.policy_version,
        model_id=row.model_id,
        prompt_version=row.prompt_version,
    )
