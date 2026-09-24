"""Proposal-extraction schema (E6-S2, E6-S3), used only after
`ai_orchestration.safety_precedence.SafetyDecision.proposal_execution_permitted`
is true for a PROMISE_TO_PAY or PAY_NOW message.

`ProposalExtractionResult` is, like `IntentResult`, an *advisory* structured
output -- it never creates a PTP or PaymentEvent itself (CLAUDE.md's core
engineering principle). It only extracts what the customer already stated
(an amount/date for a promise, or which listed payable option they mean for
a payment) so the deterministic layer
(`rules_engine.ptp_rules.validate_ptp` / the payable-amounts service) can
validate it. A missing field means the model could not find that value in
the message; `application._chat_proposal_flow` asks a clarifying question
rather than guessing.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import PayableOptionType


class ProposalExtractionResult(StrictToolModel):
    """`extra="forbid"` (via `StrictToolModel`): a model attempting to smuggle
    its own `approved`/`queue`/`reviewer_role` field is rejected as invalid,
    never silently dropped."""

    promised_amount: Annotated[str, Field(max_length=20)] | None = None
    promised_date: date | None = None
    payment_option: PayableOptionType | None = None
