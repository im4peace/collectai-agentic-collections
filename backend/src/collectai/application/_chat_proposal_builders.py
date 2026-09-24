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
    NO_PAYABLE_OPTIONS_MESSAGE,
    payment_choice_message,
    payment_offer_message,
    ptp_clarification_message,
    ptp_offer_message,
    ptp_rejection_message,
)
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import proposal_service
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.proposal import ProposalOrm
from collectai.rules_engine.payable import PayableOption
from collectai.rules_engine.ptp_rules import PtpValidationInput, validate_ptp
from collectai.types.clock import Clock
from collectai.types.enums import MessageLabel, ProposalKind
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
