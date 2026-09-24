"""Simulated PAY_NOW payment recording (E6-S3; D-021).

Records a `PaymentEvent` and reduces the account's synthetic balances.
`simulated=True` always (the ORM column also defaults true, enforced again
by the migration's `CHECK (simulated)`); this module never imports a payment
gateway SDK and never makes an HTTP call to an external payment host (AC4) --
the entire "payment" is a database write against synthetic data.

`applied_to_ptp_id` (E6-S4, Group H): the caller passes the account's
PENDING PTP id, if any, so it is set at INSERT time -- `payment_event` is
one of `deploy/db/init-roles.sql`'s insert-only tables (no UPDATE grant for
`collectai_app`), so this module never back-fills it with an UPDATE after
the fact. `domain_services.ptp_lifecycle` owns deciding KEPT/BROKEN from it;
this module only records the association.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.types.clock import Clock
from collectai.types.enums import ActorKind, AuditStage, Persona
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.money import Money

PAYMENT_RECORDED_EVENT_TYPE = "PAYMENT_EVENT_RECORDED"

_delinquency_repository = DelinquencyRecordRepository()
_ZERO: Decimal = Decimal("0")


class PaymentBalanceUpdateConflictError(Exception):
    """The account's `delinquency_record` changed between the freshness
    check `application.confirmation_flow` already ran and this write
    (concurrent update). Raised so the caller can surface it as a 409
    rather than silently applying a payment against a stale balance."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Balance update conflict recording a payment for {account_id!r}.")


async def record_simulated_payment(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    amount: Money,
    proposal_id: str,
    correlation_id: str,
    clock: Clock,
    audit_service: AuditService,
    persona: Persona,
    applied_to_ptp_id: str | None = None,
) -> PaymentEventOrm:
    """AC2 (E6-S3): exactly one `PaymentEvent`, outcome SUCCEEDED, and the
    balance reduced by `amount` -- both writes in the caller's own
    transaction (`application.confirmation_flow` commits). `record` must be
    the just-freshness-checked row for the proposal's account; its
    `record_version` is used as `expected_version` so a genuine concurrent
    change between the freshness check and this write is caught rather than
    silently overwritten. `applied_to_ptp_id` (E6-S4): the account's PENDING
    PTP id, if the caller already found one -- see this module's docstring."""
    now = clock.now()
    new_outstanding = Money(record.outstanding_balance.amount - amount.amount)
    new_overdue = Money(max(record.overdue_amount.amount - amount.amount, _ZERO))

    updated = await _delinquency_repository.update_snapshot(
        session,
        account_id=record.account_id,
        customer_id=record.customer_id,
        expected_version=record.record_version,
        outstanding_balance=new_outstanding,
        overdue_amount=new_overdue,
        dpd=record.dpd,
        bucket=record.bucket,
        collection_status=record.collection_status,
        as_of=record.as_of,
        updated_at=now,
    )
    if not updated:
        raise PaymentBalanceUpdateConflictError(record.account_id)

    event = PaymentEventOrm(
        payment_event_id=generate_id(EntityPrefix.PAYMENT_EVENT),
        account_id=record.account_id,
        customer_id=record.customer_id,
        amount=amount,
        outcome="SUCCEEDED",
        source="CUSTOMER_CHAT",
        simulated=True,
        occurred_at=now,
        balance_after=new_outstanding,
        applied_to_ptp_id=applied_to_ptp_id,
        proposal_id=proposal_id,
        created_by_persona=persona.value,
    )
    session.add(event)
    await session.flush()
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=PAYMENT_RECORDED_EVENT_TYPE,
            actor_kind=ActorKind.CUSTOMER,
            actor_persona=persona,
            customer_id=record.customer_id,
            account_id=record.account_id,
            final_action="PAYMENT_EVENT_RECORDED",
            resource_type="payment_event",
            resource_id=event.payment_event_id,
        ),
    )
    return event


_SIMULATED_PAYMENT_LABEL = "Simulated payment"


def payment_event_wire_dict(row: PaymentEventOrm) -> dict[str, object]:
    """`PaymentEvent` API shape (api-contracts.md section 4), mirroring
    `domain_services.ptp_service.ptp_wire_dict`'s pattern: used for the
    `ConfirmResult.outcome.payment_event` body and, unchanged, as the stored
    `idempotency_record.response_body` a replay later re-validates the same
    way."""
    return {
        "payment_event_id": row.payment_event_id,
        "account_id": row.account_id,
        "amount": row.amount.to_api_string(),
        "outcome": row.outcome,
        "source": row.source,
        "simulated": row.simulated,
        "simulated_label": _SIMULATED_PAYMENT_LABEL,
        "occurred_at": row.occurred_at.isoformat().replace("+00:00", "Z"),
        "balance_after": row.balance_after.to_api_string(),
        "applied_to_ptp_id": row.applied_to_ptp_id,
    }
