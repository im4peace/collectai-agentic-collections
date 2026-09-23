"""Per-account `PriorityInput` extras for the portfolio listing (E3-S2).

Split out of `domain_services/portfolio_service.py` once that module
crossed the 300-line block threshold (code-gen skill principle #1;
`rules_engine/priority.py`'s own docstring documents the same worked
example, `api/middleware/error_types.py`). `gather_priority_extras` is the
one function `portfolio_service.list_portfolio` calls; the five private
per-table queries below are acceptable N+1-per-candidate reads at this
demo scale (E3-S2 story brief's own design guidance) -- each reads exactly
one other table directly, never re-deriving anything `rules_engine.priority`
itself computes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.enums import (
    CaseStatus,
    ContactOutcome,
    DisputeStatus,
    HardshipStatus,
    PtpStatus,
)


@dataclass(frozen=True, slots=True)
class PriorityExtras:
    """The `PriorityInput` fields `list_portfolio_candidates` cannot supply
    (design guidance (b)): read directly from their own tables, one
    candidate at a time."""

    broken_ptp_count: int
    recent_contact_outcome: ContactOutcome | None
    has_active_dispute: bool
    has_active_hardship: bool
    has_open_escalation: bool


async def gather_priority_extras(session: AsyncSession, account_id: str) -> PriorityExtras:
    return PriorityExtras(
        broken_ptp_count=await _count_broken_ptps(session, account_id),
        recent_contact_outcome=await _latest_contact_outcome(session, account_id),
        has_active_dispute=await _has_open_dispute(session, account_id),
        has_active_hardship=await _has_open_hardship(session, account_id),
        has_open_escalation=await _has_open_escalation(session, account_id),
    )


async def _count_broken_ptps(session: AsyncSession, account_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(PromiseToPayOrm)
        .where(
            PromiseToPayOrm.account_id == account_id,
            PromiseToPayOrm.status == PtpStatus.BROKEN.value,
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def _latest_contact_outcome(session: AsyncSession, account_id: str) -> ContactOutcome | None:
    stmt = (
        select(InteractionOrm.outcome)
        .where(InteractionOrm.account_id == account_id)
        .order_by(InteractionOrm.occurred_at.desc())
        .limit(1)
    )
    outcome = (await session.execute(stmt)).scalar_one_or_none()
    return ContactOutcome(outcome) if outcome is not None else None


async def _has_open_dispute(session: AsyncSession, account_id: str) -> bool:
    open_statuses = (DisputeStatus.OPEN.value, DisputeStatus.UNDER_REVIEW.value)
    stmt = (
        select(DisputeOrm.dispute_id)
        .where(DisputeOrm.account_id == account_id, DisputeOrm.status.in_(open_statuses))
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def _has_open_hardship(session: AsyncSession, account_id: str) -> bool:
    open_statuses = (HardshipStatus.OPEN.value, HardshipStatus.UNDER_REVIEW.value)
    stmt = (
        select(HardshipCaseOrm.hardship_case_id)
        .where(HardshipCaseOrm.account_id == account_id, HardshipCaseOrm.status.in_(open_statuses))
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def _has_open_escalation(session: AsyncSession, account_id: str) -> bool:
    stmt = (
        select(EscalationCaseOrm.case_id)
        .where(
            EscalationCaseOrm.account_id == account_id,
            EscalationCaseOrm.status != CaseStatus.DECIDED.value,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None
