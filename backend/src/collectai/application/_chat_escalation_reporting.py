"""Deterministic escalation *reporting* for the chat flow (E6-S1 AC5).

The story's own summary line is the scope: "It reports UNKNOWN and
REQUEST_HUMAN handling to escalation." Exactly two situations ever call
`report_escalation` from `chat_flow.py`: every `REQUEST_HUMAN`
classification (immediate, AC5) and the third consecutive `UNKNOWN`
classification (`UNRESOLVED_UNKNOWN`, AC5). No other sensitive intent
(DISPUTE, FINANCIAL_HARDSHIP, a special request) writes an escalation
report from the *plan* -- those are AC4's "automated treatment pauses" only;
real case creation for hardship/dispute is `flag_hardship`/`flag_dispute`
(E8-S2/E8-S3). A vulnerability signal is different (E7-S1 AC1, BRD 13.1 row
12): `open_reported_escalation` below opens its VULNERABLE_CUSTOMER case
whenever `vulnerability_detected` is true, alongside whatever else the
message triggers.

`ESCALATION_REQUIRED` is the audit-trail signal written just before the
real `EscalationCase` (`open_reported_escalation`).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.escalation_service import create_escalation
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    CaseSource,
    EscalationReason,
    Persona,
)

ESCALATION_REQUIRED_EVENT_TYPE = "ESCALATION_REQUIRED"


async def report_escalation(
    *,
    session: AsyncSession,
    audit_service: AuditService,
    correlation_id: str,
    customer_id: str,
    account_id: str,
    reason: EscalationReason,
) -> None:
    """Write `ESCALATION_REQUIRED` in the same transaction as this turn's
    other writes (data-models.md: an audit event describing a state
    transition is written atomically with it) -- a flush failure here
    propagates and rolls back the whole turn, the same fail-closed posture
    E1-S4 established for state-changing audit writes."""
    draft = AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type=ESCALATION_REQUIRED_EVENT_TYPE,
        actor_kind=ActorKind.SYSTEM,
        actor_persona=Persona.CUSTOMER,
        customer_id=customer_id,
        account_id=account_id,
        reason_code=reason.value,
        final_action="CHAT_ESCALATION_REPORTED",
    )
    await audit_service.record_in(session, draft)


def _case_source_for(reason: EscalationReason) -> CaseSource:
    """REQUEST_HUMAN is a direct customer ask (`CaseSource.CUSTOMER`); every
    other chat-opened reason (UNRESOLVED_UNKNOWN giving up after
    `max_clarification_turns`, a vulnerability signal) is the deterministic
    chat flow acting on a validated signal (`CaseSource.SYSTEM`), never
    `CaseSource.AI` -- no LLM output decides these triggers."""
    return CaseSource.CUSTOMER if reason is EscalationReason.REQUEST_HUMAN else CaseSource.SYSTEM


async def open_reported_escalation(
    *,
    session: AsyncSession,
    audit_service: AuditService,
    policy_provider: PolicyProvider,
    clock: Clock,
    correlation_id: str,
    customer_id: str,
    account_id: str,
    conversation_id: str,
    reason: EscalationReason,
) -> EscalationCaseOrm:
    """`report_escalation`'s `ESCALATION_REQUIRED` audit signal followed by
    the real `EscalationCase` (routed by the deterministic routing service,
    never by the model), both in the caller's transaction. A second trigger
    for the same conversation and reason while a case is open returns the
    existing case (`create_escalation`'s own idempotency)."""
    await report_escalation(
        session=session,
        audit_service=audit_service,
        correlation_id=correlation_id,
        customer_id=customer_id,
        account_id=account_id,
        reason=reason,
    )
    creation = await create_escalation(
        session,
        reason=reason,
        customer_id=customer_id,
        account_id=account_id,
        conversation_id=conversation_id,
        item_id=None,
        source=_case_source_for(reason),
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    return creation.case
