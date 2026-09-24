"""The chat-confirmation PTP creation path (E6-S2 AC6), split out of
`ptp_service.py` to keep that module under the code-gen skill's 300-line
block threshold. `ptp_service.py` re-exports `record_chat_ptp` so
`application.confirmation_flow` only ever imports from `ptp_service` itself.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._ptp_exceptions import PtpAccountNotFoundError
from collectai.domain_services._ptp_helpers import (
    PtpRecordRequest,
    build_ptp_row,
    get_delinquency_record,
    to_domain_record,
)
from collectai.domain_services._ptp_validation import (
    assert_amount_and_date_valid,
    assert_fresh,
    assert_no_conflict,
)
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.clock import Clock
from collectai.types.enums import ActorKind, AuditStage, Persona, PtpSource


async def record_chat_ptp(
    session: AsyncSession,
    *,
    account_id: str,
    item_id: str | None,
    promised_amount: str,
    promised_date: date,
    proposal_record_version: int,
    conversation_id: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> PromiseToPayOrm:
    """E6-S2 AC6: the customer-confirmation path's own creation, re-running
    the same freshness/deterministic-validation/conflict checks
    `ptp_service.record_officer_ptp` runs, against `proposal_record_version`
    (the snapshot the *proposal* was generated against, not a
    client-supplied value -- `application.confirmation_flow` reads it off
    the already-fetched `ProposalOrm` row). Callers must catch
    `PtpConflictError` (freshness/conflict) and `PtpBusinessRuleViolation`
    (amount/date) exactly as `record_officer_ptp`'s callers do, and are
    responsible for translating both to `PROPOSAL_INVALID` per
    api-contracts.md's confirm-endpoint contract (this function itself only
    ever raises its own natural reason codes; the proposal-specific
    reframing is the caller's concern, not this one's).
    """
    policy = policy_provider.get_active()
    record = await get_delinquency_record(session, account_id)
    if record is None:
        raise PtpAccountNotFoundError(account_id)
    domain_record = to_domain_record(record)

    request = PtpRecordRequest(
        account_id=account_id,
        promised_amount=promised_amount,
        promised_date=promised_date,
        interaction_reference=conversation_id,
        item_id=item_id,
        record_version=proposal_record_version,
        snapshot_as_of=domain_record.as_of or clock.now(),
    )
    assert_fresh(request, domain_record, policy, clock)
    assert_amount_and_date_valid(request, record.overdue_amount, policy_provider, clock)
    await assert_no_conflict(session, request)

    new_row = build_ptp_row(
        request,
        record.customer_id,
        policy.policy_version,
        clock,
        source=PtpSource.CUSTOMER_CHAT,
        created_by_persona=Persona.CUSTOMER,
    )
    session.add(new_row)
    await session.flush()
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type="PTP_RECORDED",
            actor_kind=ActorKind.CUSTOMER,
            actor_persona=Persona.CUSTOMER,
            customer_id=new_row.customer_id,
            account_id=new_row.account_id,
            capability="chat:use",
            policy_version=new_row.policy_version,
            final_action="PTP_CONFIRMED",
            resource_type="promise_to_pay",
            resource_id=new_row.ptp_id,
        ),
    )
    return new_row
