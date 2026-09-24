"""Shared `payment_arrangement` lookup helper (E8-S1), used by both
`review_service.py` (E7-S2 AC3's MODIFY eligibility re-check) and
`arrangement_service.py`/`_chat_proposal_flow.py` (this story's own
eligibility/conflict checks) -- kept as a single, tiny, framework-free
function rather than duplicated per caller."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.types.enums import ArrangementStatus


async def has_active_arrangement(session: AsyncSession, account_id: str) -> bool:
    """AC8: an existing ACTIVE arrangement is a `CONFLICTING_ACTIVE_ITEM`
    conflict for a new one, mirroring `_ptp_helpers.has_active_pending_ptp`'s
    own one-active-item-per-account convention."""
    stmt = (
        select(PaymentArrangementOrm.arrangement_id)
        .where(
            PaymentArrangementOrm.account_id == account_id,
            PaymentArrangementOrm.status == ArrangementStatus.ACTIVE.value,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
