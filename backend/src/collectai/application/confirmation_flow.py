"""Explicit customer confirmation/cancellation of a chat proposal (E6-S2
AC1, AC3, AC6; E6-S3 AC1, AC3, AC5).

The "genuinely new" work this pair of stories add on top of E5-S4's already
-built PROPOSE tool/idempotency plumbing: a real, explicit confirm API
action (never an LLM tool decision, D-041) that revalidates authorization,
policy, snapshot freshness and proposal validity *again* -- independent of
whatever was true when the proposal was offered -- before ever calling the
deterministic domain write, exactly as `domain_services.ptp_service
.record_officer_ptp` (E6-S6) and `application.recommendation_flow` (E4-S3)
already establish that "revalidate then write" pattern for their own write
paths.

`api/routers/chat_proposals.py` is this module's only caller. `confirm_proposal`
returns a plain, JSON-safe dict (never a Pydantic response model), mirroring
`domain_services.ptp_service.RecordPtpOutcome`'s own "no `api.schemas`
import" convention. The actual PTP/PaymentEvent write dispatch lives in the
sibling `_confirmation_apply.py`; wire-dict/hash helpers live in
`_confirmation_wire.py` -- both split out to keep this module under the
code-gen skill's 300-line block threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.application._chat_persistence import persist_message
from collectai.application._confirmation_apply import (
    apply_confirmed_proposal,
    persist_confirmation_message,
)
from collectai.application._confirmation_exceptions import (
    ConfirmIdempotencyReuseError,
    ProposalAmbiguousValidationError,
    ProposalInvalidError,
    ProposalNotFoundError,
)
from collectai.application._confirmation_wire import (
    build_confirm_response_body,
    hash_confirm_request,
    message_wire_dict,
)
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import proposal_service
from collectai.domain_services.escalation_service import create_escalation
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.proposal import ProposalOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.persistence.repositories.proposal_repository import ProposalRepository
from collectai.rules_engine.freshness import check_freshness
from collectai.types.clock import Clock
from collectai.types.enums import (
    Bucket,
    CaseSource,
    CollectionStatus,
    ContentSource,
    EscalationReason,
    Freshness,
    MessageRole,
    Persona,
    ProposalStatus,
)
from collectai.types.models.delinquency_record import DelinquencyRecord

_IDEMPOTENCY_SCOPE = "confirm_proposal"

_proposal_repository = ProposalRepository()
_delinquency_repository = DelinquencyRecordRepository()
_idempotency_repository = IdempotencyRepository()


@dataclass(frozen=True, slots=True)
class ConfirmProposalOutcome:
    response_body: dict[str, Any]
    replayed: bool


@dataclass(frozen=True, slots=True)
class CancelProposalOutcome:
    proposal: ProposalOrm
    assistant_message: Any


async def confirm_proposal(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    proposal_id: str,
    terms_hash: str,
    customer_id: str,
    persona: Persona,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    idempotency_key: str,
) -> ConfirmProposalOutcome:
    request_hash = hash_confirm_request(proposal_id=proposal_id, terms_hash=terms_hash)
    existing = await _idempotency_repository.get_by_scope_and_key(
        session, _IDEMPOTENCY_SCOPE, idempotency_key
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ConfirmIdempotencyReuseError()
        return ConfirmProposalOutcome(response_body=existing.response_body, replayed=True)

    proposal = await _load_and_validate(
        session,
        conversation=conversation,
        proposal_id=proposal_id,
        terms_hash=terms_hash,
        clock=clock,
    )
    await _revalidate_freshness(
        session,
        conversation=conversation,
        proposal=proposal,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    outcome_kind, ptp_wire, payment_wire = await apply_confirmed_proposal(
        session,
        conversation=conversation,
        proposal=proposal,
        customer_id=customer_id,
        persona=persona,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    message = await persist_confirmation_message(
        session, conversation=conversation, customer_id=customer_id, proposal=proposal, clock=clock
    )
    body = build_confirm_response_body(
        proposal=proposal,
        outcome_kind=outcome_kind,
        ptp_wire=ptp_wire,
        payment_wire=payment_wire,
        message_wire=message_wire_dict(message),
    )

    idempotency_service = IdempotencyService(clock)

    async def _already_computed() -> dict[str, object]:
        return body

    stored_body, _ = await idempotency_service.get_or_create(
        session,
        scope=_IDEMPOTENCY_SCOPE,
        key=idempotency_key,
        request_hash=request_hash,
        resource_type="proposal",
        resource_id=proposal_id,
        compute_response=_already_computed,
    )
    return ConfirmProposalOutcome(response_body=stored_body, replayed=False)


async def cancel_proposal(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    proposal_id: str,
    customer_id: str,
    clock: Clock,
) -> CancelProposalOutcome:
    """Naturally idempotent (api-contracts.md): an already-CANCELLED
    proposal returns 200 unchanged rather than an error."""
    proposal = await _proposal_repository.get_by_id_for_customer(session, proposal_id, customer_id)
    if proposal is None or proposal.conversation_id != conversation.conversation_id:
        raise ProposalNotFoundError(proposal_id)
    if proposal.status not in (
        ProposalStatus.PENDING_CONFIRMATION.value,
        ProposalStatus.CANCELLED.value,
    ):
        raise ProposalInvalidError(message="This proposal is no longer pending confirmation.")

    if proposal.status == ProposalStatus.PENDING_CONFIRMATION.value:
        proposal.status = ProposalStatus.CANCELLED.value
        await session.flush()

    assistant_message = await persist_message(
        session,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content="Okay, I've cancelled that. Let me know if there's anything else I can help with.",
        content_source=ContentSource.TEMPLATE,
        labels=[],
        created_at=clock.now(),
    )
    return CancelProposalOutcome(proposal=proposal, assistant_message=assistant_message)


async def _load_and_validate(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    proposal_id: str,
    terms_hash: str,
    clock: Clock,
) -> ProposalOrm:
    proposal = await _proposal_repository.get_by_id_for_customer(
        session, proposal_id, conversation.customer_id
    )
    if proposal is None or proposal.conversation_id != conversation.conversation_id:
        raise ProposalNotFoundError(proposal_id)
    if proposal.status != ProposalStatus.PENDING_CONFIRMATION.value:
        raise ProposalInvalidError(message="This proposal is no longer pending confirmation.")
    if proposal.terms_hash != terms_hash:
        raise ProposalInvalidError(message="The proposal terms have changed since they were shown.")
    if proposal_service.is_expired(proposal, now=clock.now()):
        raise ProposalInvalidError(message="This proposal has expired.")
    return proposal


async def _revalidate_freshness(
    session: AsyncSession,
    *,
    conversation: ConversationOrm,
    proposal: ProposalOrm,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> None:
    record = await _delinquency_repository.get_by_account(
        session, conversation.account_id, conversation.customer_id
    )
    if record is None or record.record_version != proposal.record_version:
        raise ProposalInvalidError(
            message="The account snapshot changed since this proposal was offered."
        )
    policy = policy_provider.get_active()
    domain_record = DelinquencyRecord(
        account_id=record.account_id,
        customer_id=record.customer_id,
        outstanding_balance=record.outstanding_balance,
        overdue_amount=record.overdue_amount,
        dpd=record.dpd,
        bucket=Bucket(record.bucket),
        collection_status=CollectionStatus(record.collection_status),
        as_of=record.as_of,
        record_version=record.record_version,
        updated_at=record.updated_at,
    )
    freshness = check_freshness(
        snapshot_as_of=record.as_of,
        snapshot_version=record.record_version,
        current_record=domain_record,
        policy=policy,
        clock=clock,
    )
    if freshness.status is Freshness.STALE:
        raise ProposalInvalidError(
            message="This account's data is stale; please refresh and retry."
        )
    if freshness.status is Freshness.UNKNOWN:
        creation = await create_escalation(
            session,
            reason=EscalationReason.AMBIGUOUS_VALIDATION,
            customer_id=conversation.customer_id,
            account_id=conversation.account_id,
            conversation_id=conversation.conversation_id,
            item_id=None,
            source=CaseSource.SYSTEM,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
        raise ProposalAmbiguousValidationError(escalation_case_id=creation.case.case_id)
