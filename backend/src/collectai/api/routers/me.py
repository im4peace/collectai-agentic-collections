"""Customer self-service endpoints (api-contracts.md 3.7, `GET /api/me/*`).

E3-S5: the CUSTOMER persona is bound server-side to exactly one synthetic
`customer_id` (`api/deps.py`'s `BoundCustomerId`, itself built on
`require_capability("self:read")`); no request schema in this package ever
accepts a client-supplied `customer_id` (AC1). Every handler below either
scopes its query by that bound id directly (list endpoints -- a foreign
`account_id` on a by-account-list route is still checked explicitly first)
or, for a single resource by id, resolves it through
`me_ownership.require_owned` (AC2, AC3, AC5).

This module owns the accounts endpoints, the three by-account list
endpoints and the escalations list; `me_resources` owns the six
single-resource-by-id GETs and is mounted onto this same router below, so
callers only ever import `collectai.api.routers.me`. Ownership-check and
pagination plumbing shared by both lives in `me_ownership`; ORM-to-schema
mapping lives in `me_views`.

Conversation endpoints (`/api/chat/*`) are explicitly out of scope here:
they belong to story E6-S1, not yet built. `POST /api/me/ptps/{ptp_id}/cancel`
also belongs to a later story (E6-S2/E6-S4) -- this module is read-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from collectai.api.deps import AuditServiceDep, BoundCustomerId, DbSession
from collectai.api.middleware.errors import NotFoundError
from collectai.api.routers import me_resources, me_views
from collectai.api.routers.me_ownership import (
    NOT_FOUND_MESSAGE,
    SELF_READ,
    LimitQuery,
    OffsetQuery,
    paginate,
    require_owned,
)
from collectai.api.schemas.me import (
    ArrangementPage,
    CustomerAccountPage,
    CustomerAccountSummary,
    EscalationCustomerPage,
    PaymentEventPage,
    PtpPage,
)
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.escalation_case_repository import EscalationCaseRepository
from collectai.persistence.repositories.payment_arrangement_repository import (
    PaymentArrangementRepository,
)
from collectai.persistence.repositories.payment_event_repository import PaymentEventRepository
from collectai.persistence.repositories.promise_to_pay_repository import PromiseToPayRepository

router = APIRouter(prefix="/api/me", tags=["Customer Self-Service"])
router.include_router(me_resources.router)

_account_repo = AccountRepository()
_delinquency_repo = DelinquencyRecordRepository()
_ptp_repo = PromiseToPayRepository()
_payment_event_repo = PaymentEventRepository()
_arrangement_repo = PaymentArrangementRepository()
_escalation_repo = EscalationCaseRepository()


@router.get("/accounts", response_model=CustomerAccountPage, openapi_extra=SELF_READ)
async def list_my_accounts(
    db: DbSession, customer_id: BoundCustomerId, limit: LimitQuery = 20, offset: OffsetQuery = 0
) -> CustomerAccountPage:
    accounts = sorted(
        await _account_repo.list_by_customer(db, customer_id), key=lambda row: row.account_id
    )
    delinquency_by_account = {
        row.account_id: row for row in await _delinquency_repo.list_by_customer(db, customer_id)
    }
    page_accounts, page_info = paginate(accounts, limit, offset)
    items = [
        me_views.account_summary(account, delinquency_by_account[account.account_id])
        for account in page_accounts
    ]
    return CustomerAccountPage(items=items, page=page_info)


@router.get(
    "/accounts/{account_id}", response_model=CustomerAccountSummary, openapi_extra=SELF_READ
)
async def get_my_account(
    account_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> CustomerAccountSummary:
    account = await require_owned(
        db, request, audit_service, customer_id, AccountOrm, AccountOrm.account_id, account_id
    )
    delinquency = await _delinquency_repo.get_by_account(db, account_id, customer_id)
    if delinquency is None:
        raise NotFoundError(message=NOT_FOUND_MESSAGE)
    return me_views.account_summary(account, delinquency)


@router.get("/accounts/{account_id}/ptps", response_model=PtpPage, openapi_extra=SELF_READ)
async def list_my_account_ptps(
    account_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> PtpPage:
    await require_owned(
        db, request, audit_service, customer_id, AccountOrm, AccountOrm.account_id, account_id
    )
    rows = sorted(
        await _ptp_repo.list_by_account_for_customer(db, account_id, customer_id),
        key=lambda row: row.ptp_id,
    )
    page_rows, page_info = paginate(rows, limit, offset)
    return PtpPage(items=[me_views.ptp_view(row) for row in page_rows], page=page_info)


@router.get(
    "/accounts/{account_id}/payment-events",
    response_model=PaymentEventPage,
    openapi_extra=SELF_READ,
)
async def list_my_account_payment_events(
    account_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> PaymentEventPage:
    await require_owned(
        db, request, audit_service, customer_id, AccountOrm, AccountOrm.account_id, account_id
    )
    rows = sorted(
        await _payment_event_repo.list_by_account_for_customer(db, account_id, customer_id),
        key=lambda row: row.payment_event_id,
    )
    page_rows, page_info = paginate(rows, limit, offset)
    return PaymentEventPage(
        items=[me_views.payment_event_view(row) for row in page_rows], page=page_info
    )


@router.get(
    "/accounts/{account_id}/arrangements", response_model=ArrangementPage, openapi_extra=SELF_READ
)
async def list_my_account_arrangements(
    account_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> ArrangementPage:
    await require_owned(
        db, request, audit_service, customer_id, AccountOrm, AccountOrm.account_id, account_id
    )
    rows = sorted(
        await _arrangement_repo.list_by_account_for_customer(db, account_id, customer_id),
        key=lambda row: row.arrangement_id,
    )
    page_rows, page_info = paginate(rows, limit, offset)
    return ArrangementPage(
        items=[me_views.arrangement_view(row) for row in page_rows], page=page_info
    )


@router.get("/escalations", response_model=EscalationCustomerPage, openapi_extra=SELF_READ)
async def list_my_escalations(
    db: DbSession, customer_id: BoundCustomerId, limit: LimitQuery = 20, offset: OffsetQuery = 0
) -> EscalationCustomerPage:
    rows = sorted(
        await _escalation_repo.list_by_customer(db, customer_id), key=lambda row: row.case_id
    )
    page_rows, page_info = paginate(rows, limit, offset)
    return EscalationCustomerPage(
        items=[me_views.escalation_view(row) for row in page_rows], page=page_info
    )
