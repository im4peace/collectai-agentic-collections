"""EscalationCase domain model (data-models.md EscalationCase).

Queue, reviewer_role and priority are set only by the routing service (a
later story) from the reason and the active PolicyRuleSet (D-030); this model
only carries the typed shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from collectai.types.enums import (
    CaseSource,
    CaseStatus,
    EscalationPriority,
    EscalationReason,
    ExceptionType,
    ReviewerRole,
    ReviewQueue,
)
from collectai.types.ids import EntityPrefix, id_validator

CaseId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ESCALATION_CASE))]
CustomerId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CUSTOMER))]
AccountId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]
ConversationId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CONVERSATION))]
ItemId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ITEM))]
HardshipCaseId = Annotated[str, AfterValidator(id_validator(EntityPrefix.HARDSHIP_CASE))]
DisputeId = Annotated[str, AfterValidator(id_validator(EntityPrefix.DISPUTE))]
RecommendationId = Annotated[str, AfterValidator(id_validator(EntityPrefix.RECOMMENDATION))]


class EscalationCase(BaseModel):
    """A human-review case."""

    model_config = ConfigDict(frozen=True)

    case_id: CaseId
    customer_id: CustomerId
    account_id: AccountId
    conversation_id: ConversationId | None
    item_id: ItemId | None
    reason: EscalationReason
    queue: ReviewQueue
    reviewer_role: ReviewerRole
    priority: EscalationPriority
    status: CaseStatus
    source: CaseSource
    summary: str = Field(max_length=500)
    requested_terms: dict[str, object] | None
    exception_types: list[ExceptionType] | None
    hardship_case_id: HardshipCaseId | None
    dispute_id: DisputeId | None
    recommendation_id: RecommendationId | None
    parent_case_id: CaseId | None
    rerouted_to_case_id: CaseId | None
    routing_policy_version: str | None = Field(default=None, max_length=40)
    """`None` when the case was created under `PolicyUnavailable` (no active
    `PolicyRuleSet` to record a version from) -- `routing_flags` containing
    `"POLICY_UNAVAILABLE"` is the real signal a reader should key off, never
    a sentinel string here; `escalation_case.routing_policy_version` FKs to
    `policy_rule_set.policy_version`, so it must be a real version or NULL,
    never a placeholder that was never itself a real row."""
    routing_flags: list[str] = Field(default_factory=list)
    first_reviewed_at: datetime | None
    created_at: datetime
    decided_at: datetime | None
    updated_at: datetime
    version: int
