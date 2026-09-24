"""AC1, AC2: guardrails applied to a schema-valid AI recommendation before it
is ever persisted or shown to an officer (E4-S3).

Two distinct safe-fallback shapes live here:

- `apply_guardrails` (AC2): the model returned schema-valid output, but its
  free-text `rationale` cites a currency figure, date or option id
  `ai_orchestration.grounding.check_grounding` cannot find in
  `GroundedFacts`, or a `referenced_factor_ids` entry outside the ids the
  deterministic priority calculation actually returned.
  `ai_orchestration.grounding` only regex-scans free text, so the factor-id
  membership check is this module's own (E5-S3's grounding module
  deliberately does not parse structured `referenced_factor_ids` fields).
- `safe_fallback_recommendation` (AC1): `ai_orchestration.orchestrator
  .run_ai_interaction` never produced schema-valid output at all (its own
  bounded correction retry was exhausted) -- there is no AI rationale to
  ground-check in the first place, only a fixed safe response.

Both replacement texts reuse `ai_orchestration.templates
.build_grounding_fallback`: it already renders a safe, factual, hedge-free
message built only from confirmed `GroundedFacts` (or a generic sentence
when none apply), which is exactly AC1/AC2's "templated text" -- no separate
template renderer is needed here.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectai.ai_orchestration.grounding import GroundedFacts, check_grounding
from collectai.ai_orchestration.schemas.nba import NbaRecommendationOutput
from collectai.ai_orchestration.templates import build_grounding_fallback
from collectai.types.enums import ContentSource, NbaAction


@dataclass(frozen=True, slots=True)
class GuardedRecommendation:
    """A recommendation's content after every guardrail has run -- the only
    shape `application.recommendation_flow` ever persists."""

    action: NbaAction
    rationale: str
    referenced_factor_ids: list[str]
    content_source: ContentSource


def apply_guardrails(
    output: NbaRecommendationOutput,
    *,
    allowed_factor_ids: frozenset[str],
    facts: GroundedFacts,
) -> GuardedRecommendation:
    """AC2: replace `rationale` (and drop every cited factor id) if it cites
    a factor, currency amount, date or option the deterministic services
    never returned. `action` itself is untouched here -- schema validation
    already restricted it to `NbaAction`'s six members, so there is nothing
    left to ground-check about it."""
    fallback_text = build_grounding_fallback(facts)
    grounding = check_grounding(output.rationale, facts, fallback_template=fallback_text)
    unreferenced_factor_ids = set(output.referenced_factor_ids) - allowed_factor_ids
    if unreferenced_factor_ids or not grounding.is_grounded:
        return GuardedRecommendation(
            action=output.action,
            rationale=fallback_text,
            referenced_factor_ids=[],
            content_source=ContentSource.TEMPLATE,
        )
    return GuardedRecommendation(
        action=output.action,
        rationale=output.rationale,
        referenced_factor_ids=output.referenced_factor_ids,
        content_source=ContentSource.MODEL,
    )


def safe_fallback_recommendation() -> GuardedRecommendation:
    """AC1: every schema-validation retry exhausted -- a fixed safe "human
    review" recommendation with no AI-sourced content at all."""
    return GuardedRecommendation(
        action=NbaAction.ESCALATE_TO_HUMAN_REVIEW,
        rationale=build_grounding_fallback(GroundedFacts(frozenset(), frozenset(), frozenset())),
        referenced_factor_ids=[],
        content_source=ContentSource.TEMPLATE,
    )


__all__ = ["GuardedRecommendation", "apply_guardrails", "safe_fallback_recommendation"]
