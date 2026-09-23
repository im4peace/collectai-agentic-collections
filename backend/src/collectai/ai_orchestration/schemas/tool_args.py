"""Pydantic argument schemas for the six-tool registry (E5-S4 AC1, AC2, AC4).

Every schema is `extra="forbid"` (via `StrictToolModel`): a raw args dict
with an unknown key -- most pointedly `escalate_to_human` with a
`queue`/`reviewer_role`/`reviewer` key (AC4) -- is rejected as invalid,
never silently dropped. `customer_id` deliberately appears on none of these:
it is supplied by the trusted caller (see `ports.ToolBackendPort`), never by
the model.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import DisputeCategory, EscalationReason, HardshipIndicatorType
from collectai.types.models.account import AccountId

_Rationale = Annotated[str, Field(min_length=1, max_length=1000)]
_Note = Annotated[str, Field(min_length=1, max_length=1000)]
_CustomerReason = Annotated[str, Field(min_length=1, max_length=1000)]
_PromisedAmount = Annotated[str, Field(min_length=1, max_length=20)]
_ItemId = Annotated[str, Field(min_length=1, max_length=64)]


class GetAccountContextArgs(StrictToolModel):
    account_id: AccountId


class GetEligibleOptionsArgs(StrictToolModel):
    account_id: AccountId


class ProposePtpArgs(StrictToolModel):
    """`promised_amount` is a raw string, not `Money`: an unparseable value
    (e.g. "abc") must reach `rules_engine.ptp_rules.validate_ptp`, which
    turns it into a typed rejection reason code, rather than failing schema
    validation before the deterministic check ever runs."""

    account_id: AccountId
    promised_amount: _PromisedAmount
    promised_date: date


class FlagHardshipArgs(StrictToolModel):
    account_id: AccountId
    indicator_type: HardshipIndicatorType
    note: _Note


class FlagDisputeArgs(StrictToolModel):
    account_id: AccountId
    category: DisputeCategory
    customer_reason: _CustomerReason
    item_id: _ItemId | None = None


class EscalateToHumanArgs(StrictToolModel):
    """AC4: only `reason` and `rationale` -- no queue/role/reviewer field
    exists on this model at all, and `extra="forbid"` (via `StrictToolModel`)
    rejects any such key present in a raw args dict rather than silently
    dropping it. Only `rules_engine.routing.route_escalation` ever decides
    the destination."""

    reason: EscalationReason
    rationale: _Rationale
