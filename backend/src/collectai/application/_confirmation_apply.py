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
from collectai.domain_services import payment_service
from collectai.domain_services._ptp_exceptions import PtpBusinessRuleViolation, PtpConflictError
from collectai.domain_services.ptp_service import ptp_wire_dict, record_chat_ptp
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
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
) -> tuple[str, dict[str, object] | None, dict[str, object] | None]:
    """Dispatch by `proposal.kind`; marks `proposal` CONFIRMED on success.
    Returns `(outcome_kind, ptp_wire, payment_wire)`."""
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
        return ProposalKind.PTP.value, ptp_wire_dict(ptp_row), None

    record = await _delinquency_repository.get_by_account(
        session, conversation.account_id, customer_id
    )
    assert record is not None  # noqa: S101 - _revalidate_freshness already confirmed this
    payment_row = await _confirm_payment(
        session,
        record=record,
        proposal=proposal,
        correlation_id=correlation_id,
        clock=clock,
        audit_service=audit_service,
        persona=persona,
    )
    _mark_confirmed(proposal, clock, payment_row.payment_event_id)
    return ProposalKind.PAYMENT.value, None, payment_service.payment_event_wire_dict(payment_row)


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


async def _confirm_payment(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    proposal: ProposalOrm,
    correlation_id: str,
    clock: Clock,
    audit_service: AuditService,
    persona: Persona,
) -> PaymentEventOrm:
    amount = Money(str(proposal.terms["payment_amount"]))
    try:
        return await payment_service.record_simulated_payment(
            session,
            record=record,
            amount=amount,
            proposal_id=proposal.proposal_id,
            correlation_id=correlation_id,
            clock=clock,
            audit_service=audit_service,
            persona=persona,
        )
    except payment_service.PaymentBalanceUpdateConflictError as exc:
        raise ProposalInvalidError(
            message="The account balance changed since this proposal was offered."
        ) from exc


async def persist_confirmation_message(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    proposal: ProposalOrm,
    clock: Clock,
) -> ChatMessageOrm:
    is_payment = proposal.kind == ProposalKind.PAYMENT.value
    if is_payment:
        content = (
            f"Your simulated payment of {proposal.terms.get('payment_amount')} has been "
            "recorded. No real money moved."
        )
        labels = [MessageLabel.SIMULATED]
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
