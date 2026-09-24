"""Dispute creation from a chat message (E8-S3 AC1, AC4, AC5).

Unlike `proposal_service`/`ptp_service`/`arrangement_service`, this module
never validates or judges the customer's claim (AC2, CLAUDE.md: this is a
customer-reported fact to be investigated by a human, not a financial
calculation) -- it only records `category` (an LLM's *advisory*
classification of which category the customer's own words best match,
defaulting to `OTHER` when unknown or unavailable, never left blank) and
`customer_reason` (the customer's own message text, verbatim, never
re-derived), then opens the matching `EscalationCase` (routed to
DISPUTE_REVIEW by `rules_engine.routing.route_escalation`, never chosen by
this module) so a human investigates. `application._chat_dispute_flow` is
this module's only caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.escalation_service import EscalationCreationResult, create_escalation
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    CaseSource,
    DisputeCategory,
    DisputeStatus,
    EscalationReason,
    Persona,
)
from collectai.types.ids import EntityPrefix, generate_id

DISPUTE_OPENED_EVENT_TYPE = "DISPUTE_OPENED"
_IDEMPOTENCY_SCOPE = "chat_dispute"

_idempotency_repository = IdempotencyRepository()


@dataclass(frozen=True, slots=True)
class DisputeCreationResult:
    dispute: DisputeOrm
    escalation: EscalationCreationResult
    created: bool
    """`False` when an existing OPEN dispute for the same `(account_id,
    item_id)`, or the same idempotency key, was returned instead of a new
    row (AC5)."""


async def create_dispute_from_chat(
    session: AsyncSession,
    *,
    conversation_id: str,
    customer_id: str,
    account_id: str,
    item_id: str | None,
    category: DisputeCategory | None,
    customer_reason: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    idempotency_key: str | None = None,
) -> DisputeCreationResult:
    """AC5: a repeated dispute message for the same item while a dispute is
    already OPEN returns that dispute unchanged, checked first and
    independent of `idempotency_key` (a customer message carries no
    `Idempotency-Key` header at all -- see `chat.py`'s own `POST .../messages`
    contract -- so this domain-level dedupe is the only mechanism available
    here, unlike `confirm_proposal`'s explicit-header idempotency)."""
    existing = await _find_open_duplicate(session, account_id, item_id)
    if existing is not None:
        escalation = await create_escalation(
            session,
            reason=EscalationReason.DISPUTE,
            customer_id=customer_id,
            account_id=account_id,
            conversation_id=conversation_id,
            item_id=item_id,
            source=CaseSource.CUSTOMER,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            dispute_id=existing.dispute_id,
        )
        return DisputeCreationResult(dispute=existing, escalation=escalation, created=False)

    if idempotency_key is not None:
        replay = await _idempotency_repository.get_by_scope_and_key(
            session, _IDEMPOTENCY_SCOPE, idempotency_key
        )
        if replay is not None:
            dispute_id = replay.response_body["dispute_id"]
            assert isinstance(dispute_id, str)  # noqa: S101 - this module wrote it
            dispute = await session.get(DisputeOrm, dispute_id)
            assert dispute is not None  # noqa: S101 - same transaction history as above
            escalation = await create_escalation(
                session,
                reason=EscalationReason.DISPUTE,
                customer_id=customer_id,
                account_id=account_id,
                conversation_id=conversation_id,
                item_id=item_id,
                source=CaseSource.CUSTOMER,
                policy_provider=policy_provider,
                clock=clock,
                audit_service=audit_service,
                correlation_id=correlation_id,
                dispute_id=dispute.dispute_id,
            )
            return DisputeCreationResult(dispute=dispute, escalation=escalation, created=False)

    now = clock.now()
    dispute = DisputeOrm(
        dispute_id=generate_id(EntityPrefix.DISPUTE),
        account_id=account_id,
        customer_id=customer_id,
        item_id=item_id,
        category=(category or DisputeCategory.OTHER).value,
        customer_reason=customer_reason,
        status=DisputeStatus.OPEN.value,
        outcome=None,
        resolution_reason=None,
        conversation_id=conversation_id,
        escalation_case_id=None,
        created_at=now,
        resolved_at=None,
        updated_at=now,
        version=1,
    )
    session.add(dispute)
    await session.flush()
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=DISPUTE_OPENED_EVENT_TYPE,
            actor_kind=ActorKind.SYSTEM,
            actor_persona=Persona.CUSTOMER,
            customer_id=customer_id,
            account_id=account_id,
            final_action=DISPUTE_OPENED_EVENT_TYPE,
            resource_type="dispute",
            resource_id=dispute.dispute_id,
        ),
    )

    escalation = await create_escalation(
        session,
        reason=EscalationReason.DISPUTE,
        customer_id=customer_id,
        account_id=account_id,
        conversation_id=conversation_id,
        item_id=item_id,
        source=CaseSource.CUSTOMER,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        idempotency_service=IdempotencyService(clock) if idempotency_key is not None else None,
        idempotency_key=idempotency_key,
        dispute_id=dispute.dispute_id,
    )
    dispute.escalation_case_id = escalation.case.case_id
    await session.flush()

    if idempotency_key is not None:
        response_body: dict[str, object] = {"dispute_id": dispute.dispute_id}

        async def _already_computed() -> dict[str, object]:
            return response_body

        await IdempotencyService(clock).get_or_create(
            session,
            scope=_IDEMPOTENCY_SCOPE,
            key=idempotency_key,
            request_hash=f"{account_id}:{item_id}:{customer_reason}",
            resource_type="dispute",
            resource_id=dispute.dispute_id,
            compute_response=_already_computed,
        )

    return DisputeCreationResult(dispute=dispute, escalation=escalation, created=True)


async def _find_open_duplicate(
    session: AsyncSession, account_id: str, item_id: str | None
) -> DisputeOrm | None:
    conditions = [
        DisputeOrm.account_id == account_id,
        DisputeOrm.status != DisputeStatus.RESOLVED.value,
    ]
    conditions.append(
        DisputeOrm.item_id == item_id if item_id is not None else DisputeOrm.item_id.is_(None)
    )
    stmt = select(DisputeOrm).where(*conditions).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


def dispute_wire_dict(row: DisputeOrm) -> dict[str, object]:
    return {
        "dispute_id": row.dispute_id,
        "account_id": row.account_id,
        "item_id": row.item_id,
        "category": row.category,
        "customer_reason": row.customer_reason,
        "status": row.status,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }
