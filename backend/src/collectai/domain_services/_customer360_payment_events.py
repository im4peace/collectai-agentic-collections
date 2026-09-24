"""Customer 360's `payment_events` list (E6-S3, E4-S2 AC4): the account's
simulated payment history, newest first, each carrying the `simulated`/
`simulated_label` fields the UI must show a "Simulated" label from.

Split out of `customer360_service.py` for the same reason
`_customer360_ai_block.py` was (code-gen skill's 300-line block threshold --
`customer360_service.py` and `customer360_mapping.py` were both already at
the limit). Private to this package: only `customer360_service.py` calls it.
Maps `PaymentEventOrm` to `api.schemas.me.PaymentEvent` directly (rather than
importing `api.routers.me_views.payment_event_view`, which would cross the
`domain_services` -> `api.routers` layer boundary `_ptp_helpers.py` already
documents as forbidden) -- a small, deliberate duplicate of that one mapper.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.schemas.me import SIMULATED_PAYMENT_LABEL, PaymentEvent
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.repositories.payment_event_repository import PaymentEventRepository
from collectai.types.enums import PaymentOutcome, PaymentSource

_payment_event_repository = PaymentEventRepository()


async def build_payment_events(
    session: AsyncSession, *, account_id: str, customer_id: str
) -> list[PaymentEvent]:
    rows = await _payment_event_repository.list_by_account_for_customer(
        session, account_id, customer_id
    )
    ordered = sorted(rows, key=lambda row: row.occurred_at, reverse=True)
    return [_to_schema(row) for row in ordered]


def _to_schema(row: PaymentEventOrm) -> PaymentEvent:
    return PaymentEvent(
        payment_event_id=row.payment_event_id,
        account_id=row.account_id,
        amount=row.amount,
        outcome=PaymentOutcome(row.outcome),
        source=PaymentSource(row.source),
        simulated=row.simulated,
        simulated_label=SIMULATED_PAYMENT_LABEL,
        occurred_at=row.occurred_at,
        balance_after=row.balance_after,
        applied_to_ptp_id=row.applied_to_ptp_id,
    )


__all__ = ["build_payment_events"]
