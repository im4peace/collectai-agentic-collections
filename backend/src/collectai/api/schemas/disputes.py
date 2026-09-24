"""Officer-facing dispute review/resolve wire schemas (E8-S4; api-contracts.md
3.11, section 4: `DisputeStartReviewRequest`, `DisputeResolveRequest`,
`DisputeTransitionResult`). `Dispute` itself is `customer360.Dispute`, reused
verbatim -- both are the same officer-view shape, and `customer360.py`'s own
docstring already established the "reuse rather than re-declare" convention
for one shared field before (`payment_events`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from collectai.api.schemas.customer360 import Dispute
from collectai.types.enums import DisputeOutcome


class DisputeStartReviewRequest(BaseModel):
    """`POST /api/disputes/{dispute_id}/start-review`. Unknown fields are
    rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_version: int


class DisputeResolveRequest(BaseModel):
    """`POST /api/disputes/{dispute_id}/resolve`. Unknown fields are
    rejected. `outcome`/`reason` are declared optional here, deliberately
    (mirrors `ReviewDecisionRequest`'s own docstring rationale): whether
    they are *present* is a business-shape rule `dispute_review_service`
    enforces, so an omitting client gets the specific `OUTCOME_REQUIRED`/
    `REASON_REQUIRED` reason code rather than a generic Pydantic field
    error."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: DisputeOutcome | None = None
    reason: str | None = None
    expected_version: int


class DisputeTransitionResult(BaseModel):
    """Dispute after a `start-review` or `resolve` transition."""

    model_config = ConfigDict(frozen=True)

    dispute: Dispute
    replayed: bool = False
