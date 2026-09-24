"""Deterministic escalation *reporting* for the chat flow (E6-S1 AC5).

The story's own summary line is the scope: "It reports UNKNOWN and
REQUEST_HUMAN handling to escalation." Exactly two situations ever call
`report_escalation` from `chat_flow.py`: every `REQUEST_HUMAN`
classification (immediate, AC5) and the third consecutive `UNKNOWN`
classification (`UNRESOLVED_UNKNOWN`, AC5). No other sensitive intent
(DISPUTE, FINANCIAL_HARDSHIP, a vulnerability signal, a special request)
writes an escalation report here -- those are AC4's "automated treatment
pauses" only; real case creation for them is `flag_hardship`/`flag_dispute`
(E8-S2/E8-S3), not this module.

This never creates an `escalation_case` row: that table/service
(`domain_services/escalation_service.py`, E7-S1) does not exist yet in this
codebase. `ESCALATION_REQUIRED` is an audit-trail signal a later story reads
to actually open a case -- not a case itself.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.types.enums import ActorKind, AuditStage, EscalationReason, Persona

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
