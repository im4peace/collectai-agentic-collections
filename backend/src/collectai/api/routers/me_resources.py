"""Single-resource-by-id `/api/me/*` GET handlers (api-contracts.md 3.7):
PTP, payment event, arrangement, hardship case, dispute and escalation.
Split out of `me.py` (which owns the accounts and by-account-list
endpoints) once that module crossed the 300-line block threshold; both
modules are mounted onto the same `/api/me` router in `me.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from collectai.api.deps import AuditServiceDep, BoundCustomerId, DbSession
from collectai.api.routers import me_views
from collectai.api.routers.me_ownership import SELF_READ, require_owned
from collectai.api.schemas.me import (
    DisputeCustomerView,
    EscalationCustomerView,
    HardshipCustomerView,
    PaymentArrangement,
    PaymentEvent,
    PromiseToPay,
)
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm

router = APIRouter()


@router.get("/ptps/{ptp_id}", response_model=PromiseToPay, openapi_extra=SELF_READ)
async def get_my_ptp(
    ptp_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> PromiseToPay:
    row = await require_owned(
        db, request, audit_service, customer_id, PromiseToPayOrm, PromiseToPayOrm.ptp_id, ptp_id
    )
    return me_views.ptp_view(row)


@router.get(
    "/payment-events/{payment_event_id}", response_model=PaymentEvent, openapi_extra=SELF_READ
)
async def get_my_payment_event(
    payment_event_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> PaymentEvent:
    row = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        PaymentEventOrm,
        PaymentEventOrm.payment_event_id,
        payment_event_id,
    )
    return me_views.payment_event_view(row)


@router.get(
    "/arrangements/{arrangement_id}", response_model=PaymentArrangement, openapi_extra=SELF_READ
)
async def get_my_arrangement(
    arrangement_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> PaymentArrangement:
    row = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        PaymentArrangementOrm,
        PaymentArrangementOrm.arrangement_id,
        arrangement_id,
    )
    return me_views.arrangement_view(row)


@router.get(
    "/hardship-cases/{hardship_case_id}",
    response_model=HardshipCustomerView,
    openapi_extra=SELF_READ,
)
async def get_my_hardship_case(
    hardship_case_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> HardshipCustomerView:
    row = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        HardshipCaseOrm,
        HardshipCaseOrm.hardship_case_id,
        hardship_case_id,
    )
    return me_views.hardship_view(row)


@router.get("/disputes/{dispute_id}", response_model=DisputeCustomerView, openapi_extra=SELF_READ)
async def get_my_dispute(
    dispute_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> DisputeCustomerView:
    row = await require_owned(
        db, request, audit_service, customer_id, DisputeOrm, DisputeOrm.dispute_id, dispute_id
    )
    return me_views.dispute_view(row)


@router.get(
    "/escalations/{case_id}", response_model=EscalationCustomerView, openapi_extra=SELF_READ
)
async def get_my_escalation(
    case_id: str,
    request: Request,
    db: DbSession,
    customer_id: BoundCustomerId,
    audit_service: AuditServiceDep,
) -> EscalationCustomerView:
    row = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        EscalationCaseOrm,
        EscalationCaseOrm.case_id,
        case_id,
    )
    return me_views.escalation_view(row)
