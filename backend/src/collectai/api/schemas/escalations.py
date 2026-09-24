"""Staff-facing escalation list and reviewer-decision wire schemas (E7-S1
AC7: `EscalationListItem`, `EscalationPage`; E7-S2: `ReviewDecisionRequest`/
`ReviewDecisionResult`, api-contracts.md section 4).
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
    ReviewAction,
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


class ReviewDecisionRequest(BaseModel):
    """`POST /api/escalations/{case_id}/decisions` (E7-S2). Field-shape only
    (types, that a field is a valid member of its enum) -- whether `reason`/
    `note`/`escalate_reason` are *required* for a given `action` is a
    business-shape rule `domain_services.review_service._validate_shape`
    enforces, so a client omitting one gets the specific `REASON_REQUIRED`/
    `NOTE_REQUIRED`/`ESCALATE_REASON_REQUIRED` reason code rather than a
    generic Pydantic field error (mirrors every other Group E/F/G request
    schema's split, e.g. `ConfirmRequest`). `extra="forbid"` (AC6): there is
    no `destination`/`queue`/`reviewer_role` field here at all, so a client
    attempting to supply a free-form escalation destination gets a 422 for
    the unknown field rather than having it silently ignored -- the
    destination is always `rules_engine.routing.route_escalation`'s own
    decision, never accepted from the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ReviewAction
    expected_version: int
    reason: str | None = None
    note: str | None = None
    modification_option_id: str | None = None
    escalate_reason: EscalationReason | None = None


class ReviewDecisionResult(BaseModel):
    """The recorded decision plus the case's resulting status/version."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    case_id: str
    action: ReviewAction
    reason: str | None
    note: str | None
    modification_option_id: str | None
    escalate_reason: EscalationReason | None
    rerouted_case_id: str | None
    reviewer_persona: str
    decided_at: datetime
    policy_version: str
    case_status: CaseStatus
    case_version: int
    replayed: bool = False
