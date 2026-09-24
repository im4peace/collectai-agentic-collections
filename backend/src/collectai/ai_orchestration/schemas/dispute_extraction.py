"""Dispute-category extraction schema (E8-S3), used only after a message is
classified `Intent.DISPUTE`.

`DisputeExtractionResult` is, like `IntentResult` and `ProposalExtractionResult`,
an *advisory* structured output -- it never judges whether the dispute is
valid (CLAUDE.md's core engineering principle, AC2's guardrail). It only
classifies which `DisputeCategory` the customer's own words best match; the
customer's raw message text is stored verbatim as `Dispute.customer_reason`
by `domain_services.dispute_service`, never re-derived or paraphrased by the
model. A missing category defaults to `OTHER` deterministically in
`dispute_service.py` -- this schema itself never guesses a specific category
it is not confident of.
"""

from __future__ import annotations

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import DisputeCategory


class DisputeExtractionResult(StrictToolModel):
    """`extra="forbid"` (via `StrictToolModel`): a model attempting to smuggle
    a `valid`/`outcome`/`resolution` field is rejected as invalid, never
    silently dropped -- the schema itself makes AC2's guardrail structural,
    not just a prompt instruction."""

    category: DisputeCategory | None = None
