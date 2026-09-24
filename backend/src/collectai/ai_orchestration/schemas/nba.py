"""LLM structured-output schema for next-best-action generation (E4-S3 AC1).

`NbaRecommendationOutput` is what `ai_orchestration.orchestrator
.run_ai_interaction` validates the model's raw response against
(`structured_output.validate_structured_output`) -- schema-invalid output
never reaches `application.recommendation_flow`. Mirrors the
`recommendation` table's own bounds (`rationale varchar(1500)`) so a
too-long rationale fails schema validation the same way an unknown field
does, rather than silently truncating at the database layer later.
"""

from __future__ import annotations

from pydantic import Field

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import NbaAction

_RATIONALE_MAX_LENGTH = 1500
_MAX_REFERENCED_FACTOR_IDS = 10


class NbaRecommendationOutput(StrictToolModel):
    """The model's proposed next-best-action, before any guardrail check.

    `action` is restricted to `NbaAction`'s six members by Pydantic itself --
    the model cannot propose an action outside that closed set. `rationale`
    and `referenced_factor_ids` are still untrusted free content at this
    point: `application._recommendation_guardrails.apply_guardrails` is the
    only place that decides whether they may reach an officer unmodified
    (AC2)."""

    action: NbaAction
    rationale: str = Field(min_length=1, max_length=_RATIONALE_MAX_LENGTH)
    referenced_factor_ids: list[str] = Field(
        default_factory=list, max_length=_MAX_REFERENCED_FACTOR_IDS
    )


__all__ = ["NbaRecommendationOutput"]
