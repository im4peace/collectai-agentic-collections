"""Staff-facing escalation list query (E7-S1 AC7), split out of
`escalation_service.py` to keep that module (case creation) under the
code-gen skill's 300-line block threshold. The only caller is
`api/routers/escalations.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.types.enums import CaseStatus, EscalationPriority, EscalationReason, ReviewQueue


async def list_for_queue_view(
    session: AsyncSession,
    *,
    queues: Sequence[ReviewQueue] | None,
    statuses: Sequence[CaseStatus] | None,
    priorities: Sequence[EscalationPriority] | None,
    reasons: Sequence[EscalationReason] | None,
    account_id: str | None,
) -> list[EscalationCaseOrm]:
    """`GET /api/escalations`: an unscoped, cross-customer read for staff
    personas -- never used by a `/api/me/*` handler. Default status filter
    (OPEN, IN_REVIEW, AWAITING_INFORMATION) is applied by the router,
    matching api-contracts.md's documented default."""
    stmt = select(EscalationCaseOrm)
    if queues:
        stmt = stmt.where(EscalationCaseOrm.queue.in_([q.value for q in queues]))
    if statuses:
        stmt = stmt.where(EscalationCaseOrm.status.in_([s.value for s in statuses]))
    if priorities:
        stmt = stmt.where(EscalationCaseOrm.priority.in_([p.value for p in priorities]))
    if reasons:
        stmt = stmt.where(EscalationCaseOrm.reason.in_([r.value for r in reasons]))
    if account_id:
        stmt = stmt.where(EscalationCaseOrm.account_id == account_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
