"""Hardship-indicator extraction schema (E8-S2), used only after a message
is classified `Intent.FINANCIAL_HARDSHIP`.

`HardshipExtractionResult` is, like `DisputeExtractionResult`, an
*advisory* structured output -- it never promises or implies restructuring
or relief (AC2's guardrail). It only classifies which `HardshipIndicatorType`
values the customer's own words best match; the customer's raw message text
is stored verbatim as `HardshipCase`'s own statement by
`domain_services.hardship_service`, never re-derived or paraphrased by the
model.
"""

from __future__ import annotations

from pydantic import Field

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import HardshipIndicatorType


class HardshipExtractionResult(StrictToolModel):
    """`extra="forbid"` (via `StrictToolModel`): a model attempting to smuggle
    a `relief`/`restructuring`/`approved` field is rejected as invalid,
    never silently dropped -- the schema itself makes AC2's guardrail
    structural, not just a prompt instruction. `indicator_types` defaults to
    an empty list (never null) so `domain_services.hardship_service` can
    always store *some* indicator list, defaulting to `[OTHER]` when the
    model found none -- a hardship report is always recorded (AC-adjacent
    to E8-S3's own "always record, never block on classification" design)."""

    indicator_types: list[HardshipIndicatorType] = Field(default_factory=list)
