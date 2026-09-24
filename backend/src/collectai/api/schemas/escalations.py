"""Staff-facing escalation list wire schemas (E7-S1 AC7; api-contracts.md
section 4: `EscalationListItem`, `EscalationPage`). Only the Slice-1 list
shape this story owns; `EscalationDetail` and the reviewer-action schemas
belong to E7-S2 (Group H).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from collectai.api.schemas.me import PageInfo
from collectai.types.enums import (
    CaseSource,
    CaseStatus,
    EscalationPriority,
    EscalationReason,
    ReviewerRole,
    ReviewQueue,
)


class EscalationListItem(BaseModel):
    """Row of the escalation list / review queue."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    reason: EscalationReason
    queue: ReviewQueue
    reviewer_role: ReviewerRole
    priority: EscalationPriority
    status: CaseStatus
    source: CaseSource
    created_at: datetime
    age_hours: int
    aging_warning: bool
    customer_id: str
    customer_name: str
    account_id: str
    customer_360_path: str
    version: int


class EscalationPage(BaseModel):
    """Escalation list (api-contracts.md: sorted by priority, URGENT first,
    then age, oldest first)."""

    model_config = ConfigDict(frozen=True)

    items: list[EscalationListItem]
    page: PageInfo
    policy_version: str | None
