"""A reviewer's final decision on a hardship escalation case closes its
`HardshipCase` (E8-S2 AC3/AC6, BRD AC-B2-3).

`application._tool_backend_suppression.build_suppression_input` and
`customer360_service` derive "automated treatment is suppressed for hardship"
from `HardshipCase.status != DECIDED`. Nothing set `DECIDED`, so a decided
hardship case kept the account suppressed forever, contradicting "stops until
a human decision". `review_service.decide` calls this the moment the linked
escalation case reaches `DECIDED`; every other action (REQUEST_MORE_INFORMATION,
ESCALATE) leaves the hardship case open, because no final decision was made.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.types.enums import HardshipStatus


async def mark_hardship_decided(
    session: AsyncSession, case: EscalationCaseOrm, *, now: datetime
) -> None:
    """Set the case's linked `HardshipCase` to DECIDED (idempotent); a no-op
    for a case with no linked hardship case."""
    if case.hardship_case_id is None:
        return
    hardship = await session.get(HardshipCaseOrm, case.hardship_case_id)
    if hardship is None or hardship.status == HardshipStatus.DECIDED.value:
        return
    hardship.status = HardshipStatus.DECIDED.value
    hardship.decided_at = now
    hardship.updated_at = now
    hardship.version += 1
