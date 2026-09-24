"""The actual PTP/PaymentEvent write dispatch for a confirmed proposal,
split out of `confirmation_flow.py` to keep that module under the code-gen
skill's 300-line block threshold. `confirmation_flow.confirm_proposal` is
the only caller.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.application._chat_persistence import persist_message
from collectai.application._confirmation_exceptions import (
    ProposalConflictError,
    ProposalInvalidError,
)
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import arrangement_service, payment_service, ptp_lifecycle
from collectai.domain_services._arrangement_exceptions import (
    ArrangementConflictError,
    ArrangementNotEligibleError,
)
from collectai.domain_services._ptp_exceptions import PtpBusinessRuleViolation, PtpConflictError
from collectai.domain_services.ptp_service import ptp_wire_dict, record_chat_ptp
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.persistence.orm.proposal import ProposalOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.types.clock import Clock
from collectai.types.enums import (
    ContentSource,
    MessageLabel,
    MessageRole,
    Persona,
    ProposalKind,
    ProposalStatus,
)
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_delinquency_repository = DelinquencyRecordRepository()


async def apply_confirmed_proposal(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    proposal: ProposalOrm,
    customer_id: str,
    persona: Persona,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> tuple[str, dict[str, object] | None, dict[str, object] | None, dict[str, object] | None]:
    """Dispatch by `proposal.kind`; marks `proposal` CONFIRMED on success.
    Returns `(outcome_kind, ptp_wire, payment_wire, arrangement_wire)`."""
    if proposal.kind == ProposalKind.PTP.value:
        ptp_row = await _confirm_ptp(
            session,
            conversation=conversation,
            proposal=proposal,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
        _mark_confirmed(proposal, clock, ptp_row.ptp_id)
        return ProposalKind.PTP.value, ptp_wire_dict(ptp_row), None, None

    record = await _delinquency_repository.get_by_account(
        session, conversation.account_id, customer_id
    )
    assert record is not None  # noqa: S101 - _revalidate_freshness already confirmed this

    if proposal.kind == ProposalKind.ARRANGEMENT.value:
        arrangement_row = await _confirm_arrangement(
            session,
            record=record,
            proposal=proposal,
            correlation_id=correlation_id,
            clock=clock,
            audit_service=audit_service,
            policy_provider=policy_provider,
        )
        _mark_confirmed(proposal, clock, arrangement_row.arrangement_id)
        return (
            ProposalKind.ARRANGEMENT.value,
            None,
            None,
            arrangement_service.arrangement_wire_dict(arrangement_row),
        )

    payment_row = await _confirm_payment(
        session,
        record=record,
        proposal=proposal,
        correlation_id=correlation_id,
        clock=clock,
        audit_service=audit_service,
        persona=persona,
        policy_provider=policy_provider,
    )
    _mark_confirmed(proposal, clock, payment_row.payment_event_id)
    return (
        ProposalKind.PAYMENT.value,
        None,
        payment_service.payment_event_wire_dict(payment_row),
        None,
    )


def _mark_confirmed(proposal: ProposalOrm, clock: Clock, resource_id: str) -> None:
    proposal.status = ProposalStatus.CONFIRMED.value
    proposal.confirmed_at = clock.now()
    proposal.resulting_resource_id = resource_id


async def _confirm_ptp(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    proposal: ProposalOrm,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> PromiseToPayOrm:
    terms = proposal.terms
    try:
        return await record_chat_ptp(
            session,
            account_id=conversation.account_id,
            item_id=None,
            promised_amount=str(terms["promised_amount"]),
            promised_date=date.fromisoformat(str(terms["promised_date"])),
            proposal_record_version=proposal.record_version,
            conversation_id=conversation.conversation_id,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
    except PtpBusinessRuleViolation as exc:
        raise ProposalInvalidError(message=exc.message) from exc
    except PtpConflictError as exc:
        if exc.reason_code in (ReasonCode.STALE_DATA, ReasonCode.AMBIGUOUS_VALIDATION):
            raise ProposalInvalidError(message=exc.message, context=exc.context) from exc
        raise ProposalConflictError(
            reason_code=exc.reason_code, message=exc.message, context=exc.context
        ) from exc


async def _confirm_arrangement(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    proposal: ProposalOrm,
    correlation_id: str,
    clock: Clock,
    audit_service: AuditService,
    policy_provider: PolicyProvider,
) -> PaymentArrangementOrm:
    try:
        return await arrangement_service.create_arrangement_from_confirmed_proposal(
            session,
            record=record,
            option_id=str(proposal.terms["option_id"]),
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
    except ArrangementNotEligibleError as exc:
        raise ProposalInvalidError(message=exc.message) from exc
    except ArrangementConflictError as exc:
        raise ProposalConflictError(reason_code=exc.reason_code, message=exc.message) from exc


async def _confirm_payment(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    proposal: ProposalOrm,
    correlation_id: str,
    clock: Clock,
    audit_service: AuditService,
    persona: Persona,
    policy_provider: PolicyProvider,
) -> PaymentEventOrm:
    amount = Money(str(proposal.terms["payment_amount"]))
    # E6-S4: found *before* the insert -- `payment_event.applied_to_ptp_id`
    # must be set at INSERT time (see `payment_service`'s docstring), so the
    # lookup has to happen ahead of the write, not after it.
    pending_ptp = await ptp_lifecycle.find_pending_ptp_for_account(session, record.account_id)
    try:
        event = await payment_service.record_simulated_payment(
            session,
            record=record,
            amount=amount,
            proposal_id=proposal.proposal_id,
            correlation_id=correlation_id,
            clock=clock,
            audit_service=audit_service,
            persona=persona,
            applied_to_ptp_id=pending_ptp.ptp_id if pending_ptp is not None else None,
        )
    except payment_service.PaymentBalanceUpdateConflictError as exc:
        raise ProposalInvalidError(
            message="The account balance changed since this proposal was offered."
        ) from exc
    if pending_ptp is not None:
        policy = policy_provider.get_active()
        await ptp_lifecycle.apply_payment_and_evaluate(
            session,
            ptp=pending_ptp,
            policy=policy,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
    return event


async def persist_confirmation_message(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    proposal: ProposalOrm,
    clock: Clock,
) -> ChatMessageOrm:
    if proposal.kind == ProposalKind.PAYMENT.value:
        content = (
            f"Your simulated payment of {proposal.terms.get('payment_amount')} has been "
            "recorded. No real money moved."
        )
        labels = [MessageLabel.SIMULATED]
    elif proposal.kind == ProposalKind.ARRANGEMENT.value:
        content = (
            f"Your payment plan of {proposal.terms.get('installment_count')} payments, "
            "starting "
            f"{proposal.terms.get('first_installment_date')}, has been set up."
        )
        labels = []
    else:
        content = (
            f"Your promise to pay {proposal.terms.get('promised_amount')} by "
            f"{proposal.terms.get('promised_date')} has been recorded."
        )
        labels = []
    return await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content=content,
        content_source=ContentSource.TEMPLATE,
        labels=labels,
        created_at=clock.now(),
    )
