"""Per-kind proposal builders (PTP, PAYMENT), split out of
`_chat_proposal_flow.py` to keep that module under the code-gen skill's
300-line block threshold. `_chat_proposal_flow.build_proposal_reply` is the
only caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.schemas.proposal_extraction import ProposalExtractionResult
from collectai.application._chat_proposal_messages import (
    ARRANGEMENT_CONFLICT_MESSAGE,
    ARRANGEMENT_EXCEPTIONAL_MESSAGE,
    ARRANGEMENT_RULES_UNAVAILABLE_MESSAGE,
    NO_ARRANGEMENT_OPTIONS_MESSAGE,
    NO_PAYABLE_OPTIONS_MESSAGE,
    arrangement_choice_message,
    arrangement_offer_message,
    payment_choice_message,
    payment_offer_message,
    ptp_clarification_message,
    ptp_offer_message,
    ptp_rejection_message,
)
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import proposal_service
from collectai.domain_services._arrangement_helpers import has_active_arrangement
from collectai.domain_services._ptp_helpers import has_active_pending_ptp
from collectai.domain_services.escalation_service import create_escalation
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.proposal import ProposalOrm
from collectai.rules_engine.arrangement import (
    RequestedTerms,
    classify_requested_terms,
    get_eligible_options,
)
from collectai.rules_engine.payable import PayableOption
from collectai.rules_engine.ptp_rules import PtpValidationInput, validate_ptp
from collectai.types.clock import Clock
from collectai.types.enums import (
    CaseSource,
    EligibilityClass,
    EscalationReason,
    MessageLabel,
    ProposalKind,
)
from collectai.types.money import Money


@dataclass(frozen=True, slots=True)
class ProposalFlowOutcome:
    content: str
    labels: tuple[MessageLabel, ...]
    proposal: ProposalOrm | None
    ai_unavailable: bool
    policy_unavailable: bool


async def build_ptp_reply(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    extraction: ProposalExtractionResult,
    overdue_amount: Money,
    record_version: int,
    policy_provider: PolicyProvider,
    policy_version: str,
    clock: Clock,
    proposal_ttl_minutes: int,
) -> ProposalFlowOutcome:
    if extraction.promised_amount is None or extraction.promised_date is None:
        policy = policy_provider.get_active()
        window_end = clock.now().date() + timedelta(days=policy.parameters.ptp.window_days)
        content = ptp_clarification_message(
            min_amount=policy.parameters.ptp.min_amount,
            overdue_amount=overdue_amount,
            window_end=window_end,
        )
        return ProposalFlowOutcome(content, (), None, False, False)

    outcome = validate_ptp(
        PtpValidationInput(
            promised_amount=extraction.promised_amount,
            promised_date=extraction.promised_date,
            overdue_amount=overdue_amount,
        ),
        policy_provider,
        clock,
    )
    if not outcome.valid:
        content = ptp_rejection_message(
            reason_code=outcome.reason_codes[0], alternatives=outcome.alternatives
        )
        return ProposalFlowOutcome(content, (), None, False, False)

    amount = Money(extraction.promised_amount)
    terms = proposal_service.ptp_terms(
        promised_amount=amount, promised_date=extraction.promised_date.isoformat()
    )
    content = ptp_offer_message(promised_amount=amount, promised_date=extraction.promised_date)
    row = await proposal_service.create_proposal(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        account_id=conversation.account_id,
        kind=ProposalKind.PTP,
        terms=terms,
        summary=content,
        simulated=False,
        record_version=record_version,
        policy_version=policy_version,
        clock=clock,
        proposal_ttl_minutes=proposal_ttl_minutes,
    )
    return ProposalFlowOutcome(content, (), row, False, False)


async def build_payment_reply(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    extraction: ProposalExtractionResult,
    payable_options: list[PayableOption],
    record_version: int,
    policy_version: str,
    clock: Clock,
    proposal_ttl_minutes: int,
) -> ProposalFlowOutcome:
    if not payable_options:
        return ProposalFlowOutcome(NO_PAYABLE_OPTIONS_MESSAGE, (), None, False, False)

    chosen = next(
        (
            option
            for option in payable_options
            if extraction.payment_option is not None
            and option.option_type == extraction.payment_option
        ),
        None,
    )
    if chosen is None:
        content = payment_choice_message(payable_options)
        return ProposalFlowOutcome(content, (), None, False, False)

    terms = proposal_service.payment_terms(
        payment_option=chosen.option_type, payment_amount=chosen.amount
    )
    content = payment_offer_message(amount=chosen.amount)
    row = await proposal_service.create_proposal(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        account_id=conversation.account_id,
        kind=ProposalKind.PAYMENT,
        terms=terms,
        summary=content,
        simulated=True,
        record_version=record_version,
        policy_version=policy_version,
        clock=clock,
        proposal_ttl_minutes=proposal_ttl_minutes,
    )
    return ProposalFlowOutcome(content, (MessageLabel.SIMULATED,), row, False, False)


async def build_arrangement_reply(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    extraction: ProposalExtractionResult,
    record: DelinquencyRecordOrm,
    policy_provider: PolicyProvider,
    policy_version: str,
    clock: Clock,
    proposal_ttl_minutes: int,
    audit_service: AuditService,
    correlation_id: str,
) -> ProposalFlowOutcome:
    """E8-S1 AC1-AC2, AC4, AC7-AC9: present only `get_eligible_options`'s own
    options (AC1); a non-eligible account gets a message, never a fabricated
    alternative (AC2, AC8); a rules-engine failure and an off-menu
    (EXCEPTIONAL) request both escalate rather than offer/create anything
    (AC4, AC7) -- the only two paths in this whole chat flow that create an
    escalation directly from a *proposal offer* rather than from confirm-time
    revalidation, matching `confirmation_flow._revalidate_freshness`'s own
    precedent for an inline, ad hoc escalation."""
    has_ptp = await has_active_pending_ptp(session, record.account_id)
    has_arrangement = await has_active_arrangement(session, record.account_id)
    result = get_eligible_options(
        policy_provider, clock, record.overdue_amount, record.dpd, has_ptp, has_arrangement
    )
    if not result.ok or result.value is None:
        await _escalate_arrangement(
            session,
            conversation=conversation,
            customer_id=customer_id,
            reason=EscalationReason.AMBIGUOUS_VALIDATION,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
        return ProposalFlowOutcome(ARRANGEMENT_RULES_UNAVAILABLE_MESSAGE, (), None, False, False)

    eligibility = result.value
    if eligibility.classification is EligibilityClass.NOT_ELIGIBLE:
        content = (
            ARRANGEMENT_CONFLICT_MESSAGE
            if "AMEND" in eligibility.permitted_paths
            else NO_ARRANGEMENT_OPTIONS_MESSAGE
        )
        return ProposalFlowOutcome(content, (), None, False, False)

    options = eligibility.options
    if extraction.installment_count is None:
        return ProposalFlowOutcome(arrangement_choice_message(options), (), None, False, False)

    chosen = next(
        (option for option in options if option.installment_count == extraction.installment_count),
        None,
    )
    if chosen is None:
        classified = classify_requested_terms(
            policy_provider,
            clock,
            record.overdue_amount,
            record.dpd,
            has_ptp,
            has_arrangement,
            RequestedTerms(
                installment_count=extraction.installment_count,
                first_installment_date=clock.now().date() + timedelta(days=1),
                installment_amount=None,
            ),
        )
        if classified.ok and classified.value is not None:
            classification = classified.value.classification
            exception_types = [e.value for e in classified.value.exception_types]
        else:
            classification = EligibilityClass.EXCEPTIONAL
            exception_types = []
        if classification is EligibilityClass.EXCEPTIONAL:
            # E7-S4 AC1: the requested terms are stored on the case verbatim
            # -- a reviewer's later APPROVE (`review_service.py`) rebuilds
            # the actual arrangement schedule from this, never from the
            # customer's own chat message text.
            requested_terms = {
                "installment_count": extraction.installment_count,
                "first_installment_date": (
                    clock.now().date() + timedelta(days=1)
                ).isoformat(),
            }
            await _escalate_arrangement(
                session,
                conversation=conversation,
                customer_id=customer_id,
                reason=EscalationReason.EXCEPTIONAL_ARRANGEMENT,
                policy_provider=policy_provider,
                clock=clock,
                audit_service=audit_service,
                correlation_id=correlation_id,
                requested_terms=requested_terms,
                exception_types=exception_types,
            )
            return ProposalFlowOutcome(ARRANGEMENT_EXCEPTIONAL_MESSAGE, (), None, False, False)
        return ProposalFlowOutcome(arrangement_choice_message(options), (), None, False, False)

    terms = proposal_service.arrangement_terms(option=chosen)
    content = arrangement_offer_message(chosen)
    row = await proposal_service.create_proposal(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        account_id=conversation.account_id,
        kind=ProposalKind.ARRANGEMENT,
        terms=terms,
        summary=content,
        simulated=False,
        record_version=record.record_version,
        policy_version=policy_version,
        clock=clock,
        proposal_ttl_minutes=proposal_ttl_minutes,
    )
    return ProposalFlowOutcome(content, (), row, False, False)


async def _escalate_arrangement(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    customer_id: str,
    reason: EscalationReason,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    requested_terms: dict[str, object] | None = None,
    exception_types: list[str] | None = None,
) -> None:
    await create_escalation(
        session,
        reason=reason,
        customer_id=customer_id,
        account_id=conversation.account_id,
        conversation_id=conversation.conversation_id,
        item_id=None,
        source=CaseSource.SYSTEM,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        requested_terms=requested_terms,
        exception_types=exception_types,
    )
