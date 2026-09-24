"""Hardship-case creation from a chat message (E8-S2 AC1, AC4, AC5).

Mirrors `dispute_service.create_dispute_from_chat` exactly, with one
structural difference: hardship is scoped to the whole *account*, not an
item (`data-models.md`'s `HardshipCase` has no `item_id` column at all, and
`ux_hardship_case_open_per_account` is a plain `(account_id)` partial unique
index, not `(account_id, item_id)`) -- so the open-case dedup this module
does before ever writing a row (AC5) queries by `account_id` alone. Like
`dispute_service`, this module never judges whether the hardship is real
(CLAUDE.md: that is a human reviewer's job, not an LLM's or this module's);
`indicators` always contains at least one entry (`HardshipIndicatorType.OTHER`
when the model found nothing more specific), matching the table's own
`CHECK (jsonb_array_length(indicators) >= 1)` and this codebase's "always
record, never block on classification" convention.
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
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    CaseSource,
    EscalationReason,
    HardshipIndicatorType,
    HardshipStatus,
    Persona,
)
from collectai.types.ids import EntityPrefix, generate_id

HARDSHIP_CASE_OPENED_EVENT_TYPE = "HARDSHIP_CASE_OPENED"
_IDEMPOTENCY_SCOPE = "chat_hardship"

_idempotency_repository = IdempotencyRepository()


@dataclass(frozen=True, slots=True)
class HardshipCreationResult:
    hardship_case: HardshipCaseOrm
    escalation: EscalationCreationResult
    created: bool
    """`False` when an existing not-DECIDED hardship case for the same
    `account_id`, or the same idempotency key, was returned instead of a new
    row (AC5)."""


def _build_indicators(
    indicator_types: list[HardshipIndicatorType], customer_statement: str
) -> list[dict[str, object]]:
    types = indicator_types or [HardshipIndicatorType.OTHER]
    return [
        {"indicator_type": indicator_type.value, "customer_statement": customer_statement}
        for indicator_type in types
    ]


async def create_hardship_from_chat(
    session: AsyncSession,
    *,
    conversation_id: str,
    customer_id: str,
    account_id: str,
    indicator_types: list[HardshipIndicatorType],
    customer_statement: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    idempotency_key: str | None = None,
) -> HardshipCreationResult:
    """AC5: a repeated hardship message for the same account while a case is
    already open (not DECIDED) returns that case unchanged, checked first
    and independent of `idempotency_key` -- a customer message carries no
    `Idempotency-Key` header (mirrors `dispute_service`'s own rationale)."""
    existing = await _find_open_duplicate(session, account_id)
    if existing is not None:
        escalation = await create_escalation(
            session,
            reason=EscalationReason.FINANCIAL_HARDSHIP,
            customer_id=customer_id,
            account_id=account_id,
            conversation_id=conversation_id,
            item_id=None,
            source=CaseSource.CUSTOMER,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            hardship_case_id=existing.hardship_case_id,
        )
        return HardshipCreationResult(
            hardship_case=existing, escalation=escalation, created=False
        )

    if idempotency_key is not None:
        replay = await _idempotency_repository.get_by_scope_and_key(
            session, _IDEMPOTENCY_SCOPE, idempotency_key
        )
        if replay is not None:
            hardship_case_id = replay.response_body["hardship_case_id"]
            assert isinstance(hardship_case_id, str)  # noqa: S101 - this module wrote it
            hardship_case = await session.get(HardshipCaseOrm, hardship_case_id)
            assert hardship_case is not None  # noqa: S101 - same transaction history as above
            escalation = await create_escalation(
                session,
                reason=EscalationReason.FINANCIAL_HARDSHIP,
                customer_id=customer_id,
                account_id=account_id,
                conversation_id=conversation_id,
                item_id=None,
                source=CaseSource.CUSTOMER,
                policy_provider=policy_provider,
                clock=clock,
                audit_service=audit_service,
                correlation_id=correlation_id,
                hardship_case_id=hardship_case.hardship_case_id,
            )
            return HardshipCreationResult(
                hardship_case=hardship_case, escalation=escalation, created=False
            )

    now = clock.now()
    hardship_case = HardshipCaseOrm(
        hardship_case_id=generate_id(EntityPrefix.HARDSHIP_CASE),
        account_id=account_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        status=HardshipStatus.OPEN.value,
        indicators=_build_indicators(indicator_types, customer_statement),
        escalation_case_id=None,
        created_at=now,
        decided_at=None,
        updated_at=now,
        version=1,
    )
    session.add(hardship_case)
    await session.flush()
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=HARDSHIP_CASE_OPENED_EVENT_TYPE,
            actor_kind=ActorKind.SYSTEM,
            actor_persona=Persona.CUSTOMER,
            customer_id=customer_id,
            account_id=account_id,
            final_action=HARDSHIP_CASE_OPENED_EVENT_TYPE,
            resource_type="hardship_case",
            resource_id=hardship_case.hardship_case_id,
        ),
    )

    escalation = await create_escalation(
        session,
        reason=EscalationReason.FINANCIAL_HARDSHIP,
        customer_id=customer_id,
        account_id=account_id,
        conversation_id=conversation_id,
        item_id=None,
        source=CaseSource.CUSTOMER,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        idempotency_service=IdempotencyService(clock) if idempotency_key is not None else None,
        idempotency_key=idempotency_key,
        hardship_case_id=hardship_case.hardship_case_id,
    )
    hardship_case.escalation_case_id = escalation.case.case_id
    await session.flush()

    if idempotency_key is not None:
        response_body: dict[str, object] = {"hardship_case_id": hardship_case.hardship_case_id}

        async def _already_computed() -> dict[str, object]:
            return response_body

        await IdempotencyService(clock).get_or_create(
            session,
            scope=_IDEMPOTENCY_SCOPE,
            key=idempotency_key,
            request_hash=f"{account_id}:{customer_statement}",
            resource_type="hardship_case",
            resource_id=hardship_case.hardship_case_id,
            compute_response=_already_computed,
        )

    return HardshipCreationResult(hardship_case=hardship_case, escalation=escalation, created=True)


async def _find_open_duplicate(session: AsyncSession, account_id: str) -> HardshipCaseOrm | None:
    stmt = (
        select(HardshipCaseOrm)
        .where(
            HardshipCaseOrm.account_id == account_id,
            HardshipCaseOrm.status != HardshipStatus.DECIDED.value,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def hardship_case_wire_dict(row: HardshipCaseOrm) -> dict[str, object]:
    return {
        "hardship_case_id": row.hardship_case_id,
        "account_id": row.account_id,
        "status": row.status,
        "indicators": row.indicators,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }
